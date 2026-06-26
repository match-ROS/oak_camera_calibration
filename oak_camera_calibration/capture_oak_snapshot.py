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
from sensor_msgs.msg import CameraInfo, CompressedImage, Image


class OakSnapshot(Node):
    def __init__(self):
        super().__init__("oak_snapshot")

        self.declare_parameter("image_topic", "/oak/rgb/image_raw")
        self.declare_parameter("image_compressed", False)
        self.declare_parameter("camera_info_topic", "/oak/rgb/camera_info")
        self.declare_parameter("output_dir", "~/oak_handeye_samples")
        self.declare_parameter("prefix", "oak")
        self.declare_parameter("save_rectified", True)
        self.declare_parameter("timeout_sec", 60.0)
        self.declare_parameter("warmup_frames", 10)
        self.declare_parameter("select_frames", 8)
        self.declare_parameter("min_mean_intensity", 5.0)

        self.bridge = CvBridge()
        self.frame_count = 0
        self.candidate_count = 0
        self.dark_frame_count = 0
        self.best_image = None
        self.best_metrics = None
        self.best_stamp = None
        self.camera_info_msg = None

        qos = QoSProfile(depth=1)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT

        image_topic = self.get_parameter("image_topic").value
        self.image_compressed = bool(self.get_parameter("image_compressed").value) or image_topic.endswith("/compressed")
        camera_info_topic = self.get_parameter("camera_info_topic").value

        image_msg_type = CompressedImage if self.image_compressed else Image
        self.create_subscription(image_msg_type, image_topic, self._on_image, qos)
        self.create_subscription(CameraInfo, camera_info_topic, self._on_camera_info, qos)

        transport = "compressed" if self.image_compressed else "raw"
        self.get_logger().info(f"Waiting for {transport} image on {image_topic}")
        self.get_logger().info(f"Waiting for CameraInfo on {camera_info_topic}")

    def _on_image(self, msg):
        self.frame_count += 1

        warmup_frames = int(self.get_parameter("warmup_frames").value)
        if self.frame_count <= warmup_frames:
            return

        if self.image_compressed:
            image = self.bridge.compressed_imgmsg_to_cv2(msg, desired_encoding="bgr8")
        else:
            image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        metrics = self._image_metrics(image)

        min_mean_intensity = float(self.get_parameter("min_mean_intensity").value)
        if metrics["mean_intensity"] < min_mean_intensity:
            self.dark_frame_count += 1
            self.get_logger().warn(
                "Skipping dark frame "
                f"{self.frame_count}: mean={metrics['mean_intensity']:.1f}"
            )
            return

        self.candidate_count += 1
        if self.best_metrics is None or metrics["sharpness_laplacian_var"] > self.best_metrics["sharpness_laplacian_var"]:
            self.best_image = image
            self.best_metrics = metrics
            self.best_stamp = msg.header.stamp

    def _on_camera_info(self, msg):
        self.camera_info_msg = msg

    def ready(self):
        select_frames = int(self.get_parameter("select_frames").value)
        warmup_frames = int(self.get_parameter("warmup_frames").value)
        return (
            self.camera_info_msg is not None
            and self.best_image is not None
            and self.candidate_count >= select_frames
        )

    def save(self):
        output_dir = os.path.expanduser(self.get_parameter("output_dir").value)
        prefix = self.get_parameter("prefix").value
        save_rectified = bool(self.get_parameter("save_rectified").value)
        os.makedirs(output_dir, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_path = os.path.join(output_dir, f"{prefix}_{stamp}")

        image = self.best_image
        camera_info = self.camera_info_msg

        raw_path = base_path + "_raw.png"
        info_path = base_path + "_camera_info.yaml"
        metrics_path = base_path + "_image_metrics.yaml"

        cv2.imwrite(raw_path, image)
        self._write_camera_info(info_path, camera_info)
        self._write_metrics(metrics_path)

        self.get_logger().info(f"Saved raw image: {raw_path}")
        self.get_logger().info(f"Saved CameraInfo: {info_path}")
        self.get_logger().info(f"Saved image metrics: {metrics_path}")
        self.get_logger().info(
            "Best frame metrics: "
            f"mean={self.best_metrics['mean_intensity']:.1f}, "
            f"std={self.best_metrics['std_intensity']:.1f}, "
            f"sharpness={self.best_metrics['sharpness_laplacian_var']:.1f}"
        )

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
            "d": self._float_list(msg.d),
            "k": self._float_list(msg.k),
            "r": self._float_list(msg.r),
            "p": self._float_list(msg.p),
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

    def _float_list(self, values):
        return [float(value) for value in values]

    def _image_metrics(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return {
            "frame_count": int(self.frame_count),
            "mean_intensity": float(np.mean(gray)),
            "std_intensity": float(np.std(gray)),
            "min_intensity": int(np.min(gray)),
            "max_intensity": int(np.max(gray)),
            "sharpness_laplacian_var": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        }

    def _write_metrics(self, path):
        data = {
            "selected_frame": self.best_metrics,
            "selected_stamp": {
                "sec": int(self.best_stamp.sec),
                "nanosec": int(self.best_stamp.nanosec),
            },
            "warmup_frames": int(self.get_parameter("warmup_frames").value),
            "select_frames": int(self.get_parameter("select_frames").value),
            "min_mean_intensity": float(self.get_parameter("min_mean_intensity").value),
            "total_frames_seen": int(self.frame_count),
            "candidate_frames_seen": int(self.candidate_count),
            "dark_frames_skipped": int(self.dark_frame_count),
        }
        with open(path, "w", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, sort_keys=False)

    def status_text(self):
        warmup_frames = int(self.get_parameter("warmup_frames").value)
        select_frames = int(self.get_parameter("select_frames").value)
        return (
            f"frames={self.frame_count}, "
            f"warmup={min(self.frame_count, warmup_frames)}/{warmup_frames}, "
            f"candidates={self.candidate_count}/{select_frames}, "
            f"dark_skipped={self.dark_frame_count}, "
            f"camera_info={'yes' if self.camera_info_msg is not None else 'no'}, "
            f"best={'yes' if self.best_image is not None else 'no'}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = OakSnapshot()
    timeout_sec = float(node.get_parameter("timeout_sec").value)
    deadline = time.monotonic() + timeout_sec

    try:
        next_status = time.monotonic() + 2.0
        while rclpy.ok() and not node.ready():
            rclpy.spin_once(node, timeout_sec=0.1)
            now = time.monotonic()
            if now >= next_status:
                node.get_logger().info(f"Snapshot progress: {node.status_text()}")
                next_status = now + 2.0

            if now > deadline:
                node.get_logger().error(f"Timed out collecting snapshot: {node.status_text()}")
                raise SystemExit(1)

        node.save()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
