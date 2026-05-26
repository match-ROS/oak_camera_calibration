#!/usr/bin/env python3
import os
import json
import glob
import re
import cv2
import rospy
import tf
import numpy as np
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from oak_camera_calibration.old.charuco_board import board_metadata, estimate_charuco_pose


class SampleCapture:
    def __init__(self):
        rospy.init_node("handeye_sample_capture")

        self.bridge = CvBridge()
        self.listener = tf.TransformListener()
        self.latest_image = None
        self.sample_idx = 0

        self.image_topic = "/zedm/zed_node/left/image_rect_color"
        self.image_sub = rospy.Subscriber(self.image_topic, Image, self.image_cb, queue_size=1)

        self.output_dir = os.path.expanduser("~/handeye_samples")
        os.makedirs(self.output_dir, exist_ok=True)
        self.sample_idx = self.next_sample_idx()

        self.K = np.array([
            [366.14324951171875, 0.0, 322.98895263671875],
            [0.0, 366.14324951171875, 180.08743286132812],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)

        self.D = np.array([0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)

    def next_sample_idx(self):
        indices = []
        for path in glob.glob(os.path.join(self.output_dir, "sample_*.json")):
            match = re.search(r"sample_(\d+)\.json$", os.path.basename(path))
            if match:
                indices.append(int(match.group(1)))

        if not indices:
            return 0

        return max(indices) + 1

    def image_cb(self, msg):
        self.latest_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")

    def estimate_board_pose(self, image):
        detection = estimate_charuco_pose(image, self.K, self.D)
        if detection is None:
            return None

        return {
            "num_markers": int(len(detection["marker_ids"])),
            "num_charuco_corners": int(len(detection["charuco_ids"])),
            "reprojection_error_px": detection["reprojection_error_px"],
            "rvec": detection["rvec"].flatten().tolist(),
            "tvec": detection["tvec"].flatten().tolist(),
        }

    def get_tool_pose(self):
        self.listener.waitForTransform("base_link", "tool0", rospy.Time(0), rospy.Duration(1.0))
        trans, rot = self.listener.lookupTransform("base_link", "tool0", rospy.Time(0))
        return {
            "translation": list(trans),
            "quaternion": list(rot),
        }

    def run(self):
        rospy.sleep(1.0)
        print("Press 's' to save one sample, 'q' to quit.")

        while not rospy.is_shutdown():
            if self.latest_image is None:
                rospy.sleep(0.1)
                continue

            view = self.latest_image.copy()
            detection = estimate_charuco_pose(view, self.K, self.D)
            if detection is not None:
                cv2.aruco.drawDetectedMarkers(
                    view,
                    detection["marker_corners"],
                    detection["marker_ids"],
                )
                cv2.aruco.drawDetectedCornersCharuco(
                    view,
                    detection["charuco_corners"],
                    detection["charuco_ids"],
                )
                cv2.drawFrameAxes(
                    view,
                    self.K,
                    self.D,
                    detection["rvec"],
                    detection["tvec"],
                    0.05,
                )
            cv2.imshow("handeye_capture", view)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                break

            if key == ord('s'):
                image = self.latest_image.copy()

                try:
                    tool_pose = self.get_tool_pose()
                except Exception as e:
                    print("TF error:", e)
                    continue

                board_pose = self.estimate_board_pose(image)
                if board_pose is None:
                    print("Board pose could not be estimated")
                    continue

                image_name = f"sample_{self.sample_idx:03d}.jpg"
                json_name = f"sample_{self.sample_idx:03d}.json"

                cv2.imwrite(os.path.join(self.output_dir, image_name), image)

                data = {
                    "image_file": image_name,
                    "board_model": board_metadata(),
                    "camera_frame": "zedm_left_camera_optical_frame",
                    "tool_frame": "tool0",
                    "tool_pose": tool_pose,
                    "board_pose": board_pose,
                }

                with open(os.path.join(self.output_dir, json_name), "w") as f:
                    json.dump(data, f, indent=2)

                print(f"Saved sample {self.sample_idx:03d} with {board_pose['num_markers']} markers")
                print(
                    "  ChArUco corners: {num_charuco_corners}, reprojection mean: {mean:.2f}px".format(
                        num_charuco_corners=board_pose["num_charuco_corners"],
                        mean=board_pose["reprojection_error_px"]["mean"],
                    )
                )
                self.sample_idx += 1

        cv2.destroyAllWindows()

if __name__ == "__main__":
    SampleCapture().run()
