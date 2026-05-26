#!/usr/bin/env python3
import argparse
import glob
import json
import math
import os
from datetime import datetime

import cv2
import numpy as np
import yaml


HAND_EYE_METHODS = {
    "tsai": cv2.CALIB_HAND_EYE_TSAI,
    "park": cv2.CALIB_HAND_EYE_PARK,
    "horaud": cv2.CALIB_HAND_EYE_HORAUD,
    "andreff": cv2.CALIB_HAND_EYE_ANDREFF,
    "daniilidis": cv2.CALIB_HAND_EYE_DANIILIDIS,
}


def main():
    args = parse_args()
    samples_dir = os.path.expanduser(args.samples_dir)
    records, skipped = load_samples(samples_dir, args.pattern)

    print(f"Samples directory: {samples_dir}")
    print(f"Usable samples: {len(records)}")
    if skipped:
        print("Skipped samples:")
        for item in skipped:
            print(f"  {item['sample_id']}: {item['reason']}")

    if len(records) < 3:
        print("Need at least 3 usable samples with detection pose and robot TF.")
        return 2

    duplicate_pairs = find_duplicate_robot_poses(records)
    if duplicate_pairs:
        print("Warning: very similar robot poses detected:")
        for a, b in duplicate_pairs:
            print(f"  {records[a].sample_id} <-> {records[b].sample_id}")

    try:
        result = calibrate(records, args.method)
    except cv2.error as exc:
        print(f"OpenCV hand-eye calibration failed: {exc}")
        return 3

    if not np.all(np.isfinite(result["T_tcp_camera"])):
        print("Calibration returned non-finite values. Add more diverse robot poses.")
        return 4

    residuals = board_pose_residuals(records, result["T_tcp_camera"])
    print_result(result, residuals)

    if args.output:
        output_path = os.path.expanduser(args.output)
    elif args.no_save:
        output_path = None
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(samples_dir, f"handeye_result_{stamp}.yaml")

    if output_path is not None:
        save_result(output_path, args, records, result, residuals, skipped)
        print(f"Saved result: {output_path}")

    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute OAK-to-UR-TCP hand-eye calibration from saved samples."
    )
    parser.add_argument(
        "--samples-dir",
        default="~/oak_handeye_samples",
        help="Directory containing sample_*.json files.",
    )
    parser.add_argument(
        "--pattern",
        default="sample_*.json",
        help="Glob pattern inside samples-dir.",
    )
    parser.add_argument(
        "--method",
        choices=sorted(HAND_EYE_METHODS),
        default="tsai",
        help="OpenCV hand-eye method.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional YAML output path.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Print only, do not write a result YAML.",
    )
    return parser.parse_args()


class SampleRecord:
    def __init__(self, sample_id, path, data, T_base_tcp, T_camera_target):
        self.sample_id = sample_id
        self.path = path
        self.data = data
        self.T_base_tcp = T_base_tcp
        self.T_camera_target = T_camera_target

    @property
    def reprojection_mean_px(self):
        reprojection = self.data["detection"].get("reprojection_error_px") or {}
        return reprojection.get("mean")


def load_samples(samples_dir, pattern):
    records = []
    skipped = []
    for path in sorted(glob.glob(os.path.join(samples_dir, pattern))):
        sample_id = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            record = sample_from_data(sample_id, path, data)
        except (KeyError, TypeError, ValueError) as exc:
            skipped.append({"sample_id": sample_id, "reason": str(exc)})
            continue

        if isinstance(record, str):
            skipped.append({"sample_id": sample_id, "reason": record})
            continue
        records.append(record)
    return records, skipped


def sample_from_data(sample_id, path, data):
    detection = data.get("detection") or {}
    if not detection.get("ok"):
        return "detection not ok"
    pose = detection.get("pose")
    if not pose:
        return "missing board pose"

    robot_pose = data.get("robot_pose") or data.get("robot_transform")
    if not robot_pose or not robot_pose.get("ok", True):
        return "missing robot TF pose"

    T_base_tcp = transform_from_translation_quaternion(
        robot_pose["translation"],
        robot_pose["quaternion_xyzw"],
    )
    T_camera_target = transform_from_rvec_tvec(pose["rvec"], pose["tvec"])
    return SampleRecord(sample_id, path, data, T_base_tcp, T_camera_target)


def calibrate(records, method):
    R_gripper2base = []
    t_gripper2base = []
    R_target2cam = []
    t_target2cam = []

    for record in records:
        R_gripper2base.append(record.T_base_tcp[:3, :3])
        t_gripper2base.append(record.T_base_tcp[:3, 3])
        R_target2cam.append(record.T_camera_target[:3, :3])
        t_target2cam.append(record.T_camera_target[:3, 3])

    R_tcp_camera, t_tcp_camera = cv2.calibrateHandEye(
        R_gripper2base,
        t_gripper2base,
        R_target2cam,
        t_target2cam,
        method=HAND_EYE_METHODS[method],
    )
    T_tcp_camera = np.eye(4, dtype=np.float64)
    T_tcp_camera[:3, :3] = np.asarray(R_tcp_camera, dtype=np.float64)
    T_tcp_camera[:3, 3] = np.asarray(t_tcp_camera, dtype=np.float64).reshape(3)
    return {
        "method": method,
        "T_tcp_camera": T_tcp_camera,
        "translation_m": T_tcp_camera[:3, 3].tolist(),
        "quaternion_xyzw": quaternion_from_matrix(T_tcp_camera[:3, :3]).tolist(),
    }


