"""Board-specific image search and focus-bound pose estimates; no device commands."""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def freeze_config(workspace, path=None):
    import yaml
    workspace = Path(workspace)
    path = Path(path) if path else Path(__file__).resolve().parents[1] / 'config/oak4_charuco_search.json'
    config = json.loads(path.read_text())
    sources = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()}

    def read(relative, yaml_file=False):
        p = workspace / relative
        raw = p.read_bytes()
        sources[str(p)] = hashlib.sha256(raw).hexdigest()
        return yaml.safe_load(raw) if yaml_file else json.loads(raw)

    config['boards'] = read(config.pop('layout'), True)['charuco']
    config['intrinsics'] = {str(focus): read(p) for focus, p in config.pop('intrinsics_by_focus', {}).items()}
    config['base_bindings'] = read(config['base_bindings']) if config.get('base_bindings') else {}
    config['sources_sha256'] = sources
    validate_config(config)
    return config


def validate_config(config):
    focuses = config['focus_candidates']
    if not focuses or len(focuses) > 17 or len(set(focuses)) != len(focuses) or any(type(f) is not int or not 0 <= f <= 255 for f in focuses):
        raise ValueError('Expected 1..17 distinct focus positions in 0..255')
    evs = config['exposure_offsets_ev']
    if not evs or len(evs) > 5 or any(not np.isfinite(e) or abs(e) > 3 for e in evs):
        raise ValueError('Expected 1..5 exposure offsets within +/-3 EV')
    for f, profile in config.get('intrinsics', {}).items():
        k, d = np.asarray(profile['K']), np.asarray(profile['D'])
        if (profile.get('focus') != int(f) or profile.get('image_size') != [8000, 6000]
                or k.shape != (3, 3) or not np.isfinite(k).all() or min(k[0, 0], k[1, 1]) <= 0
                or d.size not in (4, 5, 8, 12, 14) or not np.isfinite(d).all()
                or profile.get('device_id') != '1479883285'):
            raise ValueError('Intrinsics profile does not match focus/native OAK4 identity')


def rank(observation, exposure=False):
    if not observation['marker_count']:
        return (-1, -1, -1.)
    quality = -abs(observation['p90_gray'] - 220.) if exposure else observation['sharpness']
    return (observation['charuco_count'], observation['marker_count'], quality)


