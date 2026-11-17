"""Validate an SDK-aligned RGB-D pair without contacting any device."""
import numpy as np


def validate_pair(rgb, depth, rgb_k, depth_k, rgb_time, depth_time,
                  sequences, previous=None, max_skew_s=.025, size=(1280, 960)):
    width, height = size
    if rgb.shape != (height, width, 3) or rgb.dtype != np.uint8:
        raise ValueError('Unexpected RGB dimensions/type')
    if depth.shape != (height, width) or depth.dtype != np.uint16:
        raise ValueError('Aligned depth must match RGB dimensions and be uint16 millimetres')
    for matrix in (rgb_k, depth_k):
        matrix = np.asarray(matrix, dtype=float)
        if (matrix.shape != (3, 3) or not np.isfinite(matrix).all()
                or min(matrix[0, 0], matrix[1, 1]) <= 0
                or not np.allclose(matrix[2], [0, 0, 1])):
            raise ValueError('Invalid actual output intrinsic matrix')
    if not np.allclose(rgb_k, depth_k, rtol=1e-5, atol=.03):
        raise ValueError('Aligned depth and RGB have different projection matrices')
    if not np.isfinite([rgb_time, depth_time]).all() or min(rgb_time, depth_time) < 0:
        raise ValueError('Invalid device timestamp')
    skew = abs(rgb_time - depth_time)
    if skew > max_skew_s + 1e-9:
        raise ValueError('RGB/depth timestamp difference exceeds threshold')
    if len(sequences) != 2 or any(s < 0 for s in sequences):
        raise ValueError('Invalid pair sequences')
    if previous is not None and any(s <= old for s, old in zip(sequences, previous)):
        raise ValueError('Duplicate or out-of-order RGB/depth pair')
    valid = depth > 0
    if not valid.any():
        raise ValueError('No valid depth in this pair')
    return dict(timestamp_difference_s=float(skew),
                valid_depth_fraction=float(valid.mean()),
                valid_depth_median_mm=float(np.median(depth[valid])))
