"""Conservative static-scene depth fusion, independent of hardware/ROS."""
import numpy as np


def median_of_sorted(samples, first, count):
    """Median of a contiguous valid span in each sorted sample vector."""
    size = np.maximum(1, count.astype(np.intp))
    start = np.minimum(first, samples.shape[-1] - 1)
    low = np.take_along_axis(samples, (start + (size - 1)//2)[..., None], axis=-1)[..., 0]
    high = np.take_along_axis(samples, (start + size//2)[..., None], axis=-1)[..., 0]
    return (low.astype(np.float32) + high) * .5


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
    # Sort the small sample vectors contiguously. Zero depths sort before
    # measurements, and invalid deviations sort after measured deviations.
    values = np.moveaxis(frames, 0, -1)
    valid = values > 0
    counts = valid.sum(axis=-1, dtype=np.uint8)
    center = median_of_sorted(np.sort(values, axis=-1), len(frames) - counts, counts)
    deviations = np.where(valid, np.abs(values - center[..., None]), np.inf)
    mad = median_of_sorted(np.sort(deviations, axis=-1), 0, counts)
    mad[counts == 0] = 0
    tolerance = np.maximum(absolute_mm, relative * center)
    inliers = (deviations <= tolerance[..., None]).sum(axis=-1, dtype=np.uint8)
    required = int(np.ceil(len(frames) * support_fraction))
    stable = (counts >= required) & (inliers >= required) & (mad <= tolerance)
    hq = np.where(stable, center, 0).round().astype(np.uint16)
    return dict(hq=hq, valid_counts=counts, inlier_counts=inliers,
                temporal_mad_mm=mad, stable=stable)


def fuse_brackets(brackets):
    """Require three consistent frames per setting and agreement across settings."""
    if brackets.ndim != 4 or brackets.shape[:2] != (4, 4) or brackets.dtype != np.uint16:
        raise ValueError('Expected four groups of four uint16 stereo frames')
    groups = [fuse_depth(frames) for frames in brackets]
    stage_depth = np.stack([group['hq'] for group in groups])
    ordered = np.sort(np.moveaxis(stage_depth, 0, -1), axis=-1)
    count = np.count_nonzero(ordered, axis=-1)
    first = 4 - count
    low = np.take_along_axis(ordered, np.minimum(first, 3)[..., None], axis=-1)[..., 0].astype(np.float32)
    high = ordered[..., -1]
    conflict = (high - low) > np.maximum(10., .01 * (high + low) * .5)
    center = median_of_sorted(ordered, first, count)
    hq = np.where(conflict, 0, center).round().astype(np.uint16)
    return dict(hq=hq, stable=(hq > 0), stage_depth_mm=stage_depth,
                stage_inlier_counts=np.stack([group['inlier_counts'] for group in groups]),
                contributing_settings=count.astype(np.uint8), cross_exposure_conflict=conflict)
