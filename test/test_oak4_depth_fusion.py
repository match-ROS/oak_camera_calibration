"""Synthetic data tests for validity and stability, not a camera accuracy test."""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from oak4_depth_fusion import fuse_depth


class FusionTests(unittest.TestCase):
    def test_zeros_never_become_measurements(self):
        data = np.zeros((16, 2, 2), np.uint16)
        data[:, 0, 0] = 2000
        data[:11, 1, 0] = 2000  # Less than 75% support.
        result = fuse_depth(data)
        self.assertEqual(result['hq'][0, 0], 2000)
        self.assertEqual(result['hq'][1, 0], 0)
        self.assertEqual(result['hq'][1, 1], 0)
        self.assertEqual(result['valid_counts'][1, 1], 0)
        self.assertTrue(np.isfinite(result['temporal_mad_mm']).all())

    def test_outlier_does_not_bias_depth(self):
        data = np.full((16, 1, 1), 2000, np.uint16)
        data[0] = 10000
        result = fuse_depth(data)
        self.assertEqual(result['hq'][0, 0], 2000)
        self.assertEqual(result['inlier_counts'][0, 0], 15)

    def test_moving_edge_is_invalid_not_a_midpoint(self):
        data = np.full((16, 1, 1), 1000, np.uint16)
        data[8:] = 3000
        self.assertEqual(fuse_depth(data)['hq'][0, 0], 0)
        data[8:] = 1000
        data[9:] = 3000  # Majority alone must not suffice.
        self.assertEqual(fuse_depth(data)['hq'][0, 0], 0)

    def test_no_spatial_blending_across_an_edge(self):
        data = np.tile(np.array([[1000, 3000]], np.uint16), (16, 1, 1))
        np.testing.assert_array_equal(fuse_depth(data)['hq'], [[1000, 3000]])

    def test_temporal_noise_reduced_for_stationary_surface(self):
        rng = np.random.default_rng(12)
        data = np.rint(2000 + rng.normal(0, 5, (16, 30, 40))).astype(np.uint16)
        result = fuse_depth(data)
        self.assertGreater(result['stable'].mean(), .99)
        self.assertLess(np.std(result['hq'].astype(float)-2000),
                        np.std(data[0].astype(float)-2000)*.5)

    def test_invalid_dtype_or_short_burst_rejected(self):
        for data in (np.ones((16, 2, 2), np.float32), np.ones((3, 2, 2), np.uint16)):
            with self.assertRaises(ValueError):
                fuse_depth(data)


if __name__ == '__main__':
    unittest.main()
