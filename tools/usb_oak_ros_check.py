#!/usr/bin/env python3
"""Bounded ROS Image/CameraInfo reception check for a selected USB OAK prefix."""
import argparse
import json
import os
from pathlib import Path
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="/oak_usb")
    parser.add_argument("--seconds", type=float, default=15.)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node("n100_usb_oak_reception_check")
    streams, camera_info, subscriptions, errors = {}, {}, {}, []

    def image_callback(topic, message):
        stamp = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
        now = time.monotonic()
        if message.width <= 0 or message.height <= 0 or len(message.data) != message.step * message.height:
            errors.append(f"Invalid image dimensions/payload: {topic}")
            return
        if topic not in streams:
            streams[topic] = {"frames": 0, "first_host": now, "first_stamp_ns": stamp,
                              "encoding": message.encoding, "width": message.width,
                              "height": message.height, "frame_id": message.header.frame_id,
                              "non_increasing_stamps": 0}
        entry = streams[topic]
        if entry["frames"] and stamp <= entry["last_stamp_ns"]:
            entry["non_increasing_stamps"] += 1
        entry.update(frames=entry["frames"]+1, last_host=now, last_stamp_ns=stamp,
                     step=message.step, payload_bytes=len(message.data))

    def info_callback(topic, message):
        camera_info[topic] = {"width": message.width, "height": message.height,
                              "K": list(message.k), "D": list(message.d),
                              "distortion_model": message.distortion_model,
                              "frame_id": message.header.frame_id}

    started = time.monotonic()
    capture_started = None
    graph = []
    next_graph_scan = 0.
    try:
        while time.monotonic() - started < 45 + args.seconds:
            if time.monotonic() >= next_graph_scan:
                graph = [(topic, types) for topic, types in node.get_topic_names_and_types()
                         if "/_buf_" not in topic]
                next_graph_scan = time.monotonic() + 1.
            for topic, types in graph:
                # Lyrical creates CPU-buffer transport topics for Image subscriptions.
                # Subscribe only to public image topics, never recursively to backends.
                if "/_buf_" in topic:
                    continue
                if not topic.startswith(args.prefix.rstrip("/") + "/") or topic in subscriptions:
                    continue
                if "sensor_msgs/msg/Image" in types:
                    subscriptions[topic] = node.create_subscription(
                        Image, topic, lambda msg, t=topic: image_callback(t, msg), qos_profile_sensor_data)
                elif "sensor_msgs/msg/CameraInfo" in types:
                    subscriptions[topic] = node.create_subscription(
                        CameraInfo, topic, lambda msg, t=topic: info_callback(t, msg), qos_profile_sensor_data)
            rclpy.spin_once(node, timeout_sec=.1)
            if streams and capture_started is None:
                capture_started = time.monotonic()
            if capture_started is not None and time.monotonic() - capture_started >= args.seconds:
                break
    finally:
        node.destroy_node()
        rclpy.shutdown()
    for entry in streams.values():
        elapsed = entry.pop("last_host") - entry.pop("first_host")
        entry["host_received_fps"] = (entry["frames"]-1)/elapsed if elapsed else 0
    colors = [topic for topic, entry in streams.items()
              if entry["encoding"] in ("rgb8", "bgr8", "rgba8", "bgra8") and entry["frames"] >= 5]
    depths = [topic for topic, entry in streams.items()
              if entry["encoding"] in ("16UC1", "32FC1") and entry["frames"] >= 5]
    info_valid = bool(camera_info) and all(
        v["K"][0] > 0 and v["K"][4] > 0 and v["width"] > 0 and v["height"] > 0
        for v in camera_info.values())
    success = bool(colors and depths and info_valid and not errors
                   and not any(e["non_increasing_stamps"] for e in streams.values()))
    result = {"success": success, "scope": "ROS transport and image metadata, not metric calibration",
              "domain": os.getenv("ROS_DOMAIN_ID"),
              "discovery_range": os.getenv("ROS_AUTOMATIC_DISCOVERY_RANGE"),
              "elapsed_s": time.monotonic()-started, "streams": streams,
              "camera_info": camera_info, "color_topics": colors, "depth_topics": depths,
              "camera_info_valid": info_valid, "errors": errors,
              "graph": graph}
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