class Board:
    def __init__(self, config, side):
        self.side = side
        count = config['squares_x'] * config['squares_y'] // 2
        first = config['boards'][side]['marker_start']
        self.marker_ids = list(range(first, first + count))
        self.dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, config['dictionary']))
        self.board = cv2.aruco.CharucoBoard((config['squares_x'], config['squares_y']),
            config['square_length'], config['marker_length'], self.dictionary, np.array(self.marker_ids, np.int32))
        self.board.setLegacyPattern(config.get('legacy_pattern', False))
        params = cv2.aruco.DetectorParameters()
        params.minMarkerPerimeterRate = .003
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, params)
        self.charuco = cv2.aruco.CharucoDetector(self.board, cv2.aruco.CharucoParameters(), params)

    def observe(self, image, roi=None):
        h, w = image.shape[:2]
        x, y, rw, rh = (0, 0, w, h) if roi is None else roi
        crop = image[y:y+rh, x:x+rw]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.detector.detectMarkers(gray)
        keep = [] if ids is None else [i for i, n in enumerate(ids.ravel()) if n in self.marker_ids]
        result = dict(marker_count=len(keep), charuco_count=0, marker_ids=[], marker_pixels=[],
                      charuco_ids=[], charuco_pixels=[], sharpness=0., p90_gray=0., clipped_fraction=0.)
        if not keep:
            return result
        local = [corners[i] for i in keep]
        marker_ids = ids[keep].astype(np.int32)
        cc, ci, _, _ = self.charuco.detectBoard(gray, markerCorners=local, markerIds=marker_ids)
        pixels = np.concatenate(local).reshape(-1, 2) + [x, y]
        lo = np.maximum(0, np.floor(pixels.min(axis=0) - 10)).astype(int)
        hi = np.minimum([w, h], np.ceil(pixels.max(axis=0) + 10)).astype(int)
        region = cv2.cvtColor(image[lo[1]:hi[1], lo[0]:hi[0]], cv2.COLOR_BGR2GRAY)
        contrast = max(10., float(np.std(region)))
        result.update(marker_ids=marker_ids.ravel().tolist(), marker_pixels=pixels.reshape(-1, 4, 2).tolist(),
            roi=[int(lo[0]), int(lo[1]), int(hi[0]-lo[0]), int(hi[1]-lo[1])],
            sharpness=float(cv2.Laplacian(region, cv2.CV_32F).var() / contrast**2),
            p90_gray=float(np.percentile(region, 90)), clipped_fraction=float(np.mean(region >= 253)))
        if ci is not None:
            result.update(charuco_count=len(ci), charuco_ids=ci.ravel().tolist(),
                          charuco_pixels=(cc.reshape(-1, 2)+[x, y]).tolist())
        return result

    def pose(self, observation, profile, image_size=(8000, 6000)):
        """Fit marker corners; hold out whole markers to avoid neighbouring-corner leakage."""
        ids = observation['marker_ids']
        if len(ids) < 4:
            return dict(status='INSUFFICIENT_MARKERS', reason='Need four distributed markers')
        objects = np.concatenate([self.board.getObjPoints()[self.marker_ids.index(i)] for i in ids]).astype(np.float64)
        pixels = np.array(observation['marker_pixels'], np.float64).reshape(-1, 2)
        fit = np.repeat(np.arange(len(ids)) % 3 != 0, 4)
        if fit.sum() < 8 or np.min(np.ptp(objects[fit, :2], axis=0)) < .02:
            return dict(status='INSUFFICIENT_DISTRIBUTION')
        k = np.array(profile['K'], np.float64).copy()
        sx, sy = image_size[0]/8000, image_size[1]/6000
        k[0] *= sx; k[1] *= sy
        k[0, 2] += (sx-1)/2; k[1, 2] += (sy-1)/2
        d = np.array(profile['D'], np.float64)
        ok, rvecs, tvecs, _ = cv2.solvePnPGeneric(objects[fit], pixels[fit], k, d, flags=cv2.SOLVEPNP_IPPE)
        candidates = []
        if ok:
            for r, t in zip(rvecs, tvecs):
                if np.min((objects @ cv2.Rodrigues(r)[0].T + t.ravel())[:, 2]) <= 0:
                    continue
                uv = cv2.projectPoints(objects[fit], r, t, k, d)[0].reshape(-1, 2)
                candidates.append((float(np.mean((uv-pixels[fit])**2)), r, t))
        if not candidates:
            return dict(status='NO_POSITIVE_DEPTH_POSE')
        _, r, t = min(candidates, key=lambda v: v[0])
        r, t = cv2.solvePnPRefineLM(objects[fit], pixels[fit], k, d, r, t)
        error = np.linalg.norm(cv2.projectPoints(objects, r, t, k, d)[0].reshape(-1, 2)-pixels, axis=1)
        transform = np.eye(4); transform[:3, :3] = cv2.Rodrigues(r)[0]; transform[:3, 3] = t.ravel()
        rms = float(np.sqrt(np.mean(error[~fit]**2)))
        return dict(status='POSE_CANDIDATE', T_camera_board=transform.tolist(),
                    fit_rms_px=float(np.sqrt(np.mean(error[fit]**2))), held_out_rms_px=rms,
                    fit_marker_ids=np.array(ids)[fit[::4]].tolist(), check_marker_ids=np.array(ids)[~fit[::4]].tolist(),
                    image_check_passed=rms <= 2.*sx, image_limit_px=2.*sx,
                    board_origin_distance_m=float(np.linalg.norm(t)), image_size=list(image_size))
