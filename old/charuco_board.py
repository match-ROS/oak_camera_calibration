import cv2
import numpy as np


BOARD_MODEL_ID = "calibio_charuco_14x9_20mm_15mm_dict5x5_100"
SQUARES_X = 14
SQUARES_Y = 9
SQUARE_LENGTH_M = 0.020
MARKER_LENGTH_M = 0.015
MIN_CHARUCO_CORNERS = 8


def create_dictionary():
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)


def board_metadata():
    return {
        "model_id": BOARD_MODEL_ID,
        "squares_x": SQUARES_X,
        "squares_y": SQUARES_Y,
        "square_length_m": SQUARE_LENGTH_M,
        "marker_length_m": MARKER_LENGTH_M,
        "dictionary": "DICT_5X5_100",
    }


def create_board(dictionary=None):
    dictionary = dictionary if dictionary is not None else create_dictionary()

    if hasattr(cv2.aruco, "CharucoBoard_create"):
        return cv2.aruco.CharucoBoard_create(
            SQUARES_X,
            SQUARES_Y,
            SQUARE_LENGTH_M,
            MARKER_LENGTH_M,
            dictionary,
        )

    return cv2.aruco.CharucoBoard(
        (SQUARES_X, SQUARES_Y),
        SQUARE_LENGTH_M,
        MARKER_LENGTH_M,
        dictionary,
    )


def detect_markers(image, dictionary):
    if hasattr(cv2.aruco, "ArucoDetector"):
        detector = cv2.aruco.ArucoDetector(dictionary)
        return detector.detectMarkers(image)

    return cv2.aruco.detectMarkers(image, dictionary)


def estimate_charuco_pose(image, camera_matrix, distortion_coeffs):
    dictionary = create_dictionary()
    board = create_board(dictionary)
    marker_corners, marker_ids, rejected = detect_markers(image, dictionary)

    if marker_ids is None or len(marker_ids) == 0:
        return None

    num_corners, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
        marker_corners,
        marker_ids,
        image,
        board,
        camera_matrix,
        distortion_coeffs,
    )

    if charuco_ids is None or int(num_corners) < MIN_CHARUCO_CORNERS:
        return None

    ok, rvec, tvec = cv2.aruco.estimatePoseCharucoBoard(
        charuco_corners,
        charuco_ids,
        board,
        camera_matrix,
        distortion_coeffs,
        None,
        None,
    )
    if not ok:
        return None

    return {
        "board": board,
        "marker_corners": marker_corners,
        "marker_ids": marker_ids,
        "rejected": rejected,
        "charuco_corners": charuco_corners,
        "charuco_ids": charuco_ids,
        "rvec": rvec,
        "tvec": tvec,
        "reprojection_error_px": reprojection_error(
            board,
            charuco_corners,
            charuco_ids,
            rvec,
            tvec,
            camera_matrix,
            distortion_coeffs,
        ),
    }


def reprojection_error(
    board,
    charuco_corners,
    charuco_ids,
    rvec,
    tvec,
    camera_matrix,
    distortion_coeffs,
):
    object_corners = get_chessboard_corners(board)
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


def get_chessboard_corners(board):
    if hasattr(board, "getChessboardCorners"):
        return board.getChessboardCorners()

    return board.chessboardCorners
