import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from oak4_depth_geometry import depth_to_xyz


class GeometryTests(unittest.TestCase):
    def test_pinhole_projection_and_millimetres(self):
        depth = np.zeros((3, 3), np.uint16)
        depth[1, 1] = 2000
        depth[2, 2] = 1000
        k = [[100, 0, 1], [0, 100, 1], [0, 0, 1]]
        points = depth_to_xyz(depth, k)
        np.testing.assert_allclose(points, [[0, 0, 2], [.01, .01, 1]])
        self.assertEqual(points.dtype, np.dtype('<f4'))
        self.assertTrue(points.flags.c_contiguous)

    def test_invalid_depth_is_not_at_the_origin(self):
        xyz = depth_to_xyz(np.zeros((2, 2), np.uint16), np.eye(3))
        self.assertEqual(xyz.shape, (0, 3))

    def test_bad_calibration_or_depth_rejected(self):
        depth = np.ones((2, 2), np.uint16)
        for k in (np.zeros((3, 3)), [[100, 0, 1], [0, 100, 1], [0, 0, 0]], np.full((3, 3), np.nan)):
            with self.assertRaises(ValueError):
                depth_to_xyz(depth, k)
        with self.assertRaises(ValueError):
            depth_to_xyz(depth.astype(np.uint8), np.eye(3))


if __name__ == '__main__':
    unittest.main()
