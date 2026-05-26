#!/usr/bin/env python3
import os
import time
from datetime import datetime

import cv2
import numpy as np
import rclpy
import yaml
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image


class OakSnapshot(Node):
    def __init__(self):
        super().__init__("oak_snapshot")

        self.declare_parameter("image_topic", "/oak/rgb/image_raw")
        self.declare_parameter("camera_info_topic", "/oak/rgb/camera_info")
        self.declare_parameter("output_dir", "~/oak_handeye_samples")
        self.declare_parameter("prefix", "oak")
        self.declare_parameter("save_rectified", True)
        self.declare_parameter("timeout_sec", 10.0)

        self.bridge = CvBridge()
        self.image_msg = None
        self.camera_info_msg = None

        qos = QoSProfile(depth=1)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT

        image_topic = self.get_parameter("image_topic").value
        camera_info_topic = self.get_parameter("camera_info_topic").value

        self.create_subscription(Image, image_topic, self._on_image, qos)
        self.create_subscription(CameraInfo, camera_info_topic, self._on_camera_info, qos)

        self.get_logger().info(f"Waiting for image on {image_topic}")
        self.get_logger().info(f"Waiting for CameraInfo on {camera_info_topic}")

    def _on_image(self, msg):
        self.image_msg = msg

    def _on_camera_info(self, msg):
        self.camera_info_msg = msg

    def ready(self):
        return self.image_msg is not None and self.camera_info_msg is not None

    def save(self):
        output_dir = os.path.expanduser(self.get_parameter("output_dir").value)
        prefix = self.get_parameter("prefix").value
        save_rectified = bool(self.get_parameter("save_rectified").value)
        os.makedirs(output_dir, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_path = os.path.join(output_dir, f"{prefix}_{stamp}")

        image = self.bridge.imgmsg_to_cv2(self.image_msg, desired_encoding="bgr8")
        camera_info = self.camera_info_msg

        raw_path = base_path + "_raw.png"
        info_path = base_path + "_camera_info.yaml"

        cv2.imwrite(raw_path, image)
        self._write_camera_info(info_path, camera_info)

        self.get_logger().info(f"Saved raw image: {raw_path}")
        self.get_logger().info(f"Saved CameraInfo: {info_path}")

        if save_rectified:
            rectified = self._rectify(image, camera_info)
            rectified_path = base_path + "_rectified.png"
            cv2.imwrite(rectified_path, rectified)
            self.get_logger().info(f"Saved rectified image: {rectified_path}")

    def _rectify(self, image, camera_info):
        k = np.array(camera_info.k, dtype=np.float64).reshape(3, 3)
        d = np.array(camera_info.d, dtype=np.float64)

        if d.size == 0 or np.allclose(d, 0.0):
            self.get_logger().info("CameraInfo has no distortion; rectified image equals raw image.")
            return image.copy()

        height, width = image.shape[:2]
        new_k, _ = cv2.getOptimalNewCameraMatrix(k, d, (width, height), 0.0)
        return cv2.undistort(image, k, d, None, new_k)

    def _write_camera_info(self, path, msg):
        data = {
            "header": {
                "frame_id": msg.header.frame_id,
                "stamp": {
                    "sec": int(msg.header.stamp.sec),
                    "nanosec": int(msg.header.stamp.nanosec),
                },
            },
            "height": int(msg.height),
            "width": int(msg.width),
            "distortion_model": msg.distortion_model,
            "d": list(msg.d),
            "k": list(msg.k),
            "r": list(msg.r),
            "p": list(msg.p),
            "binning_x": int(msg.binning_x),
            "binning_y": int(msg.binning_y),
            "roi": {
                "x_offset": int(msg.roi.x_offset),
                "y_offset": int(msg.roi.y_offset),
                "height": int(msg.roi.height),
                "width": int(msg.roi.width),
                "do_rectify": bool(msg.roi.do_rectify),
            },
        }
        with open(path, "w", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, sort_keys=False)


def main(args=None):
    rclpy.init(args=args)
    node = OakSnapshot()
    timeout_sec = float(node.get_parameter("timeout_sec").value)
    deadline = time.monotonic() + timeout_sec

    try:
        while rclpy.ok() and not node.ready():
            rclpy.spin_once(node, timeout_sec=0.1)
            if time.monotonic() > deadline:
                node.get_logger().error("Timed out waiting for image and CameraInfo.")
                raise SystemExit(1)

        node.save()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
