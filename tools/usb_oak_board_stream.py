#!/usr/bin/env python3
"""Continuous native and preview streams for the six-camera USB OAK session."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import sys
import threading
import time
import uuid

os.environ.setdefault('DEPTHAI_PROTOCOL', 'usb')
os.environ.setdefault('DEPTHAI_TELEMETRY', '0')

import cv2
import depthai as dai

from usb_oak_photo import describe, factory_bytes


def run(args, running):
    static_size = (4056, 3040)
    output_lock = threading.Lock()

    def send(kind, metadata, payload=None):
        # Idle previews may drop while a completed native PNG uses the pipe.
        if not output_lock.acquire(blocking=(kind != 'FRAME')):
            return
        try:
            if payload is not None:
                metadata['bytes'] = len(payload)
            stream = sys.stdout.buffer
            stream.write(('UWA_' + kind + ' ').encode() + json.dumps(metadata).encode() + b'\n')
            if payload is not None:
                stream.write(payload)
            stream.flush()
        finally:
            output_lock.release()

    def archive(frame, metadata):
        try:
            image = frame.getCvFrame()
            if image.shape != (static_size[1], static_size[0], 3):
                raise ValueError('Unexpected native USB frame shape')
            ok, png = cv2.imencode('.png', image, [cv2.IMWRITE_PNG_COMPRESSION, 1])
            if not ok:
                raise RuntimeError('Cannot encode native USB PNG')
            send('PHOTO', metadata, memoryview(png))
        except Exception as error:
            send('ERROR', dict(request_id=metadata['request_id'], error=str(error)))

    with (Path.home() / 'uwa-camera/.camera.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        devices = [info for info in dai.Device.getAllAvailableDevices()
                   if 'USB' in str(info.protocol) and info.getDeviceId() == args.device_id]
        if len(devices) != 1:
            raise RuntimeError('Selected USB OAK unavailable')
        with dai.Device(devices[0]) as device:
            device.setMaxReconnectionAttempts(0)
            if device.getPlatform() != dai.Platform.RVC2 or device.getDeviceId() != args.device_id:
                raise RuntimeError('Unexpected USB OAK')
            sensor = next(s for s in device.getConnectedCameraFeatures()
                          if s.socket == dai.CameraBoardSocket.CAM_A)
            if (sensor.width, sensor.height) != static_size:
                raise ValueError('Unexpected native USB sensor dimensions')
            factory = factory_bytes(device)
            factory_sha = hashlib.sha256(factory).hexdigest()
            distortion = device.readCalibration().getDistortionCoefficients(dai.CameraBoardSocket.CAM_A)
            session = dict(device_id=args.device_id, selected_focus=args.focus,
                native_size=list(static_size), factory_sha256_before=factory_sha,
                usb_speed=str(device.getUsbSpeed()), sensor=sensor.sensorName, session_id=uuid.uuid4().hex)
            cv2.setNumThreads(2)
            with dai.Pipeline(device) as pipeline:
                camera = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A,
                    sensorResolution=static_size, sensorFps=5)
                camera.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                camera.initialControl.setManualFocus(args.focus)
                camera.initialControl.setAutoExposureEnable()
                # A single native queue preserves the full field of view. The preview
                # is derived from those same pixels; nothing is archived while idle.
                frames = camera.requestFullResolutionOutput(
                    fps=2, useHighestResolution=True).createOutputQueue(maxSize=1, blocking=False)
                pipeline.start()
                pending = writer = None
                try:
                    with ThreadPoolExecutor(max_workers=1) as writers:
                        while running.is_set() and pipeline.isRunning():
                            if select.select([sys.stdin], [], [], .01)[0]:
                                line = sys.stdin.readline()
                                if not line or line.strip() == 'stop':
                                    break
                                request_id = str(uuid.UUID(hex=line.strip()))
                                if pending or (writer and not writer.done()):
                                    send('ERROR', dict(request_id=request_id, error='USB capture already in progress'))
                                else:
                                    pending = (request_id, dai.Clock.now())
                            frame = frames.tryGet()
                            if pending and (dai.Clock.now() - pending[1]).total_seconds() > 15:
                                request_id, _ = pending
                                send('ERROR', dict(request_id=request_id, error='Timed out waiting for fresh USB frame'))
                                pending = None
                            if frame is None or frame.getLensPosition() != args.focus:
                                continue
                            if (frame.getWidth(), frame.getHeight()) != static_size:
                                raise ValueError(f'Unexpected USB frame {frame.getWidth()}×{frame.getHeight()}')
                            exposure = frame.getTimestamp(dai.CameraExposureOffset.START)
                            if pending and exposure > pending[1]:
                                request_id, requested = pending
                                info = describe(frame)
                                send('ACQUIRED', dict(request_id=request_id, sequence=info['sequence']))
                                metadata = dict(session, request_id=request_id, photo=dict(info, path='native.png'),
                                    factory_calibration=json.loads(factory), success=True,
                                    exposure_start_after_request_s=(exposure - requested).total_seconds(),
                                    projection=dict(K=frame.getTransformation().getIntrinsicMatrix(),
                                        D=distortion, rectified=False, focus=args.focus,
                                        status='SDK/factory optics; focus-specific accuracy not independently validated'))
                                writer = writers.submit(archive, frame, metadata)
                                pending = None
                            preview = cv2.resize(frame.getCvFrame(), (1280, 960))
                            ok, jpeg = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 90])
                            if ok:
                                send('FRAME', dict(sequence=frame.getSequenceNum(), received=time.time(),
                                    size=[preview.shape[1], preview.shape[0]], device_id=args.device_id,
                                    device_timestamp_s=frame.getTimestampDevice().total_seconds(),
                                    lens_position=frame.getLensPosition(),
                                    exposure_us=frame.getExposureTime().total_seconds()*1e6,
                                    reported_iso=frame.getSensitivity(), rectified=False, factory_sha256=factory_sha,
                                    source='N100 USB SDK preview; raw sensor orientation'), memoryview(jpeg))
                finally:
                    try:
                        if factory != factory_bytes(device):
                            raise RuntimeError('Factory calibration changed during the USB session')
                    finally:
                        pipeline.stop()
                        pipeline.wait()
    print('USB_OAK_RELEASED', file=sys.stderr, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-id', default='18443010314F3B1300')
    parser.add_argument('--focus', type=int, choices=range(256), default=112)
    args = parser.parse_args()
    running = threading.Event()
    running.set()
    signal.signal(signal.SIGINT, lambda *_: running.clear())
    signal.signal(signal.SIGTERM, lambda *_: running.clear())
    run(args, running)


if __name__ == '__main__':
    main()
