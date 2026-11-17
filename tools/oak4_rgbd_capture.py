#!/usr/bin/env python3
"""Bounded RVC4 RGB-D capture. Invoke through the shared photo transaction."""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import time

os.environ.setdefault('DEPTHAI_TELEMETRY', '0')
import cv2
import depthai as dai
import numpy as np
from oak4_rgbd_geometry import validate_pair

SIZE = (1280, 960)
FPS = 10
MAX_SKEW = .025


def save(path, image):
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f'Cannot save {path}')


def info(frame):
    return dict(sequence=int(frame.getSequenceNum()),
                timestamp_device_s=frame.getTimestampDevice().total_seconds())


def next_group(queue):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        group = queue.tryGet()
        if group is not None:
            return group
        time.sleep(.005)
    raise TimeoutError('No synchronized RGB-D pair within 30 seconds')


def preview(output, rgb, depth):
    color = cv2.applyColorMap(np.clip(depth / 6000 * 255, 0, 255).astype(np.uint8),
                             cv2.COLORMAP_TURBO)
    color[depth == 0] = 0
    blend = rgb.copy()
    valid = depth > 0
    blend[valid] = cv2.addWeighted(rgb, .5, color, .5, 0)[valid]
    canvas = np.zeros((540, 1920, 3), np.uint8)
    for index, (label, image) in enumerate([
        ('RGB - undistorted', rgb), ('Depth - RGB perspective', color),
        ('Overlay - inspect edges', blend),
    ]):
        x = 640 * index
        cv2.putText(canvas, label, (x + 12, 32), cv2.FONT_HERSHEY_SIMPLEX,
                    .65, (255, 255, 255), 2)
        canvas[45:525, x:x + 640] = cv2.resize(image, (640, 480), interpolation=cv2.INTER_NEAREST)
    save(output / 'preview.png', canvas)


