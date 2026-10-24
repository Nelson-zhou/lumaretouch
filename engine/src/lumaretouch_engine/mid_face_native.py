# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict mid-face length inverse-field boundary. AUTHORED / UNRUN.

No Python deformation fallback, RGB sampling, inference, runtime build/download.
The host establishes upper-eye-boundary, nose and retained lower-face
measurement, support padding and compositing evidence.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

MAX_POINTS = 65536
PARAMS_LEN = 12
GAIN = 0.08
FRAME_TOLERANCE = 1.0e-10
MIN_TAIL = 0.25
MAX_TAIL = 4.0
MIN_PLATEAU_END = 1.25
MAX_PLATEAU_END = 8.0
MIN_FORWARD_DERIVATIVE = 0.4
P = C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_mid_face.so'
    if not path.is_file():
        raise RuntimeError('中庭 Rust 核心未安装；未应用替代算法')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_mid_face_abi.argtypes = []
        lib.lrt_mid_face_abi.restype = C.c_uint32
        if lib.lrt_mid_face_abi() != 1:
            raise RuntimeError('中庭 Rust ABI 不匹配')
        lib.lrt_mid_face_evaluate_v1.argtypes = (
            [P, C.c_size_t] * 2 + [C.c_size_t, P, C.c_size_t])
        lib.lrt_mid_face_evaluate_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise RuntimeError('中庭 Rust 核心不能加载所需 ABI') from error
    return lib


