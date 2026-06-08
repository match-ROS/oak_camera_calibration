#!/usr/bin/env python3
import time

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import TwistStamped
from rclpy.node import Node


class RobotJogGui(Node):
    def __init__(self):
        super().__init__("robot_jog_gui")

        self.declare_parameter("robot_name", "mur620")
        self.declare_parameter("arm", "r")
        self.declare_parameter("twist_topic", "")
        self.declare_parameter("jog_frame", "")
        self.declare_parameter("linear_velocity", 0.03)
        self.declare_parameter("angular_velocity", 0.25)
        self.declare_parameter("linear_acceleration", 0.12)
        self.declare_parameter("angular_acceleration", 1.0)
        self.declare_parameter("hold_timeout", 0.45)
        self.declare_parameter("publish_rate_hz", 50.0)
        self.declare_parameter("window_name", "mur620 robot jog")
        self.declare_parameter("log_key_codes", True)

        robot_name = str(self.get_parameter("robot_name").value)
        arm = str(self.get_parameter("arm").value)
        self.twist_topic = self.param_or_default(
            "twist_topic", f"/{robot_name}/jparse_velocity_controller_{arm}/twist_cmd"
        )
        self.jog_frame = self.param_or_default("jog_frame", f"UR10_{arm}/base_link")
        self.window_name = str(self.get_parameter("window_name").value)

        self.publisher = self.create_publisher(TwistStamped, self.twist_topic, 10)
        self.target_linear = np.zeros(3, dtype=np.float64)
        self.target_angular = np.zeros(3, dtype=np.float64)
        self.current_linear = np.zeros(3, dtype=np.float64)
        self.current_angular = np.zeros(3, dtype=np.float64)
        self.last_command_time = 0.0
        self.last_update_time = time.monotonic()
        self.rotation_mode = False
        self.last_key_text = "none"
        self.last_command_text = "idle"
        self.mouse_button_command = None
        self.buttons = []

        self.get_logger().info(
            f"Robot jog GUI publishing {self.twist_topic} in frame {self.jog_frame}"
        )

    def run(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self.on_mouse)
        try:
            while rclpy.ok():
                self.update_output()
                cv2.imshow(self.window_name, self.render())
                key = cv2.waitKeyEx(20)
                if key != -1 and not self.handle_key(key):
                    break
                rclpy.spin_once(self, timeout_sec=0.0)
        finally:
            self.stop()
            cv2.destroyWindow(self.window_name)

    def render(self):
        image = np.full((540, 760, 3), 34, dtype=np.uint8)
        self.buttons = []

        self.put_text(image, "Robot jog", (24, 42), scale=1.0, color=(255, 255, 255))
        self.put_text(image, f"topic: {self.twist_topic}", (24, 78))
        self.put_text(image, f"frame: {self.jog_frame}", (24, 106))
        self.put_text(
            image,
            f"mode: {'rotation' if self.rotation_mode else 'translation'}",
            (24, 134),
            color=(180, 230, 255),
        )
        self.put_text(image, f"last key: {self.last_key_text}", (24, 162))
        self.put_text(image, f"cmd: {self.last_command_text}", (24, 190))
        self.put_text(
            image,
            f"subscribers: {self.publisher.get_subscription_count()}",
            (24, 218),
            color=(180, 230, 180),
        )

        self.add_button(image, "Y+", (140, 270, 110, 58), [0, 1, 0], [0, 0, 0])
        self.add_button(image, "Y-", (140, 400, 110, 58), [0, -1, 0], [0, 0, 0])
        self.add_button(image, "X-", (25, 335, 110, 58), [-1, 0, 0], [0, 0, 0])
        self.add_button(image, "X+", (255, 335, 110, 58), [1, 0, 0], [0, 0, 0])
        self.add_button(image, "Z+", (410, 270, 110, 58), [0, 0, 1], [0, 0, 0])
        self.add_button(image, "Z-", (410, 400, 110, 58), [0, 0, -1], [0, 0, 0])

        self.add_button(image, "RX+", (565, 270, 74, 58), [0, 0, 0], [1, 0, 0])
        self.add_button(image, "RX-", (650, 270, 74, 58), [0, 0, 0], [-1, 0, 0])
        self.add_button(image, "RY+", (565, 335, 74, 58), [0, 0, 0], [0, 1, 0])
        self.add_button(image, "RY-", (650, 335, 74, 58), [0, 0, 0], [0, -1, 0])
        self.add_button(image, "RZ+", (565, 400, 74, 58), [0, 0, 0], [0, 0, 1])
        self.add_button(image, "RZ-", (650, 400, 74, 58), [0, 0, 0], [0, 0, -1])

        self.add_button(image, "STOP", (300, 470, 160, 48), [0, 0, 0], [0, 0, 0])

        self.put_text(
            image,
            "Keys: arrows XY, PgUp/PgDn Z, m toggles rot, i/k j/l u/o rot, space stop, q quit",
            (24, 525),
            scale=0.52,
            color=(220, 220, 220),
        )
        return image

    def add_button(self, image, label, rect, linear_unit, angular_unit):
        x, y, w, h = rect
        self.buttons.append((rect, np.array(linear_unit), np.array(angular_unit), label))
        active = (
            self.mouse_button_command == label
            or label == "STOP"
            and np.linalg.norm(self.target_linear) < 1.0e-9
            and np.linalg.norm(self.target_angular) < 1.0e-9
        )
        color = (70, 112, 155) if active else (64, 64, 64)
        cv2.rectangle(image, (x, y), (x + w, y + h), color, -1)
        cv2.rectangle(image, (x, y), (x + w, y + h), (170, 170, 170), 1)
        text_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
        tx = x + (w - text_size[0]) // 2
        ty = y + (h + text_size[1]) // 2
        self.put_text(image, label, (tx, ty), scale=0.75, thickness=2)

    def on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            for rect, linear_unit, angular_unit, label in self.buttons:
                bx, by, bw, bh = rect
                if bx <= x <= bx + bw and by <= y <= by + bh:
                    self.mouse_button_command = label
                    self.set_command(linear_unit, angular_unit, f"mouse {label}")
                    return
        if event in (cv2.EVENT_LBUTTONUP, cv2.EVENT_RBUTTONDOWN):
            self.mouse_button_command = None
            self.stop()

    def handle_key(self, key):
        name = self.key_name(key)
        char = self.ascii_char(key)
        self.last_key_text = f"{key} ({name or char or 'unknown'})"
        if bool(self.get_parameter("log_key_codes").value):
            self.get_logger().info(f"Jog GUI key: {self.last_key_text}")
        if char == "q" or key == 27:
            return False
        if char == " " or char == ".":
            self.stop()
            return True
        if char == "m":
            self.rotation_mode = not self.rotation_mode
            self.last_command_text = (
                f"mode {'rotation' if self.rotation_mode else 'translation'}"
            )
            return True

        linear, angular = self.command_from_key(name)
        if linear is not None:
            self.set_command(linear, angular, f"key {name}")
        return True

    def command_from_key(self, name):
        if name is None:
            return None, None
        zero = np.zeros(3, dtype=np.float64)
        translation = {
            "left": np.array([-1.0, 0.0, 0.0]),
            "right": np.array([1.0, 0.0, 0.0]),
            "up": np.array([0.0, 1.0, 0.0]),
            "down": np.array([0.0, -1.0, 0.0]),
            "page_up": np.array([0.0, 0.0, 1.0]),
            "page_down": np.array([0.0, 0.0, -1.0]),
            "a": np.array([-1.0, 0.0, 0.0]),
            "d": np.array([1.0, 0.0, 0.0]),
            "w": np.array([0.0, 1.0, 0.0]),
            "x": np.array([0.0, -1.0, 0.0]),
            "r": np.array([0.0, 0.0, 1.0]),
            "f": np.array([0.0, 0.0, -1.0]),
        }
        rotation = {
            "left": np.array([1.0, 0.0, 0.0]),
            "right": np.array([-1.0, 0.0, 0.0]),
            "up": np.array([0.0, 1.0, 0.0]),
            "down": np.array([0.0, -1.0, 0.0]),
            "page_up": np.array([0.0, 0.0, 1.0]),
            "page_down": np.array([0.0, 0.0, -1.0]),
            "j": np.array([1.0, 0.0, 0.0]),
            "l": np.array([-1.0, 0.0, 0.0]),
            "i": np.array([0.0, 1.0, 0.0]),
            "k": np.array([0.0, -1.0, 0.0]),
            "u": np.array([0.0, 0.0, 1.0]),
            "o": np.array([0.0, 0.0, -1.0]),
        }
        if name in ("i", "j", "k", "l", "u", "o") or self.rotation_mode:
            angular = rotation.get(name)
            if angular is None:
                return None, None
            return zero, angular
        linear = translation.get(name)
        if linear is None:
            return None, None
        return linear, zero

    def set_command(self, linear_unit, angular_unit, label):
        linear_speed = float(self.get_parameter("linear_velocity").value)
        angular_speed = float(self.get_parameter("angular_velocity").value)
        self.target_linear = np.asarray(linear_unit, dtype=np.float64) * linear_speed
        self.target_angular = np.asarray(angular_unit, dtype=np.float64) * angular_speed
        self.last_command_time = time.monotonic()
        self.last_command_text = (
            f"{label}: lin=[{self.target_linear[0]:.3f}, {self.target_linear[1]:.3f}, {self.target_linear[2]:.3f}] "
            f"ang=[{self.target_angular[0]:.3f}, {self.target_angular[1]:.3f}, {self.target_angular[2]:.3f}]"
        )

    def update_output(self):
        now = time.monotonic()
        dt = max(1.0e-4, now - self.last_update_time)
        self.last_update_time = now
        if self.mouse_button_command is not None:
            self.last_command_time = now
        if now - self.last_command_time > float(self.get_parameter("hold_timeout").value):
            self.target_linear = np.zeros(3, dtype=np.float64)
            self.target_angular = np.zeros(3, dtype=np.float64)

        self.current_linear = slew_vector(
            self.current_linear,
            self.target_linear,
            float(self.get_parameter("linear_acceleration").value) * dt,
        )
        self.current_angular = slew_vector(
            self.current_angular,
            self.target_angular,
            float(self.get_parameter("angular_acceleration").value) * dt,
        )
        if (
            np.linalg.norm(self.current_linear) > 1.0e-5
            or np.linalg.norm(self.current_angular) > 1.0e-5
            or np.linalg.norm(self.target_linear) > 1.0e-5
            or np.linalg.norm(self.target_angular) > 1.0e-5
        ):
            self.publish_twist(self.current_linear, self.current_angular)

    def publish_twist(self, linear, angular):
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.jog_frame
        msg.twist.linear.x = float(linear[0])
        msg.twist.linear.y = float(linear[1])
        msg.twist.linear.z = float(linear[2])
        msg.twist.angular.x = float(angular[0])
        msg.twist.angular.y = float(angular[1])
        msg.twist.angular.z = float(angular[2])
        self.publisher.publish(msg)

    def stop(self):
        self.target_linear = np.zeros(3, dtype=np.float64)
        self.target_angular = np.zeros(3, dtype=np.float64)
        self.current_linear = np.zeros(3, dtype=np.float64)
        self.current_angular = np.zeros(3, dtype=np.float64)
        self.last_command_text = "stopped"
        for _ in range(3):
            self.publish_twist(self.current_linear, self.current_angular)
            time.sleep(0.01)

    def key_name(self, key):
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
            0x01000012: "left",
            0x01000013: "up",
            0x01000014: "right",
            0x01000015: "down",
            0x01000016: "page_up",
            0x01000017: "page_down",
            0x250000: "left",
            0x260000: "up",
            0x270000: "right",
            0x280000: "down",
            0x210000: "page_up",
            0x220000: "page_down",
        }
        candidates = {
            key,
            key & 0xFFFF,
            key & 0xFFFFFF,
            key & 0x01FFFFFF,
            key & ~0x04000000,
            key & ~0x00100000,
            key & ~0x00040000,
        }
        for candidate in candidates:
            if candidate in arrow_codes:
                return arrow_codes[candidate]
        char = self.ascii_char(key)
        if char in ("w", "a", "d", "x", "r", "f", "i", "j", "k", "l", "u", "o"):
            return char
        return None

    def ascii_char(self, key):
        if 0 <= key < 128:
            return chr(key).lower()
        return ""

    def put_text(self, image, text, origin, scale=0.62, color=(255, 255, 255), thickness=1):
        cv2.putText(
            image,
            text,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (0, 0, 0),
            thickness + 2,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            text,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )

    def param_or_default(self, name, default):
        value = str(self.get_parameter(name).value)
        return default if value == "" else value


def slew_vector(current, target, max_delta):
    current = np.asarray(current, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    delta = target - current
    norm = np.linalg.norm(delta)
    if norm <= max_delta or norm < 1.0e-12:
        return target.copy()
    return current + delta * (max_delta / norm)


def main(args=None):
    rclpy.init(args=args)
    node = RobotJogGui()
    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
