#!/usr/bin/env python3
"""Exclusive 48 MP SDK worker. Invoke through oak4_photo_service.py / oak4_photo.sh."""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import time

os.environ.setdefault('DEPTHAI_TELEMETRY', '0')
import cv2
import depthai as dai
import numpy as np
from oak4_hdr import acquire as acquire_hdr, finish as finish_hdr


def metadata(frame):
    return dict(width=frame.getWidth(), height=frame.getHeight(),
                exposure_us=round(frame.getExposureTime().total_seconds() * 1e6),
                reported_iso=frame.getSensitivity(), lens_position=frame.getLensPosition(),
                white_balance_K=frame.getColorTemperature(), sequence=frame.getSequenceNum(),
                timestamp_device_s=frame.getTimestampDevice().total_seconds())


def exposure_for(reference_ev, iso):
    return max(100, min(90000, round(reference_ev / iso)))


def collect(args, report):
    def save(name, image):
        if image.shape != (6000, 8000, 3):
            raise RuntimeError(f'Expected native 8000x6000 BGR, received {image.shape}')
        if not cv2.imwrite(str(args.output / name), image, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
            raise RuntimeError(f'Cannot save {name}')
        return name

    with dai.Device(dai.DeviceInfo(args.ip)) as device:
        device.setMaxReconnectionAttempts(0)
        report['device_id'] = device.getDeviceId()
        if args.device_id and report['device_id'] != args.device_id:
            raise RuntimeError('Device ID does not match inventory')
        with dai.Pipeline(device) as pipeline:
            cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A,
                            sensorResolution=(8000, 6000), sensorFps=10)
            cam.initialControl.setAutoExposureEnable()
            if args.focus is None:
                cam.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.CONTINUOUS_PICTURE)
            else:
                cam.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                cam.initialControl.setManualFocus(args.focus)
            full = cam.requestFullResolutionOutput(fps=10, useHighestResolution=True)
            gate = pipeline.create(dai.node.Script)
            full.link(gate.inputs['frames'])
            # Send only requested full frames; continuous 48 MP does not fit 2.5 GbE.
            gate.setScript('''
while True:
    frame = node.io['frames'].get()
    if node.io['trigger'].tryGet() is not None:
        node.io['still'].send(frame)
''')
            output = gate.outputs['still'].createOutputQueue(maxSize=1, blocking=False)
            trigger = gate.inputs['trigger'].createInputQueue()
            control = cam.inputControl.createInputQueue()
            preview = None
            if args.mode == 'hdr':
                # OAK4 8K supports one ISP output: derive metadata preview from it.
                small = pipeline.create(dai.node.ImageManip)
                small.initialConfig.setOutputSize(320, 240)
                small.setMaxOutputFrameSize(320 * 240 * 3)
                small.inputImage.setBlocking(False)
                small.inputImage.setMaxSize(1)
                full.link(small.inputImage)
                preview = small.out.createOutputQueue(maxSize=2, blocking=False)
            last_sequence = -1

            def capture():
                nonlocal last_sequence
                trigger.send(dai.Buffer())
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    frame = output.tryGet()
                    if frame is not None:
                        info = metadata(frame)
                        if info['sequence'] <= last_sequence:
                            raise RuntimeError('Duplicate or out-of-order image')
                        if (info['width'], info['height']) != (8000, 6000):
                            raise RuntimeError(f'Unexpected dimensions: {info}')
                        last_sequence = info['sequence']
                        return frame, info
                    time.sleep(0.02)
                raise TimeoutError('No native frame within 30 seconds')

            pipeline.start()
            try:
                if args.mode == 'hdr':
                    def manual_control():
                        ctrl = dai.CameraControl()
                        ctrl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                        return ctrl
                    return acquire_hdr(args, report, capture, control, preview, manual_control, metadata)
                time.sleep(5)
                frame, meter = capture()
                report['metering'] = meter
                del frame
                lock = dai.CameraControl()
                lock.setAutoWhiteBalanceLock(True)
                lock.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                if not 0 <= meter['lens_position'] <= 255:
                    raise RuntimeError('No valid autofocus result')
                lock.setManualFocus(meter['lens_position'])
                control.send(lock)
                time.sleep(1.5)
                frame, standard = capture()
                report['standard'] = standard
                if args.focus is not None and standard['lens_position'] != args.focus:
                    raise RuntimeError('Requested manual focus not confirmed by frame readback')
                if args.mode in ('standard', 'compare'):
                    image = frame.getCvFrame()
                    standard['path'] = save('standard.png', image)
                    del image
                del frame
                if args.mode == 'standard':
                    return
                reference_ev = standard['exposure_us'] * max(1, standard['reported_iso'])
                if reference_ev <= 0:
                    raise RuntimeError('Invalid metering exposure')
                requested = exposure_for(reference_ev, args.iso)
                for attempt in range(3):
                    ctrl = dai.CameraControl()
                    ctrl.setManualExposure(requested, args.iso)
                    control.send(ctrl)
                    time.sleep(1.5)
                    frame, actual = capture()
                    report['exposure_trials'].append(dict(requested_us=requested,
                                                       requested_iso=args.iso, actual=actual))
                    actual_ev = max(1, actual['exposure_us']) * max(1, actual['reported_iso'])
                    ratio = reference_ev / actual_ev
                    corrected = max(100, min(90000, round(requested * ratio)))
                    if abs(math.log2(ratio)) < .1 or corrected == requested or attempt == 2:
                        break
                    requested = corrected
                    del frame
                report['hq_requested'] = dict(iso=args.iso, exposure_us=requested)
                report['exposure_difference_ev'] = math.log2(actual_ev / reference_ev)
                report['exposure_limited'] = abs(report['exposure_difference_ev']) > .2
                # Verify actual readback before averaging; an ignored control is an error.
                if actual['reported_iso'] != args.iso:
                    raise RuntimeError(f'ISO control not applied: {actual}')
                first = frame.getCvFrame()
                report['hq_single'] = dict(actual, path=save('hq-single.png', first))
                accumulator = first.astype(np.float32)
                report['hq_frames'].append(actual)
                del first, frame
                for i in range(1, args.frames):
                    frame, info = capture()
                    if any(info[key] != actual[key] for key in
                           ('reported_iso', 'exposure_us', 'lens_position', 'white_balance_K')):
                        raise RuntimeError(f'Camera controls changed during averaging: {info}')
                    accumulator += frame.getCvFrame()
                    report['hq_frames'].append(info)
                    print(f'HQ {i + 1}/{args.frames}', flush=True)
                    del frame
                accumulator /= args.frames
                np.rint(accumulator, out=accumulator)
                np.clip(accumulator, 0, 255, out=accumulator)
                result = accumulator.astype(np.uint8)
                report['hq'] = dict(path=save('hq.png', result), frame_count=args.frames)
            finally:
                # Controls belong to this temporary pipeline, not another live session.
                restore = dai.CameraControl()
                restore.setAutoExposureEnable()
                restore.setAutoWhiteBalanceLock(False)
                restore.setAutoFocusMode(dai.CameraControl.AutoFocusMode.CONTINUOUS_VIDEO)
                try:
                    control.send(restore)
                    if args.mode != 'hdr':
                        time.sleep(.3)
                finally:
                    pipeline.stop()
                    pipeline.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ip', required=True)
    p.add_argument('--device-id', default='')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--mode', choices=('standard', 'hq', 'compare', 'hdr'), default='hq')
    p.add_argument('--frames', type=int, default=None)
    p.add_argument('--iso', type=int, default=100)
    p.add_argument('--focus', type=int, default=None)
    args = p.parse_args()
    args.frames = (1 if args.mode == 'hdr' else 8) if args.frames is None else args.frames
    if not 1 <= args.frames <= 32 or not 100 <= args.iso <= 1600:
        p.error('frames must be 1..32 and ISO 100..1600')
    if args.focus is not None and not 0 <= args.focus <= 255:
        p.error('focus must be 0..255')
    if args.mode == 'hdr' and args.frames > 8:
        p.error('HDR supports 1..8 frames per exposure')
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / 'metadata.json').exists():
        p.error('Output already contains a capture')
    report = dict(schema=1, started_at=datetime.now().astimezone().isoformat(),
                  mode=args.mode, camera_ip=args.ip, depthai=dai.__version__,
                  opencv=cv2.__version__,
                  sensor_fps=10, width=8000, height=6000, requested_iso=args.iso,
                  requested_frames=args.frames, exposure_trials=[], hq_frames=[],
                  requested_manual_focus=args.focus,
                  averaging='arithmetic mean of ISP-decoded 8-bit BGR; no alignment or exposure normalization',
                  timestamps='device monotonic time; not synchronized to ROS/wall clock',
                  success=False)
    try:
        tick = time.monotonic()
        images = collect(args, report)
        camera_closed = time.monotonic()
        if args.mode == 'hdr':
            report['hdr_timing_s']['camera_session'] = camera_closed - tick
            report['hdr_implementation'] = 'metadata-confirmed controls; in-memory fusion; concurrent lossless PNG level1'
            print('HDR camera CLOSED; fusion RUNNING', flush=True)
            finish_hdr(args.output, images, report)
            report['averaging'] = 'Within each exposure only, before fusion' if args.frames > 1 else 'none'
            report['hdr_timing_s']['worker_total'] = time.monotonic() - tick
        report['success'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['finished_at'] = datetime.now().astimezone().isoformat()
        (args.output / 'metadata.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
