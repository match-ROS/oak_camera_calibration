import cv2
import numpy as np


ARUCO_DICTIONARIES = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
}


class ArucoGridDetector:
    def __init__(
        self,
        markers_x=10,
        markers_y=7,
        marker_length_m=0.030,
        marker_separation_m=0.010,
        dictionary_name="DICT_4X4_250",
        coarse_max_side=1600,
        refine_max_side=2000,
        roi_margin_ratio=0.20,
        roi_margin_px=80,
        subpix_window=5,
    ):
        self.markers_x = int(markers_x)
        self.markers_y = int(markers_y)
        self.marker_length_m = float(marker_length_m)
        self.marker_separation_m = float(marker_separation_m)
        self.dictionary_name = dictionary_name.upper()
        self.coarse_max_side = int(coarse_max_side)
        self.refine_max_side = int(refine_max_side)
        self.roi_margin_ratio = float(roi_margin_ratio)
        self.roi_margin_px = int(roi_margin_px)
        self.subpix_window = int(subpix_window)

        if self.dictionary_name not in ARUCO_DICTIONARIES:
            raise ValueError(f"Unsupported ArUco dictionary: {dictionary_name}")

        self.dictionary = cv2.aruco.getPredefinedDictionary(
            ARUCO_DICTIONARIES[self.dictionary_name]
        )
        self.parameters = self._create_detector_parameters()
        self.board = self._create_board()

    def board_metadata(self):
        return {
            "type": "aruco_grid_board",
            "markers_x": self.markers_x,
            "markers_y": self.markers_y,
            "marker_length_m": self.marker_length_m,
            "marker_separation_m": self.marker_separation_m,
            "dictionary": self.dictionary_name,
        }

    def detect(self, image_bgr, camera_matrix=None, distortion_coeffs=None):
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        image_h, image_w = gray.shape[:2]

        coarse = self._detect_scaled(gray, self.coarse_max_side)
        if coarse["ids"] is None or len(coarse["ids"]) == 0:
            return self._result(None, None, None, image_w, image_h, None)

        coarse_corners = self._scale_corners(coarse["corners"], 1.0 / coarse["scale"])
        roi = self._roi_from_corners(coarse_corners, image_w, image_h)
        x, y, w, h = roi
        roi_gray = gray[y : y + h, x : x + w]

        refined = self._detect_scaled(roi_gray, self.refine_max_side)
        if refined["ids"] is None or len(refined["ids"]) == 0:
            corners = coarse_corners
            ids = coarse["ids"]
            used_roi = None
        else:
            corners = self._scale_corners(refined["corners"], 1.0 / refined["scale"])
            corners = self._offset_corners(corners, x, y)
            corners = self._refine_subpix(gray, corners)
            ids = refined["ids"]
            used_roi = roi

        corners, ids = self._filter_board_ids(corners, ids)

        pose = None
        reprojection_error = None
        if camera_matrix is not None and ids is not None and len(ids) >= 4:
            pose = self._estimate_pose(corners, ids, camera_matrix, distortion_coeffs)
            if pose is not None:
                reprojection_error = self._reprojection_error(
                    corners,
                    ids,
                    pose["rvec"],
                    pose["tvec"],
                    camera_matrix,
                    distortion_coeffs,
                )

        return self._result(corners, ids, pose, image_w, image_h, used_roi, reprojection_error)

    def draw_detection(self, image_bgr, detection, camera_matrix=None, distortion_coeffs=None):
        view = image_bgr.copy()
        if detection is None or detection["marker_ids"] is None:
            return view

        cv2.aruco.drawDetectedMarkers(
            view,
            detection["marker_corners"],
            detection["marker_ids"],
        )

        pose = detection.get("pose")
        if pose is not None and camera_matrix is not None:
            d = self._distortion_array(distortion_coeffs)
            cv2.drawFrameAxes(
                view,
                camera_matrix,
                d,
                pose["rvec"],
                pose["tvec"],
                self.marker_length_m * 2.0,
            )

        roi = detection.get("roi")
        if roi is not None:
            x, y, w, h = roi
            cv2.rectangle(view, (x, y), (x + w, y + h), (0, 180, 255), 3)

        return view

    def _create_detector_parameters(self):
        if hasattr(cv2.aruco, "DetectorParameters_create"):
            return cv2.aruco.DetectorParameters_create()
        return cv2.aruco.DetectorParameters()

    def _create_board(self):
        if hasattr(cv2.aruco, "GridBoard_create"):
            return cv2.aruco.GridBoard_create(
                self.markers_x,
                self.markers_y,
                self.marker_length_m,
                self.marker_separation_m,
                self.dictionary,
            )
        return cv2.aruco.GridBoard(
            (self.markers_x, self.markers_y),
            self.marker_length_m,
            self.marker_separation_m,
            self.dictionary,
        )

    def _detect_scaled(self, gray, max_side):
        h, w = gray.shape[:2]
        scale = min(1.0, float(max_side) / float(max(h, w)))
        if scale < 1.0:
            detect_image = cv2.resize(
                gray,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_AREA,
            )
        else:
            detect_image = gray

        corners, ids, rejected = cv2.aruco.detectMarkers(
            detect_image,
            self.dictionary,
            parameters=self.parameters,
        )
        return {
            "corners": corners,
            "ids": ids,
            "rejected": rejected,
            "scale": scale,
        }

    def _scale_corners(self, corners, scale):
        return [(corner.astype(np.float32) * scale) for corner in corners]

    def _offset_corners(self, corners, offset_x, offset_y):
        offset = np.array([offset_x, offset_y], dtype=np.float32)
        return [(corner.astype(np.float32) + offset) for corner in corners]

    def _roi_from_corners(self, corners, image_w, image_h):
        points = np.concatenate([corner.reshape(-1, 2) for corner in corners], axis=0)
        x_min, y_min = np.min(points, axis=0)
        x_max, y_max = np.max(points, axis=0)

        box_w = x_max - x_min
        box_h = y_max - y_min
        margin = max(
            self.roi_margin_px,
            int(max(box_w, box_h) * self.roi_margin_ratio),
        )

        x = max(0, int(np.floor(x_min)) - margin)
        y = max(0, int(np.floor(y_min)) - margin)
        x2 = min(image_w, int(np.ceil(x_max)) + margin)
        y2 = min(image_h, int(np.ceil(y_max)) + margin)
        return (x, y, x2 - x, y2 - y)

    def _refine_subpix(self, gray, corners):
        if self.subpix_window <= 0 or not corners:
            return corners

        points = np.concatenate([corner.reshape(-1, 2) for corner in corners], axis=0)
        points = points.astype(np.float32).reshape(-1, 1, 2)
        criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30,
            0.01,
        )
        cv2.cornerSubPix(
            gray,
            points,
            (self.subpix_window, self.subpix_window),
            (-1, -1),
            criteria,
        )

        refined = []
        idx = 0
        for corner in corners:
            count = corner.reshape(-1, 2).shape[0]
            refined.append(points[idx : idx + count].reshape(corner.shape))
            idx += count
        return refined

    def _filter_board_ids(self, corners, ids):
        if ids is None or corners is None:
            return corners, ids

        max_id = self.markers_x * self.markers_y
        keep = [
            index
            for index, marker_id in enumerate(ids.flatten())
            if 0 <= int(marker_id) < max_id
        ]
        if len(keep) == len(ids):
            return corners, ids

        filtered_corners = [corners[index] for index in keep]
        filtered_ids = ids[keep].reshape(-1, 1).astype(ids.dtype)
        return filtered_corners, filtered_ids

    def _estimate_pose(self, corners, ids, camera_matrix, distortion_coeffs):
        d = self._distortion_array(distortion_coeffs)
        ok, rvec, tvec = cv2.aruco.estimatePoseBoard(
            corners,
            ids,
            self.board,
            camera_matrix,
            d,
            None,
            None,
        )
        if not ok:
            return None
        return {
            "markers_used": int(ok),
            "rvec": rvec,
            "tvec": tvec,
        }

    def _reprojection_error(
        self,
        corners,
        ids,
        rvec,
        tvec,
        camera_matrix,
        distortion_coeffs,
    ):
        d = self._distortion_array(distortion_coeffs)
        object_points, image_points = cv2.aruco.getBoardObjectAndImagePoints(
            self.board,
            corners,
            ids,
        )
        projected, _ = cv2.projectPoints(
            object_points,
            rvec,
            tvec,
            camera_matrix,
            d,
        )
        projected = projected.reshape(-1, 2)
        image_points = image_points.reshape(-1, 2)
        errors = np.linalg.norm(projected - image_points, axis=1)
        return {
            "mean": float(np.mean(errors)),
            "median": float(np.median(errors)),
            "max": float(np.max(errors)),
        }

    def _distortion_array(self, distortion_coeffs):
        if distortion_coeffs is None:
            return np.zeros((5, 1), dtype=np.float64)
        d = np.array(distortion_coeffs, dtype=np.float64).reshape(-1, 1)
        if d.size == 0:
            return np.zeros((5, 1), dtype=np.float64)
        return d

    def _result(
        self,
        corners,
        ids,
        pose,
        image_w,
        image_h,
        roi,
        reprojection_error=None,
    ):
        return {
            "marker_corners": corners,
            "marker_ids": ids,
            "num_markers": 0 if ids is None else int(len(ids)),
            "pose": pose,
            "reprojection_error_px": reprojection_error,
            "image_width": int(image_w),
            "image_height": int(image_h),
            "roi": None if roi is None else tuple(int(v) for v in roi),
            "board": self.board_metadata(),
        }
