#!/usr/bin/env python3
"""Bounded, USB-only OAK/RVC2 RGB/stereo smoke test; no calibration writes."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import traceback

os.environ.setdefault("DEPTHAI_PROTOCOL", "usb")
os.environ.setdefault("DEPTHAI_TELEMETRY", "0")

import cv2
import depthai as dai
import numpy as np


def calibration_bytes(device):
    return json.dumps(device.readCalibration().eepromToJson(), sort_keys=True, indent=2).encode()


def sensor_report(feature):
    return {
        "socket": str(feature.socket), "sensor": feature.sensorName,
        "native_size": [feature.width, feature.height],
        "autofocus": feature.hasAutofocus,
    }


def run(args, report):
    devices = [d for d in dai.Device.getAllAvailableDevices()
               if "USB" in str(d.protocol)]
    report["available_usb_devices"] = [str(d) for d in devices]
    if args.device_id:
        devices = [d for d in devices if d.getDeviceId() == args.device_id]
    if len(devices) != 1:
        raise RuntimeError(f"Expected exactly one selected USB device, found {len(devices)}")
    with dai.Device(devices[0]) as device:
        device.setMaxReconnectionAttempts(0)
        if device.getPlatform() != dai.Platform.RVC2:
            raise RuntimeError("This USB check is intended for RVC2, not the Ethernet OAK4")
        features = device.getConnectedCameraFeatures()
        report.update(device_id=device.getDeviceId(), name=device.getDeviceName(),
                      platform=str(device.getPlatform()), usb_speed=str(device.getUsbSpeed()),
                      sensors=[sensor_report(f) for f in features])
        factory = calibration_bytes(device)
        (args.output / "factory-calibration.json").write_bytes(factory)
        report["factory_sha256_before"] = hashlib.sha256(factory).hexdigest()
        eeprom = json.loads(factory)
        report["product_name"] = eeprom.get("productName")
        report["board_name"] = eeprom.get("boardName")
        report["board_revision"] = eeprom.get("boardRev")
        sockets = {f.socket for f in features}
        if dai.CameraBoardSocket.CAM_A not in sockets:
            raise RuntimeError("No CAM_A sensor found")
        stereo_available = {dai.CameraBoardSocket.CAM_B, dai.CameraBoardSocket.CAM_C} <= sockets
        report["stereo_available"] = stereo_available
        with dai.Pipeline(device) as pipeline:
            rgb = pipeline.create(dai.node.Camera).build(
                dai.CameraBoardSocket.CAM_A, sensorFps=args.fps)
            queues = {"rgb": rgb.requestOutput(
                (640, 480), type=dai.ImgFrame.Type.NV12, fps=args.fps
            ).createOutputQueue(maxSize=4, blocking=False)}
            if stereo_available:
                mono_outputs = {}
                for label, socket in (("left", dai.CameraBoardSocket.CAM_B),
                                      ("right", dai.CameraBoardSocket.CAM_C)):
                    camera = pipeline.create(dai.node.Camera).build(socket, sensorFps=args.fps)
                    output = camera.requestOutput((640, 400), type=dai.ImgFrame.Type.GRAY8,
                                                  fps=args.fps)
                    mono_outputs[label] = output
                    queues[label] = output.createOutputQueue(maxSize=4, blocking=False)
                stereo = pipeline.create(dai.node.StereoDepth)
                stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.FAST_ACCURACY)
                stereo.setLeftRightCheck(True)
                mono_outputs["left"].link(stereo.left)
                mono_outputs["right"].link(stereo.right)
                queues["depth"] = stereo.depth.createOutputQueue(maxSize=4, blocking=False)
            samples = {name: [] for name in queues}
            last_frames = {}
            pipeline.start()
            started = time.monotonic()
            deadline = started + args.seconds
            try:
                while time.monotonic() < deadline and pipeline.isRunning():
                    for name, queue in queues.items():
                        frame = queue.tryGet()
                        if frame is None:
                            continue
                        sequence = int(frame.getSequenceNum())
                        device_time = frame.getTimestampDevice().total_seconds()
                        if samples[name] and (sequence <= samples[name][-1][1]
                                              or device_time <= samples[name][-1][2]):
                            raise RuntimeError(f"Non-increasing frame sequence/time: {name}")
                        array = frame.getCvFrame()
                        if array.size == 0:
                            raise RuntimeError(f"Empty frame: {name}")
                        samples[name].append((time.monotonic(), sequence, device_time))
                        last_frames[name] = array
                    time.sleep(.002)
                # Pipeline owns the supplied Device and closes it on context exit.
                after = calibration_bytes(device)
                report["factory_sha256_after"] = hashlib.sha256(after).hexdigest()
                if report["factory_sha256_before"] != report["factory_sha256_after"]:
                    raise RuntimeError("Factory calibration changed unexpectedly")
            finally:
                pipeline.stop()
            report["capture_wall_s"] = time.monotonic() - started
            streams = {}
            for name, values in samples.items():
                if len(values) < 5:
                    raise RuntimeError(f"Only {len(values)} frames received from {name}")
                array = last_frames[name]
                streams[name] = {
                    "frames": len(values), "shape": list(array.shape), "dtype": str(array.dtype),
                    "host_received_fps": (len(values)-1)/(values[-1][0]-values[0][0]),
                    "device_frame_fps": (values[-1][1]-values[0][1])/(values[-1][2]-values[0][2]),
                    "sequence_gaps": values[-1][1]-values[0][1]+1-len(values),
                    "first_device_time_s": values[0][2], "last_device_time_s": values[-1][2],
                }
                if name == "depth":
                    valid = array > 0
                    streams[name]["valid_fraction"] = float(np.mean(valid))
                    if np.any(valid):
                        streams[name]["valid_depth_median_mm"] = float(np.median(array[valid]))
                    preview = cv2.applyColorMap(
                        np.clip(array / 5000 * 255, 0, 255).astype(np.uint8), cv2.COLORMAP_TURBO)
                    preview[~valid] = 0
                    if not cv2.imwrite(str(args.output / "depth-preview.png"), preview):
                        raise RuntimeError("Depth preview write failed")
                if not cv2.imwrite(str(args.output / f"{name}.png"), array):
                    raise RuntimeError(f"Frame write failed: {name}")
            report["streams"] = streams
    report["camera_closed"] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id")
    parser.add_argument("--seconds", type=float, default=15.)
    parser.add_argument("--fps", type=float, default=10.)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 2 <= args.seconds <= 120 or not 1 <= args.fps <= 30:
        parser.error("Use 2..120 seconds and 1..30 fps")
    args.output.mkdir(parents=True, exist_ok=False)
    lock_path = Path.home() / "uwa-camera" / ".camera.lock"
    lock_path.parent.mkdir(exist_ok=True)
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "success": False,
              "sdk_version": dai.__version__, "opencv_version": cv2.__version__,
              "requested_fps": args.fps, "requested_seconds": args.seconds,
              "scope": "USB-only functionality; no metric accuracy or calibration validation"}
    try:
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(args, report)
        report["success"] = True
    except Exception as exc:
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
