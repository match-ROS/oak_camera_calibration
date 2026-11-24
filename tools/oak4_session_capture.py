#!/usr/bin/env python3
"""Native fixed-focus OAK4 stills, with optional persistent preview and control."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import socket
import time

import cv2
import depthai as dai

from oak4_photo_capture import metadata


def utc():
    return datetime.now(timezone.utc).isoformat()


def reply(connection, event, **values):
    connection.sendall(json.dumps(dict(event=event, **values)).encode() + b'\n')


def store_preview(frame, path, device_id):
    success, jpg = cv2.imencode('.jpg', frame.getCvFrame(), [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not success:
        raise RuntimeError('OAK4 preview JPEG encoding failed')
    info = metadata(frame)
    info.update(received=time.time(), size=[info['width'], info['height']],
                device_timestamp_s=info['timestamp_device_s'], device_id=device_id,
                source='Live preview from native 8000x6000 pipeline')
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(json.dumps(info).encode() + b'\n' + jpg.tobytes())
    temporary.replace(path)


def photograph(args, destination, on_acquired, trigger, native, previous, factory, wb, running):
    if destination.exists():
        raise FileExistsError(destination)
    started = utc()
    request_time = dai.Clock.now()
    deadline = time.monotonic() + 12
    trigger.send(dai.Buffer())
    while running() and time.monotonic() < deadline:
        frame = native.tryGet()
        if frame is None:
            time.sleep(.005)
            continue
        start = frame.getTimestamp(dai.CameraExposureOffset.START)
        end = frame.getTimestamp(dai.CameraExposureOffset.END)
        received = dai.Clock.now()
        if start < request_time or frame.getSequenceNum() <= previous:
            # A frame may already have been in the ISP when the device received the trigger.
            trigger.send(dai.Buffer())
            continue
        info = metadata(frame)
        if ((info['width'], info['height']) != (8000, 6000) or info['lens_position'] != args.focus or
                info['white_balance_K'] != wb or min(info['exposure_us'], info['reported_iso'], info['white_balance_K']) <= 0 or
                end < start or start > received):
            raise ValueError('Unexpected native OAK4 frame dimensions, optics or timestamp')
        info.update(path=destination.name, sdk_exposure_start_s=start.total_seconds(),
                    sdk_exposure_end_s=end.total_seconds(), request_to_exposure_start_s=(start-request_time).total_seconds(),
                    request_to_host_frame_s=(received-request_time).total_seconds())
        on_acquired()
        image = frame.getCvFrame()
        if image.shape != (6000, 8000, 3):
            raise ValueError('OAK4 decoder returned wrong image dimensions')
        temporary = destination.with_suffix('.partial.png')
        try:
            if not cv2.imwrite(str(temporary), image, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
                raise IOError('Native OAK4 PNG write failed')
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        report = dict(schema=1, mode='standard', success=True, source='persistent_native_session',
                      width=8000, height=6000, sensor_fps=10, device_id=args.device_id,
                      camera_ip=args.ip, requested_manual_focus=args.focus, requested_frames=1,
                      standard=info, depthai=dai.__version__, opencv=cv2.__version__,
                      factory_optics_approximate_only=factory,
                      timestamps='SDK host-synchronized exposure relative to local OAK trigger; device time is monotonic',
                      started_at=started, finished_at=utc())
        return report
    raise TimeoutError('No confirmed new native OAK4 frame after trigger')


def run(args, connection, running):
    with dai.Device(dai.DeviceInfo(args.ip)) as device, dai.Pipeline(device) as pipeline:
        device.setMaxReconnectionAttempts(0)
        if device.getDeviceId() != args.device_id:
            raise ValueError('OAK4 device ID differs from inventory')
        calibration = device.readCalibration()
        rgb = dai.CameraBoardSocket.CAM_A
        factory = dict(K=calibration.getCameraIntrinsics(rgb, 8000, 6000),
                       D=calibration.getDistortionCoefficients(rgb),
                       factory_lens_position=calibration.getLensPosition(rgb))
        camera = pipeline.create(dai.node.Camera).build(rgb, sensorResolution=(8000, 6000), sensorFps=10)
        camera.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
        camera.initialControl.setManualFocus(args.focus)
        camera.initialControl.setAutoExposureEnable()
        full = camera.requestFullResolutionOutput(fps=10, useHighestResolution=True)
        gate = pipeline.create(dai.node.Script)
        full.link(gate.inputs['frames'])
        gate.setScript("""