def board_pose_residuals(records, T_tcp_camera):
    board_poses = [
        record.T_base_tcp @ T_tcp_camera @ record.T_camera_target for record in records
    ]
    residuals = []
    for i, pose_i in enumerate(board_poses):
        trans_errors = []
        rot_errors = []
        for j, pose_j in enumerate(board_poses):
            if i == j:
                continue
            delta = np.linalg.inv(pose_i) @ pose_j
            trans_errors.append(np.linalg.norm(delta[:3, 3]))
            rot_errors.append(rotation_angle(delta[:3, :3]))

        residuals.append(
            {
                "sample_id": records[i].sample_id,
                "translation_mean_m": float(np.mean(trans_errors)),
                "translation_max_m": float(np.max(trans_errors)),
                "rotation_mean_deg": float(math.degrees(np.mean(rot_errors))),
                "rotation_max_deg": float(math.degrees(np.max(rot_errors))),
                "reprojection_mean_px": records[i].reprojection_mean_px,
            }
        )
    residuals.sort(
        key=lambda item: (item["translation_mean_m"], item["rotation_mean_deg"]),
        reverse=True,
    )
    return residuals


def find_duplicate_robot_poses(records):
    duplicates = []
    for i, first in enumerate(records):
        for j in range(i + 1, len(records)):
            second = records[j]
            delta = np.linalg.inv(first.T_base_tcp) @ second.T_base_tcp
            trans_m = np.linalg.norm(delta[:3, 3])
            rot_deg = math.degrees(rotation_angle(delta[:3, :3]))
            if trans_m < 0.001 and rot_deg < 0.1:
                duplicates.append((i, j))
    return duplicates


def print_result(result, residuals):
    T = result["T_tcp_camera"]
    print("")
    print("Estimated transform: tcp <- camera")
    print("translation_m:")
    print(f"  x: {T[0, 3]: .6f}")
    print(f"  y: {T[1, 3]: .6f}")
    print(f"  z: {T[2, 3]: .6f}")
    q = result["quaternion_xyzw"]
    print("quaternion_xyzw:")
    print(f"  x: {q[0]: .6f}")
    print(f"  y: {q[1]: .6f}")
    print(f"  z: {q[2]: .6f}")
    print(f"  w: {q[3]: .6f}")

    print("")
    print("Per-sample consistency against the other samples:")
    print(
        "  sample        trans_mean_mm  trans_max_mm  rot_mean_deg  rot_max_deg  reproj_px"
    )
    for item in residuals:
        reproj = item["reprojection_mean_px"]
        reproj_text = "n/a" if reproj is None else f"{reproj:7.3f}"
        print(
            f"  {item['sample_id']:<12}"
            f"{item['translation_mean_m'] * 1000.0:14.2f}"
            f"{item['translation_max_m'] * 1000.0:14.2f}"
            f"{item['rotation_mean_deg']:14.3f}"
            f"{item['rotation_max_deg']:13.3f}"
            f"  {reproj_text}"
        )


def save_result(path, args, records, result, residuals, skipped):
    first_robot_pose = records[0].data.get("robot_pose") or {}
    data = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "method": result["method"],
        "sample_count": len(records),
        "samples": [record.sample_id for record in records],
        "skipped_samples": skipped,
        "transform": {
            "parent_frame": first_robot_pose.get("child_frame", "tool0"),
            "child_frame": records[0].data.get(
                "camera_frame", "oak_rgb_camera_optical_frame"
            ),
            "translation_m": [float(value) for value in result["translation_m"]],
            "quaternion_xyzw": [
                float(value) for value in result["quaternion_xyzw"]
            ],
            "matrix": result["T_tcp_camera"].reshape(-1).astype(float).tolist(),
        },
        "residuals": residuals,
        "command": {
            "samples_dir": args.samples_dir,
            "pattern": args.pattern,
            "method": args.method,
        },
    }
    with open(path, "w", encoding="utf-8") as stream:
        yaml.safe_dump(data, stream, sort_keys=False)


def transform_from_rvec_tvec(rvec, tvec):
    R, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64).reshape(3, 1))
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = np.asarray(tvec, dtype=np.float64).reshape(3)
    return T


def transform_from_translation_quaternion(translation, quaternion_xyzw):
    T = np.eye(4, dtype=np.float64)
    T[:3, 3] = np.asarray(translation, dtype=np.float64).reshape(3)
    T[:3, :3] = matrix_from_quaternion(quaternion_xyzw)
    return T


def matrix_from_quaternion(quaternion_xyzw):
    x, y, z, w = np.asarray(quaternion_xyzw, dtype=np.float64).reshape(4)
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm == 0.0:
        raise ValueError("zero-length robot quaternion")
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def quaternion_from_matrix(R):
    trace = np.trace(R)
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    q = np.array([x, y, z, w], dtype=np.float64)
    return q / np.linalg.norm(q)


def rotation_angle(R):
    value = (np.trace(R) - 1.0) * 0.5
    return math.acos(float(np.clip(value, -1.0, 1.0)))


if __name__ == "__main__":
    raise SystemExit(main())
