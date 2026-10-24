# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict private Rust forward-control boundary. AUTHORED / UNRUN.

No runtime build/download, fallback, RGB sampling, TPS or anatomy inference.
Host verifies source-owned oval roles and subject sides before calling controls.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path

import numpy as np

MAX_CONTROLS = 256
REGION_GAIN = 0.035
MAX_DISPLACEMENT = 0.08
FRAME_TOLERANCE = 1.0e-6
P = C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_face_contour.so'
    if not path.is_file():
        raise RuntimeError('脸部轮廓 Rust 核心未安装；未应用替代算法')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_face_contour_abi.argtypes = []
        lib.lrt_face_contour_abi.restype = C.c_uint32
        if lib.lrt_face_contour_abi() != 1:
            raise RuntimeError('脸部轮廓 Rust ABI 不匹配')
        lib.lrt_face_contour_controls_v1.argtypes = (
            [P, C.c_size_t] * 5 + [C.c_size_t, P, C.c_size_t])
        lib.lrt_face_contour_controls_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise RuntimeError('脸部轮廓 Rust 核心不能加载所需 ABI') from error
    return lib


def available():
    """Probe loading and required versioned symbols, not just file existence."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float64 or array.shape != shape:
        raise ValueError(label + ' requires exact native float64 shape ' + str(shape))


def _snapshot(array):
    # Always copy, even contiguous/read-only inputs: a caller-owned mutable base
    # must not remain aliased during the native call while ctypes releases GIL.
    owned = np.array(array, dtype=np.float64, order='C', copy=True)
    if not np.isfinite(owned).all():
        raise ValueError('脸部轮廓 Rust 输入必须全部为有限数值')
    owned.setflags(write=False)
    return owned


def _frame(frame):
    right_norm = float(np.hypot(frame[0], frame[1]))
    up_norm = float(np.hypot(frame[2], frame[3]))
    if (not np.isfinite(right_norm) or not np.isfinite(up_norm)
            or abs(right_norm - 1) > FRAME_TOLERANCE
            or abs(up_norm - 1) > FRAME_TOLERANCE
            or abs(float(frame[:2] @ frame[2:4])) > FRAME_TOLERANCE
            or frame[6] <= 0):
        raise ValueError('脸部轮廓需要单位正交头部坐标系和正的脸宽')


def _pair(array):
    return array.ctypes.data_as(P), array.size


def controls(points, roles, sides, frame, values):
    """Return owned float64 FORWARD displacements [N,2], never RGB or a grid.

    All arguments are numpy float64 arrays. Noncontiguous inputs are accepted
    through independent snapshots, never implicit dtype coercion. Callers must
    not mutate inputs while their snapshots are copied. N is in [1,256].
    roles[N,3] are unitless temple/cheekbone/jaw weights in [0,1].
    sides[N] is +1 for subject left, -1 for subject right, relative to head-right.
    frame[7]=[right_x,right_y,up_x,up_y,center_x,center_y,width].
    values[6]=[temple_left,temple_right,cheekbone_left,cheekbone_right,jaw_left,jaw_right].
    """
    if (type(points) is not np.ndarray or points.ndim != 2
            or points.shape[1] != 2 or not 1 <= len(points) <= MAX_CONTROLS):
        raise ValueError('脸部轮廓控制点必须为 [N,2]，N 在 [1,256]')
    count = len(points)
    inputs = ((points, (count, 2), 'points'), (roles, (count, 3), 'roles'),
              (sides, (count,), 'sides'), (frame, (7,), 'frame'),
              (values, (6,), 'values'))
    # Reject all dtypes/shapes before allocating any snapshots or loading code.
    for array, shape, label in inputs:
        _shape(array, shape, label)
    p, r, s, f, v = [_snapshot(array) for array, _, _ in inputs]
    if (np.any(r < 0) or np.any(r > 1) or np.any((s != 1) & (s != -1))
            or np.any(v < -1) or np.any(v > 1)):
        raise ValueError('脸部轮廓权重、人物侧别或参数超出允许范围')
    _frame(f)
    selected = np.where(s[:, None] == 1, v[::2], v[1::2])
    absolute_fraction = np.sum(REGION_GAIN * r * np.abs(selected), axis=1)
    if np.any(absolute_fraction > MAX_DISPLACEMENT):
        raise ValueError('脸部轮廓区域位移总预算超过脸宽的 8%；未缩减强度')
    inactive = np.all((r == 0) | (selected == 0), axis=1)
    output = np.empty((count, 2), dtype=np.float64)
    status = native().lrt_face_contour_controls_v1(
        *_pair(p), *_pair(r), *_pair(s), *_pair(f), *_pair(v), count, *_pair(output))
    if status:
        reasons = {1: '无效 ABI、长度、指针或别名', 2: '无效有限值、权重、侧别或参数',
                   3: '无效头部坐标系', 4: '超过原始位移预算', 5: 'Rust 内部异常'}
        message = '脸部轮廓 Rust 拒绝几何：' + reasons.get(status, str(status))
        if status == 5 or status not in reasons:
            raise RuntimeError(message)
        raise ValueError(message)
    if (not np.isfinite(output).all()
            or np.any(np.hypot(output[:, 0], output[:, 1]) > MAX_DISPLACEMENT * f[6])):
        raise RuntimeError('脸部轮廓 Rust 返回非有限或越界位移；结果已丢弃')
    # This checks direction, not a second deformation algorithm. Frame admits
    # small orthogonality roundoff; twice that tolerance covers dot rounding.
    if np.any(np.abs(output @ f[2:4]) > MAX_DISPLACEMENT * f[6] * FRAME_TOLERANCE * 2):
        raise RuntimeError('脸部轮廓 Rust 返回非头部横向位移；结果已丢弃')
    if np.any(output[inactive] != 0) or np.any(np.signbit(output[inactive])):
        raise RuntimeError('脸部轮廓 Rust 改动中性或零权重控制点；结果已丢弃')
    return output