def acquire(args, report):
    with dai.Device(dai.DeviceInfo(args.ip)) as device:
        device.setMaxReconnectionAttempts(0)
        report['device_id'] = device.getDeviceId()
        if args.device_id and report['device_id'] != args.device_id:
            raise RuntimeError('OAK identity differs from inventory')
        if device.getPlatform() != dai.Platform.RVC4:
            raise RuntimeError('This capture profile requires RVC4')
        factory = json.dumps(device.readCalibration().eepromToJson(), indent=2).encode()
        (args.output / 'factory-calibration.json').write_bytes(factory)
        report['factory_sha256'] = hashlib.sha256(factory).hexdigest()
        with dai.Pipeline(device) as pipeline:
            rgb_cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A,
                        sensorResolution=(8000, 6000), sensorFps=FPS)
            rgb_cam.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
            rgb_cam.initialControl.setManualFocus(args.focus)
            rgb_cam.initialControl.setAutoExposureEnable()
            rgb_out = rgb_cam.requestOutput(SIZE, type=dai.ImgFrame.Type.NV12,
                        fps=FPS, enableUndistortion=True, alphaScaling=0.)
            stereo = pipeline.create(dai.node.StereoDepth)
            stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.FAST_ACCURACY)
            stereo.setExtendedDisparity(False)
            stereo.initialConfig.algorithmControl.enableSwLeftRightCheck = True
            stereo.initialConfig.postProcessing.decimationFilter.decimationFactor = 1
            stereo.initialConfig.postProcessing.spatialFilter.enable = False
            stereo.initialConfig.postProcessing.temporalFilter.enable = False
            stereo.initialConfig.postProcessing.speckleFilter.enable = False
            stereo.initialConfig.setMedianFilter(dai.StereoDepthConfig.MedianFilter.MEDIAN_OFF)
            for socket, destination in [(dai.CameraBoardSocket.CAM_B, stereo.left),
                                         (dai.CameraBoardSocket.CAM_C, stereo.right)]:
                cam = pipeline.create(dai.node.Camera).build(socket,
                            sensorResolution=(1280, 800), sensorFps=FPS)
                cam.requestOutput((1280, 800), type=dai.ImgFrame.Type.GRAY8,
                                  fps=FPS).link(destination)
            align = pipeline.create(dai.node.ImageAlign)
            align.setOutputSize(*SIZE)
            stereo.depth.link(align.input)
            rgb_out.link(align.inputAlignTo)
            sync = pipeline.create(dai.node.Sync)
            sync.setSyncThreshold(timedelta(seconds=MAX_SKEW))
            sync.setSyncAttempts(-1)
            rgb_out.link(sync.inputs['rgb'])
            align.outputAligned.link(sync.inputs['depth'])
            queue = sync.out.createOutputQueue(maxSize=2, blocking=False)
            pipeline.start()
            try:
                time.sleep(5)
                queue.tryGetAll()
                previous = None
                previous_times = None
                previous_k = None
                for index in range(args.frames):
                    group = next_group(queue)
                    rgb_frame, depth_frame = group['rgb'], group['depth']
                    rgb, depth = rgb_frame.getCvFrame(), depth_frame.getCvFrame()
                    rgb_meta, depth_meta = info(rgb_frame), info(depth_frame)
                    k = np.asarray(rgb_frame.getTransformation().getIntrinsicMatrix(), float)
                    depth_k = np.asarray(depth_frame.getTransformation().getIntrinsicMatrix(), float)
                    sequences = (rgb_meta['sequence'], depth_meta['sequence'])
                    times = (rgb_meta['timestamp_device_s'], depth_meta['timestamp_device_s'])
                    metrics = validate_pair(rgb, depth, k, depth_k, *times,
                                            sequences, previous, MAX_SKEW, SIZE)
                    if previous_times and any(t <= old for t, old in zip(times, previous_times)):
                        raise RuntimeError('Device time did not advance')
                    if previous_k is not None and not np.allclose(k, previous_k):
                        raise RuntimeError('RGB-D intrinsics changed during capture')
                    if rgb_frame.getLensPosition() != args.focus:
                        raise RuntimeError('Requested RGB focus not confirmed')
                    age = (dai.Clock.now() - rgb_frame.getTimestamp()).total_seconds()
                    if not -.05 <= age <= 1.:
                        raise RuntimeError('RGB-D frame is stale or host timestamp mapping invalid')
                    stem = f'{index:06d}.png'
                    save(args.output / 'rgb' / stem, rgb)
                    save(args.output / 'depth' / stem, depth)
                    save(args.output / 'valid' / stem, (depth > 0).astype(np.uint8) * 255)
                    report['pairs'].append(dict(index=index, rgb=rgb_meta, depth=depth_meta,
                        rgb_path=f'rgb/{stem}', depth_path=f'depth/{stem}', valid_path=f'valid/{stem}',
                        actual_focus=rgb_frame.getLensPosition(), sdk_rgb_age_s=age,
                        exposure_us=rgb_frame.getExposureTime().total_seconds() * 1e6,
                        reported_iso=rgb_frame.getSensitivity(), **metrics))
                    if index == 0:
                        report['projection'] = dict(K=k.tolist(), depth_K=depth_k.tolist(),
                            size=list(SIZE), D=[0., 0., 0., 0., 0.],
                            source='actual undistorted RGB and ImageAlign frame transformations',
                            coordinate_frame='CAM_A undistorted optical: X right, Y down, Z forward')
                        np.savetxt(args.output / 'cam_K.txt', k)
                        preview(args.output, rgb, depth)
                    previous, previous_times, previous_k = sequences, times, k
                    print(f'RGB-D {index + 1}/{args.frames}: skew={metrics["timestamp_difference_s"] * 1000:.2f}ms', flush=True)
            finally:
                pipeline.stop()
                pipeline.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True)
    parser.add_argument('--device-id', default='')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=8)
    parser.add_argument('--focus', type=int, default=116)
    args = parser.parse_args()
    if not 1 <= args.frames <= 32 or not 0 <= args.focus <= 255:
        parser.error('frames must be 1..32 and focus 0..255')
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / 'metadata.json').exists():
        parser.error('Capture directory already used')
    for name in ('rgb', 'depth', 'valid'):
        (args.output / name).mkdir(exist_ok=True)
    report = dict(schema=1, kind='rgbd', mode='rgbd', success=False, pairs=[],
        started_at=datetime.now().astimezone().isoformat(), camera_ip=args.ip,
        depthai=dai.__version__, requested_frames=args.frames, requested_focus=args.focus,
        requested_fps=FPS, max_timestamp_difference_s=MAX_SKEW,
        geometry='ImageAlign stereo Z-depth reprojected to undistorted RGB CAM_A',
        stereo=dict(preset='FAST_ACCURACY', software_lr=True, native_size=[1280, 800],
                    extended_disparity=False, spatial=False, temporal=False,
                    speckle=False, median=False, decimation=1),
        unit='depth PNG: uint16 millimetres; zero invalid',
        temporal_fusion=False, accuracy_validated=False, alignment_visually_validated=False,
        scene_static='Requested from operator; not independently measured',
        timestamps='device monotonic timestamps; grouping is not simultaneous exposure or UR synchronization',
        standard=dict(path='preview.png'),
        data_files=dict(intrinsics='cam_K.txt', factory='factory-calibration.json'))
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
