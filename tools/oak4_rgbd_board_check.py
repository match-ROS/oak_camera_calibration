#!/usr/bin/env python3
"""Offline fixed-K board/depth consistency check; never changes calibration."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import yaml


def fit_pose(objects, pixels, k):
    ok, rotations, translations, _ = cv2.solvePnPGeneric(
        objects, pixels, k, np.zeros(5), flags=cv2.SOLVEPNP_IPPE)
    candidates = []
    if ok:
        for r, t in zip(rotations, translations):
            if np.min((objects @ cv2.Rodrigues(r)[0].T + t.ravel())[:, 2]) <= 0:
                continue
            projected = cv2.projectPoints(objects, r, t, k, None)[0].reshape(-1, 2)
            candidates.append((np.mean(np.sum((projected - pixels) ** 2, axis=1)), r, t))
    if not candidates:
        raise ValueError('No positive-depth planar board pose')
    _, r, t = min(candidates, key=lambda x: x[0])
    r, t = cv2.solvePnPRefineLM(objects, pixels, k, np.zeros(5), r, t)
    return r, t


def expected_z(pixels, k, normal, plane_distance):
    rays = np.c_[pixels, np.ones(len(pixels))] @ np.linalg.inv(k).T
    denominator = rays @ normal
    if np.any(np.abs(denominator) < 1e-9):
        raise ValueError('Board plane parallel to image ray')
    return plane_distance / denominator, rays


def fit_depth_plane(points):
    if len(points) < 30:
        raise ValueError('Insufficient independent depth fit samples')
    rng = np.random.default_rng(0)
    best = np.zeros(len(points), dtype=bool)
    for _ in range(128):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        normal = np.cross(b - a, c - a)
        length = np.linalg.norm(normal)
        if length < 1e-9:
            continue
        normal /= length
        inliers = np.abs((points - a) @ normal) < .006
        if inliers.sum() > best.sum():
            best = inliers
    if best.sum() < 30:
        raise ValueError('No supported depth plane')
    center = points[best].mean(axis=0)
    _, _, vectors = np.linalg.svd(points[best] - center, full_matrices=False)
    normal = vectors[-1]
    return normal, float(normal @ center), int(best.sum())


def depth_metrics(depth, k, rvec, tvec, width, height):
    rectangle = np.array([[0., 0., 0.], [width, 0., 0.],
                          [width, height, 0.], [0., height, 0.]])
    polygon = cv2.projectPoints(rectangle, rvec, tvec, k, None)[0].reshape(-1, 2)
    mask = np.zeros(depth.shape, np.uint8)
    cv2.fillConvexPoly(mask, np.rint(polygon).astype(np.int32), 255)
    mask = cv2.erode(mask, np.ones((9, 9), np.uint8))
    y, x = np.where(mask > 0)
    if not len(x):
        raise ValueError('Projected board has no interior pixels')
    valid = depth[y, x] > 0
    coverage = float(valid.mean())
    # Spatially sample to bound work. Validation blocks are never plane-fit inputs.
    x, y = x[valid][::4], y[valid][::4]
    if len(x) < 60:
        return dict(valid_fraction=coverage, samples=len(x), status='INSUFFICIENT_DEPTH'), polygon
    normal = cv2.Rodrigues(rvec)[0][:, 2]
    theoretical, rays = expected_z(np.c_[x, y], k, normal, float(normal @ tvec.ravel()))
    measured = depth[y, x] / 1000.
    residual = (measured - theoretical) * 1000
    xyz = rays * measured[:, None]
    fit = ((x // 4 + y // 4) % 3) != 0
    depth_normal, distance, support = fit_depth_plane(xyz[fit])
    plane_test = np.abs(xyz[~fit] @ depth_normal - distance) * 1000
    angle = np.degrees(np.arccos(np.clip(abs(depth_normal @ normal), 0, 1)))
    result = dict(valid_fraction=coverage, samples=len(x),
        signed_z_median_mm=float(np.median(residual)),
        abs_z_median_mm=float(np.median(abs(residual))),
        abs_z_p95_mm=float(np.percentile(abs(residual), 95)),
        depth_plane_fit_samples=int(fit.sum()), depth_plane_inliers=support,
        depth_plane_validation_samples=int((~fit).sum()),
        depth_plane_validation_median_mm=float(np.median(plane_test)),
        depth_plane_validation_p95_mm=float(np.percentile(plane_test, 95)),
        plane_normal_difference_deg=float(angle),
        note='RGB plane uses nominal print scale and fixed K; not independent absolute accuracy')
    return result, polygon


def check_board(image, depth, k, config, table):
    definition = config['boards'][table]
    count = config['squares_x'] * config['squares_y'] // 2
    first = definition['marker_start']
    marker_ids = np.asarray(definition.get('marker_ids', np.arange(first, first + count)), dtype=np.int32)
    if len(marker_ids) != count or len(np.unique(marker_ids)) != count:
        raise ValueError('Board marker definition has wrong count or duplicates')
    board = cv2.aruco.CharucoBoard((config['squares_x'], config['squares_y']),
        config['square_length'], config['marker_length'],
        cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, config['dictionary'])),
        marker_ids)
    board.setLegacyPattern(config.get('legacy_pattern', False))
    parameters = cv2.aruco.DetectorParameters()
    parameters.minMarkerPerimeterRate = .01
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    # Interpolate without supplying K or a known scene pose to the detector.
    detector = cv2.aruco.CharucoDetector(board, cv2.aruco.CharucoParameters(), parameters)
    corners, ids, _, _ = detector.detectBoard(image)
    if ids is None or len(ids) < config['min_corners']:
        return dict(table=table, status='NOT_ENOUGH_CORNERS', corners=0 if ids is None else len(ids)), image.copy()
    ids = ids.ravel()
    objects = board.getChessboardCorners()[ids].astype(np.float64)
    pixels = corners.reshape(-1, 2).astype(np.float64)
    fit = ids % 3 != 0
    if fit.sum() < 6 or (~fit).sum() < 4:
        return dict(table=table, status='INSUFFICIENT_VALIDATION_CORNERS', corners=len(ids)), image.copy()
    r, t = fit_pose(objects[fit], pixels[fit], k)
    projected = cv2.projectPoints(objects, r, t, k, None)[0].reshape(-1, 2)
    error = np.linalg.norm(projected - pixels, axis=1)
    pose = np.eye(4)
    pose[:3, :3], pose[:3, 3] = cv2.Rodrigues(r)[0], t.ravel()
    result = dict(table=table, marker_start=first, status='REVIEW_REQUIRED', corners=len(ids),
        square_length_m=config['square_length'], marker_ids=marker_ids.tolist(), corner_ids=ids.tolist(),
        fit_ids=ids[fit].tolist(), validation_ids=ids[~fit].tolist(),
        fit_rms_px=float(np.sqrt(np.mean(error[fit] ** 2))),
        validation_rms_px=float(np.sqrt(np.mean(error[~fit] ** 2))),
        image_limit_px=config['max_reprojection_error_px'],
        image_limit_passed=bool(np.sqrt(np.mean(error[~fit] ** 2)) <= config['max_reprojection_error_px']),
        T_camera_board=pose.tolist(),
        board_center_z_m=float((pose @ np.array([config['squares_x'] * config['square_length'] / 2,
            config['squares_y'] * config['square_length'] / 2, 0, 1]))[2]))
    result['depth'], polygon = depth_metrics(depth, k, r, t,
        config['squares_x'] * config['square_length'], config['squares_y'] * config['square_length'])
    annotated = image.copy()
    cv2.polylines(annotated, [np.rint(polygon).astype(np.int32)], True, (0, 255, 255), 2)
    for index, (pixel, estimate) in enumerate(zip(pixels, projected)):
        cv2.circle(annotated, tuple(np.rint(pixel).astype(int)), 3, (0, 255, 0) if fit[index] else (0, 100, 255), 1)
        cv2.drawMarker(annotated, tuple(np.rint(estimate).astype(int)), (255, 0, 255), cv2.MARKER_CROSS, 5, 1)
    text = f'{table}: {fit.sum()} fit / {(~fit).sum()} check | check RMS {result["validation_rms_px"]:.3f}px'
    cv2.rectangle(annotated, (0, 0), (image.shape[1], 55), (0, 0, 0), -1)
    cv2.putText(annotated, text, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 2)
    return result, annotated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--mobile-definition', type=Path,
                        help='Optional separate mobile board YAML; never use table dimensions for it')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    metadata_path = args.capture / 'metadata.json'
    metadata = json.loads(metadata_path.read_text())
    if not metadata.get('success') or metadata.get('kind') != 'rgbd':
        raise ValueError('Need a successful RGB-D capture')
    if np.any(np.asarray(metadata['projection']['D']) != 0):
        raise ValueError('This check requires the recorded undistorted stream')
    k = np.array(metadata['projection']['K'])
    config = yaml.safe_load(args.layout.read_text())['charuco']
    targets = [(table, config) for table in config['boards']]
    if args.mobile_definition:
        mobile = yaml.safe_load(args.mobile_definition.read_text())
        mobile_config = dict(config, **{key: mobile[key] for key in (
            'squares_x', 'squares_y', 'square_length', 'marker_length', 'dictionary', 'legacy_pattern')})
        mobile_config['boards'] = dict(mobile=dict(marker_start=mobile['marker_ids'][0],
                                                  marker_ids=mobile['marker_ids']))
        targets.append(('mobile', mobile_config))
    report = dict(status='REVIEW_REQUIRED', frames=[], K_fixed=True,
        capture=str(args.capture.resolve()), source_metadata_sha256=hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        layout_sha256=hashlib.sha256(args.layout.read_bytes()).hexdigest(),
        absolute_accuracy_validated=False, manipulation_approved=False,
        note='Temporal samples of one setup; printed scale and absolute accuracy are not established by this check')
    if args.mobile_definition:
        report['mobile_definition_sha256'] = hashlib.sha256(args.mobile_definition.read_bytes()).hexdigest()
    for pair in metadata['pairs']:
        image = cv2.imread(str(args.capture / pair['rgb_path']))
        depth = cv2.imread(str(args.capture / pair['depth_path']), -1)
        if image is None or depth is None or depth.shape != image.shape[:2] or depth.dtype != np.uint16:
            raise ValueError('Invalid saved RGB-D payload')
        for table, board_config in targets:
            result, annotated = check_board(image, depth, k, board_config, table)
            result['frame'] = pair['index']
            report['frames'].append(result)
            if result['status'] == 'REVIEW_REQUIRED' and pair['index'] in (0, len(metadata['pairs']) - 1):
                cv2.imwrite(str(args.output / f'{table}_{pair["index"]:03d}.png'), annotated)
    usable = [x for x in report['frames'] if 'depth' in x and 'signed_z_median_mm' in x['depth']]
    if not usable:
        report['status'] = 'INSUFFICIENT_REFERENCE'
    else:
        report['summary'] = dict(board_frames=len(usable),
            max_validation_rms_px=max(x['validation_rms_px'] for x in usable),
            median_signed_z_mm=float(np.median([x['depth']['signed_z_median_mm'] for x in usable])),
            median_abs_z_mm=float(np.median([x['depth']['abs_z_median_mm'] for x in usable])),
            median_depth_valid_fraction=float(np.median([x['depth']['valid_fraction'] for x in usable])),
            median_normal_difference_deg=float(np.median([x['depth']['plane_normal_difference_deg'] for x in usable])))
        report['by_board'] = {}
        for table, _ in targets:
            rows = [x for x in usable if x['table'] == table]
            if rows:
                report['by_board'][table] = dict(frames=len(rows),
                    max_validation_rms_px=max(x['validation_rms_px'] for x in rows),
                    image_limit_passed=all(x['image_limit_passed'] for x in rows),
                    median_board_center_z_m=float(np.median([x['board_center_z_m'] for x in rows])),
                    median_signed_z_mm=float(np.median([x['depth']['signed_z_median_mm'] for x in rows])),
                    median_abs_z_mm=float(np.median([x['depth']['abs_z_median_mm'] for x in rows])),
                    median_valid_depth_fraction=float(np.median([x['depth']['valid_fraction'] for x in rows])))
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'frames'}, indent=2))


if __name__ == '__main__':
    main()
