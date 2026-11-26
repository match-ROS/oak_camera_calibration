#!/usr/bin/env python3
"""Native stereo snapshot + robust multi-frame depth for a static scene."""
import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import signal
import time

os.environ.setdefault('DEPTHAI_TELEMETRY', '0')
import cv2
import depthai as dai
import numpy as np
from oak4_depth_fusion import fuse_brackets, fuse_depth

SIZE = (1280, 800)
HDR_ISO = 200
IR_SETTLE = timedelta(seconds=.35)


def frame_info(frame):
    return dict(width=frame.getWidth(), height=frame.getHeight(),
                sequence=frame.getSequenceNum(), timestamp_device_s=frame.getTimestampDevice().total_seconds(),
                exposure_us=round(frame.getExposureTime().total_seconds() * 1e6),
                reported_iso=frame.getSensitivity())


def wait(queue, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        frame = queue.tryGet()
        if frame is not None:
            return frame
        time.sleep(.005)
    raise TimeoutError('No stereo frame within 30 seconds')


def save_png(path, image):
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f'Cannot save {path}')


def preview(out, standard, fused, count, hdr=False):
    def color(depth):
        scaled = np.clip(depth.astype(np.float32) / 6000 * 255, 0, 255).astype(np.uint8)
        image = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
        image[depth == 0] = 0
        return image
    panels = [('Standard: one passive frame', color(standard))]
    if hdr:
        support = fused['contributing_settings']
        colored = cv2.applyColorMap((support.astype(float) * 255 / 4).astype(np.uint8), cv2.COLORMAP_TURBO)
        colored[support == 0] = 0
        colored[fused['cross_exposure_conflict']] = (255, 0, 255)
        panels.extend([('Stereo HDR: 4 x 4 frames', color(fused['hq'])),
                       ('Supporting settings: 1-4. Magenta: conflict.', colored)])
    else:
        mad = cv2.applyColorMap(
            np.clip(fused['temporal_mad_mm'] * 255 / 50, 0, 255).astype(np.uint8), cv2.COLORMAP_TURBO)
        mad[fused['valid_counts'] == 0] = 0
        panels.extend([(f'Static HQ: {count}-frame robust median', color(fused['hq'])),
                       ('Temporal MAD: 0-50 mm (blue-red)', mad)])
    canvas = np.full((620, 2400, 3), 245, np.uint8)
    for i, (label, image) in enumerate(panels):
        canvas[55:555, i*800:(i+1)*800] = cv2.resize(image, (800, 500), interpolation=cv2.INTER_NEAREST)
        cv2.putText(canvas, label, (i*800+12, 33), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 2)
    legend = 'Depth scale: 0-6000 mm, blue-red. Black = invalid.'
    if not hdr:
        legend += ' MAD = variation, not accuracy.'
    cv2.putText(canvas, legend,
                (15, 590), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 2)
    save_png(out / 'comparison.png', canvas)


def projection(frame, coordinate_frame='rectified right virtual optical: X right, Y down, Z forward'):
    transform = frame.getTransformation()
    k = np.asarray(transform.getIntrinsicMatrix(), dtype=float)
    if k.shape != (3, 3) or not np.isfinite(k).all() or min(k[0, 0], k[1, 1]) <= 0:
        raise RuntimeError('Depth frame has no valid rectified projection matrix')
    return dict(source='actual depth ImgFrame.getTransformation().getIntrinsicMatrix()',
                K=k.tolist(), size=list(transform.getSize()),
                coordinate_frame=coordinate_frame,
                T_reference_from_depth_m=transform.getExtrinsics().getTransformationMatrix(unit=dai.LengthUnit.METER),
                reference_camera_socket=str(transform.getExtrinsics().toCameraSocket))


def projector(device, intensity):
    if not device.setIrLaserDotProjectorIntensity(intensity):
        raise RuntimeError(f'Projector command {intensity:.0%} was rejected')


