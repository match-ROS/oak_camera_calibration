"""Reject plausible-looking RGB-D pairs with inconsistent geometry or time."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from oak4_rgbd_geometry import validate_pair


class RgbdGeometryTests(unittest.TestCase):
    def setUp(self):
        self.rgb = np.zeros((3, 4, 3), np.uint8)
        self.depth = np.full((3, 4), 1200, np.uint16)
        self.k = np.array([[5., 0., 2.], [0., 5., 1.5], [0., 0., 1.]])

    def validate(self, **kwargs):
        options = dict(rgb=self.rgb, depth=self.depth, rgb_k=self.k,
                       depth_k=self.k.copy(), rgb_time=10., depth_time=10.01,
                       sequences=(20, 19), previous=(19, 18), size=(4, 3))
        options.update(kwargs)
        return validate_pair(**options)

    def test_valid_pair_keeps_invalid_pixels_invalid(self):
        self.depth[0, 0] = 0
        report = self.validate()
        self.assertAlmostEqual(report['valid_depth_fraction'], 11 / 12)
        self.assertEqual(report['valid_depth_median_mm'], 1200)
        self.assertEqual(self.depth[0, 0], 0)

    def test_wrong_depth_perspective_or_unit_rejected(self):
        different_k = self.k.copy()
        different_k[0, 2] += 3
        for options in [dict(depth_k=different_k), dict(depth=self.depth.astype(float) / 1000),
                        dict(depth=np.zeros((2, 4), np.uint16))]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.validate(**options)

    def test_stale_duplicate_or_bad_metadata_rejected(self):
        for options in [dict(depth_time=10.1), dict(rgb_time=float('nan')),
                        dict(sequences=(19, 19)), dict(sequences=(20, 18)),
                        dict(rgb_k=np.zeros((3, 3))), dict(depth=np.zeros_like(self.depth))]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.validate(**options)


if __name__ == '__main__':
    unittest.main()
