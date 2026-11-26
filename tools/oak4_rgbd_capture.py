#!/usr/bin/env python3
"""Bounded RVC4 RGB-D capture. Invoke through the shared photo transaction."""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import signal
import time

os.environ.setdefault('DEPTHAI_TELEMETRY', '0')
import cv2
import depthai as dai
import numpy as np
from oak4_depth_capture import acquire_hdr as acquire_stereo_hdr, projection as depth_projection, projector
from oak4_depth_fusion import fuse_brackets
from oak4_hdr import bracket_plan, fuse, verify_exposure
from oak4_rgbd_geometry import validate_pair

SIZE = (1280, 960)
FPS = 10
MAX_SKEW = .025
HDR_ISO = 400
RGB_FRAME = 'CAM_A undistorted optical: X right, Y down, Z forward'


def save(path, image):
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f'Cannot save {path}')


def info(frame):
    return dict(sequence=int(frame.getSequenceNum()),
                timestamp_device_s=frame.getTimestampDevice().total_seconds())


def next_group(queue, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        group = queue.tryGet()
        if group is not None:
            return group
        time.sleep(.005)
    raise TimeoutError('No synchronized RGB-D pair before deadline')


def preview(output, rgb, depth, rgb_label='RGB - undistorted'):
    color = cv2.applyColorMap(np.clip(depth / 6000 * 255, 0, 255).astype(np.uint8),
                             cv2.COLORMAP_TURBO)
    color[depth == 0] = 0
    blend = rgb.copy()
    valid = depth > 0
    blend[valid] = cv2.addWeighted(rgb, .5, color, .5, 0)[valid]
    canvas = np.zeros((540, 1920, 3), np.uint8)
    for index, (label, image) in enumerate([
        (rgb_label, rgb), ('Depth - RGB perspective', color),
        ('Overlay - inspect edges', blend),
    ]):
        x = 640 * index
        cv2.putText(canvas, label, (x + 12, 32), cv2.FONT_HERSHEY_SIMPLEX,
                    .65, (255, 255, 255), 2)
        canvas[45:525, x:x + 640] = cv2.resize(image, (640, 480), interpolation=cv2.INTER_NEAREST)
    save(output / 'preview.png', canvas)


def rgb_settings(frame):
    return dict(exposure_us=round(frame.getExposureTime().total_seconds() * 1e6),
                reported_iso=frame.getSensitivity(), lens_position=frame.getLensPosition(),
                white_balance_K=frame.getColorTemperature())


def capture_hdr(queue, control, output, projection, focus, previous, frames_per_exposure=1):
    reference = rgb_settings(next_group(queue)['rgb'])
    if reference['lens_position'] != focus or reference['white_balance_K'] <= 0:
        raise RuntimeError('RGB-HDR focus or white balance not confirmed')
    plan = bracket_plan(reference['exposure_us'] * reference['reported_iso'], HDR_ISO)
    k = np.asarray(projection['K'])
    brackets, images = [], []
    for step in plan:
        message = dai.CameraControl()
        message.setManualExposure(step['exposure_us'], HDR_ISO)
        message.setManualWhiteBalance(reference['white_balance_K'])
        message.setManualFocus(focus)
        queue.tryGetAll()
        control.send(message)
        after = dai.Clock.now()
        deadline = time.monotonic() + 9
        samples, colors = [], []
        while len(colors) < frames_per_exposure:
            group = next_group(queue, timeout=max(.001, deadline - time.monotonic()))
            rgb_frame, depth_frame = group['rgb'], group['depth']
            if time.monotonic() >= deadline:
                raise TimeoutError(f"RGB-HDR {step['name']} exposure did not complete")
            settings = rgb_settings(rgb_frame)
            if (rgb_frame.getSequenceNum() <= previous[0] or depth_frame.getSequenceNum() <= previous[1]
                    or rgb_frame.getTimestamp() <= after):
                continue
            try:
                verify_exposure(settings, step['exposure_us'], HDR_ISO, reference)
            except RuntimeError:
                continue
            rgb, depth = rgb_frame.getCvFrame(), depth_frame.getCvFrame()
            rgb_info, depth_info = info(rgb_frame), info(depth_frame)
            actual_k = np.asarray(rgb_frame.getTransformation().getIntrinsicMatrix())
            depth_k = np.asarray(depth_frame.getTransformation().getIntrinsicMatrix())
            if not np.allclose(actual_k, k):
                raise RuntimeError('RGB-HDR projection differs from RGB-D projection')
            sequences = rgb_info['sequence'], depth_info['sequence']
            metrics = validate_pair(rgb, depth, actual_k, depth_k, rgb_info['timestamp_device_s'],
                                    depth_info['timestamp_device_s'], sequences, previous, MAX_SKEW, SIZE)
            previous = sequences
            if samples and settings['exposure_us'] != samples[0]['exposure_us']:
                raise RuntimeError('RGB-HDR exposure changed during averaging')
            samples.append(dict(**settings, rgb=rgb_info, depth=depth_info, **metrics))
            colors.append(rgb)
            if step['name'] == 'base' and len(colors) == 1:
                base_depth = depth
        path = f"hdr-{step['name']}.png"
        average = np.rint(np.mean(colors, axis=0, dtype=np.float32)).astype(np.uint8) if len(colors) > 1 else colors[0]
        save(output / path, average)
        images.append(average)
        brackets.append(dict(name=step['name'], target_ev=step['target_ev'], path=path,
                             requested_exposure_us=step['exposure_us'], **samples[0], frames=samples))
    save(output / 'hdr-base-depth-mm.png', base_depth)
    return images, base_depth, dict(path='hdr.png', depth_path='hdr-base-depth-mm.png',
                                    method='OpenCV Mertens exposure fusion',
                                    reference_bracket='base', metering=reference, brackets=brackets)


def capture_quality(device, args, queue, rgb_control, mono_controls, report):
    stereo = dict(frames=[], timing_s={})
    def aligned_projection(frame):
        result = depth_projection(frame, coordinate_frame=RGB_FRAME)
        if (result['reference_camera_socket'] != str(dai.CameraBoardSocket.CAM_A)
                or result['size'] != list(SIZE)):
            raise RuntimeError('Stereo HDR depth is not in the expected aligned RGB frame')
        return result

    try:
        raw, _, _ = acquire_stereo_hdr(device, mono_controls, queue, stereo, size=SIZE,
                                       projection_for_frame=aligned_projection)
    finally:
        projector(device, 0.)
        stereo['projector_off_confirmed_by_sdk'] = True
    k = stereo['projection']['K']
    report['projection'] = dict(K=k, depth_K=k, size=list(SIZE), D=[0.] * 5,
        source='actual undistorted RGB and ImageAlign frame transformations',
        coordinate_frame=RGB_FRAME)
    report['depth_hdr'] = stereo
    images, _, report['hdr'] = capture_hdr(queue, rgb_control, args.output, report['projection'],
                                          args.focus, (-1, -1), frames_per_exposure=args.frames)
    return raw, images


def finish_quality(args, report, raw, images):
    hdr = fuse(images)
    quality = fuse_brackets(raw)
    if not quality['stable'].any():
        raise RuntimeError('Stereo HDR found no stable depth pixels')
    depth = quality['hq']
    save(args.output / 'hdr.png', hdr)
    save(args.output / 'hq-depth-mm.png', depth)
    save(args.output / 'hq-valid-mask.png', quality['stable'].astype(np.uint8) * 255)
    np.savez(args.output / 'depth-brackets.npz', raw_depth_mm=raw, **quality)
    np.savetxt(args.output / 'cam_K.txt', report['projection']['K'])
    report['hq'] = dict(path='hq-depth-mm.png', depth_path='hq-depth-mm.png', rgb_path='hdr.png',
                        valid_path='hq-valid-mask.png', actual_focus=args.focus, index=0,
                        sample_kind='static_rgb_stereo_hdr',
                        valid_depth_fraction=float(quality['stable'].mean()))
    report['data_files'].update(depth_brackets='depth-brackets.npz', valid='hq-valid-mask.png')
    preview(args.output, hdr, depth, rgb_label='RGB HQ HDR - undistorted')


def acquire(args, report):
    with dai.Device(dai.DeviceInfo(args.ip)) as device:
        device.setMaxReconnectionAttempts(0)
        report['device_id'] = device.getDeviceId()
        if args.device_id and report['device_id'] != args.device_id:
            raise RuntimeError('OAK identity differs from inventory')
        if device.getPlatform() != dai.Platform.RVC4:
            raise RuntimeError('This capture profile requires RVC4')
        if args.hq and device.getProductName() != 'OAK-4-PRO-AF':
            raise RuntimeError('Aligned Stereo HDR requires the OAK4 Pro projector')
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
            rgb_control = rgb_cam.inputControl.createInputQueue() if args.hdr or args.hq else None
            stereo = pipeline.create(dai.node.StereoDepth)
            stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.FAST_ACCURACY)
            stereo.setExtendedDisparity(False)
            stereo.initialConfig.algorithmControl.enableSwLeftRightCheck = True
            stereo.initialConfig.postProcessing.decimationFilter.decimationFactor = 1
            stereo.initialConfig.postProcessing.spatialFilter.enable = False
            stereo.initialConfig.postProcessing.temporalFilter.enable = False
            stereo.initialConfig.postProcessing.speckleFilter.enable = False
            stereo.initialConfig.setMedianFilter(dai.StereoDepthConfig.MedianFilter.MEDIAN_OFF)
            sync = pipeline.create(dai.node.Sync)
            sync.setSyncThreshold(timedelta(seconds=MAX_SKEW))
            sync.setSyncAttempts(-1)
            mono_controls = []
            for name, socket, destination in [('left', dai.CameraBoardSocket.CAM_B, stereo.left),
                                               ('right', dai.CameraBoardSocket.CAM_C, stereo.right)]:
                cam = pipeline.create(dai.node.Camera).build(socket,
                            sensorResolution=(1280, 800), sensorFps=FPS)
                mono = cam.requestOutput((1280, 800), type=dai.ImgFrame.Type.GRAY8, fps=FPS)
                mono.link(destination)
                if args.hq:
                    mono.link(sync.inputs[name])
                    mono_controls.append(cam.inputControl.createInputQueue())
            align = pipeline.create(dai.node.ImageAlign)
            align.setOutputSize(*SIZE)
            stereo.depth.link(align.input)
            rgb_out.link(align.inputAlignTo)
            rgb_out.link(sync.inputs['rgb'])
            align.outputAligned.link(sync.inputs['depth'])
            queue = sync.out.createOutputQueue(maxSize=2, blocking=False)
            pipeline.start()
            if args.hq:
                try:
                    return capture_quality(device, args, queue, rgb_control, mono_controls, report)
                finally:
                    pipeline.stop()
                    pipeline.wait()
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
                            coordinate_frame=RGB_FRAME)
                        np.savetxt(args.output / 'cam_K.txt', k)
                        if not args.hdr:
                            preview(args.output, rgb, depth)
                    previous, previous_times, previous_k = sequences, times, k
                    print(f'RGB-D {index + 1}/{args.frames}: skew={metrics["timestamp_difference_s"] * 1000:.2f}ms', flush=True)
                if args.hdr:
                    hdr_images, base_depth, report['hdr'] = capture_hdr(
                        queue, rgb_control, args.output, report['projection'], args.focus, previous)
            finally:
                pipeline.stop()
                pipeline.wait()
    if args.hdr:
        hdr = fuse(hdr_images)
        save(args.output / report['hdr']['path'], hdr)
        preview(args.output, hdr, base_depth, rgb_label='RGB HDR - undistorted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True)
    parser.add_argument('--device-id', default='')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int)
    parser.add_argument('--focus', type=int, default=116)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--hdr', action='store_true')
    modes.add_argument('--hq', action='store_true')
    args = parser.parse_args()
    if args.frames is None:
        args.frames = 6 if args.hq else 8
    if not 1 <= args.frames <= 32 or not 0 <= args.focus <= 255:
        parser.error('frames must be 1..32 and focus 0..255')
    if args.hq and args.frames != 6:
        parser.error('RGB-D HQ uses six color frames per exposure')
    if args.hq:
        def terminate(_signum, _frame):
            raise InterruptedError('RGB-D HQ capture was cancelled')

        signal.signal(signal.SIGTERM, terminate)
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / 'metadata.json').exists():
        parser.error('Capture directory already used')
    if not args.hq:
        for name in ('rgb', 'depth', 'valid'):
            (args.output / name).mkdir(exist_ok=True)
    mode = 'rgbd_hq' if args.hq else 'rgbd_hdr' if args.hdr else 'rgbd'
    report = dict(schema=1, kind='rgbd', mode=mode, success=False, pairs=[],
        started_at=datetime.now().astimezone().isoformat(), camera_ip=args.ip,
        depthai=dai.__version__, requested_frames=args.frames, requested_focus=args.focus,
        requested_fps=FPS, max_timestamp_difference_s=MAX_SKEW,
        geometry='ImageAlign stereo Z-depth reprojected to undistorted RGB CAM_A',
        stereo=dict(preset='FAST_ACCURACY', software_lr=True, native_size=[1280, 800],
                    extended_disparity=False, spatial=False, temporal=False,
                    speckle=False, median=False, decimation=1),
        unit='depth PNG: uint16 millimetres; zero invalid',
        temporal_fusion=args.hq, accuracy_validated=False, alignment_visually_validated=False,
        scene_static='Requested from operator; not independently measured',
        timestamps='device monotonic timestamps; grouping is not simultaneous exposure or UR synchronization',
        standard=dict(path='preview.png'),
        data_files=dict(intrinsics='cam_K.txt', factory='factory-calibration.json'))
    try:
        captured = acquire(args, report)
        if args.hq:
            finish_quality(args, report, *captured)
        report['success'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['finished_at'] = datetime.now().astimezone().isoformat()
        (args.output / 'metadata.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