def acquire_hdr(device, controls, queue, report, size=SIZE, projection_for_frame=projection):
    def pairs(timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            group = queue.tryGet()
            if group is None:
                time.sleep(.003)
                continue
            left, right, depth = group['left'], group['right'], group['depth']
            times = [frame.getTimestampDevice().total_seconds() for frame in (left, right, depth)]
            if (max(times) - min(times) > .012 or abs(times[1] - times[2]) > .002
                    or right.getSequenceNum() != depth.getSequenceNum()):
                raise RuntimeError('Depth and stereo input frame times do not agree')
            yield left, right, depth

    projector(device, 0.)
    recent, last_sequence = [], -1
    started = time.monotonic()
    for left, right, _ in pairs(6):
        metering = [frame_info(frame) for frame in (left, right)]
        recent.append([row['exposure_us'] * row['reported_iso'] for row in metering])
        recent = recent[-5:]
        if time.monotonic() - started < .6 or len(recent) < 5:
            continue
        values = np.asarray(recent)
        if values.min() > 0 and np.all(values.max(axis=0) <= 1.10 * values.min(axis=0)):
            break
    else:
        raise TimeoutError('Mono auto-exposure did not stabilize')
    report['mono_metering'] = metering
    report['timing_s']['metering'] = time.monotonic() - started
    metered = int(np.rint(np.median(values) / HDR_ISO))
    base = int(np.clip(metered, 1200, 12000))
    report['exposure_limited'] = base != metered
    # Keep the same exposure when enabling IR after the passive middle bracket.
    settings = [('short', base // 4), ('long', base * 4), ('base', base), ('base_ir', base)]
    batches, standard, monos = [], None, None
    report['brackets'] = []
    for name, exposure in settings:
        tick = time.monotonic()
        active = name == 'base_ir'
        if active:
            projector(device, 1.)
            after = dai.Clock.now() + IR_SETTLE
        else:
            control = dai.CameraControl()
            control.setManualExposure(exposure, HDR_ISO)
            for target in controls:
                target.send(control)
            after = dai.Clock.now()
        frames, samples = [], []
        for left, right, depth in pairs(6):
            if any(frame.getTimestamp() <= after for frame in (left, right)):
                continue
            mono = [frame_info(frame) for frame in (left, right)]
            if any(abs(row['exposure_us'] - exposure) > max(75, exposure * .035)
                   or row['reported_iso'] != HDR_ISO for row in mono):
                continue
            if samples and any(
                (row['exposure_us'], row['reported_iso']) != (first['exposure_us'], first['reported_iso'])
                for row, first in zip(mono, samples[0]['mono'])
            ):
                raise RuntimeError('Mono exposure changed within an HDR setting')
            meta = frame_info(depth)
            if meta['sequence'] <= last_sequence:
                raise RuntimeError('Duplicate or out-of-order stereo frame')
            last_sequence = meta['sequence']
            array = depth.getCvFrame()
            if array.shape != size[::-1] or array.dtype != np.uint16:
                raise RuntimeError('Unexpected stereo depth format')
            current_projection = projection_for_frame(depth)
            if current_projection != report.setdefault('projection', current_projection):
                raise RuntimeError('Rectified stereo projection changed')
            frames.append(array.copy())
            samples.append(dict(depth=meta, mono=mono))
            if name == 'base' and standard is None:
                standard = frames[-1]
                report['standard'] = dict(meta, path='standard-depth-mm.png')
                monos = [frame.getCvFrame().copy() for frame in (left, right)]
            if len(frames) == 4:
                break
        else:
            raise TimeoutError(f'{name}: only {len(frames)}/4 frames with confirmed stereo settings')
        batches.append(np.stack(frames))
        report['frames'].extend(sample['depth'] for sample in samples)
        report['brackets'].append(dict(name=name, requested_exposure_us=exposure,
                                       projector_intensity=float(active), frames=samples))
        report['timing_s'][name] = time.monotonic() - tick
        print(f'Stereo HDR {name}: 4 frames', flush=True)
    return np.stack(batches), standard, monos


def finish_hdr(out, report, captured):
    raw, standard, monos = captured
    tick = time.monotonic()
    fused = fuse_brackets(raw)
    report['timing_s']['fusion'] = time.monotonic() - tick
    if not fused['stable'].any():
        raise RuntimeError('No stable depth pixels across stereo HDR settings')
    report['hq'] = dict(path='hq-depth-mm.png', frame_count=16)
    report['data_files'] = dict(raw_and_quality='depth-data.npz', stable_mask='stable-mask.png',
                                comparison='comparison.png', factory='factory-calibration.json',
                                mono_left='mono-left.png', mono_right='mono-right.png')
    report['fusion'] = dict(method='temporal median per setting and median of agreeing settings',
                            required_count_per_setting=3, tolerance_mm='max(10 mm, 1% of depth)',
                            hole_filling=False)
    report['statistics'] = dict(standard_valid_fraction=float(np.mean(standard > 0)),
                                hq_valid_fraction=float(fused['stable'].mean()),
                                conflict_fraction=float(fused['cross_exposure_conflict'].mean()))
    for name, image in [('standard-depth-mm.png', standard), ('hq-depth-mm.png', fused['hq']),
                        ('stable-mask.png', fused['stable'].astype(np.uint8) * 255),
                        ('mono-left.png', monos[0]), ('mono-right.png', monos[1])]:
        save_png(out / name, image)
    np.savez(out / 'depth-data.npz', raw_depth_mm=raw, standard_depth_mm=standard, **fused)
    preview(out, standard, fused, 16, hdr=True)


def acquire(args, report):
    with dai.Device(dai.DeviceInfo(args.ip)) as device:
        device.setMaxReconnectionAttempts(0)
        report['device_id'] = device.getDeviceId()
        if args.device_id and report['device_id'] != args.device_id:
            raise RuntimeError('Device ID does not match inventory')
        hdr = args.mode == 'hdr'
        if hdr and (device.getPlatform() != dai.Platform.RVC4 or device.getProductName() != 'OAK-4-PRO-AF'):
            raise RuntimeError('Stereo HDR requires the OAK4 Pro projector')
        calibration = device.readCalibration()
        (args.output / 'factory-calibration.json').write_text(json.dumps(calibration.eepromToJson(), indent=2))
        report['geometry'] = dict(alignment='RECTIFIED_RIGHT (CAM_C)', unit='millimetres, Z-depth',
                                 rectification_rotation=calibration.getStereoRightRectificationRotation(),
                                 note='Factory backup is unrectified calibration; no point cloud or world registration provided')
        with dai.Pipeline(device) as pipeline:
            mono_queues = []
            outputs = []
            controls = []
            for socket in (dai.CameraBoardSocket.CAM_B, dai.CameraBoardSocket.CAM_C):
                cam = pipeline.create(dai.node.Camera).build(socket,
                            sensorResolution=(1280, 800), sensorFps=10)
                cam.initialControl.setAutoExposureEnable()
                output = cam.requestOutput((1280, 800), type=dai.ImgFrame.Type.GRAY8, fps=10)
                outputs.append(output)
                if not hdr:
                    mono_queues.append(output.createOutputQueue(maxSize=2, blocking=False))
                controls.append(cam.inputControl.createInputQueue())
            stereo = pipeline.create(dai.node.StereoDepth)
            stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.FAST_ACCURACY)
            outputs[0].link(stereo.left)
            outputs[1].link(stereo.right)
            stereo.setDepthAlign(dai.StereoDepthConfig.AlgorithmControl.DepthAlign.RECTIFIED_RIGHT)
            stereo.setExtendedDisparity(False)
            config = stereo.initialConfig
            config.postProcessing.decimationFilter.decimationFactor = 1
            config.algorithmControl.enableSwLeftRightCheck = True
            config.postProcessing.spatialFilter.enable = False
            config.postProcessing.temporalFilter.enable = False
            config.postProcessing.speckleFilter.enable = False
            config.setMedianFilter(dai.StereoDepthConfig.MedianFilter.MEDIAN_OFF)
            if hdr:
                sync = pipeline.create(dai.node.Sync)
                sync.setSyncThreshold(timedelta(milliseconds=12))
                sync.setSyncAttempts(-1)
                outputs[0].link(sync.inputs['left'])
                outputs[1].link(sync.inputs['right'])
                stereo.depth.link(sync.inputs['depth'])
                queue = sync.out.createOutputQueue(maxSize=4, blocking=False)
            else:
                queue = stereo.depth.createOutputQueue(maxSize=2, blocking=False)
            report['stereo'] = dict(preset='FAST_ACCURACY', software_lr=True, decimation=1,
                extended_disparity=False, hardware_subpixel_bits=4,
                spatial=False, temporal=False, speckle=False, median=False,
                sensor_fps=10, output_fps=10)
            pipeline.start()
            if hdr:
                try:
                    return acquire_hdr(device, controls, queue, report)
                finally:
                    try:
                        projector(device, 0.)
                        report['projector_off_confirmed_by_sdk'] = True
                    finally:
                        pipeline.stop()
                        pipeline.wait()
            try:
                time.sleep(5)
                # Freeze each mono camera's settled AE; verify stability during burst.
                report['mono_metering'] = [frame_info(wait(q)) for q in mono_queues]
                for control in controls:
                    lock = dai.CameraControl()
                    lock.setAutoExposureLock(True)
                    control.send(lock)
                time.sleep(1)
                queue.tryGetAll()
                for q in mono_queues:
                    q.tryGetAll()
                baseline = wait(queue)
                report['projection'] = projection(baseline)
                standard = baseline.getCvFrame().copy()
                if standard.shape != (800, 1280) or standard.dtype != np.uint16:
                    raise RuntimeError(f'Unexpected native depth format {standard.shape}/{standard.dtype}')
                report['standard'] = dict(frame_info(baseline), path='standard-depth-mm.png')
                save_png(args.output / report['standard']['path'], standard)
                report['mono_locked'] = []
                for name, q in zip(('mono-left.png', 'mono-right.png'), mono_queues):
                    frame = wait(q)
                    report['mono_locked'].append(frame_info(frame))
                    save_png(args.output / name, frame.getCvFrame())
                if args.mode == 'standard':
                    return
                frames = []
                sequence = baseline.getSequenceNum()
                for i in range(args.frames):
                    frame = wait(queue)
                    if frame.getSequenceNum() <= sequence:
                        raise RuntimeError('Duplicate or out-of-order stereo frame')
                    sequence = frame.getSequenceNum()
                    depth = frame.getCvFrame()
                    if depth.shape != standard.shape or depth.dtype != np.uint16:
                        raise RuntimeError('Depth format changed during burst')
                    report['frames'].append(frame_info(frame))
                    frames.append(depth.copy())
                    for j, q in enumerate(mono_queues):
                        info = frame_info(wait(q))
                        if any(info[key] != report['mono_locked'][j][key]
                               for key in ('exposure_us', 'reported_iso')):
                            raise RuntimeError('Mono exposure changed during burst')
                burst = np.stack(frames)
                fused = fuse_depth(burst)
                save_png(args.output / 'hq-depth-mm.png', fused['hq'])
                save_png(args.output / 'stable-mask.png', fused['stable'].astype(np.uint8) * 255)
                np.savez_compressed(args.output / 'depth-data.npz', raw_depth_mm=burst,
                                    standard_depth_mm=standard, **fused)
                report['hq'] = dict(path='hq-depth-mm.png', frame_count=args.frames)
                report['data_files'] = dict(raw_and_quality='depth-data.npz', stable_mask='stable-mask.png',
                                            comparison='comparison.png', factory='factory-calibration.json',
                                            mono_left='mono-left.png', mono_right='mono-right.png')
                report['fusion'] = dict(method='valid-only temporal median; no hole filling or spatial smoothing',
                    support_fraction=.75, tolerance_mm='max(10 mm, 1% of median depth)',
                    required_count=int(np.ceil(.75 * args.frames)),
                    note='Stability heuristic, not calibrated confidence or proof of static scene')
                mask = fused['stable']
                report['statistics'] = dict(standard_valid_fraction=float(np.mean(standard > 0)),
                    hq_valid_fraction=float(mask.mean()),
                    median_temporal_mad_mm=float(np.median(fused['temporal_mad_mm'][mask])) if mask.any() else None,
                    accuracy='Not measured against a metrological ground truth')
                preview(args.output, standard, fused, args.frames)
                if not mask.any():
                    raise RuntimeError('No stable depth pixels; inspect raw data and scene texture')
            finally:
                for control in controls:
                    auto = dai.CameraControl()
                    auto.setAutoExposureLock(False)
                    auto.setAutoExposureEnable()
                    control.send(auto)
                pipeline.stop()
                pipeline.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True)
    parser.add_argument('--device-id', default='')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('standard', 'hq', 'compare', 'hdr'), default='hq')
    parser.add_argument('--frames', type=int)
    args = parser.parse_args()
    if args.frames is None:
        args.frames = 4 if args.mode == 'hdr' else 16
    if not 4 <= args.frames <= 32:
        parser.error('depth frames must be 4..32')
    if args.mode == 'hdr' and args.frames != 4:
        parser.error('Stereo HDR uses four frames per setting')
    if args.mode == 'hdr':
        def terminate(_signum, _frame):
            raise InterruptedError('Stereo HDR capture was cancelled')

        signal.signal(signal.SIGTERM, terminate)
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / 'metadata.json').exists():
        parser.error('Output already contains a capture')
    report = dict(schema=1, kind='depth', mode=args.mode, success=False, frames=[],
                  camera_ip=args.ip, depthai=dai.__version__,
                  started_at=datetime.now().astimezone().isoformat(),
                  timestamps='device monotonic time; not synchronized to ROS/wall clock')
    try:
        report['timing_s'] = {}
        tick = time.monotonic()
        captured = acquire(args, report)
        if args.mode == 'hdr':
            report['timing_s']['camera_session'] = time.monotonic() - tick
            finish_hdr(args.output, report, captured)
        report['timing_s']['worker_total'] = time.monotonic() - tick
        report['success'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['finished_at'] = datetime.now().astimezone().isoformat()
        (args.output / 'metadata.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
