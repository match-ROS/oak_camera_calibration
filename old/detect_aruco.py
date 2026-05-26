import cv2
import numpy as np
from oak_camera_calibration.old.charuco_board import estimate_charuco_pose

image_path = "left0000.jpg"

img = cv2.imread(image_path)
if img is None:
    raise RuntimeError(f"Could not load image: {image_path}")

# Camera intrinsics
K = np.array([
    [366.14324951171875, 0.0, 322.98895263671875],
    [0.0, 366.14324951171875, 180.08743286132812],
    [0.0, 0.0, 1.0]
], dtype=np.float64)

D = np.array([0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)

pose = estimate_charuco_pose(img, K, D)
if pose is None:
    print("No valid ChArUco pose detected")
    raise SystemExit

ids = pose["marker_ids"].flatten()
print("Detected marker IDs:")
print(ids.tolist())
print("Number of markers:", len(ids))
print("Number of ChArUco corners:", len(pose["charuco_ids"]))
print("Reprojection error [px]:", pose["reprojection_error_px"])
print("rvec:\n", pose["rvec"])
print("tvec:\n", pose["tvec"])

out = img.copy()
cv2.aruco.drawDetectedMarkers(out, pose["marker_corners"], pose["marker_ids"])
cv2.aruco.drawDetectedCornersCharuco(out, pose["charuco_corners"], pose["charuco_ids"])
cv2.drawFrameAxes(out, K, D, pose["rvec"], pose["tvec"], 0.05)

cv2.imshow("pose", out)
cv2.waitKey(0)
cv2.destroyAllWindows()
