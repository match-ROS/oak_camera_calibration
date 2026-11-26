"""Static ISP exposure bracketing and OpenCV Mertens exposure fusion."""
import math
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np


def wait_metadata(queue, describe, predicate, timeout=8., consecutive=2):
    """Only accept consecutive confirmed frames, with bounded device wait."""
    deadline = time.monotonic() + timeout
    count, last_sequence = 0, -1
    while time.monotonic() < deadline:
        frame = queue.tryGet()
        if frame is None:
            time.sleep(.005)
            continue
        info = describe(frame)
        if info['sequence'] <= last_sequence:
            count = 0
            continue
        last_sequence = info['sequence']
        count = count + 1 if predicate(info) else 0
        if count >= consecutive:
            return info
    raise TimeoutError('HDR camera metadata did not settle/confirm within deadline')


def acquire(args, report, capture, control, preview, make_control, describe, request_burst=None):
    """Acquire full-resolution brackets without serial PNG I/O or fixed sleeps."""
    started = time.monotonic()
    timings = report.setdefault('hdr_timing_s', {})
    recent = []

    def stable(info):
        recent.append(info)
        del recent[:-5]
        report['metering_observations'] = list(recent)
        minimum_warmup = 5. if args.focus is None else 2.
        if time.monotonic() - started < minimum_warmup or len(recent) < 5:
            return False
        if (info['exposure_us'] <= 0 or info['reported_iso'] <= 0 or info['white_balance_K'] <= 0
                or not 0 <= info['lens_position'] <= 255):
            return False
        if args.focus is not None and info['lens_position'] != args.focus:
            return False
        evs = [v['exposure_us'] * v['reported_iso'] for v in recent]
        return (min(evs) > 0 and math.log2(max(evs) / min(evs)) < .05
                and max(v['white_balance_K'] for v in recent) - min(v['white_balance_K'] for v in recent) <= 30
                and len({v['lens_position'] for v in recent}) == 1)

    standard = wait_metadata(preview, describe, stable, timeout=10., consecutive=1)
    report['metering'] = report['standard'] = standard
    timings['auto_metering'] = time.monotonic() - started
    reference_ev = standard['exposure_us'] * standard['reported_iso']
    plan = bracket_plan(reference_ev, args.iso)
    report['hdr_brackets'] = []
    report['exposure_difference_ev'] = math.log2(plan[1]['exposure_us'] * args.iso / reference_ev)
    report['exposure_limited'] = abs(report['exposure_difference_ev']) > .2
    images = []
    for step in plan:
        tick = time.monotonic()
        # Clear queued metadata before changing controls.
        while preview.tryGet() is not None:
            pass
        ctrl = make_control()
        ctrl.setManualExposure(step['exposure_us'], args.iso)
        ctrl.setManualWhiteBalance(standard['white_balance_K'])
        ctrl.setManualFocus(standard['lens_position'])
        control.send(ctrl)

        def confirmed(info):
            try:
                verify_exposure(info, step['exposure_us'], args.iso, standard)
                return True
            except RuntimeError:
                return False

        settled = wait_metadata(preview, describe, confirmed)
        entry = dict(step, frames=[], path=f"hdr-{step['name']}.png")
        report['hdr_brackets'].append(entry)
        accumulator = None
        deadline = time.monotonic() + 8
        if request_burst is not None:
            request_burst(args.frames)
        while len(entry['frames']) < args.frames:
            frame, info = capture()
            if request_burst is not None and (
                not confirmed(info) or info['sequence'] <= settled['sequence']
            ):
                raise RuntimeError('HDR burst frame does not follow the confirmed exposure')
            if not confirmed(info):
                del frame
                if time.monotonic() > deadline:
                    raise RuntimeError('HDR full-resolution controls not confirmed')
                continue
            if entry['frames'] and info['exposure_us'] != entry['frames'][0]['exposure_us']:
                raise RuntimeError('HDR exposure changed during averaging')
            image = frame.getCvFrame()
            del frame
            entry['frames'].append(info)
            if args.frames > 1:
                if accumulator is None:
                    accumulator = image.astype(np.float32)
                else:
                    accumulator += image
                del image
        if args.frames > 1:
            accumulator /= args.frames
            np.rint(accumulator, out=accumulator)
            image = accumulator.astype(np.uint8)
        images.append(image)
        timings[step['name'] + '_acquisition'] = time.monotonic() - tick
        print(f"HDR {step['name']}: DONE ({len(entry['frames'])} frames)", flush=True)
    actual_base = report['hdr_brackets'][1]['frames'][0]['exposure_us']
    for entry in report['hdr_brackets']:
        entry['actual_ev'] = math.log2(entry['frames'][0]['exposure_us'] / actual_base)
        if abs(entry['actual_ev'] - entry['target_ev']) > .1:
            raise RuntimeError('HDR bracket spacing not confirmed')
    timings['acquisition_total'] = time.monotonic() - started
    return images


