#!/usr/bin/env python3
"""Leased USB-OAK preview over an owned SSH stream; stdin stop/EOF releases it."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import sys
import time

os.environ.setdefault('DEPTHAI_PROTOCOL', 'usb')
os.environ.setdefault('DEPTHAI_TELEMETRY', '0')
import cv2
import depthai as dai


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device-id', default='18443010314F3B1300')
    p.add_argument('--focus', type=int, choices=range(256), default=112)
    args = p.parse_args()
    running = [True]
    signal.signal(signal.SIGINT, lambda *_: running.__setitem__(0, False))
    signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))
    with (Path.home()/'uwa-camera/.camera.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        devices = [d for d in dai.Device.getAllAvailableDevices()
                   if 'USB' in str(d.protocol) and d.getDeviceId() == args.device_id]
        if len(devices) != 1:
            raise RuntimeError('USB OAK unavailable; its other camera user must release the lease')
        with dai.Device(devices[0]) as device:
            device.setMaxReconnectionAttempts(0)
            if device.getPlatform() != dai.Platform.RVC2:
                raise RuntimeError('Expected the N100 USB RVC2 OAK')
            factory = json.dumps(device.readCalibration().eepromToJson(), sort_keys=True).encode()
            sensor = next(s for s in device.getConnectedCameraFeatures() if s.socket == dai.CameraBoardSocket.CAM_A)
            with dai.Pipeline(device) as pipeline:
                cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A,
                    sensorResolution=(sensor.width, sensor.height), sensorFps=5)
                cam.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                cam.initialControl.setManualFocus(args.focus)
                cam.initialControl.setAutoExposureEnable()
                frames = cam.requestOutput((1280,960), type=dai.ImgFrame.Type.NV12,
                    fps=2, enableUndistortion=False).createOutputQueue(maxSize=1, blocking=False)
                pipeline.start()
                try:
                    while running[0] and pipeline.isRunning():
                        if select.select([sys.stdin], [], [], 0)[0]:
                            command = sys.stdin.readline()
                            if not command or command.strip() == 'stop':
                                break
                        frame = frames.tryGet()
                        if frame is None:
                            time.sleep(.03)
                            continue
                        if frame.getLensPosition() != args.focus:
                            continue
                        jpeg = cv2.imencode('.jpg', frame.getCvFrame(), [cv2.IMWRITE_JPEG_QUALITY,90])[1].tobytes()
                        metadata = dict(sequence=frame.getSequenceNum(), received=time.time(),
                            size=[frame.getWidth(),frame.getHeight()], device_id=device.getDeviceId(),
                            device_timestamp_s=frame.getTimestampDevice().total_seconds(),
                            lens_position=frame.getLensPosition(),
                            exposure_us=frame.getExposureTime().total_seconds()*1e6,
                            reported_iso=frame.getSensitivity(), rectified=False,
                            factory_sha256=hashlib.sha256(factory).hexdigest(), bytes=len(jpeg),
                            source='N100 USB SDK preview; raw sensor orientation')
                        sys.stdout.buffer.write(b'UWA_FRAME '+json.dumps(metadata).encode()+b'\n'+jpeg)
                        sys.stdout.buffer.flush()
                finally:
                    try:
                        after = json.dumps(device.readCalibration().eepromToJson(),sort_keys=True).encode()
                        if factory != after:
                            raise RuntimeError('Factory calibration changed during preview')
                    finally:
                        pipeline.stop()
                        pipeline.wait()
    print('USB_OAK_RELEASED', file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
