"""Conservative static-scene depth fusion, independent of hardware/ROS."""
import warnings
import numpy as np


def fuse_depth(frames, support_fraction=.75, absolute_mm=10., relative=.01):
    """Median of valid depths; require repeated agreement, never fill holes.

    Zeros are invalid, not zero-distance measurements. Returned MAD describes
    observed temporal variation, not calibrated uncertainty or absolute accuracy.
    """
    frames = np.asarray(frames)
    if frames.ndim != 3 or frames.dtype != np.uint16 or not 4 <= len(frames) <= 32:
        raise ValueError('Expected 4..32 uint16 depth frames with identical HxW shape')
    if not .5 < support_fraction <= 1 or absolute_mm <= 0 or relative < 0:
        raise ValueError('Invalid stability thresholds')
    valid = frames > 0
    counts = valid.sum(axis=0).astype(np.uint8)
    values = np.where(valid, frames, np.nan).astype(np.float32)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)  # Entirely invalid pixels.
        center = np.nanmedian(values, axis=0)
        deviations = np.abs(values - center)
        mad = np.nanmedian(deviations, axis=0)
    tolerance = np.maximum(absolute_mm, relative * center)
    inliers = (valid & (deviations <= tolerance)).sum(axis=0).astype(np.uint8)
    required = int(np.ceil(len(frames) * support_fraction))
    stable = (counts >= required) & (inliers >= required) & (mad <= tolerance)
    hq = np.where(stable, np.nan_to_num(center), 0).round().astype(np.uint16)
    return dict(hq=hq, valid_counts=counts, inlier_counts=inliers,
                temporal_mad_mm=np.nan_to_num(mad), stable=stable)
