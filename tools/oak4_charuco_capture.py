#!/usr/bin/env python3
"""Exclusive OAK4 per-board focus/exposure search; invoked by the photo service."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import math
import os
from pathlib import Path
import time

os.environ.setdefault('DEPTHAI_TELEMETRY', '0')
import cv2
import depthai as dai
import numpy as np

from oak4_charuco import Board, rank, validate_config
from oak4_photo_capture import metadata


def run(args, report):
    config = json.loads(args.search_config.read_text())
    validate_config(config)
    boards = {side: Board(config['boards'], side) for side in ('right', 'left')}
    cv2.setNumThreads(2)
    jobs = []

    def save(path, image):
        path = args.output/path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(path), image, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
            raise RuntimeError('Cannot save '+str(path))

    with ThreadPoolExecutor(max_workers=2) as writers:
        with dai.Device(dai.DeviceInfo(args.ip)) as device:
            device.setMaxReconnectionAttempts(0)
            report['device_id'] = device.getDeviceId()
            if report['device_id'] != args.device_id:
                raise RuntimeError('Device identity differs from inventory')
            calibration = device.readCalibration()
            factory = dict(K=calibration.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, 8000, 6000),
                           D=calibration.getDistortionCoefficients(dai.CameraBoardSocket.CAM_A))
            report['factory_optics_approximate_only'] = factory
            with dai.Pipeline(device) as pipeline:
                camera = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A,
                    sensorResolution=(8000, 6000), sensorFps=10)
                camera.initialControl.setAutoExposureEnable()
                camera.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
                camera.initialControl.setManualFocus(107)
                full = camera.requestFullResolutionOutput(fps=10, useHighestResolution=True)
                small = pipeline.create(dai.node.ImageManip)
                small.initialConfig.setOutputSize(2000, 1500)
                small.setMaxOutputFrameSize(2000*1500*3)
                small.inputImage.setBlocking(False); small.inputImage.setMaxSize(1)
                full.link(small.inputImage)
                preview = small.out.createOutputQueue(maxSize=2, blocking=False)
                gate = pipeline.create(dai.node.Script)
                full.link(gate.inputs['frames'])
                gate.setScript("""
while True:
    frame = node.io['frames'].get()
    if node.io['trigger'].tryGet() is not None:
        node.io['still'].send(frame)
