#!/usr/bin/env python3
"""Native stereo snapshot + robust multi-frame depth for a static scene."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import time

os.environ.setdefault('DEPTHAI_TELEMETRY', '0')
import cv2
import depthai as dai
import numpy as np
from oak4_depth_fusion import fuse_depth


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


def preview(out, standard, fused, count):
    def color(depth):
        scaled = np.clip(depth.astype(np.float32) / 6000 * 255, 0, 255).astype(np.uint8)
        image = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
        image[depth == 0] = 0
        return image
    panels = [('Standard: one frame', color(standard)),
              (f'Static HQ: {count}-frame robust median', color(fused['hq'])),
              ('Temporal MAD: 0-50 mm (blue-red)', cv2.applyColorMap(
                  np.clip(fused['temporal_mad_mm'] * 255 / 50, 0, 255).astype(np.uint8),
                  cv2.COLORMAP_TURBO))]
    panels[-1][1][fused['valid_counts'] == 0] = 0
    canvas = np.full((620, 2400, 3), 245, np.uint8)
    for i, (label, image) in enumerate(panels):
        canvas[55:555, i*800:(i+1)*800] = cv2.resize(image, (800, 500), interpolation=cv2.INTER_NEAREST)
        cv2.putText(canvas, label, (i*800+12, 33), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 2)
    cv2.putText(canvas, 'Depth scale: 0-6000 mm, blue-red. Black = invalid. MAD = variation, not accuracy.',
                (15, 590), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 2)
    save_png(out / 'comparison.png', canvas)


def acquire(args, report):
    with dai.Device(dai.DeviceInfo(args.ip)) as device:
        device.setMaxReconnectionAttempts(0)
        report['device_id'] = device.getDeviceId()
        if args.device_id and report['device_id'] != args.device_id:
            raise RuntimeError('Device ID does not match inventory')
        calibration = device.readCalibration()
        (args.output / 'factory-calibration.json').write_text(json.dumps(calibration.eepromToJson(), indent=2))
        report['geometry'] = dict(alignment='RECTIFIED_RIGHT (CAM_C)', unit='millimetres, Z-depth',
                                 rectification_rotation=calibration.getStereoRightRectificationRotation(),
                                 note='Factory backup is unrectified calibration; no point cloud or world registration provided')
        with dai.Pipeline(device) as pipeline:
            cameras = []
            mono_queues = []
            outputs = []
            controls = []
            for socket in (dai.CameraBoardSocket.CAM_B, dai.CameraBoardSocket.CAM_C):
                cam = pipeline.create(dai.node.Camera).build(socket,
                            sensorResolution=(1280, 800), sensorFps=10)
                cam.initialControl.setAutoExposureEnable()
                output = cam.requestOutput((1280, 800), type=dai.ImgFrame.Type.GRAY8, fps=10)
                outputs.append(output)
                mono_queues.append(output.createOutputQueue(maxSize=2, blocking=False))
                controls.append(cam.inputControl.createInputQueue())
                cameras.append(cam)
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
            queue = stereo.depth.createOutputQueue(maxSize=2, blocking=False)
            report['stereo'] = dict(preset='FAST_ACCURACY', software_lr=True, decimation=1,
                extended_disparity=False, hardware_subpixel_bits=4,
                spatial=False, temporal=False, speckle=False, median=False,
                sensor_fps=10, output_fps=10)
            pipeline.start()
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
                transform = baseline.getTransformation()
                intrinsic = np.asarray(transform.getIntrinsicMatrix(), dtype=float)
                if intrinsic.shape != (3, 3) or not np.isfinite(intrinsic).all() or min(intrinsic[0, 0], intrinsic[1, 1]) <= 0:
                    raise RuntimeError('Depth frame has no valid rectified projection matrix')
                report['projection'] = dict(
                    source='actual depth ImgFrame.getTransformation().getIntrinsicMatrix()',
                    K=intrinsic.tolist(), size=list(transform.getSize()),
                    coordinate_frame='rectified right virtual optical: X right, Y down, Z forward',
                    T_reference_from_depth_m=transform.getExtrinsics().getTransformationMatrix(unit=dai.LengthUnit.METER),
                    reference_camera_socket=str(transform.getExtrinsics().toCameraSocket))
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
    parser.add_argument('--mode', choices=('standard', 'hq', 'compare'), default='hq')
    parser.add_argument('--frames', type=int, default=16)
    args = parser.parse_args()
    if not 4 <= args.frames <= 32:
        parser.error('depth frames must be 4..32')
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / 'metadata.json').exists():
        parser.error('Output already contains a capture')
    report = dict(schema=1, kind='depth', mode=args.mode, success=False, frames=[],
                  camera_ip=args.ip, depthai=dai.__version__,
                  started_at=datetime.now().astimezone().isoformat(),
                  timestamps='device monotonic time; not synchronized to ROS/wall clock')
    try:
        acquire(args, report)
        report['success'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['finished_at'] = datetime.now().astimezone().isoformat()
        (args.output / 'metadata.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