count = 0
while True:
    frame = node.io['frames'].get()
    if node.io['trigger'].tryGet() is not None:
        node.io['still'].send(frame)
    if count % 5 == 0:
        node.io['preview'].send(frame)
    count += 1
""")
        small = pipeline.create(dai.node.ImageManip)
        small.initialConfig.setOutputSize(2000, 1500)
        small.setMaxOutputFrameSize(2000 * 1500 * 3)
        small.inputImage.setBlocking(False)
        small.inputImage.setMaxSize(1)
        gate.outputs['preview'].link(small.inputImage)
        preview = small.out.createOutputQueue(maxSize=1, blocking=False)
        native = gate.outputs['still'].createOutputQueue(maxSize=1, blocking=False)
        trigger = gate.inputs['trigger'].createInputQueue()
        controls = camera.inputControl.createInputQueue()
        pipeline.start()
        previous = -1
        wb = None
        ready = False
        warm_at = time.monotonic() + (0 if args.no_preview or args.once else 5)
        ready_deadline = time.monotonic() + 30
        recent = []
        last_preview = -1
        pending = b''
        try:
            while running() and pipeline.isRunning():
                if not ready and time.monotonic() > ready_deadline:
                    raise RuntimeError('OAK4 focus, exposure and white balance did not settle')
                if connection is None:
                    time.sleep(.005)
                elif select.select([connection], [], [], .005)[0]:
                    packet = connection.recv(8192)
                    if not packet:
                        break
                    pending += packet
                    if len(pending) > 65536:
                        raise ValueError('Oversized OAK4 command')
                if ready and b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    request = json.loads(line)
                    try:
                        destination = Path(request['directory']) / ('standard.png' if args.no_preview else 'image.png')
                        report = photograph(args, destination, lambda: reply(connection, 'acquired', id=request['id']),
                                            trigger, native, previous, factory, wb, running)
                        previous = report['standard']['sequence']
                        reply(connection, 'saved', id=request['id'], metadata=report)
                    except Exception as error:
                        reply(connection, 'error', id=request['id'], error=str(error))
                frame = preview.tryGet()
                if frame is None or time.monotonic() < warm_at or frame.getLensPosition() != args.focus:
                    continue
                if frame.getSequenceNum() <= last_preview:
                    continue
                last_preview = frame.getSequenceNum()
                if wb is None:
                    temperature = frame.getColorTemperature()
                    exposure = frame.getExposureTime().total_seconds()
                    iso = frame.getSensitivity()
                    if args.no_preview or args.once:
                        if min(temperature, exposure, iso) <= 0:
                            recent.clear()
                            continue
                        recent.append((exposure, iso, temperature))
                        recent = recent[-3:]
                        if (len(recent) != 3 or
                                any(max(column) > 1.06 * min(column) for column in zip(*recent))):
                            continue
                    if temperature <= 0:
                        continue
                    wb = temperature
                    control = dai.CameraControl()
                    control.setManualWhiteBalance(wb)
                    controls.send(control)
                    continue
                if frame.getColorTemperature() != wb:
                    continue
                if args.once:
                    report = photograph(args, args.output / 'standard.png', lambda: None,
                                        trigger, native, previous, factory, wb, running)
                    report['source'] = 'fixed_focus_single_capture'
                    (args.output / 'metadata.json').write_text(json.dumps(report, indent=2) + '\n')
                    return
                if not args.no_preview:
                    store_preview(frame, args.output / 'frame.bin', args.device_id)
                ready = True
        finally:
            pipeline.stop()
            pipeline.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True)
    parser.add_argument('--device-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--lock', type=Path)
    parser.add_argument('--socket')
    parser.add_argument('--lease-fd', type=int, help='One still under the inherited photo service lease')
    parser.add_argument('--no-preview', action='store_true')
    parser.add_argument('--focus', type=int, choices=range(256), required=True)
    args = parser.parse_args()
    args.once = args.lease_fd is not None
    active = [True]
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: active.__setitem__(0, False))
    if args.once:
        if args.socket or args.lock:
            parser.error('Single-shot mode runs under the inherited photo service lease')
        fcntl.flock(args.lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args, None, lambda: active[0])
    else:
        if not args.socket or not args.lock:
            parser.error('The persistent worker requires --socket and --lock')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection, args.lock.open('a') as lease:
            connection.connect(args.socket)
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(args, connection, lambda: active[0])


if __name__ == '__main__':
    main()