""")
                native = gate.outputs['still'].createOutputQueue(maxSize=1, blocking=False)
                trigger = gate.inputs['trigger'].createInputQueue()
                control = camera.inputControl.createInputQueue()
                last_preview = last_native = -1

                def get(queue, timeout=8):
                    deadline = time.monotonic()+timeout
                    while time.monotonic() < deadline:
                        frame = queue.tryGet()
                        if frame is not None:
                            return frame, metadata(frame)
                        time.sleep(.005)
                    raise TimeoutError('No camera frame before deadline')

                def setting(focus, exposure, wb):
                    nonlocal last_preview
                    while preview.tryGet() is not None:
                        pass
                    ctrl = dai.CameraControl()
                    ctrl.setManualFocus(focus); ctrl.setManualExposure(exposure, args.iso)
                    ctrl.setManualWhiteBalance(wb); control.send(ctrl)
                    deadline = time.monotonic()+8
                    consecutive = 0
                    while time.monotonic() < deadline:
                        frame, info = get(preview)
                        correct = (info['sequence'] > last_preview and info['lens_position'] == focus
                            and info['reported_iso'] == args.iso and info['white_balance_K'] == wb
                            and info['exposure_us'] > 0 and abs(math.log2(info['exposure_us']/exposure)) < .1)
                        last_preview = info['sequence']
                        consecutive = consecutive+1 if correct else 0
                        if consecutive >= 2:
                            return frame.getCvFrame(), info
                    raise RuntimeError('Focus/exposure/white balance not confirmed')

                def full_image(expected):
                    nonlocal last_native
                    for _ in range(3):
                        trigger.send(dai.Buffer())
                        frame, info = get(native, 30)
                        if info['sequence'] <= last_native:
                            raise RuntimeError('Duplicate native search image')
                        last_native = info['sequence']
                        if ((info['width'], info['height']) == (8000, 6000)
                            and all(info[k] == expected[k] for k in
                                    ('exposure_us', 'reported_iso', 'lens_position', 'white_balance_K'))):
                            return frame.getCvFrame(), info
                    raise RuntimeError('Native frame does not confirm selected settings')

                pipeline.start()
                try:
                    # Meter on the overview; require a stable focus/exposure window.
                    started = time.monotonic(); recent = []
                    while time.monotonic()-started < 10:
                        frame, meter = get(preview)
                        recent.append(meter); recent = recent[-5:]
                        evs = [m['exposure_us']*m['reported_iso'] for m in recent]
                        if (time.monotonic()-started >= 2 and len(recent) == 5 and min(evs) > 0
                            and math.log2(max(evs)/min(evs)) < .1 and meter['lens_position'] == 107
                            and meter['white_balance_K'] > 0):
                            break
                    else:
                        raise TimeoutError('Overview exposure did not settle')
                    overview = frame.getCvFrame()
                    save('overview.png', overview)
                    report['overview'] = dict(meter, path='overview.png')
                    report['overview_boards'] = {}
                    overview_optics = config['intrinsics'].get('107', factory)
                    for side, board in boards.items():
                        observation = board.observe(overview)
                        rough = board.pose(observation, overview_optics, (2000, 1500))
                        rough['purpose'] = 'Coarse search guidance only; not a global camera registration'
                        report['overview_boards'][side] = dict(observation=observation, approximate_pose=rough)
                    wb = meter['white_balance_K']
                    base = max(100, min(90000, round(meter['exposure_us']*meter['reported_iso']/args.iso)))
                    report['search_trials'] = []
                    coarse = {side: [] for side in boards}
                    for focus in config['focus_candidates']:
                        image, info = setting(focus, base, wb)
                        trial = dict(stage='focus', actual=info, boards={})
                        for side, board in boards.items():
                            observation = board.observe(image)
                            trial['boards'][side] = observation
                            coarse[side].append(dict(focus=focus, observation=observation))
                        report['search_trials'].append(trial)
                        print(f'RUNNING focus {focus}: '+str({s:o['charuco_count'] for s,o in trial['boards'].items()}), flush=True)
                    report['boards'] = {}
                    for side, board in boards.items():
                        found = [v for v in coarse[side] if v['observation']['marker_count']]
                        if not found:
                            report['boards'][side] = dict(status='NOT_FOUND')
                            continue
                        ranked = sorted(found, key=lambda v: rank(v['observation']), reverse=True)
                        target_focus = ranked[0]['focus']
                        exposures = sorted({max(100, min(90000, round(base*2**ev))) for ev in config['exposure_offsets_ev']})
                        exposure_trials = []
                        for exposure in exposures:
                            image, info = setting(target_focus, exposure, wb)
                            obs = board.observe(image)
                            report['search_trials'].append(dict(stage='exposure', board=side, actual=info, observation=obs))
                            exposure_trials.append(dict(exposure=exposure, observation=obs))
                        exposure = max(exposure_trials, key=lambda v: rank(v['observation'], exposure=True))['exposure']
                        # Native final verification can reverse a low-resolution focus ranking.
                        shortlist = [v['focus'] for v in ranked[:2]]
                        calibrated = [v for v in ranked if str(v['focus']) in config['intrinsics']]
                        if calibrated and calibrated[0]['focus'] not in shortlist:
                            shortlist.append(calibrated[0]['focus'])
                        candidates = []
                        for focus in shortlist:
                            _, expected = setting(focus, exposure, wb)
                            image, info = full_image(expected)
                            # Native detection only near this board; no full-frame 48MP vision batch.
                            reference = next((v['observation'] for v in found if v['focus'] == focus), ranked[0]['observation'])
                            x, y, w, h = reference['roi']
                            x0, y0 = max(0, (x-w*.35)*4), max(0, (y-h*.35)*4)
                            x1, y1 = min(8000, (x+w*1.35)*4), min(6000, (y+h*1.35)*4)
                            roi = [int(x0), int(y0), int(x1-x0), int(y1-y0)]
                            observation = board.observe(image, roi)
                            path = f'{side}/focus-{focus}.png'
                            jobs.append(writers.submit(save, path, image))
                            profile = config['intrinsics'].get(str(focus))
                            pose = board.pose(observation, profile) if profile else dict(status='NEEDS_FOCUS_INTRINSICS')
                            candidates.append(dict(path=path, actual=info, observation=observation, pose=pose,
                                intrinsics=profile, intrinsics_status='focus_specific_candidate' if profile else 'missing'))
                        best = max(candidates, key=lambda v: rank(v['observation']))
                        usable = [v for v in candidates if v['pose'].get('image_check_passed')]
                        pose_best = max(usable, key=lambda v: rank(v['observation'])) if usable else None
                        rough_profile = config['intrinsics'].get(str(best['actual']['lens_position']), factory)
                        rough = board.pose(best['observation'], rough_profile)
                        if 'T_camera_board' in rough:
                            rough['approximate_only'] = best['intrinsics'] is None
                        row = dict(status='FOUND' if best['observation']['marker_count'] else 'NATIVE_NOT_FOUND',
                                   best=best, pose_selection=pose_best, candidates=candidates,
                                   approximate_pose=rough, optimum_scope='Best tested native shortlist; no global optimum claim')
                        if pose_best:
                            tcb = np.array(pose_best['pose']['T_camera_board'])
                            bindings = config.get('base_bindings', {}).get('robots', {})
                            row['camera_in_adopted_bases'] = {
                                arm: (np.array(binding['T_base_board']) @ np.linalg.inv(tcb)).tolist()
                                for arm, binding in bindings.items() if binding['board_id'] == side+'_table_board'}
                        report['boards'][side] = row
                        print(f'DONE {side}: focus {best["actual"]["lens_position"]}; pose '+('candidate available' if pose_best else 'not ready'), flush=True)
                finally:
                    pipeline.stop(); pipeline.wait()
        report['camera_closed_at'] = datetime.now().astimezone().isoformat()
        for job in jobs:
            job.result()
    report['summary'] = dict(both_boards_found=all(report['boards'][s]['status']=='FOUND' for s in boards),
        both_pose_candidates_available=all(report['boards'][s].get('pose_selection') is not None for s in boards),
        global_calibration_applied=False, absolute_accuracy_validated=False)
    if report['summary']['both_pose_candidates_available']:
        left = np.array(report['boards']['left']['pose_selection']['pose']['T_camera_board'])
        right = np.array(report['boards']['right']['pose_selection']['pose']['T_camera_board'])
        report['two_board_geometry'] = dict(T_left_board_right_board_candidate=(np.linalg.inv(left) @ right).tolist(),
            assumption='Camera and boards stationary between images; each image uses matching focus intrinsics',
            applied=False)
    for side, row in report['boards'].items():
        if row.get('status') != 'FOUND':
            continue
        (args.output/side/'metadata.json').write_text(json.dumps(dict(success=True, mode='standard',
            device_id=report['device_id'],
            standard=dict(row['best']['actual'], path=Path(row['best']['path']).name)), indent=2)+'\n')
        if row['best']['intrinsics']:
            (args.output/side/'intrinsics.json').write_text(json.dumps(row['best']['intrinsics'], indent=2)+'\n')
        selected = row.get('pose_selection')
        if selected:
            dest = args.output/side/'pose'; dest.mkdir()
            os.link(args.output/selected['path'], dest/'standard.png')
            (dest/'metadata.json').write_text(json.dumps(dict(success=True, mode='standard',
                device_id=report['device_id'],
                standard=dict(selected['actual'], path='standard.png')), indent=2)+'\n')
            (dest/'intrinsics.json').write_text(json.dumps(selected['intrinsics'], indent=2)+'\n')
            (dest/'pose.json').write_text(json.dumps(dict(board=side, observation=selected['observation'],
                pose=selected['pose'], camera_in_adopted_bases=row['camera_in_adopted_bases'],
                source_config_sha256=config['sources_sha256'], applied=False), indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True); parser.add_argument('--device-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--search-config', type=Path, required=True)
    parser.add_argument('--iso', type=int, default=100); parser.add_argument('--frames', type=int, default=1)
    args = parser.parse_args()
    if not 100 <= args.iso <= 1600 or args.frames != 1:
        parser.error('ISO100..1600 and --frames1 required; search captures separate hypotheses')
    report = dict(schema=1, mode='charuco', success=False, started_at=datetime.now().astimezone().isoformat(),
                  depthai=dai.__version__, opencv=cv2.__version__, data_files=dict(search_config='search-config.json'))
    try:
        run(args, report)
        report['success'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['finished_at'] = datetime.now().astimezone().isoformat()
        (args.output/'metadata.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
