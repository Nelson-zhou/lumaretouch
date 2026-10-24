# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict eye-symmetry boundary over the unchanged shared eye-shape Rust ABI.

AUTHORED / UNRUN. This adapter converts admitted isotropic scale and head-up
translation to the existing size/position slots, then delegates every offset
to eye_shape_native.controls. No second solver, native binary or fallback.
"""
import math
import numpy as np

from . import eye_shape_native as _shared

MAX_POINTS = 256
FRAME_LEN = 10
SIZE_GAIN = 0.12
POSITION_GAIN = 0.08
MAX_DISPLACEMENT_GAIN = 0.30
FRAME_TOLERANCE = 1e-6


def _message(error):
    message = str(error)
    if '眼形 Rust' in message:
        return message.replace('眼形 Rust', '眼睛对称共用的眼形 Rust')
    return '眼睛对称：' + message


def available():
    """Load actual liblrt_eye_shape.so and verify ABI 1 and controls symbol.

    The shared cached loader checks both symbols. File existence alone is not
    capability. Success does not establish a usable source or measured request.
    """
    try:
        _shared.native()
    except (OSError, RuntimeError, AttributeError):
        return False
    return True


def _shape(value, shape, label):
    if (type(value) is not np.ndarray or value.shape != shape
            or value.dtype != np.dtype(np.float64) or not value.dtype.isnative):
        raise ValueError(f'{label} 需要精确形状 {shape} 的原生 float64 ndarray')


def _snapshot(value):
    result = np.array(value, dtype=np.float64, order='C', copy=True)
    result.setflags(write=False)
    return result


def _number(value, lower, upper, label):
    if (type(value) not in (int, float) or not lower <= value <= upper
            or not math.isfinite(value)):
        raise ValueError(f'{label} 超出有限的共享眼形控制范围，未截断或改写')
    return float(value)


def controls(points, frame, *, scale, shift):
    """Return owned float64 forward offsets from the unchanged Rust controls.

    points[N,2] and frame[10] must be exact native float64 ndarrays, N=1..256.
    Frame: outward(2), independent head-up(2), corner-center(2), iris-center(2),
    corner-width, opening-height. Width/height >=1; axes unit and orthogonal to
    the unchanged ABI's 1e-6 tolerance. No frame repair or anatomy inference.

    Built-in finite scale and shift become values[0]=(scale-1)/.12 and
    values[9]=shift/(.08*width). Converted controls must lie strictly within
    [-1,1], including floating-point endpoints; they are never clipped. All
    eight other controls and both role weights are exactly zero. Roles do not
    participate in the shared size/position terms. Scale/shift are target
    measurements, not portable recipe strengths and not an alternate solver.

    Both inputs are shape/dtype checked before private read-only snapshots;
    validation and native delegation use those same snapshots. The caller
    must not mutate during copying. Direct identity calls still require the
    native library. Valid all-zero output is not evidence of missing native.
    The host must establish whether requested source targets are resolved.
    """
    try:
        if (type(points) is not np.ndarray or points.ndim != 2
                or points.shape[1] != 2 or not 1 <= len(points) <= MAX_POINTS):
            raise ValueError('points 必须为 [N,2]，N 在 [1,256]')
        _shape(points, (len(points), 2), 'points')
        _shape(frame, (FRAME_LEN,), 'frame')
        p, f = _snapshot(points), _snapshot(frame)
        if not np.isfinite(p).all() or not np.isfinite(f).all():
            raise ValueError('源点与坐标帧必须全部有限')
        if (abs(float(f[:2] @ f[:2]) - 1.0) > FRAME_TOLERANCE
                or abs(float(f[2:4] @ f[2:4]) - 1.0) > FRAME_TOLERANCE
                or abs(float(f[:2] @ f[2:4])) > FRAME_TOLERANCE
                or f[8] < 1.0 or f[9] < 1.0):
            raise ValueError('坐标帧、眼宽或眼裂高不满足共享眼形严格边界')
        factor = _number(scale, 1.0 - SIZE_GAIN, 1.0 + SIZE_GAIN, 'scale')
        limit = POSITION_GAIN * float(f[8])
        distance = _number(shift, -limit, limit, 'shift')
        values = np.zeros(FRAME_LEN, dtype=np.float64)
        values[0] = (factor - 1.0) / SIZE_GAIN
        values[9] = distance / limit
        if (not np.isfinite(values).all() or np.any(np.abs(values) > 1.0)
                or (distance != 0.0 and values[9] == 0.0)):
            raise ValueError('换算后的共享控制超界或丢失非零位移，未截断或改写')
        roles = np.zeros((len(p), 2), dtype=np.float64)
        roles.setflags(write=False)
        values.setflags(write=False)
        result = _shared.controls(p, roles, f, values)
        _shape(result, p.shape, 'Rust output')
        if not np.isfinite(result).all():
            raise RuntimeError('Rust 输出非有限')
        if np.any(np.hypot(result[:, 0], result[:, 1])
                  > MAX_DISPLACEMENT_GAIN * float(f[8])):
            raise RuntimeError('Rust 输出超出原始逐点位移边界')
        if values[0] == 0.0 and values[9] == 0.0 and np.any(result != 0.0):
            raise RuntimeError('Rust 恒等控制产生了非零位移')
        # Publish only independent output, even when a foreign test double or
        # future shared bridge returns a view. This does not evaluate offsets.
        return np.array(result, dtype=np.float64, order='C', copy=True)
    except (ValueError, RuntimeError, OSError, AttributeError) as error:
        raise type(error)(_message(error)) from error
