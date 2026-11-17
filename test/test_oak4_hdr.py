"""Exposure/readback and real OpenCV fusion tests; no device access."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location('oak4_hdr',
    Path(__file__).resolve().parents[1] / 'tools/oak4_hdr.py')
hdr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hdr)


class HDRTests(unittest.TestCase):
    def test_bracket_keeps_four_stops_without_exposure_clipping(self):
        for reference in (1, 100 * 100, 20000 * 100, 90000 * 1600):
            with self.subTest(reference=reference):
                steps = hdr.bracket_plan(reference, 100)
                times = [step['exposure_us'] for step in steps]
                self.assertTrue(all(100 <= t <= 90000 for t in times))
                self.assertEqual(times[1] / times[0], 4)
                self.assertEqual(times[2] / times[1], 4)

    def test_invalid_metering(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                hdr.bracket_plan(value, 100)

    def test_readback_rejects_ignored_exposure_and_changed_optics(self):
        good = dict(exposure_us=10000, reported_iso=100,
                    lens_position=107, white_balance_K=4100)
        hdr.verify_exposure(good, 10000, 100, good)
        for key, value in (('exposure_us', 2500), ('reported_iso', 200),
                           ('lens_position', 116), ('white_balance_K', 4300)):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                hdr.verify_exposure(dict(good, **{key: value}), 10000, 100, good)

    def test_fusion_recovers_structure_at_both_ends(self):
        # Same static scene: dark stripes vanish in short, bright stripes clip in long.
        radiance = np.empty((128, 192, 3), np.float32)
        stripes = (np.arange(192) % 16 < 8).astype(np.float32)
        radiance[:64] = (.01 + .01 * stripes)[None, :, None]
        radiance[64:] = (.6 + .3 * stripes)[None, :, None]
        images = [np.rint(np.clip(radiance * t, 0, 1) * 255).astype(np.uint8)
                  for t in (.25, 1, 4)]
        result = hdr.fuse(images)
        self.assertEqual(result.shape, radiance.shape)
        self.assertEqual(result.dtype, np.uint8)
        for y in (24, 96):
            self.assertGreater(abs(float(result[y, 83, 0]) - float(result[y, 91, 0])), 2)
        self.assertFalse(np.array_equal(result, images[1]))

    def test_mismatched_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            hdr.fuse([np.zeros((2, 2, 3), np.uint8)] * 2)


if __name__ == '__main__':
    unittest.main()
