#!/usr/bin/env python3
"""Bounded OAK live preview owned by UWA Camera Capture, sharing the photo lock."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import time

import cv2
import depthai as dai


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ip', required=True)
    p.add_argument('--device-id', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--lock', type=Path, required=True)
    p.add_argument('--focus', type=int, required=True, choices=range(256))
    p.add_argument('--fps',type=float,default=2.)
    p.add_argument('--width',type=int,default=2000)
    p.add_argument('--height',type=int,default=1500)
    p.add_argument('--tracking-metadata',action='store_true')
    args = p.parse_args()
    if not (0<args.fps<=10 and 320<=args.width<=2000 and args.height*4==args.width*3):
        raise ValueError('Preview requires full4:3 size, width320..2000 and outputfps<=10')
    args.output.mkdir(parents=True, exist_ok=True)
    running = [True]
    signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))
    signal.signal(signal.SIGINT, lambda *_: running.__setitem__(0, False))
    with args.lock.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with dai.Device(dai.DeviceInfo(args.ip)) as device:
            device.setMaxReconnectionAttempts(0)
            if device.getDeviceId() != args.device_id:
                raise RuntimeError('OAK device ID differs from inventory')
            distortion=device.readCalibration().getDistortionCoefficients(dai.CameraBoardSocket.CAM_A) if args.tracking_metadata else None
            with dai.Pipeline(device) as pipeline:
                cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A,
                                      sensorResolution=(8000, 6000), sensorFps=10)
                cam.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                cam.initialControl.setManualFocus(args.focus)
                cam.initialControl.setAutoExposureEnable()
                output = cam.requestOutput((args.width,args.height), type=dai.ImgFrame.Type.NV12,
                    fps=args.fps,enableUndistortion=False if args.tracking_metadata else None)
                queue = output.createOutputQueue(maxSize=1, blocking=False)
                pipeline.start()
                warmed_at = time.monotonic() + 5
                try:
                    while running[0] and pipeline.isRunning():
                        frame = queue.tryGet()
                        if frame is None:
                            time.sleep(.03)
                            continue
                        if time.monotonic() < warmed_at:
                            continue
                        image = frame.getCvFrame()
                        data = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
                        # Atomic single file pairs image + metadata without a reader race.
                        metadata=dict(received=time.time(), sequence=frame.getSequenceNum(),
                            device_timestamp_s=frame.getTimestampDevice().total_seconds(),
                            lens_position=frame.getLensPosition(), size=[frame.getWidth(), frame.getHeight()],
                            exposure_us=frame.getExposureTime().total_seconds() * 1e6,
                            reported_iso=frame.getSensitivity(),
                            source='live SDK preview; full 4:3 sensor field')
                        if args.tracking_metadata:
                            latency=(dai.Clock.now()-frame.getTimestamp()).total_seconds()
                            if latency<-.05 or latency>1.:
                                raise RuntimeError('SDK frame is stale or timestamp mapping invalid')
                            metadata.update(K=frame.getTransformation().getIntrinsicMatrix(),D=distortion,
                                sdk_frame_age_s=latency,rectified=False,
                                timestamp_semantics='SDK host-synchronized image timestamp mapped by measured receive age; device timestamp retained',
                                output_fps_requested=args.fps,focus_profile='manual'+str(args.focus))
                        header=json.dumps(metadata).encode()
                        temporary = args.output / 'frame.tmp'
                        temporary.write_bytes(header + b'\n' + data)
                        os.replace(temporary, args.output / 'frame.bin')
                finally:
                    pipeline.stop()
                    pipeline.wait()


if __name__ == '__main__':
    main()
