"""Geometry for rectified depth snapshots. No device/ROS access."""
import numpy as np


def depth_to_xyz(depth_mm, intrinsic):
    """Deproject uint16 Z-depth using the actual rectified frame's K, in metres."""
    depth_mm = np.asarray(depth_mm)
    k = np.asarray(intrinsic, dtype=float)
    if depth_mm.ndim != 2 or depth_mm.dtype != np.uint16:
        raise ValueError('Expected a uint16 HxW millimetre depth map')
    if k.shape != (3, 3) or not np.isfinite(k).all() or min(k[0, 0], k[1, 1]) <= 0:
        raise ValueError('Invalid depth projection matrix')
    if not np.allclose(k[2], [0, 0, 1]) or abs(np.linalg.det(k)) < 1e-9:
        raise ValueError('Invalid pinhole projection')
    v, u = np.nonzero(depth_mm)
    rays = np.stack((u, v, np.ones_like(u)), axis=1) @ np.linalg.inv(k).T
    xyz = rays * (depth_mm[v, u].astype(float) / 1000)[:, None]
    if not np.isfinite(xyz).all():
        raise ValueError('Non-finite point cloud')
    return np.ascontiguousarray(xyz, dtype='<f4')
