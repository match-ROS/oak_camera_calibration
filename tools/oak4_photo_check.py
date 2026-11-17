#!/usr/bin/env python3
"""Bounded native OAK restart/acquisition check; never commands robot motion."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from oak4_photo_service import PhotoCapture


def utc():
    return datetime.now().astimezone().isoformat()


def image_info(path):
    import cv2
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Native image could not be decoded')
    height, width = image.shape[:2]
    with path.open('rb') as file:
        checksum = hashlib.file_digest(file, 'sha256').hexdigest()
    return dict(width=width, height=height, sha256=checksum)


def check_standard(capture, *, count=3, focus=116, report_path):
    if type(count) is not int or not 1 <= count <= 10:
        raise ValueError('Count must be 1..10')
    if type(focus) is not int or not 0 <= focus <= 255:
        raise ValueError('Focus must be 0..255')
    report_path = Path(report_path)
    if report_path.exists():
        raise FileExistsError('Check report already exists')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = dict(schema=1, started_at=utc(), requested_count=count, requested_focus=focus,
        captures=[], passed=False, robot_commands=False, device_reset_requested=False,
        assessment='Bounded repeated-start check, not a permanent reliability guarantee')
    previous_time = None
    device_id = None
    checksums = set()
    def save():
        temporary = report_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2)+'\n')
        temporary.replace(report_path)
    save()
    for index in range(count):
        item = dict(index=index+1, success=False)
        start = time.monotonic()
        try:
            result = capture.capture('standard', focus=focus)
            item['directory'] = result['directory']
            metadata = json.loads(Path(result['metadata']).read_text())
            frame = metadata['standard']
            if not metadata.get('success') or not metadata.get('device_id'):
                raise ValueError('Native worker did not confirm success and device identity')
            if (frame['width'], frame['height']) != (8000, 6000) or frame['lens_position'] != focus:
                raise ValueError('Native size or fixed focus does not match')
            current_id = metadata['device_id']
            if device_id is not None and current_id != device_id:
                raise ValueError('Physical camera changed between captures')
            device_id = current_id
            timestamp = frame['timestamp_device_s']
            if not math.isfinite(timestamp) or (previous_time is not None and timestamp <= previous_time):
                raise ValueError('Device timestamp did not advance; stale frame or device restart')
            info = image_info(Path(result['images']['standard']))
            if (info['width'], info['height']) != (8000, 6000):
                raise ValueError('Decoded image is not native 8000x6000')
            if info['sha256'] in checksums:
                raise ValueError('Identical image payload repeated; freshness not confirmed')
            checksums.add(info['sha256']); previous_time = timestamp
            item.update(success=True, device_id=device_id, actual_frame=frame, image=info,
                        sdk=metadata.get('depthai'))
        except Exception as error:
            item['error'] = str(error)
        item['elapsed_s'] = time.monotonic()-start
        report['captures'].append(item); save()
        if not item['success']:
            break
    report.update(finished_at=utc(), passed=len(report['captures']) == count and
        all(item['success'] for item in report['captures']))
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=3)
    parser.add_argument('--focus', type=int, default=116)
    args = parser.parse_args()
    capture = PhotoCapture()
    directory = capture.workspace/'setup/oak4/checks'/(
        datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    report = check_standard(capture, count=args.count, focus=args.focus, report_path=directory/'report.json')
    print(json.dumps(dict(passed=report['passed'], completed=len(report['captures']),
        requested=args.count, report=str(directory/'report.json'),
        captures=report['captures']), indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
