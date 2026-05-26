#!/usr/bin/env python3
import glob
import json
import os
import re
from datetime import datetime

import cv2
import numpy as np
import rclpy
import yaml
from cv_bridge import CvBridge
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import Buffer, TransformException, TransformListener

from oak_camera_calibration.aruco_grid_detector import ArucoGridDetector


class OakSampleGui(Node):
    def __init__(self):
        super().__init__("oak_sample_gui")

        self.declare_parameter("image_topic", "/oak/rgb/image_raw")
        self.declare_parameter("camera_info_topic", "/oak/rgb/camera_info")
        self.declare_parameter("output_dir", "~/oak_handeye_samples")
        self.declare_parameter("sample_prefix", "sample")
        self.declare_parameter("display_max_side", 1600)
        self.declare_parameter("detect_every_n_frames", 1)
        self.declare_parameter("save_rectified", True)
        self.declare_parameter("robot_base_frame", "base_link")
        self.declare_parameter("robot_tcp_frame", "tool0")
        self.declare_parameter("tf_timeout_sec", 0.5)
        self.declare_parameter("require_robot_pose", True)
        self.declare_parameter("require_detection_pose", True)

        self.declare_parameter("markers_x", 10)
        self.declare_parameter("markers_y", 7)
        self.declare_parameter("marker_length_m", 0.030)
        self.declare_parameter("marker_separation_m", 0.010)
        self.declare_parameter("dictionary", "DICT_4X4_250")
        self.declare_parameter("coarse_max_side", 1600)
        self.declare_parameter("refine_max_side", 2000)
        self.declare_parameter("roi_margin_ratio", 0.20)
        self.declare_parameter("roi_margin_px", 80)

        self.bridge = CvBridge()
        self.latest_image_msg = None
        self.latest_camera_info = None
        self.latest_image = None
        self.latest_detection = None
        self.frame_count = 0
        self.detect_enabled = True
        self.quit_requested = False
        self.window_name = "oak_sample_gui"
        self.output_dir = os.path.expanduser(self.get_parameter("output_dir").value)
        self.sample_prefix = self.get_parameter("sample_prefix").value
        os.makedirs(self.output_dir, exist_ok=True)
        self.sample_idx = self._next_sample_idx()
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.last_tf_ok = False

        self.detector = ArucoGridDetector(
            markers_x=self.get_parameter("markers_x").value,
            markers_y=self.get_parameter("markers_y").value,
            marker_length_m=self.get_parameter("marker_length_m").value,
            marker_separation_m=self.get_parameter("marker_separation_m").value,
            dictionary_name=self.get_parameter("dictionary").value,
            coarse_max_side=self.get_parameter("coarse_max_side").value,
            refine_max_side=self.get_parameter("refine_max_side").value,
            roi_margin_ratio=self.get_parameter("roi_margin_ratio").value,
            roi_margin_px=self.get_parameter("roi_margin_px").value,
        )

        qos = QoSProfile(depth=1)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT

        image_topic = self.get_parameter("image_topic").value
        camera_info_topic = self.get_parameter("camera_info_topic").value
        self.create_subscription(Image, image_topic, self._on_image, qos)
        self.create_subscription(CameraInfo, camera_info_topic, self._on_camera_info, qos)
        self.create_timer(0.03, self._update_gui)

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        self.get_logger().info(f"Listening for images on {image_topic}")
        self.get_logger().info(f"Listening for CameraInfo on {camera_info_topic}")
        self.get_logger().info(f"Writing samples to {self.output_dir}")
        self.get_logger().info(
            "Saving robot pose from "
            f"{self.get_parameter('robot_base_frame').value} -> "
            f"{self.get_parameter('robot_tcp_frame').value}"
        )
        self.get_logger().info("Keys: s=save sample, d=toggle detection, q/ESC=quit")

    def _on_image(self, msg):
        self.latest_image_msg = msg

    def _on_camera_info(self, msg):
        self.latest_camera_info = msg

    def _update_gui(self):
        if self.latest_image_msg is None:
            self._show_waiting()
            self._handle_key(cv2.waitKey(1) & 0xFF)
            return

        self.latest_image = self.bridge.imgmsg_to_cv2(
            self.latest_image_msg,
            desired_encoding="bgr8",
        )
        self.frame_count += 1

        if self.detect_enabled and self._should_detect():
            self.latest_detection = self._detect(self.latest_image)

        display = self._display_image(self.latest_image)
        cv2.imshow(self.window_name, display)
        self._handle_key(cv2.waitKey(1) & 0xFF)

    def _should_detect(self):
        every_n = max(1, int(self.get_parameter("detect_every_n_frames").value))
        return self.frame_count % every_n == 0

    def _detect(self, image):
        camera_matrix, distortion_coeffs = self._camera_model()
        return self.detector.detect(image, camera_matrix, distortion_coeffs)

    def _display_image(self, image):
        camera_matrix, distortion_coeffs = self._camera_model()
        display, scale = self._resize_for_display(image)

        if self.latest_detection is not None:
            detection = self._scaled_detection(self.latest_detection, scale)
            k = None if camera_matrix is None else self._scaled_camera_matrix(camera_matrix, scale)
            display = self.detector.draw_detection(display, detection, k, distortion_coeffs)

        self._draw_hud(display)
        return display

    def _show_waiting(self):
        view = np.zeros((360, 960, 3), dtype=np.uint8)
        cv2.putText(
            view,
            "Waiting for OAK image...",
            (30, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (230, 230, 230),
            2,
            cv2.LINE_AA,
        )
        cv2.imshow(self.window_name, view)

    def _handle_key(self, key):
        if key in (ord("q"), 27):
            self.get_logger().info("Closing GUI. Samples remain on disk.")
            self.quit_requested = True
        elif key == ord("s"):
            self._save_sample()
        elif key == ord("d"):
            self.detect_enabled = not self.detect_enabled
            state = "enabled" if self.detect_enabled else "disabled"
            self.get_logger().info(f"Detection {state}")

    def _save_sample(self):
        if self.latest_image is None:
            self.get_logger().warn("No image available yet.")
            return
        if self.latest_camera_info is None:
            self.get_logger().warn("No CameraInfo available yet; sample not saved.")
            return

        robot_pose = self._lookup_robot_pose()
        if robot_pose is None and bool(self.get_parameter("require_robot_pose").value):
            self.get_logger().warn(
                "No robot TF available; sample not saved. "
                "Check robot_base_frame/robot_tcp_frame or set require_robot_pose:=false."
            )
            return
        if (
            bool(self.get_parameter("require_detection_pose").value)
            and not self._has_detection_pose()
        ):
            self.get_logger().warn(
                "No board pose available; sample not saved. "
                "Move the board into view or set require_detection_pose:=false."
            )
            return

        base = f"{self.sample_prefix}_{self.sample_idx:03d}"
        base_path = os.path.join(self.output_dir, base)
        raw_path = base_path + "_raw.png"
        rectified_path = base_path + "_rectified.png"
        annotated_path = base_path + "_annotated.png"
        camera_info_path = base_path + "_camera_info.yaml"
        sample_path = base_path + ".json"

        image = self.latest_image.copy()
        detection = self.latest_detection
        camera_matrix, distortion_coeffs = self._camera_model()

        cv2.imwrite(raw_path, image)
        self._write_camera_info(camera_info_path, self.latest_camera_info)

        rectified_file = None
        if bool(self.get_parameter("save_rectified").value):
            cv2.imwrite(rectified_path, self._rectify(image, camera_matrix, distortion_coeffs))
            rectified_file = rectified_path

        annotated = self.detector.draw_detection(
            image,
            detection,
            camera_matrix,
            distortion_coeffs,
        )
        cv2.imwrite(annotated_path, annotated)

        data = self._sample_metadata(
            base,
            raw_path,
            rectified_file,
            annotated_path,
            camera_info_path,
            detection,
            robot_pose,
        )
        with open(sample_path, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)

        marker_count = 0 if detection is None else detection["num_markers"]
        self.get_logger().info(
            f"Saved sample {self.sample_idx:03d}: {marker_count} markers, {sample_path}"
        )
        self.sample_idx += 1

    def _sample_metadata(
        self,
        sample_id,
        raw_path,
        rectified_path,
        annotated_path,
        camera_info_path,
        detection,
        robot_pose,
    ):
        detection_ok = detection is not None and detection["marker_ids"] is not None
        pose = None
        marker_ids = []
        reprojection_error = None
        roi = None
        if detection_ok:
            marker_ids = [int(value) for value in detection["marker_ids"].flatten()]
            roi = None if detection["roi"] is None else list(detection["roi"])
            reprojection_error = detection["reprojection_error_px"]
            if detection["pose"] is not None:
                pose = {
                    "markers_used": int(detection["pose"]["markers_used"]),
                    "rvec": detection["pose"]["rvec"].flatten().astype(float).tolist(),
                    "tvec": detection["pose"]["tvec"].flatten().astype(float).tolist(),
                }

        return {
            "sample_id": sample_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "image_file": os.path.basename(raw_path),
            "rectified_image_file": None if rectified_path is None else os.path.basename(rectified_path),
            "annotated_image_file": os.path.basename(annotated_path),
            "camera_info_file": os.path.basename(camera_info_path),
            "camera_frame": self.latest_camera_info.header.frame_id,
            "robot_pose": robot_pose
            if robot_pose is not None
            else {
                "ok": False,
                "parent_frame": self.get_parameter("robot_base_frame").value,
                "child_frame": self.get_parameter("robot_tcp_frame").value,
            },
            "board_model": self.detector.board_metadata(),
            "detection": {
                "ok": bool(detection_ok),
                "num_markers": 0 if detection is None else detection["num_markers"],
                "marker_ids": marker_ids,
                "roi": roi,
                "pose": pose,
                "reprojection_error_px": reprojection_error,
            },
        }

    def _draw_hud(self, image):
        marker_count = 0
        pose_text = "pose: no"
        if self.latest_detection is not None:
            marker_count = self.latest_detection["num_markers"]
            if self.latest_detection.get("pose") is not None:
                pose_text = "pose: yes"
        self.last_tf_ok = self._can_lookup_robot_pose()
        tf_text = (
            f"tf {self.get_parameter('robot_base_frame').value}->"
            f"{self.get_parameter('robot_tcp_frame').value}: "
            f"{'yes' if self.last_tf_ok else 'no'}"
        )

        lines = [
            f"markers: {marker_count}  {pose_text}",
            tf_text,
            f"next: {self.sample_prefix}_{self.sample_idx:03d}   s=save d=detect q=quit",
            f"detection: {'on' if self.detect_enabled else 'off'}",
        ]
        y = 30
        for line in lines:
            cv2.putText(
                image,
                line,
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 0),
                4,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                line,
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            y += 32

    def _camera_model(self):
        if self.latest_camera_info is None:
            return None, None
        k = np.array(self.latest_camera_info.k, dtype=np.float64).reshape(3, 3)
        d = np.array(self.latest_camera_info.d, dtype=np.float64)
        if d.size == 0:
            d = np.zeros((5, 1), dtype=np.float64)
        return k, d

    def _resize_for_display(self, image):
        max_side = int(self.get_parameter("display_max_side").value)
        h, w = image.shape[:2]
        scale = min(1.0, float(max_side) / float(max(h, w)))
        if scale >= 1.0:
            return image.copy(), 1.0
        resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return resized, scale

    def _scaled_detection(self, detection, scale):
        scaled = dict(detection)
        if detection["marker_corners"] is not None:
            scaled["marker_corners"] = [
                corner.astype(np.float32) * scale for corner in detection["marker_corners"]
            ]
        if detection["roi"] is not None:
            scaled["roi"] = tuple(int(round(value * scale)) for value in detection["roi"])
        return scaled

    def _scaled_camera_matrix(self, camera_matrix, scale):
        k = camera_matrix.copy()
        k[0, :] *= scale
        k[1, :] *= scale
        return k

    def _rectify(self, image, camera_matrix, distortion_coeffs):
        if camera_matrix is None or distortion_coeffs is None or np.allclose(distortion_coeffs, 0.0):
            return image.copy()
        h, w = image.shape[:2]
        new_k, _ = cv2.getOptimalNewCameraMatrix(camera_matrix, distortion_coeffs, (w, h), 0.0)
        return cv2.undistort(image, camera_matrix, distortion_coeffs, None, new_k)

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
            "d": [float(value) for value in msg.d],
            "k": [float(value) for value in msg.k],
            "r": [float(value) for value in msg.r],
            "p": [float(value) for value in msg.p],
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

    def _can_lookup_robot_pose(self):
        base_frame = self.get_parameter("robot_base_frame").value
        tcp_frame = self.get_parameter("robot_tcp_frame").value
        return self.tf_buffer.can_transform(base_frame, tcp_frame, Time())

    def _has_detection_pose(self):
        return (
            self.latest_detection is not None
            and self.latest_detection.get("pose") is not None
        )

    def _lookup_robot_pose(self):
        base_frame = self.get_parameter("robot_base_frame").value
        tcp_frame = self.get_parameter("robot_tcp_frame").value
        timeout_sec = float(self.get_parameter("tf_timeout_sec").value)
        try:
            transform = self.tf_buffer.lookup_transform(
                base_frame,
                tcp_frame,
                Time(),
                timeout=Duration(seconds=timeout_sec),
            )
        except TransformException as exc:
            self.get_logger().warn(f"Could not look up TF {base_frame}->{tcp_frame}: {exc}")
            return None

        translation = transform.transform.translation
        rotation = transform.transform.rotation
        stamp = transform.header.stamp
        return {
            "ok": True,
            "parent_frame": transform.header.frame_id,
            "child_frame": transform.child_frame_id,
            "stamp": {
                "sec": int(stamp.sec),
                "nanosec": int(stamp.nanosec),
            },
            "translation": [
                float(translation.x),
                float(translation.y),
                float(translation.z),
            ],
            "quaternion_xyzw": [
                float(rotation.x),
                float(rotation.y),
                float(rotation.z),
                float(rotation.w),
            ],
        }

    def _next_sample_idx(self):
        pattern = os.path.join(self.output_dir, f"{self.sample_prefix}_*.json")
        indices = []
        for path in glob.glob(pattern):
            match = re.search(
                rf"{re.escape(self.sample_prefix)}_(\d+)\.json$",
                os.path.basename(path),
            )
            if match:
                indices.append(int(match.group(1)))
        if not indices:
            return 0
        return max(indices) + 1


def main(args=None):
    rclpy.init(args=args)
    node = OakSampleGui()
    try:
        while rclpy.ok() and not node.quit_requested:
            rclpy.spin_once(node, timeout_sec=0.05)
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
