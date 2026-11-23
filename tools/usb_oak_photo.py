#!/usr/bin/env python3
"""One native-resolution USB OAK RGB photograph; exclusive N100 camera lease."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

os.environ.setdefault('DEPTHAI_PROTOCOL', 'usb')
os.environ.setdefault('DEPTHAI_TELEMETRY', '0')
import cv2
import depthai as dai


def factory_bytes(device):
    return json.dumps(device.readCalibration().eepromToJson(), sort_keys=True, indent=2).encode()


def describe(frame):
    return dict(width=frame.getWidth(), height=frame.getHeight(), sequence=frame.getSequenceNum(),
        timestamp_device_s=frame.getTimestampDevice().total_seconds(),
        exposure_us=round(frame.getExposureTime().total_seconds()*1e6), reported_iso=frame.getSensitivity(),
        lens_position=frame.getLensPosition(), white_balance_K=frame.getColorTemperature())


def capture(args, report):
    with (Path.home()/'uwa-camera/.camera.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        devices = [d for d in dai.Device.getAllAvailableDevices()
                   if 'USB' in str(d.protocol) and d.getDeviceId() == args.device_id]
        if len(devices) != 1:
            raise RuntimeError('Selected USB OAK unavailable; close its own SDK/ROS stream first')
        with dai.Device(devices[0]) as device:
            device.setMaxReconnectionAttempts(0)
            if device.getPlatform() != dai.Platform.RVC2 or device.getDeviceId() != args.device_id:
                raise RuntimeError('Expected the selected USB RVC2 camera, not Ethernet OAK4')
            sensor = next(f for f in device.getConnectedCameraFeatures() if f.socket == dai.CameraBoardSocket.CAM_A)
            size = (sensor.width, sensor.height)
            report.update(device_id=device.getDeviceId(), device_name=device.getDeviceName(),
                          sensor=sensor.sensorName, native_size=list(size), usb_speed=str(device.getUsbSpeed()))
            before = factory_bytes(device)
            (args.output/'factory-calibration.json').write_bytes(before)
            report['factory_sha256_before'] = hashlib.sha256(before).hexdigest()
            factory_focus = next(data['lensPosition'] for socket, data in json.loads(before)['cameraData'] if socket == 0)
            selected_focus = factory_focus if args.focus is None else args.focus
            report['selected_focus'] = selected_focus
            report['focus_policy'] = 'factory-calibration focus' if args.focus is None else 'explicit manual focus'
            with dai.Pipeline(device) as pipeline:
                cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A,
                    sensorResolution=size, sensorFps=5)
                cam.initialControl.setAutoExposureEnable()
                cam.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                cam.initialControl.setManualFocus(selected_focus)
                queue = cam.requestFullResolutionOutput(fps=1, useHighestResolution=True).createOutputQueue(maxSize=1, blocking=False)
                controls = cam.inputControl.createInputQueue()
                pipeline.start()
                try:
                    start = time.monotonic(); history = []
                    while time.monotonic()-start < 20:
                        frame = queue.tryGet()
                        if frame is None:
                            time.sleep(.02); continue
                        info = describe(frame)
                        if (info['width'], info['height']) != size:
                            raise RuntimeError(f'Native dimensions not confirmed: {info}')
                        history.append(info)
                        if time.monotonic()-start >= 3 and len(history) >= 3 and len({f['lens_position'] for f in history[-3:]}) == 1:
                            break
                    else:
                        raise TimeoutError('No settled native image within20s')
                    focus = info['lens_position']
                    if not 0 <= focus <= 255 or focus != selected_focus:
                        raise RuntimeError('Native manual/autofocus readback invalid')
                    ctrl = dai.CameraControl()
                    ctrl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                    ctrl.setManualFocus(focus)
                    controls.send(ctrl)
                    previous = info['sequence']; deadline = time.monotonic()+8
                    while time.monotonic() < deadline:
                        frame = queue.tryGet()
                        if frame is None:
                            time.sleep(.02); continue
                        actual = describe(frame)
                        if actual['sequence'] > previous and actual['lens_position'] == focus:
                            break
                    else:
                        raise TimeoutError('Locked-focus native photo not confirmed')
                    image = frame.getCvFrame()
                    if image.shape != (size[1], size[0], 3):
                        raise RuntimeError(f'Unexpected native payload {image.shape}')
                    report['photo'] = dict(actual, path='native.png')
                    report['focus_warmup_frames'] = history
                    report['projection'] = dict(K=frame.getTransformation().getIntrinsicMatrix(),
                        D=device.readCalibration().getDistortionCoefficients(dai.CameraBoardSocket.CAM_A),
                        rectified=False, focus=focus, status='SDK/factory optics; focus-specific accuracy not independently validated')
                    report['focus_scan'] = []
                    for candidate in args.focus_values or []:
                        while queue.tryGet() is not None:
                            pass
                        ctrl = dai.CameraControl()
                        ctrl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                        ctrl.setManualFocus(candidate)
                        controls.send(ctrl)
                        deadline = time.monotonic()+8; confirmed = 0
                        while time.monotonic() < deadline:
                            scan_frame = queue.tryGet()
                            if scan_frame is None:
                                time.sleep(.02); continue
                            scan_info = describe(scan_frame)
                            confirmed = confirmed+1 if scan_info['lens_position'] == candidate else 0
                            if confirmed >= 2:
                                break
                        else:
                            raise TimeoutError(f'Focus scan position {candidate} not confirmed')
                        scan_image = scan_frame.getCvFrame()
                        if scan_image.shape != (size[1], size[0], 3):
                            raise RuntimeError('Focus scan dimensions differ from native sensor')
                        scan_path = f'focus-{candidate}.png'
                        if not cv2.imwrite(str(args.output/scan_path), scan_image, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
                            raise RuntimeError('Cannot save '+scan_path)
                        report['focus_scan'].append(dict(scan_info, path=scan_path))
                        print(f'FOCUS {candidate}: DONE', flush=True)
                    if not cv2.imwrite(str(args.output/'native.png'), image, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
                        raise RuntimeError('Cannot save native PNG')
                    preview = cv2.resize(image, (1600, round(size[1]*1600/size[0])))
                    if not cv2.imwrite(str(args.output/'preview.jpg'), preview, [cv2.IMWRITE_JPEG_QUALITY, 94]):
                        raise RuntimeError('Cannot save display preview')
                    after = factory_bytes(device)
                    report['factory_sha256_after'] = hashlib.sha256(after).hexdigest()
                    if before != after:
                        raise RuntimeError('Factory calibration unexpectedly changed')
                finally:
                    pipeline.stop(); pipeline.wait()
        report['camera_closed'] = True
    report['camera_lease_released'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-id', default='18443010314F3B1300')
    parser.add_argument('--focus', type=int)
    parser.add_argument('--focus-values', type=int, nargs='+', help='Optional native focus sweep after reference photo')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.focus is not None and not 0 <= args.focus <= 255:
        parser.error('Focus must be0..255')
    if args.focus_values and (len(args.focus_values)>12 or any(not 0<=f<=255 for f in args.focus_values)):
        parser.error('Focus sweep requires at most12 positions in0..255')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), success=False,
        depthai=dai.__version__, opencv=cv2.__version__, requested_focus=args.focus,
        scope='USB camera-only native photograph; no robot or calibration writes')
    try:
        capture(args, report)
        report['success'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (args.output/'metadata.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