def available():
    """Actual load, ABI and versioned-symbol capability, not anatomical readiness."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def canonical_frame(right, down):
    """Validate 1e-10 orthonormal tolerance, then remove only frame roundoff.

    Return ((right_x,right_y),(down_x,down_y)); both handednesses are supported.
    The host should use these same axes for measurements, support and targets.
    This does not repair skewed frames or infer anatomical orientation.
    """
    try:
        if len(right) != 2 or len(down) != 2:
            raise ValueError('中庭头部坐标轴必须各含两个分量')
        values = (*right, *down)
        if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.floating))
               for v in values):
            raise ValueError('中庭头部坐标轴必须为有限数值')
        rx, ry, dx, dy = (float(v) for v in values)
    except (TypeError, OverflowError) as error:
        raise ValueError('中庭头部坐标轴必须为有限的二元数值') from error
    rn, dn = math.hypot(rx, ry), math.hypot(dx, dy)
    dot = rx * dx + ry * dy
    if (not all(math.isfinite(v) for v in (rx, ry, dx, dy, rn, dn, dot))
            or abs(rn - 1.0) > FRAME_TOLERANCE
            or abs(dn - 1.0) > FRAME_TOLERANCE or abs(dot) > FRAME_TOLERANCE):
        raise ValueError('中庭需要单位正交头部坐标系；不修复倾斜坐标轴')
    right_pair = (rx / rn, ry / rn)
    down_pair = ((-right_pair[1], right_pair[0]) if rx * dy - ry * dx > 0
                 else (right_pair[1], -right_pair[0]))
    return right_pair, down_pair


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float64 or array.shape != shape:
        raise ValueError(label + ' requires exact native float64 shape ' + str(shape))


def _snapshot(array):
    # Caller must not mutate during copying. Native owns independent input storage
    # even when the original was already contiguous or read-only.
    result = np.array(array, dtype=np.float64, order='C', copy=True)
    if not np.isfinite(result).all():
        raise ValueError('中庭 Rust 输入必须全部为有限数值')
    result.setflags(write=False)
    return result


def _parameters(params):
    if not -1 <= params[11] <= 1:
        raise ValueError('中庭强度必须在 [-1,1]；不截断强度')
    axes = canonical_frame(params[2:4], params[4:6])
    if params[6] <= 0:
        raise ValueError('中庭需要正的测量高度 H')
    if not 0 < params[7] < params[8]:
        raise ValueError('中庭需要 0 < inner_x < outer_x')
    if not MIN_PLATEAU_END <= params[9] <= MAX_PLATEAU_END:
        raise ValueError('中庭需要测量得到的 plateau_end 在 [1.25,8]；不猜测下脸边界')
    if not MIN_TAIL <= params[10] <= MAX_TAIL:
        raise ValueError('中庭需要 tail 在 [0.25,4]')
    return axes


def _pair(array):
    return array.ctypes.data_as(P), array.size


def _unchanged_queries(points, params, axes):
    """Support postcondition only; not another deformation evaluator."""
    if params[11] == 0:
        return np.ones(len(points), dtype=bool)
    right, down = axes
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        offset = points - params[:2]
        u = offset[:, 0] * right[0] + offset[:, 1] * right[1]
        v = offset[:, 0] * down[0] + offset[:, 1] * down[1]
        t = v / params[6]
    if not np.isfinite(offset).all() or not np.isfinite(u).all() or not np.isfinite(v).all():
        raise RuntimeError('中庭 Rust 接受了溢出的坐标；结果已丢弃')
    return (np.abs(u) >= params[8]) | (t <= 0) | (t >= params[9] + params[10])


def evaluate(points, params):
    """Return owned writable float64 D[N,2]=q-source(q), not forward motion.

    Exact native NumPy float64 shapes: points[N,2], params[12], N=1..65536.
    Parameters: [ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,plateau_end,tail,amount].
    Origin, widths, height and points share source-coordinate units. Amount is
    signed [-1,1]: positive lengthens, negative shortens. Lateral coordinate is
    preserved; the upper boundary and at/outside support are exactly unchanged.
    H measures upper-eye-boundary to nose; plateau_end covers the measured
    retained lower-face extent, including chin, plus measured support padding.
    The nose-through-chin interval translates equally inside the lateral core.
    Runtime derives tail=max(.25,.5*(plateau_end-1)); ABI permits tail=.25..4
    and plateau_end=1.25..8. A direct neutral call still requires the native
    core and all validation. State-only neutral does not.
    No caller arrays are mutated, aliased, dtype-coerced or silently repaired.
    """
    if (type(points) is not np.ndarray or points.ndim != 2
            or points.shape[1] != 2 or not 1 <= len(points) <= MAX_POINTS):
        raise ValueError('中庭查询点必须为 [N,2]，N 在 [1,65536]')
    count = len(points)
    _shape(points, (count, 2), 'points')
    _shape(params, (PARAMS_LEN,), 'params')
    p, f = _snapshot(points), _snapshot(params)
    axes = _parameters(f)
    output = np.empty((count, 2), dtype=np.float64)
    status = native().lrt_mid_face_evaluate_v1(
        *_pair(p), *_pair(f), count, *_pair(output))
    if status:
        reasons = {1: '无效 ABI、长度、指针或别名', 2: '非有限值或强度越界',
                   3: '无效头部坐标系或测量高度',
                   4: '支持范围、溢出、精度不足或逆映射残差超限',
                   5: '有界临时内存分配失败', 6: 'Rust 内部异常'}
        message = '中庭 Rust 拒绝几何：' + reasons.get(status, str(status))
        if status in (1, 2, 3, 4):
            raise ValueError(message)
        raise RuntimeError(message)
    with np.errstate(over='ignore', invalid='ignore'):
        source = p - output
    if not np.isfinite(output).all() or not np.isfinite(source).all():
        raise RuntimeError('中庭 Rust 返回非有限位移或源坐标；结果已丢弃')
    unchanged = _unchanged_queries(p, f, axes)
    if np.any(output[unchanged] != 0) or np.any(np.signbit(output[unchanged])):
        raise RuntimeError('中庭 Rust 改动中性、上边界或支持范围外查询点；结果已丢弃')
    # Check axis-only/sign/max-amplitude guarantees without a second inverse.
    right, down = axes
    with np.errstate(over='ignore', invalid='ignore'):
        lateral_delta = output[:, 0] * right[0] + output[:, 1] * right[1]
        axial_delta = output[:, 0] * down[0] + output[:, 1] * down[1]
        scale = np.maximum(np.abs(output[:, 0]), np.abs(output[:, 1]))
        tolerance = np.maximum(64 * np.finfo(np.float64).eps * scale,
                               8 * np.nextafter(0.0, 1.0))
        bound = abs((GAIN * float(f[6])) * float(f[11]))
    if (not np.isfinite(lateral_delta).all() or not np.isfinite(axial_delta).all()
            or np.any(np.abs(lateral_delta) > tolerance)
            or np.any(np.abs(axial_delta) > bound + tolerance)
            or (f[11] > 0 and np.any(axial_delta < -tolerance))
            or (f[11] < 0 and np.any(axial_delta > tolerance))):
        raise RuntimeError('中庭 Rust 违反头轴、方向或位移上界；结果已丢弃')
    return output
