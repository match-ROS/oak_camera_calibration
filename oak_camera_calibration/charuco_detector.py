import cv2
import numpy as np


ARUCO_DICTIONARIES = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
}


class CharucoDetector:
    def __init__(
        self,
        squares_x=14,
        squares_y=9,
        square_length_m=0.020,
        marker_length_m=0.015,
        dictionary_name="DICT_5X5_100",
        min_charuco_corners=8,
        coarse_max_side=1600,
        refine_max_side=2200,
        roi_margin_ratio=0.20,
        roi_margin_px=80,
    ):
        self.squares_x = int(squares_x)
        self.squares_y = int(squares_y)
        self.square_length_m = float(square_length_m)
        self.marker_length_m = float(marker_length_m)
        self.dictionary_name = dictionary_name.upper()
        self.min_charuco_corners = int(min_charuco_corners)
        self.coarse_max_side = int(coarse_max_side)
        self.refine_max_side = int(refine_max_side)
        self.roi_margin_ratio = float(roi_margin_ratio)
        self.roi_margin_px = int(roi_margin_px)

        if self.dictionary_name not in ARUCO_DICTIONARIES:
            raise ValueError(f"Unsupported ArUco dictionary: {dictionary_name}")

        self.dictionary = cv2.aruco.getPredefinedDictionary(
            ARUCO_DICTIONARIES[self.dictionary_name]
        )
        self.parameters = self._create_detector_parameters()
        self.board = self._create_board()

    def board_metadata(self):
        return {
            "type": "charuco_board",
            "squares_x": self.squares_x,
            "squares_y": self.squares_y,
            "square_length_m": self.square_length_m,
            "marker_length_m": self.marker_length_m,
            "dictionary": self.dictionary_name,
            "min_charuco_corners": self.min_charuco_corners,
        }

    def board_center_offset(self):
        corners = self._get_chessboard_corners()
        return np.mean(corners.reshape(-1, 3), axis=0).astype(np.float64)

    def detect(self, image_bgr, camera_matrix=None, distortion_coeffs=None):
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        image_h, image_w = gray.shape[:2]

        coarse = self._detect_scaled(gray, self.coarse_max_side)
        if coarse["ids"] is None or len(coarse["ids"]) == 0:
            rejected = self._scale_corners(coarse["rejected"], 1.0 / coarse["scale"])
            return self._result(
                None,
                None,
                None,
                None,
                None,
                image_w,
                image_h,
                None,
                rejected_corners=rejected,
            )

        coarse_corners = self._scale_corners(coarse["corners"], 1.0 / coarse["scale"])
        roi = self._roi_from_corners(coarse_corners, image_w, image_h)
        x, y, w, h = roi
        roi_gray = gray[y : y + h, x : x + w]

        refined = self._detect_scaled(roi_gray, self.refine_max_side)
        if refined["ids"] is None or len(refined["ids"]) == 0:
            marker_corners = coarse_corners
            marker_ids = coarse["ids"]
            used_roi = None
            rejected_corners = self._scale_corners(
                coarse["rejected"],
                1.0 / coarse["scale"],
            )
        else:
            marker_corners = self._scale_corners(
                refined["corners"],
                1.0 / refined["scale"],
            )
            marker_corners = self._offset_corners(marker_corners, x, y)
            marker_ids = refined["ids"]
            used_roi = roi
            rejected_corners = self._offset_corners(
                self._scale_corners(refined["rejected"], 1.0 / refined["scale"]),
                x,
                y,
            )

        charuco_corners = None
        charuco_ids = None
        pose = None
        reprojection_error = None
        if camera_matrix is not None and marker_ids is not None:
            d = self._distortion_array(distortion_coeffs)
            count, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
                marker_corners,
                marker_ids,
                gray,
                self.board,
                camera_matrix,
                d,
            )
            if charuco_ids is not None and int(count) >= self.min_charuco_corners:
                pose = self._estimate_pose(
                    charuco_corners,
                    charuco_ids,
                    camera_matrix,
                    d,
                )
                if pose is not None:
                    reprojection_error = self._reprojection_error(
                        charuco_corners,
                        charuco_ids,
                        pose["rvec"],
                        pose["tvec"],
                        camera_matrix,
                        d,
                    )

        return self._result(
            marker_corners,
            marker_ids,
            charuco_corners,
            charuco_ids,
            pose,
            image_w,
            image_h,
            used_roi,
            reprojection_error,
            rejected_corners,
        )

    def draw_detection(
        self,
        image_bgr,
        detection,
        camera_matrix=None,
        distortion_coeffs=None,
        draw_rejected=False,
    ):
        view = image_bgr.copy()
        if detection is None:
            return view

        if draw_rejected and detection.get("rejected_corners"):
            for corner in detection["rejected_corners"]:
                points = corner.reshape(-1, 2).astype(int)
                cv2.polylines(view, [points], True, (70, 70, 230), 2, cv2.LINE_AA)

        if detection.get("marker_ids") is not None:
            cv2.aruco.drawDetectedMarkers(
                view,
                detection["marker_corners"],
                detection["marker_ids"],
            )
            for marker_id, corner in zip(
                detection["marker_ids"].flatten(),
                detection["marker_corners"],
            ):
                center = corner.reshape(-1, 2).mean(axis=0).astype(int)
                cv2.putText(
                    view,
                    str(int(marker_id)),
                    tuple(center),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

        if detection.get("charuco_ids") is not None:
            cv2.aruco.drawDetectedCornersCharuco(
                view,
                detection["charuco_corners"],
                detection["charuco_ids"],
                (30, 220, 30),
            )

        pose = detection.get("pose")
        if pose is not None and camera_matrix is not None:
            cv2.drawFrameAxes(
                view,
                camera_matrix,
                self._distortion_array(distortion_coeffs),
                pose["rvec"],
                pose["tvec"],
                self.square_length_m * 2.0,
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
        if hasattr(cv2.aruco, "CharucoBoard_create"):
            return cv2.aruco.CharucoBoard_create(
                self.squares_x,
                self.squares_y,
                self.square_length_m,
                self.marker_length_m,
                self.dictionary,
            )
        return cv2.aruco.CharucoBoard(
            (self.squares_x, self.squares_y),
            self.square_length_m,
            self.marker_length_m,
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

        if hasattr(cv2.aruco, "ArucoDetector"):
            detector = cv2.aruco.ArucoDetector(self.dictionary, self.parameters)
            corners, ids, rejected = detector.detectMarkers(detect_image)
        else:
            corners, ids, rejected = cv2.aruco.detectMarkers(
                detect_image,
                self.dictionary,
                parameters=self.parameters,
            )
        return {"corners": corners, "ids": ids, "rejected": rejected, "scale": scale}

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

    def _estimate_pose(self, charuco_corners, charuco_ids, camera_matrix, distortion_coeffs):
        ok, rvec, tvec = cv2.aruco.estimatePoseCharucoBoard(
            charuco_corners,
            charuco_ids,
            self.board,
            camera_matrix,
            distortion_coeffs,
            None,
            None,
        )
        if not ok:
            return None
        return {
            "markers_used": int(len(charuco_ids)),
            "rvec": rvec,
            "tvec": tvec,
        }

    def _reprojection_error(
        self,
        charuco_corners,
        charuco_ids,
        rvec,
        tvec,
        camera_matrix,
        distortion_coeffs,
    ):
        object_corners = self._get_chessboard_corners()
        ids = charuco_ids.flatten().astype(int)
        object_points = object_corners[ids].astype(np.float32)
        image_points = charuco_corners.reshape(-1, 2).astype(np.float32)

        projected, _ = cv2.projectPoints(
            object_points,
            rvec,
            tvec,
            camera_matrix,
            distortion_coeffs,
        )
        projected = projected.reshape(-1, 2)
        errors = np.linalg.norm(projected - image_points, axis=1)

        return {
            "mean": float(np.mean(errors)),
            "median": float(np.median(errors)),
            "max": float(np.max(errors)),
        }

    def _get_chessboard_corners(self):
        if hasattr(self.board, "getChessboardCorners"):
            return self.board.getChessboardCorners()
        return self.board.chessboardCorners

    def _distortion_array(self, distortion_coeffs):
        if distortion_coeffs is None:
            return np.zeros((5, 1), dtype=np.float64)
        d = np.asarray(distortion_coeffs, dtype=np.float64)
        if d.size == 0:
            return np.zeros((5, 1), dtype=np.float64)
        return d

    def _result(
        self,
        marker_corners,
        marker_ids,
        charuco_corners,
        charuco_ids,
        pose,
        image_w,
        image_h,
        roi,
        reprojection_error=None,
        rejected_corners=None,
    ):
        return {
            "image_size": (int(image_w), int(image_h)),
            "marker_corners": marker_corners,
            "marker_ids": marker_ids,
            "charuco_corners": charuco_corners,
            "charuco_ids": charuco_ids,
            "num_markers": 0 if marker_ids is None else int(len(marker_ids)),
            "num_charuco_corners": 0 if charuco_ids is None else int(len(charuco_ids)),
            "num_rejected_candidates": 0
            if rejected_corners is None
            else int(len(rejected_corners)),
            "rejected_corners": rejected_corners,
            "pose": pose,
            "roi": roi,
            "reprojection_error_px": reprojection_error,
        }
