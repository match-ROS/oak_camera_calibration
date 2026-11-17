"""Static ISP exposure bracketing and OpenCV Mertens exposure fusion."""
import math

import cv2
import numpy as np


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


def fuse(images):
    if len(images) != 3 or any(im.dtype != np.uint8 or im.shape != images[0].shape
                               or im.ndim != 3 or im.shape[2] != 3 for im in images):
        raise ValueError('HDR requires three matching uint8 BGR images')
    # Bound CPU parallelism while other workspace applications are running.
    cv2.setNumThreads(2)
    result = cv2.createMergeMertens(1., 1., 1.).process(images)
    if not np.isfinite(result).all():
        raise RuntimeError('Nonfinite HDR fusion output')
    np.multiply(result, 255, out=result)
    np.rint(result, out=result)
    np.clip(result, 0, 255, out=result)
    return result.astype(np.uint8)