def finish(output, images, report, fast=False):
    """Keep decoded brackets for fusion; archive PNGs concurrently and losslessly."""
    timings = report['hdr_timing_s']

    def save(name, image):
        tick = time.monotonic()
        if image.shape != (6000, 8000, 3):
            raise RuntimeError(f'Expected native 8000x6000 BGR, received {image.shape}')
        if not cv2.imwrite(str(output / name), image, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
            raise RuntimeError(f'Cannot save {name}')
        return time.monotonic() - tick

    # Two archive writers + the unchanged two-thread fusion, bounded CPU usage.
    tick = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as writers:
        jobs = [(step['name'], writers.submit(save, step['path'], im))
                for step, im in zip(report['hdr_brackets'], images)]
        fusion_start = time.monotonic()
        result = fuse(images, threads=4) if fast else fuse(images)
        timings['fusion'] = time.monotonic() - fusion_start
        timings['final_png'] = save('hdr.png', result)
        for name, job in jobs:
            timings[name + '_png'] = job.result()  # Never accept incomplete archives.
    timings['processing_wall'] = time.monotonic() - tick
    report['hdr'] = dict(path='hdr.png', method='OpenCV Mertens (contrast=1,saturation=1,exposure=1)',
                         encoding='ISP 8-bit BGR exposure fusion; not radiometric RAW HDR',
                         alignment='none; static camera and scene required',
                         frame_count=sum(len(s['frames']) for s in report['hdr_brackets']))


def bracket_plan(reference_ev, iso):
    """Keep all three exposures in the established 100..90000 us range."""
    if not math.isfinite(reference_ev) or reference_ev <= 0 or not 100 <= iso <= 1600:
        raise ValueError('Invalid metering or ISO')
    base = max(400, min(22500, round(reference_ev / iso)))
    return [dict(name=name, target_ev=ev, exposure_us=round(base * 2 ** ev))
            for name, ev in (('short', -2), ('base', 0), ('long', 2))]


def verify_exposure(info, expected, iso, fixed):
    if info['reported_iso'] != iso or info['exposure_us'] <= 0:
        raise RuntimeError('HDR manual ISO/exposure not confirmed')
    if abs(math.log2(info['exposure_us'] / expected)) > .1:
        raise RuntimeError('HDR exposure time not confirmed')
    if any(info[key] != fixed[key] for key in ('lens_position', 'white_balance_K')):
        raise RuntimeError('HDR focus/white balance changed')


def fuse(images, threads=2):
    if len(images) != 3 or any(im.dtype != np.uint8 or im.shape != images[0].shape
                               or im.ndim != 3 or im.shape[2] != 3 for im in images):
        raise ValueError('HDR requires three matching uint8 BGR images')
    # OpenCV implements the fusion in native code. Bound the worker pool.
    cv2.setNumThreads(threads)
    result = cv2.createMergeMertens(1., 1., 1.).process(images)
    if not np.isfinite(result).all():
        raise RuntimeError('Nonfinite HDR fusion output')
    np.multiply(result, 255, out=result)
    np.rint(result, out=result)
    np.clip(result, 0, 255, out=result)
    return result.astype(np.uint8)
