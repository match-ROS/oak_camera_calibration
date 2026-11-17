"""Geometric checks with independent synthetic poses and excluded image points."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import oak4_rgbd_board_check as check


class BoardCheckTests(unittest.TestCase):
    def setUp(self):
        self.k = np.array([[500., 0., 160.], [0., 500., 120.], [0., 0., 1.]])
        self.r = np.array([.35, -.08, .1])
        self.t = np.array([-.12, -.08, 1.])
        self.config = dict(squares_x=7, squares_y=5, square_length=.04,
            marker_length=.028, dictionary='DICT_4X4_100', min_corners=12,
            max_reprojection_error_px=1., boards=dict(right=dict(marker_start=50)))
        board = cv2.aruco.CharucoBoard((7, 5), .04, .028,
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100),
            np.arange(50, 67, dtype=np.int32))
        self.objects = board.getChessboardCorners().astype(float)
        self.pixels = cv2.projectPoints(self.objects, self.r, self.t, self.k, None)[0].astype(np.float32)
        y, x = np.mgrid[:240, :320]
        n = cv2.Rodrigues(self.r)[0][:, 2]
        z, _ = check.expected_z(np.c_[x.ravel(), y.ravel()], self.k, n, n @ self.t)
        self.depth = np.rint(z.reshape(240, 320) * 1000).astype(np.uint16)

    def test_z_uses_optical_axis_not_ray_distance(self):
        z, rays = check.expected_z(np.array([[160., 120.], [260., 120.]]),
                                  self.k, np.array([0., 0., 1.]), 1.)
        np.testing.assert_allclose(z, 1.)
        self.assertGreater(np.linalg.norm(rays[1]), 1.)

    def test_excluded_corner_perturbation_does_not_change_pose(self):
        ids = np.arange(24, dtype=np.int32).reshape(-1, 1)
        detector = Mock()
        detector.detectBoard.return_value = (self.pixels, ids, None, None)
        image = np.zeros((240, 320, 3), np.uint8)
        with patch.object(check.cv2.aruco, 'CharucoDetector', return_value=detector):
            before, _ = check.check_board(image, self.depth, self.k, self.config, 'right')
            disturbed = self.pixels.copy()
            disturbed[ids.ravel() % 3 == 0] += [12., -8.]
            detector.detectBoard.return_value = (disturbed, ids, None, None)
            after, _ = check.check_board(image, self.depth, self.k, self.config, 'right')
        np.testing.assert_allclose(before['T_camera_board'], after['T_camera_board'])
        self.assertTrue(before['image_limit_passed'])
        self.assertFalse(after['image_limit_passed'])

    def test_known_z_bias_is_retained_in_report(self):
        metrics, _ = check.depth_metrics(self.depth + 12, self.k, self.r, self.t, .28, .2)
        self.assertAlmostEqual(metrics['signed_z_median_mm'], 12., delta=.5)
        self.assertAlmostEqual(metrics['abs_z_median_mm'], 12., delta=.5)

    def test_robust_plane_fit_does_not_use_validation_points(self):
        rng = np.random.default_rng(5)
        points = np.c_[rng.uniform(-.2, .2, (500, 2)), np.ones(500)]
        points[:, 2] += rng.normal(0, .0005, len(points))
        points[:80, 2] += .1
        normal, distance, support = check.fit_depth_plane(points)
        self.assertGreater(abs(normal[2]), .999)
        self.assertAlmostEqual(abs(distance), 1., delta=.001)
        self.assertGreaterEqual(support, 400)

    def test_all_invalid_depth_is_not_filled(self):
        metrics, _ = check.depth_metrics(np.zeros_like(self.depth), self.k,
                                        self.r, self.t, .28, .2)
        self.assertEqual(metrics['status'], 'INSUFFICIENT_DEPTH')
        self.assertEqual(metrics['valid_fraction'], 0)

    def test_mobile_marker_identity_and_38mm_scale_are_separate(self):
        board = cv2.aruco.CharucoBoard((7, 5), .038, .028,
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100),
            np.arange(75, 92, dtype=np.int32))
        board.setLegacyPattern(False)
        image = np.full((240, 320), 255, np.uint8)
        image[25:215, 27:293] = board.generateImage((266, 190), marginSize=0)
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        config = dict(self.config, square_length=.038,
                      boards=dict(mobile=dict(marker_start=75, marker_ids=list(range(75, 92)))))
        result, _ = check.check_board(image, np.full((240, 320), 500, np.uint16),
                                      self.k, config, 'mobile')
        self.assertEqual(result['corners'], 24)
        self.assertEqual(result['marker_ids'], list(range(75, 92)))
        self.assertEqual(result['square_length_m'], .038)
        self.assertTrue(result['image_limit_passed'])

    def test_duplicate_marker_identity_is_rejected(self):
        config = dict(self.config, boards=dict(mobile=dict(marker_start=75, marker_ids=[75] * 17)))
        with self.assertRaisesRegex(ValueError, 'duplicates'):
            check.check_board(np.zeros((240, 320, 3), np.uint8), self.depth,
                              self.k, config, 'mobile')


if __name__ == '__main__':
    unittest.main()
