#!/usr/bin/env python3
import glob
import json
import math
import os
import re
import threading
import time
from datetime import datetime

import cv2
import numpy as np
import rclpy
import yaml
from cv_bridge import CvBridge
from geometry_msgs.msg import PoseStamped
from geometry_msgs.msg import TwistStamped
from mur_control.action import JparseMove
from oak_camera_calibration.charuco_detector import CharucoDetector
from oak_camera_calibration.compute_handeye import (
    board_pose_residuals,
    calibrate,
    load_samples,
    quaternion_from_matrix,
    transform_from_rvec_tvec,
    transform_from_translation_quaternion,
)
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import Buffer, TransformException, TransformListener


class SemiAutoHandeyeSession(Node):
    def __init__(self):
        super().__init__("semi_auto_handeye_session")

        self.declare_parameter("image_topic", "/oak/rgb/image_raw")
        self.declare_parameter("camera_info_topic", "/oak/rgb/camera_info")
        self.declare_parameter("output_dir", "~/oak_charuco_handeye_samples")
        self.declare_parameter("sample_prefix", "sample")
        self.declare_parameter("robot_name", "mur620")
        self.declare_parameter("arm", "l")
        self.declare_parameter("robot_base_frame", "")
        self.declare_parameter("robot_tcp_frame", "")
        self.declare_parameter("action_name", "")
        self.declare_parameter("move_enabled", False)
        self.declare_parameter("gui_enabled", True)
        self.declare_parameter("keyboard_jog_enabled", False)
        self.declare_parameter("jog_twist_topic", "")
        self.declare_parameter("jog_linear_velocity", 0.03)
        self.declare_parameter("jog_angular_velocity", 0.25)
        self.declare_parameter("jog_linear_acceleration", 0.12)
        self.declare_parameter("jog_angular_acceleration", 1.0)
        self.declare_parameter("jog_hold_timeout", 1.0)
        self.declare_parameter("log_key_codes", True)
        self.declare_parameter("display_max_side", 1600)
        self.declare_parameter("draw_rejected_markers", True)
        self.declare_parameter("planning_frame", "")
        self.declare_parameter("samples", 12)
        self.declare_parameter("sphere_radius_m", 0.0)
        self.declare_parameter("sphere_yaw_span_deg", 50.0)
        self.declare_parameter("sphere_pitch_span_deg", 35.0)
        self.declare_parameter("max_linear_velocity", 0.06)
        self.declare_parameter("max_angular_velocity", 0.25)
        self.declare_parameter("move_timeout", 30.0)
        self.declare_parameter("handeye_method", "tsai")

        self.declare_parameter("squares_x", 14)
        self.declare_parameter("squares_y", 9)
        self.declare_parameter("square_length_m", 0.065)
        self.declare_parameter("marker_length_m", 0.048)
        self.declare_parameter("dictionary", "DICT_4X4_250")
        self.declare_parameter("min_charuco_corners", 8)
        self.declare_parameter("coarse_max_side", 1600)
        self.declare_parameter("refine_max_side", 2200)

        self.bridge = CvBridge()
        self.latest_image_msg = None
        self.latest_camera_info = None
        self.latest_image = None
        self.data_lock = threading.Lock()
        self.last_wait_status = "startup"
        self.last_status_log_time = 0.0

        self.output_dir = os.path.expanduser(self.get_parameter("output_dir").value)
        self.sample_prefix = self.get_parameter("sample_prefix").value
        os.makedirs(self.output_dir, exist_ok=True)
        self.sample_idx = self._next_sample_idx()

        arm = self.get_parameter("arm").value
        robot_name = self.get_parameter("robot_name").value
        self.robot_base_frame = self._param_or_default(
            "robot_base_frame",
            f"{robot_name}/UR10_{arm}/base_link",
        )
        self.robot_tcp_frame = self._param_or_default(
            "robot_tcp_frame",
            f"{robot_name}/UR10_{arm}/tool0",
        )
        self.planning_frame = self._param_or_default("planning_frame", self.robot_base_frame)
        self.action_name = self._param_or_default("action_name", f"/{robot_name}/jparse_move_{arm}")
        self.move_enabled = bool(self.get_parameter("move_enabled").value)
        self.gui_enabled = bool(self.get_parameter("gui_enabled").value)
        self.keyboard_jog_enabled = bool(self.get_parameter("keyboard_jog_enabled").value)
        self.jog_twist_topic = self._param_or_default(
            "jog_twist_topic",
            f"/{robot_name}/jparse_velocity_controller_{arm}/twist_cmd",
        )
        self.jog_target_linear = np.zeros(3, dtype=np.float64)
        self.jog_target_angular = np.zeros(3, dtype=np.float64)
        self.jog_current_linear = np.zeros(3, dtype=np.float64)
        self.jog_current_angular = np.zeros(3, dtype=np.float64)
        self.last_jog_key_time = 0.0
        self.last_jog_update_time = time.monotonic()
        self.jog_rotation_mode = False
        self.last_key_text = "none"

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.action_client = ActionClient(self, JparseMove, self.action_name)
        self.jog_twist_pub = self.create_publisher(TwistStamped, self.jog_twist_topic, 10)
        self.detector = CharucoDetector(
            squares_x=self.get_parameter("squares_x").value,
            squares_y=self.get_parameter("squares_y").value,
            square_length_m=self.get_parameter("square_length_m").value,
            marker_length_m=self.get_parameter("marker_length_m").value,
            dictionary_name=self.get_parameter("dictionary").value,
            min_charuco_corners=self.get_parameter("min_charuco_corners").value,
            coarse_max_side=self.get_parameter("coarse_max_side").value,
            refine_max_side=self.get_parameter("refine_max_side").value,
        )
        self.T_tcp_camera = np.eye(4, dtype=np.float64)
        self.T_base_board = None

        qos = QoSProfile(depth=1)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self.create_subscription(Image, self.get_parameter("image_topic").value, self._on_image, qos)
        self.create_subscription(
            CameraInfo,
            self.get_parameter("camera_info_topic").value,
            self._on_camera_info,
            qos,
        )

        self.get_logger().info(f"Writing samples to {self.output_dir}")
        self.get_logger().info(
            "Camera topics: "
            f"{self.get_parameter('image_topic').value}, "
            f"{self.get_parameter('camera_info_topic').value}"
        )
        self.get_logger().info(f"Robot TF: {self.robot_base_frame} -> {self.robot_tcp_frame}")
        self.get_logger().info(
            f"Motion {'enabled' if self.move_enabled else 'disabled'}; action={self.action_name}"
        )
        self.get_logger().info(
            "GUI "
            f"{'enabled' if self.gui_enabled else 'disabled'}; "
            f"keyboard_jog={'enabled' if self.keyboard_jog_enabled else 'disabled'}; "
            f"twist={self.jog_twist_topic}"
        )

    def run_session(self):
        if self.gui_enabled:
            self.run_gui_session()
            return

        self.get_logger().info("Waiting for image, CameraInfo, ChArUco pose, and robot TF...")
        first = self.wait_for_complete_observation()
        if first is None:
            return

        self.update_board_estimate(first)
        radius = self._sphere_radius(first["T_base_tcp"])
        self.get_logger().info(
            f"Initial board estimate in {self.robot_base_frame}: "
            f"{self.T_base_board[:3, 3].round(4).tolist()}, radius={radius:.3f} m"
        )

        if self.prompt("Save current manually positioned start sample? [s/N/q] ", "snq") == "s":
            self.save_sample(first)
            self.recompute_handeye()

        current_observation = first
        visited_target_positions = []
        total_targets = max(1, int(self.get_parameter("samples").value))
        for index in range(total_targets):
            targets = self.generate_targets(current_observation["T_base_tcp"], radius)
            target = self.select_next_target(
                targets,
                current_observation["T_base_tcp"],
                visited_target_positions,
            )
            visited_target_positions.append(target[:3, 3].copy())
            print("")
            self.print_target(index + 1, total_targets, target)
            choice = self.prompt("Target: [m]ove/[s]kip/[q]uit? ", "msq")
            if choice == "q":
                break
            if choice == "s":
                continue

            if self.move_enabled:
                if not self.send_pose_goal(target):
                    self.get_logger().warn("Target move failed or timed out.")
                    if self.prompt("Continue with capture here anyway? [s/N/q] ", "snq") != "s":
                        continue
            else:
                self.get_logger().warn("move_enabled is false; no command was sent.")

            while rclpy.ok():
                observation = self.wait_for_complete_observation()
                if observation is None:
                    return
                detection = observation["detection"]
                reproj = detection.get("reprojection_error_px") or {}
                self.get_logger().info(
                    "Detection: "
                    f"{detection['num_charuco_corners']} ChArUco corners, "
                    f"reproj_mean={reproj.get('mean', float('nan')):.3f}px"
                )
                choice = self.prompt("[s]ave/[r]etry/[k]skip/[q]uit? ", "srkq")
                if choice == "s":
                    self.save_sample(observation)
                    self.recompute_handeye()
                    self.update_board_estimate(observation)
                    current_observation = observation
                    break
                if choice == "k":
                    break
                if choice == "q":
                    return

        self.write_session_state()

    def run_gui_session(self):
        window_name = "semi_auto_handeye_session"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        self.get_logger().info(
            "GUI keys: c=save sample/frame, q=quit, .=stop, "
            "arrows=XY, PgUp/PgDn=Z, Ctrl+arrows/PgUp/PgDn=rotation. "
            "If Ctrl is not detected by OpenCV, use i/k j/l u/o or press m to toggle rotation mode."
        )

        try:
            while rclpy.ok():
                frame = self.current_frame_detection()
                view = self.render_gui_frame(frame)
                cv2.imshow(window_name, view)
                self.update_jog_output()
                key = cv2.waitKeyEx(20)
                if key == -1:
                    continue
                if not self.handle_gui_key(key, frame):
                    break
        finally:
            self.stop_jog(force=True)
            cv2.destroyWindow(window_name)

    def current_frame_detection(self):
        with self.data_lock:
            image_msg = self.latest_image_msg
            camera_info = self.latest_camera_info

        if image_msg is None:
            self.last_wait_status = (
                f"waiting for image on {self.get_parameter('image_topic').value}"
            )
            return None

        image = self.bridge.imgmsg_to_cv2(image_msg, desired_encoding="bgr8")
        camera_matrix = None
        distortion_coeffs = None
        detection = None
        if camera_info is None:
            self.last_wait_status = (
                f"waiting for CameraInfo on {self.get_parameter('camera_info_topic').value}"
            )
        else:
            camera_matrix, distortion_coeffs = self.camera_model(camera_info)
            detection = self.detector.detect(image, camera_matrix, distortion_coeffs)
            if detection is None or detection.get("pose") is None:
                if detection is None:
                    self.last_wait_status = "waiting for ChArUco detector result"
                else:
                    self.last_wait_status = (
                        "waiting for ChArUco pose: "
                        f"markers={detection.get('num_markers', 0)}, "
                        f"corners={detection.get('num_charuco_corners', 0)}"
                    )
            else:
                self.last_wait_status = (
                    "ChArUco pose ok: "
                    f"corners={detection.get('num_charuco_corners', 0)}"
                )

        return {
            "image": image,
            "image_msg": image_msg,
            "camera_info": camera_info,
            "camera_matrix": camera_matrix,
            "distortion_coeffs": distortion_coeffs,
            "detection": detection,
        }

    def render_gui_frame(self, frame):
        if frame is None:
            view = np.zeros((480, 960, 3), dtype=np.uint8)
            self.draw_text_lines(
                view,
                [
                    "Waiting for OAK image...",
                    self.last_wait_status,
                ],
            )
            return view

        image = frame["image"]
        detection = frame["detection"]
        camera_matrix = frame["camera_matrix"]
        distortion_coeffs = frame["distortion_coeffs"]
        if detection is None:
            view = image.copy()
        else:
            view = self.detector.draw_detection(
                image,
                detection,
                camera_matrix,
                distortion_coeffs,
                draw_rejected=bool(self.get_parameter("draw_rejected_markers").value),
            )

        view = self.resize_for_display(view)
        status_lines = [
            self.last_wait_status,
            self.detection_summary(detection),
            (
                f"board: {self.detector.dictionary_name} "
                f"{self.detector.squares_x}x{self.detector.squares_y} "
                f"square={self.detector.square_length_m * 1000.0:.0f}mm "
                f"marker={self.detector.marker_length_m * 1000.0:.0f}mm"
            ),
            f"next sample: {self.sample_prefix}_{self.sample_idx:03d}",
            (
                "keyboard jog ON"
                if self.keyboard_jog_enabled
                else "keyboard jog OFF"
            ),
            f"mode: {'rotation' if self.jog_rotation_mode else 'translation'}",
            f"last key: {self.last_key_text}",
            "c=save q=quit .=stop arrows=XY PgUp/PgDn=Z Ctrl/m or i/k j/l u/o=rotation",
        ]
        self.draw_text_lines(view, status_lines)
        return view

    def detection_summary(self, detection):
        if detection is None:
            return "detection: no image/camera model yet"
        reproj = detection.get("reprojection_error_px") or {}
        reproj_text = "n/a" if "mean" not in reproj else f"{reproj['mean']:.2f}px"
        pose_text = "pose yes" if detection.get("pose") is not None else "pose no"
        return (
            "detection: "
            f"markers={detection.get('num_markers', 0)} "
            f"charuco={detection.get('num_charuco_corners', 0)} "
            f"rejected={detection.get('num_rejected_candidates', 0)} "
            f"{pose_text} reproj={reproj_text}"
        )

    def handle_gui_key(self, key, frame):
        char = self.ascii_char(key)
        self.last_key_text = (
            f"{key} ({self.key_name(key) or char or 'unknown'}, "
            f"{'ctrl' if self.key_has_ctrl(key) else 'no-ctrl'})"
        )
        if bool(self.get_parameter("log_key_codes").value):
            self.get_logger().info(f"GUI key: {self.last_key_text}")
        if char == "q" or key == 27:
            return False
        if char == "c":
            observation = self.current_observation()
            if observation is not None:
                self.save_sample(observation)
                self.recompute_handeye()
                self.update_board_estimate(observation)
            elif frame is not None:
                self.save_debug_frame(frame)
            return True
        if char == ".":
            self.stop_jog(force=True)
            return True
        if char == "m":
            self.jog_rotation_mode = not self.jog_rotation_mode
            self.get_logger().info(
                f"Jog mode: {'rotation' if self.jog_rotation_mode else 'translation'}"
            )
            return True

        linear, angular = self.jog_command_from_key(key)
        if linear is None:
            return True
        self.set_jog_target(linear, angular)
        return True

    def jog_command_from_key(self, key):
        v = float(self.get_parameter("jog_linear_velocity").value)
        w = float(self.get_parameter("jog_angular_velocity").value)
        key_name = self.key_name(key)
        if key_name is None:
            return None, None

        direct_rotation = key_name in ("i", "j", "k", "l", "u", "o")
        rotate = self.jog_rotation_mode or self.key_has_ctrl(key)
        zero = [0.0, 0.0, 0.0]
        translation = {
            "left": ([-v, 0.0, 0.0], zero),
            "right": ([v, 0.0, 0.0], zero),
            "up": ([0.0, v, 0.0], zero),
            "down": ([0.0, -v, 0.0], zero),
            "page_up": ([0.0, 0.0, v], zero),
            "page_down": ([0.0, 0.0, -v], zero),
            "a": ([-v, 0.0, 0.0], zero),
            "d": ([v, 0.0, 0.0], zero),
            "w": ([0.0, v, 0.0], zero),
            "x": ([0.0, -v, 0.0], zero),
            "r": ([0.0, 0.0, v], zero),
            "f": ([0.0, 0.0, -v], zero),
        }
        rotation = {
            "left": (zero, [w, 0.0, 0.0]),
            "right": (zero, [-w, 0.0, 0.0]),
            "up": (zero, [0.0, w, 0.0]),
            "down": (zero, [0.0, -w, 0.0]),
            "page_up": (zero, [0.0, 0.0, w]),
            "page_down": (zero, [0.0, 0.0, -w]),
            "j": (zero, [w, 0.0, 0.0]),
            "l": (zero, [-w, 0.0, 0.0]),
            "i": (zero, [0.0, w, 0.0]),
            "k": (zero, [0.0, -w, 0.0]),
            "u": (zero, [0.0, 0.0, w]),
            "o": (zero, [0.0, 0.0, -w]),
        }
        return (rotation if rotate or direct_rotation else translation).get(key_name, (None, None))

    def key_name(self, key):
        low = key & 0xFFFF
        arrow_codes = {
            81: "left",
            82: "up",
            83: "right",
            84: "down",
            85: "page_up",
            86: "page_down",
            2424832: "left",
            2490368: "up",
            2555904: "right",
            2621440: "down",
            2162688: "page_up",
            2228224: "page_down",
            65361: "left",
            65362: "up",
            65363: "right",
            65364: "down",
            65365: "page_up",
            65366: "page_down",
        }
        if key in arrow_codes:
            return arrow_codes[key]
        if low in arrow_codes:
            return arrow_codes[low]
        char = self.ascii_char(key)
        if char in ("w", "a", "d", "x", "r", "f", "i", "j", "k", "l", "u", "o"):
            return char
        return None

    def ascii_char(self, key):
        if 0 <= key < 128:
            return chr(key).lower()
        return ""

    def key_has_ctrl(self, key):
        # OpenCV does not expose modifiers consistently across HighGUI backends.
        # Qt builds usually encode Ctrl as 0x04000000; other backends vary.
        return (
            bool(key & 0x04000000)
            or bool(key & 0x00040000)
            or bool(key & 0x00100000)
        )

    def set_jog_target(self, linear, angular):
        if not self.keyboard_jog_enabled:
            self.get_logger().warn(
                "Keyboard jog is disabled. Start with keyboard_jog_enabled:=true to move."
            )
            return
        self.jog_target_linear = np.asarray(linear, dtype=np.float64)
        self.jog_target_angular = np.asarray(angular, dtype=np.float64)
        self.last_jog_key_time = time.monotonic()

    def update_jog_output(self):
        if not self.keyboard_jog_enabled:
            return

        now = time.monotonic()
        dt = max(1.0e-4, now - self.last_jog_update_time)
        self.last_jog_update_time = now
        if now - self.last_jog_key_time > float(self.get_parameter("jog_hold_timeout").value):
            self.jog_target_linear = np.zeros(3, dtype=np.float64)
            self.jog_target_angular = np.zeros(3, dtype=np.float64)

        self.jog_current_linear = slew_vector(
            self.jog_current_linear,
            self.jog_target_linear,
            float(self.get_parameter("jog_linear_acceleration").value) * dt,
        )
        self.jog_current_angular = slew_vector(
            self.jog_current_angular,
            self.jog_target_angular,
            float(self.get_parameter("jog_angular_acceleration").value) * dt,
        )

        if (
            np.linalg.norm(self.jog_current_linear) > 1.0e-5
            or np.linalg.norm(self.jog_current_angular) > 1.0e-5
            or np.linalg.norm(self.jog_target_linear) > 1.0e-5
            or np.linalg.norm(self.jog_target_angular) > 1.0e-5
        ):
            self.publish_jog_twist(
                self.jog_current_linear,
                self.jog_current_angular,
                force=True,
            )

    def publish_jog_twist(self, linear, angular, force=False):
        if not self.keyboard_jog_enabled and not force:
            self.get_logger().warn(
                "Keyboard jog is disabled. Start with keyboard_jog_enabled:=true to move."
            )
            return

        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.robot_base_frame
        msg.twist.linear.x = float(linear[0])
        msg.twist.linear.y = float(linear[1])
        msg.twist.linear.z = float(linear[2])
        msg.twist.angular.x = float(angular[0])
        msg.twist.angular.y = float(angular[1])
        msg.twist.angular.z = float(angular[2])
        self.jog_twist_pub.publish(msg)

    def stop_jog(self, force=False):
        self.jog_target_linear = np.zeros(3, dtype=np.float64)
        self.jog_target_angular = np.zeros(3, dtype=np.float64)
        self.jog_current_linear = np.zeros(3, dtype=np.float64)
        self.jog_current_angular = np.zeros(3, dtype=np.float64)
        for _ in range(3):
            self.publish_jog_twist(
                self.jog_current_linear,
                self.jog_current_angular,
                force=force,
            )
            time.sleep(0.02)

    def save_debug_frame(self, frame):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"debug_{stamp}"
        raw_path = os.path.join(self.output_dir, base + "_raw.png")
        annotated_path = os.path.join(self.output_dir, base + "_annotated.png")
        image = frame["image"].copy()
        cv2.imwrite(raw_path, image)
        if frame["detection"] is None:
            cv2.imwrite(annotated_path, image)
        else:
            cv2.imwrite(
                annotated_path,
                self.detector.draw_detection(
                    image,
                    frame["detection"],
                    frame["camera_matrix"],
                    frame["distortion_coeffs"],
                    draw_rejected=True,
                ),
            )
        self.get_logger().info(
            f"Saved debug frame without complete calibration pose: {raw_path}"
        )

    def resize_for_display(self, image):
        max_side = int(self.get_parameter("display_max_side").value)
        h, w = image.shape[:2]
        scale = min(1.0, float(max_side) / float(max(h, w)))
        if scale >= 1.0:
            return image
        return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    def draw_text_lines(self, image, lines):
        y = 28
        for line in lines:
            cv2.putText(
                image,
                line,
                (18, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.68,
                (0, 0, 0),
                4,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                line,
                (18, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.68,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            y += 28

    def _on_image(self, msg):
        with self.data_lock:
            self.latest_image_msg = msg

    def _on_camera_info(self, msg):
        with self.data_lock:
            self.latest_camera_info = msg

    def wait_for_complete_observation(self, timeout_sec=30.0):
        deadline = self.get_clock().now() + Duration(seconds=timeout_sec)
        while rclpy.ok() and self.get_clock().now() < deadline:
            observation = self.current_observation()
            if observation is not None:
                return observation
            self.log_wait_status()
            time.sleep(0.05)
        self.get_logger().error("Timed out while waiting for a complete observation.")
        self.get_logger().error(f"Last wait status: {self.last_wait_status}")
        return None

    def current_observation(self):
        with self.data_lock:
            image_msg = self.latest_image_msg
            camera_info = self.latest_camera_info

        if image_msg is None:
            self.last_wait_status = (
                f"waiting for image on {self.get_parameter('image_topic').value}"
            )
            return None
        if camera_info is None:
            self.last_wait_status = (
                f"waiting for CameraInfo on {self.get_parameter('camera_info_topic').value}"
            )
            return None

        image = self.bridge.imgmsg_to_cv2(image_msg, desired_encoding="bgr8")
        camera_matrix, distortion_coeffs = self.camera_model(camera_info)
        detection = self.detector.detect(image, camera_matrix, distortion_coeffs)
        if detection is None or detection.get("pose") is None:
            if detection is None:
                self.last_wait_status = "waiting for ChArUco detector result"
            else:
                reproj = detection.get("reprojection_error_px") or {}
                self.last_wait_status = (
                    "waiting for ChArUco pose: "
                    f"markers={detection.get('num_markers', 0)}, "
                    f"corners={detection.get('num_charuco_corners', 0)}, "
                    f"reproj_mean={reproj.get('mean', 'n/a')}"
                )
            return None

        robot_pose = self.lookup_robot_pose()
        if robot_pose is None:
            return None

        T_base_tcp = transform_from_translation_quaternion(
            robot_pose["translation"],
            robot_pose["quaternion_xyzw"],
        )
        T_camera_board = transform_from_rvec_tvec(
            detection["pose"]["rvec"],
            detection["pose"]["tvec"],
        )
        self.latest_image = image
        return {
            "image": image,
            "camera_info": camera_info,
            "camera_matrix": camera_matrix,
            "distortion_coeffs": distortion_coeffs,
            "detection": detection,
            "robot_pose": robot_pose,
            "T_base_tcp": T_base_tcp,
            "T_camera_board": T_camera_board,
        }

    def log_wait_status(self):
        now = time.monotonic()
        if now - self.last_status_log_time < 2.0:
            return
        self.last_status_log_time = now
        self.get_logger().info(f"Still waiting: {self.last_wait_status}")

    def lookup_robot_pose(self):
        try:
            transform = self.tf_buffer.lookup_transform(
                self.robot_base_frame,
                self.robot_tcp_frame,
                Time(),
                timeout=Duration(seconds=0.5),
            )
        except TransformException as exc:
            self.last_wait_status = (
                f"waiting for TF {self.robot_base_frame}->{self.robot_tcp_frame}: {exc}"
            )
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
            "translation": [float(translation.x), float(translation.y), float(translation.z)],
            "quaternion_xyzw": [
                float(rotation.x),
                float(rotation.y),
                float(rotation.z),
                float(rotation.w),
            ],
        }

    def update_board_estimate(self, observation):
        self.T_base_board = (
            observation["T_base_tcp"] @ self.T_tcp_camera @ observation["T_camera_board"]
        )

    def generate_targets(self, T_base_tcp_current, radius):
        board_center = self.T_base_board[:3, 3]
        current_camera = (T_base_tcp_current @ self.T_tcp_camera)[:3, 3]
        direction = current_camera - board_center
        direction = normalize(direction)

        yaw_span = math.radians(float(self.get_parameter("sphere_yaw_span_deg").value))
        pitch_span = math.radians(float(self.get_parameter("sphere_pitch_span_deg").value))
        sample_count = max(1, int(self.get_parameter("samples").value))

        candidates = []
        rings = [
            (0.0, 0.0),
            (-0.5 * yaw_span, 0.0),
            (0.5 * yaw_span, 0.0),
            (0.0, -0.5 * pitch_span),
            (0.0, 0.5 * pitch_span),
            (-0.5 * yaw_span, -0.5 * pitch_span),
            (0.5 * yaw_span, -0.5 * pitch_span),
            (-0.5 * yaw_span, 0.5 * pitch_span),
            (0.5 * yaw_span, 0.5 * pitch_span),
            (-yaw_span, 0.0),
            (yaw_span, 0.0),
            (0.0, -pitch_span),
            (0.0, pitch_span),
        ]
        for yaw, pitch in rings:
            rotated = rotate_about_axis(direction, np.array([0.0, 0.0, 1.0]), yaw)
            side_axis = normalize(np.cross(np.array([0.0, 0.0, 1.0]), rotated))
            if np.linalg.norm(side_axis) < 1.0e-9:
                side_axis = np.array([1.0, 0.0, 0.0], dtype=np.float64)
            rotated = rotate_about_axis(rotated, side_axis, pitch)
            T_base_camera = look_at_camera_pose(board_center + radius * rotated, board_center)
            T_base_tcp = T_base_camera @ np.linalg.inv(self.T_tcp_camera)
            candidates.append(T_base_tcp)

        candidates.sort(key=lambda pose: np.linalg.norm(pose[:3, 3] - T_base_tcp_current[:3, 3]))
        return candidates[:sample_count]

    def select_next_target(self, targets, current_pose, visited_positions):
        current_position = current_pose[:3, 3]
        for target in targets:
            target_position = target[:3, 3]
            if np.linalg.norm(target_position - current_position) < 0.015:
                continue
            if any(np.linalg.norm(target_position - visited) < 0.025 for visited in visited_positions):
                continue
            return target
        return targets[0]

    def send_pose_goal(self, T_base_tcp):
        if not self.action_client.wait_for_server(timeout_sec=3.0):
            self.get_logger().error(f"Action server not available: {self.action_name}")
            return False

        goal = JparseMove.Goal()
        goal.mode = "task_space"
        goal.accuracy = "approach"
        goal.target_pose = pose_stamped_from_matrix(T_base_tcp, self.planning_frame, self.get_clock().now().to_msg())
        goal.max_linear_velocity = float(self.get_parameter("max_linear_velocity").value)
        goal.max_angular_velocity = float(self.get_parameter("max_angular_velocity").value)
        goal.timeout = float(self.get_parameter("move_timeout").value)

        future = self.action_client.send_goal_async(goal)
        wait_for_future(future)
        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            return False
        result_future = goal_handle.get_result_async()
        wait_for_future(result_future)
        result = result_future.result().result
        self.get_logger().info(
            f"Move result: success={result.success}, message={result.message}, "
            f"pos_err={result.final_position_error:.4f}, ori_err={result.final_orientation_error:.4f}"
        )
        return bool(result.success)

    def save_sample(self, observation):
        base = f"{self.sample_prefix}_{self.sample_idx:03d}"
        base_path = os.path.join(self.output_dir, base)
        raw_path = base_path + "_raw.png"
        annotated_path = base_path + "_annotated.png"
        camera_info_path = base_path + "_camera_info.yaml"
        sample_path = base_path + ".json"

        image = observation["image"].copy()
        detection = observation["detection"]
        cv2.imwrite(raw_path, image)
        cv2.imwrite(
            annotated_path,
            self.detector.draw_detection(
                image,
                detection,
                observation["camera_matrix"],
                observation["distortion_coeffs"],
            ),
        )
        self.write_camera_info(camera_info_path, observation["camera_info"])

        pose = detection["pose"]
        data = {
            "sample_id": base,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "image_file": os.path.basename(raw_path),
            "rectified_image_file": None,
            "annotated_image_file": os.path.basename(annotated_path),
            "camera_info_file": os.path.basename(camera_info_path),
            "camera_frame": observation["camera_info"].header.frame_id,
            "robot_pose": observation["robot_pose"],
            "board_model": self.detector.board_metadata(),
            "detection": {
                "ok": True,
                "num_markers": int(detection["num_markers"]),
                "num_charuco_corners": int(detection["num_charuco_corners"]),
                "marker_ids": [
                    int(value) for value in detection["marker_ids"].flatten()
                ],
                "charuco_ids": [
                    int(value) for value in detection["charuco_ids"].flatten()
                ],
                "roi": None if detection["roi"] is None else list(detection["roi"]),
                "pose": {
                    "markers_used": int(pose["markers_used"]),
                    "rvec": np.asarray(pose["rvec"]).flatten().astype(float).tolist(),
                    "tvec": np.asarray(pose["tvec"]).flatten().astype(float).tolist(),
                },
                "reprojection_error_px": detection["reprojection_error_px"],
            },
        }
        with open(sample_path, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
        self.get_logger().info(f"Saved {sample_path}")
        self.sample_idx += 1

    def recompute_handeye(self):
        records, skipped = load_samples(self.output_dir, f"{self.sample_prefix}_*.json")
        if len(records) < 3:
            self.get_logger().info(f"Hand-eye estimate waits for >=3 samples ({len(records)} now).")
            return
        method = self.get_parameter("handeye_method").value
        result = calibrate(records, method)
        if not np.all(np.isfinite(result["T_tcp_camera"])):
            self.get_logger().warn("Hand-eye estimate is non-finite; keeping previous estimate.")
            return
        self.T_tcp_camera = result["T_tcp_camera"]
        residuals = board_pose_residuals(records, self.T_tcp_camera)
        worst = residuals[0]
        self.get_logger().info(
            "Updated tcp<-camera: "
            f"t={np.round(self.T_tcp_camera[:3, 3], 5).tolist()}, "
            f"worst_mean={worst['translation_mean_m'] * 1000.0:.1f} mm, "
            f"{worst['rotation_mean_deg']:.2f} deg; skipped={len(skipped)}"
        )
        self.write_session_state()

    def write_session_state(self):
        path = os.path.join(self.output_dir, "semi_auto_session_state.yaml")
        q = quaternion_from_matrix(self.T_tcp_camera[:3, :3])
        data = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "robot_base_frame": self.robot_base_frame,
            "robot_tcp_frame": self.robot_tcp_frame,
            "planning_frame": self.planning_frame,
            "action_name": self.action_name,
            "move_enabled": self.move_enabled,
            "tcp_camera_estimate": {
                "translation_m": self.T_tcp_camera[:3, 3].astype(float).tolist(),
                "quaternion_xyzw": q.astype(float).tolist(),
                "matrix": self.T_tcp_camera.reshape(-1).astype(float).tolist(),
            },
            "base_board_estimate": None
            if self.T_base_board is None
            else self.T_base_board.reshape(-1).astype(float).tolist(),
        }
        with open(path, "w", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, sort_keys=False)

    def camera_model(self, msg):
        k = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        d = np.array(msg.d, dtype=np.float64)
        if d.size == 0:
            d = np.zeros((5, 1), dtype=np.float64)
        return k, d

    def write_camera_info(self, path, msg):
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

    def _sphere_radius(self, T_base_tcp):
        configured = float(self.get_parameter("sphere_radius_m").value)
        if configured > 0.0:
            return configured
        board_center = self.T_base_board[:3, 3]
        camera_center = (T_base_tcp @ self.T_tcp_camera)[:3, 3]
        return float(np.linalg.norm(camera_center - board_center))

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
        return 0 if not indices else max(indices) + 1

    def _param_or_default(self, name, default):
        value = str(self.get_parameter(name).value)
        return default if value == "" else value

    def print_target(self, index, total, T_base_tcp):
        q = quaternion_from_matrix(T_base_tcp[:3, :3])
        p = T_base_tcp[:3, 3]
        print(f"Target {index}/{total} in {self.planning_frame}")
        print(f"  position:    x={p[0]: .4f} y={p[1]: .4f} z={p[2]: .4f}")
        print(f"  quaternion:  x={q[0]: .5f} y={q[1]: .5f} z={q[2]: .5f} w={q[3]: .5f}")

    def prompt(self, text, allowed):
        allowed = set(allowed)
        while rclpy.ok():
            answer = input(text).strip().lower()
            if answer == "" and "n" in allowed:
                answer = "n"
            if answer in allowed:
                return answer
            print(f"Allowed: {', '.join(sorted(allowed))}")
        return "q"


def normalize(vector):
    vector = np.asarray(vector, dtype=np.float64)
    norm = np.linalg.norm(vector)
    if norm < 1.0e-9:
        return np.array([1.0, 0.0, 0.0], dtype=np.float64)
    return vector / norm


def slew_vector(current, target, max_delta):
    current = np.asarray(current, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    delta = target - current
    delta_norm = np.linalg.norm(delta)
    if delta_norm <= max_delta or delta_norm < 1.0e-12:
        return target.copy()
    return current + delta * (max_delta / delta_norm)


def rotate_about_axis(vector, axis, angle):
    axis = normalize(axis)
    vector = np.asarray(vector, dtype=np.float64)
    return (
        vector * math.cos(angle)
        + np.cross(axis, vector) * math.sin(angle)
        + axis * np.dot(axis, vector) * (1.0 - math.cos(angle))
    )


def look_at_camera_pose(camera_position, target_position):
    camera_position = np.asarray(camera_position, dtype=np.float64)
    target_position = np.asarray(target_position, dtype=np.float64)
    z_axis = normalize(target_position - camera_position)
    world_down = np.array([0.0, 0.0, -1.0], dtype=np.float64)
    x_axis = normalize(np.cross(world_down, z_axis))
    if np.linalg.norm(x_axis) < 1.0e-9:
        x_axis = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    y_axis = normalize(np.cross(z_axis, x_axis))

    T = np.eye(4, dtype=np.float64)
    T[:3, 0] = x_axis
    T[:3, 1] = y_axis
    T[:3, 2] = z_axis
    T[:3, 3] = camera_position
    return T


def pose_stamped_from_matrix(T, frame_id, stamp):
    msg = PoseStamped()
    msg.header.frame_id = frame_id
    msg.header.stamp = stamp
    msg.pose.position.x = float(T[0, 3])
    msg.pose.position.y = float(T[1, 3])
    msg.pose.position.z = float(T[2, 3])
    q = quaternion_from_matrix(T[:3, :3])
    msg.pose.orientation.x = float(q[0])
    msg.pose.orientation.y = float(q[1])
    msg.pose.orientation.z = float(q[2])
    msg.pose.orientation.w = float(q[3])
    return msg


def wait_for_future(future):
    while rclpy.ok() and not future.done():
        time.sleep(0.02)


def main(args=None):
    rclpy.init(args=args)
    node = SemiAutoHandeyeSession()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    try:
        node.run_session()
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
