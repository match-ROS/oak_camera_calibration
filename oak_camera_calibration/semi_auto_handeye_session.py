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
        self.declare_parameter("square_length_m", 0.020)
        self.declare_parameter("marker_length_m", 0.015)
        self.declare_parameter("dictionary", "DICT_5X5_100")
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

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.action_client = ActionClient(self, JparseMove, self.action_name)
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

    def run_session(self):
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
