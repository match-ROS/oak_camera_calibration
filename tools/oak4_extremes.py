#!/usr/bin/env python3
"""Standalone Ethernet OAK4 live view and repeatable sensor/host-rate tests."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import time

import cv2
import depthai as dai
import numpy as np


PROFILES = {
    'rgb_preview': dict(kind='rgb', sensor=(1920, 1080), sensor_fps=30, size=(1280, 720), fps=30),
    'rgb_full': dict(kind='rgb', sensor=(8000, 6000), sensor_fps=18, size=(8000, 6000), fps=4),
    'rgb_fast': dict(kind='rgb', sensor=(1280, 720), sensor_fps=480, size=(320, 180), fps=480),
    'rgb_1080_fast': dict(kind='rgb', sensor=(1920, 1080), sensor_fps=240, size=(640, 360), fps=240),
    'depth_quality': dict(kind='depth', sensor=(1280, 800), sensor_fps=30,
                          size=(1280, 800), fps=30, preset='ACCURACY'),
    'depth_detail': dict(kind='depth', sensor=(1280, 800), sensor_fps=30,
                         size=(1280, 800), fps=30, preset='HIGH_DETAIL', extended=True),
    'depth_neural_quality': dict(kind='depth', sensor=(1280, 800), sensor_fps=30,
                                 size=(1248, 780), fps=30, model='NEURAL_DEPTH_EXTRA_LARGE'),
    'depth_fast': dict(kind='depth', sensor=(1280, 800), sensor_fps=60,
                       size=(640, 400), fps=60, preset='FAST_DENSITY'),
    'depth_full_fast': dict(kind='depth', sensor=(1280, 800), sensor_fps=60,
                            size=(1280, 800), fps=60, preset='FAST_DENSITY'),
}


def sensor_info(device):
    result = []
    for sensor in device.getConnectedCameraFeatures():
        result.append(dict(socket=str(sensor.socket), name=sensor.sensorName,
            full_size=[sensor.width, sensor.height], autofocus=sensor.hasAutofocus,
            modes=[{key: getattr(mode, key) for key in
                    ('width', 'height', 'minFps', 'maxFps', 'hdr', 'hfr')}
                   for mode in sensor.configs]))
    return result


def build(pipeline, profile):
    if profile['kind'] == 'rgb':
        camera = pipeline.create(dai.node.Camera).build(
            dai.CameraBoardSocket.CAM_A, sensorResolution=profile['sensor'],
            sensorFps=profile['sensor_fps'])
        camera.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.CONTINUOUS_VIDEO)
        output = camera.requestOutput(profile['size'], type=dai.ImgFrame.Type.NV12,
                                      fps=profile['fps'])
        return output.createOutputQueue(maxSize=2, blocking=False), {}
    left = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B,
        sensorResolution=profile['sensor'], sensorFps=profile['sensor_fps'])
    right = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C,
        sensorResolution=profile['sensor'], sensorFps=profile['sensor_fps'])
    lo = left.requestOutput(profile['size'], type=dai.ImgFrame.Type.GRAY8, fps=profile['fps'])
    ro = right.requestOutput(profile['size'], type=dai.ImgFrame.Type.GRAY8, fps=profile['fps'])
    if 'model' in profile:
        neural = pipeline.create(dai.node.NeuralDepth).build(
            lo, ro, getattr(dai.DeviceModelZoo, profile['model']))
        neural.initialConfig.setConfidenceThreshold(125)
        neural.initialConfig.setEdgeThreshold(10)
        neural.initialConfig.postProcessing.temporalFilter.enable = True
        return neural.depth.createOutputQueue(maxSize=2, blocking=False), dict(
            model=profile['model'], confidence_threshold=125, edge_threshold=10,
            temporal_filter=True, note='Learned stereo; not a metrological accuracy guarantee')
    stereo = pipeline.create(dai.node.StereoDepth)
    stereo.setDefaultProfilePreset(getattr(dai.node.StereoDepth.PresetMode, profile['preset']))
    lo.link(stereo.left); ro.link(stereo.right)
    config = stereo.initialConfig
    config.postProcessing.decimationFilter.decimationFactor = 1
    quality = profile['preset'] in ('ACCURACY', 'HIGH_DETAIL')
    stereo.setExtendedDisparity(profile.get('extended', False))
    config.algorithmControl.enableSwLeftRightCheck = quality
    config.postProcessing.spatialFilter.enable = quality
    config.postProcessing.temporalFilter.enable = quality
    config.postProcessing.speckleFilter.enable = quality
    config.setMedianFilter(dai.StereoDepthConfig.MedianFilter.KERNEL_5x5 if quality
                          else dai.StereoDepthConfig.MedianFilter.MEDIAN_OFF)
    details = dict(preset=profile['preset'], software_lr_check=quality,
        spatial_filter=quality, temporal_filter=quality, speckle_filter=quality,
        median_filter='5x5' if quality else 'off', decimation=1,
        extended_disparity=profile.get('extended', False),
        subpixel_bits=4, note='RVC4 subpixel is fixed in hardware')
    return stereo.depth.createOutputQueue(maxSize=2, blocking=False), details


def visualize(message, kind):
    frame = message.getCvFrame()
    if kind == 'depth':
        # Fixed 0..5m display scale; original uint16 millimetres are kept in snapshots.
        preview = cv2.applyColorMap(np.uint8(np.clip(frame, 0, 5000) * (255 / 5000)), cv2.COLORMAP_TURBO)
        preview[frame == 0] = 0
    else:
        preview = frame
    factor = min(1.0, 1100 / preview.shape[1], 780 / preview.shape[0])
    if factor < 1:
        preview = cv2.resize(preview, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    return frame, preview


def run(args):
    # OpenCV's wheel sets a bundled Qt font path that is absent on this build.
    # Set it after importing cv2, which otherwise overwrites the launcher value.
    system_fonts = Path('/usr/share/fonts/truetype/dejavu')
    if args.preview and system_fonts.is_dir():
        os.environ['QT_QPA_FONTDIR'] = str(system_fonts)
    stopping = False

    def stop_requested(signum, frame):
        nonlocal stopping
        stopping = True

    previous_handler = signal.signal(signal.SIGINT, stop_requested)
    profile = dict(PROFILES[args.profile])
    if args.fps is not None:
        profile['fps'] = args.fps
    args.output.mkdir(parents=True, exist_ok=True)
    result = dict(profile=args.profile, requested=profile, ip=args.ip,
        timestamp_utc=datetime.now(timezone.utc).isoformat(), depthai=dai.__version__,
        opencv=cv2.__version__, success=False)
    started = time.monotonic()
    try:
        with dai.Device(dai.DeviceInfo(args.ip)) as device:
            result['device_name'] = device.getDeviceName()
            result['platform'] = str(device.getPlatform())
            result['sensors'] = sensor_info(device)
            with dai.Pipeline(device) as pipeline:
                queue, details = build(pipeline, profile)
                result['processing'] = details
                print(json.dumps({'starting': args.profile, 'requested': profile}), flush=True)
                pipeline.start()
                first_deadline = time.monotonic() + 35
                host_times, device_times, sequences, bytes_received = [], [], [], 0
                first_seen, measurement_start, last_preview, last_report = None, None, 0., 0.
                last_received = time.monotonic()
                last = None
                title = 'UWA OAK4 Ethernet - ' + args.profile + ' (Q / Esc: close)'
                if args.preview:
                    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(title, 1100, 740)
                while pipeline.isRunning() and not stopping:
                    batch = queue.tryGetAll()
                    now = time.monotonic()
                    if not batch:
                        if first_seen is None and now > first_deadline:
                            raise TimeoutError('No image received within 35 seconds')
                        if first_seen is not None and now - last_received > 20:
                            raise TimeoutError('Image stream stalled for more than 20 seconds')
                        if measurement_start and args.seconds and now - measurement_start >= args.seconds:
                            break
                        if args.preview and cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                            break
                        time.sleep(.001)
                        continue
                    if first_seen is None:
                        first_seen = now
                    last_received = now
                    for message in batch:
                        last = message
                        if now - first_seen >= args.warmup:
                            if measurement_start is None:
                                measurement_start = now
                            host_times.append(time.monotonic())
                            device_times.append(message.getTimestampDevice().total_seconds())
                            sequences.append(message.getSequenceNum())
                            bytes_received += message.getData().nbytes
                    elapsed = now - measurement_start if measurement_start else 0.
                    fps = ((len(host_times) - 1) / (host_times[-1] - host_times[0])
                           if len(host_times) > 1 and host_times[-1] > host_times[0] else 0.)
                    if args.preview and now - last_preview >= 1 / 15:
                        _, preview = visualize(last, profile['kind'])
                        cv2.putText(preview, f'{args.profile}  {last.getWidth()}x{last.getHeight()}  host {fps:.1f} fps',
                                    (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 2)
                        cv2.imshow(title, preview)
                        last_preview = now
                    if args.preview and cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                        break
                    if args.preview and last_preview and cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                        break
                    if now - last_report > 5:
                        print(f'{args.profile}: {len(host_times)} measured frames, host {fps:.2f} fps', flush=True)
                        last_report = now
                    if args.seconds and elapsed >= args.seconds:
                        break
                if len(host_times) < 2:
                    raise RuntimeError('Not enough measured frames')
                elapsed = host_times[-1] - host_times[0]
                device_elapsed = device_times[-1] - device_times[0]
                frame, preview = visualize(last, profile['kind'])
                result.update(success=True, measured_frames=len(host_times), measurement_elapsed_s=elapsed,
                    received_fps=(len(host_times) - 1) / elapsed,
                    device_sequence_rate=(sequences[-1] - sequences[0]) / device_elapsed if device_elapsed > 0 else None,
                    delivered_sequence_gaps=int(sum(max(0, b-a-1) for a,b in zip(sequences,sequences[1:]))),
                    payload_MB_per_second=bytes_received/elapsed/1e6,
                    actual_size=[last.getWidth(), last.getHeight()], frame_type=str(last.getType()),
                    first_frame_latency_s=first_seen-started)
                if profile['kind'] == 'depth':
                    valid=frame[frame>0]
                    result['depth'] = dict(valid_fraction=float(np.mean(frame>0)),
                        percentiles_mm=np.percentile(valid,[5,50,95]).tolist() if len(valid) else [],
                        unit='millimetres', accuracy_note='No metrological ground-truth target in this test')
                cv2.imwrite(str(args.output/(args.profile+'-sample.png')), frame)
                cv2.imwrite(str(args.output/(args.profile+'-preview.jpg')), preview)
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    finally:
        signal.signal(signal.SIGINT, previous_handler)
        if args.preview:
            cv2.destroyAllWindows()
        (args.output/(args.profile+'.json')).write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='sensors'},indent=2),flush=True)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip',default='192.168.8.238')
    parser.add_argument('--profile',choices=PROFILES,default='rgb_preview')
    parser.add_argument('--seconds',type=float,default=15,help='Measurement duration; 0 = continuous')
    parser.add_argument('--warmup',type=float,default=3)
    parser.add_argument('--fps',type=float,help='Override output rate, not sensor rate')
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--output',type=Path,default=Path.home()/'UWA_ws/setup/oak4/measurements')
    raise SystemExit(run(parser.parse_args()))
