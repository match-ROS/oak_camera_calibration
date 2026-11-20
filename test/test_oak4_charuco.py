"""Synthetic board identity, focus scoring and focus-bound pose checks; no device."""
import importlib.util
from pathlib import Path
import unittest

import cv2
import numpy as np

spec = importlib.util.spec_from_file_location('oak4_charuco',
    Path(__file__).resolve().parents[1]/'tools/oak4_charuco.py')
search = importlib.util.module_from_spec(spec); spec.loader.exec_module(search)
CONFIG = dict(squares_x=7, squares_y=5, square_length=.04, marker_length=.028,
              dictionary='DICT_4X4_100', boards=dict(left=dict(marker_start=0), right=dict(marker_start=50)))


class SearchTests(unittest.TestCase):
    def test_board_identity_and_crop_coordinates(self):
        canvas = np.full((700, 1400, 3), 255, np.uint8)
        for side, x in (('left', 50), ('right', 750)):
            board = search.Board(CONFIG, side)
            tile = board.board.generateImage((560, 400))
            canvas[150:550, x:x+560] = tile[:, :, None]
        for side, x in (('left', 50), ('right', 750)):
            board = search.Board(CONFIG, side)
            full = board.observe(canvas)
            cropped = board.observe(canvas, (x-20, 130, 600, 440))
            self.assertEqual(full['charuco_count'], 24)
            self.assertEqual(full['marker_count'], 17)
            self.assertEqual(set(full['marker_ids']), set(board.marker_ids))
            np.testing.assert_allclose(full['charuco_pixels'], cropped['charuco_pixels'], atol=.1)

    def test_focus_score_prefers_sharp_board_to_defocus(self):
        board = search.Board(CONFIG, 'right')
        tile = board.board.generateImage((280, 200), marginSize=12)
        image = cv2.cvtColor(tile, cv2.COLOR_GRAY2BGR)
        sharp = board.observe(image)
        blurred = board.observe(cv2.GaussianBlur(image, (9, 9), 2.))
        self.assertGreater(search.rank(sharp), search.rank(blurred))

    def test_pose_uses_disjoint_whole_markers(self):
        board = search.Board(CONFIG, 'right')
        k = np.array([[5800., 0, 4000], [0, 5800, 3000], [0, 0, 1]])
        r, t = np.array([.2, .1, .02]), np.array([-.1, -.1, 1.3])
        obj = np.concatenate(board.board.getObjPoints()).astype(np.float64)
        uv = cv2.projectPoints(obj, r, t, k, np.zeros(5))[0].reshape(-1, 4, 2)
        result = board.pose(dict(marker_ids=board.marker_ids, marker_pixels=uv.tolist()), dict(K=k, D=np.zeros(5)))
        self.assertTrue(result['image_check_passed'])
        self.assertFalse(set(result['fit_marker_ids']) & set(result['check_marker_ids']))
        np.testing.assert_allclose(np.array(result['T_camera_board'])[:3, 3], t, atol=1e-6)

    def test_unmatched_focus_or_device_profile_rejected(self):
        for change in (dict(focus=116), dict(device_id='other'), dict(image_size=[2000, 1500])):
            profile = dict(K=[[5800, 0, 4000], [0, 5800, 3000], [0, 0, 1]], D=[0]*5,
                           focus=107, device_id='1479883285', image_size=[8000, 6000])
            profile.update(change)
            with self.assertRaises(ValueError):
                search.validate_config(dict(focus_candidates=[107], exposure_offsets_ev=[0], intrinsics={'107': profile}))

    def test_missing_board_cannot_outrank_a_detected_board(self):
        board = search.Board(CONFIG, 'left')
        empty = board.observe(np.full((200, 300, 3), 255, np.uint8))
        self.assertEqual(empty['marker_count'], 0)
        self.assertLess(search.rank(empty), (1, 1, 0.))


if __name__ == '__main__':
    unittest.main()
