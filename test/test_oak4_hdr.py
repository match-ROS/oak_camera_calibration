"""Exposure/readback and real OpenCV fusion tests; no device access."""
import importlib.util
from pathlib import Path
import unittest
import itertools
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

spec = importlib.util.spec_from_file_location('oak4_hdr',
    Path(__file__).resolve().parents[1] / 'tools/oak4_hdr.py')
hdr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hdr)


class HDRTests(unittest.TestCase):
    def test_acquisition_discards_stale_controls_and_averages_only_confirmed_frames(self):
        current = dict(exposure_us=10000, reported_iso=100,
                       lens_position=107, white_balance_K=4100)
        sequence = 0
        good_frames = 0
        pending_bad = False

        def description():
            nonlocal sequence
            sequence += 1
            return dict(current, sequence=sequence)

        class Queue:
            empty = False
            def tryGet(self):
                self.empty = not self.empty
                return None if self.empty else description()

        def send(ctrl):
            nonlocal pending_bad
            exposure, iso = ctrl.setManualExposure.call_args.args
            current.update(exposure_us=exposure, reported_iso=iso)
            pending_bad = True

        def capture():
            nonlocal pending_bad, good_frames
            info = description()
            if pending_bad:
                pending_bad = False
                info['reported_iso'] = 99  # stale full frame despite ready preview
                return Mock(getCvFrame=Mock(side_effect=AssertionError('Must discard'))), info
            good_frames += 1
            return Mock(getCvFrame=Mock(return_value=np.full((3, 4, 3), good_frames*10, np.uint8))), info

        report = {}
        with patch.object(hdr.time, 'monotonic', side_effect=itertools.count(0, .02).__next__), \
             patch.object(hdr.time, 'sleep'):
            images = hdr.acquire(SimpleNamespace(iso=100, focus=107, frames=2), report,
                capture, Mock(send=Mock(side_effect=send)), Queue(), Mock, lambda x: x)
        self.assertEqual([int(im[0, 0, 0]) for im in images], [15, 35, 55])
        self.assertEqual([len(step['frames']) for step in report['hdr_brackets']], [2]*3)
        self.assertEqual(good_frames, 6)

    def test_metadata_wait_rejects_transition_and_duplicate_frames(self):
        frames = [dict(sequence=1, ready=True), dict(sequence=2, ready=False),
                  dict(sequence=3, ready=True), dict(sequence=3, ready=True),
                  dict(sequence=4, ready=True), dict(sequence=5, ready=True)]
        queue = Mock(tryGet=Mock(side_effect=frames))
        result = hdr.wait_metadata(queue, lambda x: x, lambda x: x['ready'])
        self.assertEqual(result['sequence'], 5)

    def test_metadata_wait_timeout_is_failure(self):
        with patch.object(hdr.time, 'monotonic', side_effect=[0, 0, 9]), \
             patch.object(hdr.time, 'sleep'):
            with self.assertRaises(TimeoutError):
                hdr.wait_metadata(Mock(tryGet=Mock(return_value=None)), lambda x: x, lambda x: True)

    def test_native_archives_are_required_even_if_fusion_succeeds(self):
        image = np.broadcast_to(np.zeros((1, 1, 3), np.uint8), (6000, 8000, 3))
        report = dict(hdr_timing_s={}, hdr_brackets=[dict(name=n, path=n+'.png', frames=[{}])
                                                  for n in ('short', 'base', 'long')])
        with patch.object(hdr, 'fuse', return_value=image), \
             patch.object(hdr.cv2, 'imwrite', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'Cannot save'):
                hdr.finish(Path('/tmp'), [image]*3, report)
        self.assertNotIn('hdr', report)

    def test_finish_fuses_existing_arrays_and_keeps_all_archives(self):
        image = np.broadcast_to(np.zeros((1, 1, 3), np.uint8), (6000, 8000, 3))
        report = dict(hdr_timing_s={}, hdr_brackets=[dict(name=n, path=n+'.png', frames=[{}, {}])
                                                  for n in ('short', 'base', 'long')])
        images = [image]*3
        with patch.object(hdr, 'fuse', return_value=image) as merge, \
             patch.object(hdr.cv2, 'imwrite', return_value=True) as save, \
             patch.object(hdr.cv2, 'imread', side_effect=AssertionError('No PNG reread')):
            hdr.finish(Path('/tmp'), images, report)
        self.assertIs(merge.call_args.args[0], images)
        self.assertEqual({Path(c.args[0]).name for c in save.call_args_list},
                         {'short.png', 'base.png', 'long.png', 'hdr.png'})
        self.assertEqual(report['hdr']['frame_count'], 6)

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
