#!/usr/bin/env python3
"""Compare per-view fixed-K checks and an explicitly hypothetical print scale."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import yaml
from oak4_rgbd_board_check import depth_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', nargs='+', type=Path, required=True)
    parser.add_argument('--mobile-definition', type=Path, required=True)
    parser.add_argument('--reported-five-field-mm', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 180 <= args.reported_five_field_mm <= 200:
        parser.error('Unexpected mobile-board span; verify board identity and units')
    definition = yaml.safe_load(args.mobile_definition.read_text())
    nominal_span = 5 * definition['square_length'] * 1000
    scale = args.reported_five_field_mm / nominal_span
    report = dict(schema=1, status='REVIEW_REQUIRED', views=[],
        absolute_accuracy_validated=False, calibration_modified=False,
        comparison_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        reference=dict(nominal_five_field_mm=nominal_span,
            reported_five_field_mm=args.reported_five_field_mm, source='operator ruler measurement',
            uncertainty_mm=None, hypothetical_isotropic_scale=scale,
            note='Sensitivity scenario only; one-axis ruler measurement does not establish isotropic scale or calibrated uncertainty'),
        note='One view per capture; temporal frames are repeated samples, not independent viewpoints')
    for capture in args.captures:
        metadata = json.loads((capture / 'metadata.json').read_text())
        check_path = capture / 'board-check-v1/report.json'
        check = json.loads(check_path.read_text())
        rows = [x for x in check['frames'] if x['table'] == 'mobile'
                and x.get('image_limit_passed') and 'signed_z_median_mm' in x.get('depth', {})]
        row = dict(capture=str(capture.resolve()),
            metadata_sha256=hashlib.sha256((capture / 'metadata.json').read_bytes()).hexdigest(),
            board_check_sha256=hashlib.sha256(check_path.read_bytes()).hexdigest(),
            mobile_reference_frames=len(rows), total_pairs=len(metadata['pairs']),
            usable_for_mobile_comparison=bool(rows))
        if not rows:
            row['reason'] = 'Mobile pattern absent, clipped, or insufficient detected/check corners'
            report['views'].append(row)
            continue
        k = np.asarray(metadata['projection']['K'])
        values = []
        for result in rows:
            pair = next(p for p in metadata['pairs'] if p['index'] == result['frame'])
            depth = cv2.imread(str(capture / pair['depth_path']), -1)
            pose = np.asarray(result['T_camera_board'])
            metrics, _ = depth_metrics(depth, k, cv2.Rodrigues(pose[:3, :3])[0],
                pose[:3, 3] * scale, definition['squares_x'] * definition['square_length'] * scale,
                definition['squares_y'] * definition['square_length'] * scale)
            values.append(metrics['signed_z_median_mm'])
        row.update(
            center_z_m_median=float(np.median([x['board_center_z_m'] for x in rows])),
            nominal_signed_z_mm_median=float(np.median([x['depth']['signed_z_median_mm'] for x in rows])),
            hypothetical_scaled_signed_z_mm_median=float(np.median(values)),
            max_validation_rms_px=max(x['validation_rms_px'] for x in rows),
            valid_depth_fraction_median=float(np.median([x['depth']['valid_fraction'] for x in rows])))
        report['views'].append(row)
    usable = [r for r in report['views'] if r['usable_for_mobile_comparison']]
    report['summary'] = dict(captures=len(report['views']), usable_mobile_views=len(usable),
        rejected_mobile_views=len(report['views']) - len(usable),
        no_offset_correction_applied=True)
    if args.output.exists():
        parser.error('Output already exists; preserve previous comparison')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
