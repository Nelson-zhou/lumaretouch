# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict bilateral chin-width inverse boundary. AUTHORED / UNRUN.

No Python deformation fallback, RGB sampling, inference, runtime build/download.
The host measures the below-lips plane, chin-centered frame and source support.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

MAX_POINTS = 65536
PARAMS_LEN = 11
GAIN = 0.08
TAIL = 0.5
FRAME_TOLERANCE = 1.0e-10
MIN_FORWARD_DERIVATIVE = 0.7
MAX_FORWARD_DERIVATIVE = 1.3
P = C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_chin_shape.so'
    if not path.is_file():
        raise RuntimeError('尖下巴 Rust 核心未安装；未应用替代算法')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_chin_shape_abi.argtypes = []
        lib.lrt_chin_shape_abi.restype = C.c_uint32
        if lib.lrt_chin_shape_abi() != 1:
            raise RuntimeError('尖下巴 Rust ABI 不匹配')
        lib.lrt_chin_shape_evaluate_v1.argtypes = (
            [P, C.c_size_t] * 2 + [C.c_size_t, P, C.c_size_t])
        lib.lrt_chin_shape_evaluate_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise RuntimeError('尖下巴 Rust 核心不能加载所需 ABI') from error
    return lib


def available():
    """Actual load, ABI and versioned symbol, not anatomical readiness."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def canonical_frame(right, down):
    """Validate unit orthogonal axes, then remove only <=1e-10 frame roundoff.

    Both handednesses are supported. The host supplies anatomical orientation
    and uses these same axes for measurements, targets and support evidence.
    """
    try:
        if len(right) != 2 or len(down) != 2:
            raise ValueError('尖下巴头部坐标轴必须各含两个分量')
        values = (*right, *down)
        if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, float, np.floating))
               for v in values):
            raise ValueError('尖下巴头部坐标轴必须为有限数值')
        rx, ry, dx, dy = (float(v) for v in values)
    except (TypeError, OverflowError) as error:
        raise ValueError('尖下巴头部坐标轴必须为有限二元数值') from error
    rn, dn = math.hypot(rx, ry), math.hypot(dx, dy)
    dot = rx * dx + ry * dy
    if (not all(math.isfinite(v) for v in (rx, ry, dx, dy, rn, dn, dot))
            or abs(rn - 1.0) > FRAME_TOLERANCE
            or abs(dn - 1.0) > FRAME_TOLERANCE or abs(dot) > FRAME_TOLERANCE):
        raise ValueError('尖下巴需要单位正交头部坐标系；不修复倾斜坐标轴')
    right_pair = (rx / rn, ry / rn)
    down_pair = ((-right_pair[1], right_pair[0]) if rx * dy - ry * dx > 0
                 else (right_pair[1], -right_pair[0]))
    return right_pair, down_pair


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float64 or array.shape != shape:
        raise ValueError(label + ' requires exact native float64 shape ' + str(shape))


def _snapshot(array):
    # Caller must not mutate during copying. Native receives independent inputs.
    result = np.array(array, dtype=np.float64, order='C', copy=True)
    if not np.isfinite(result).all():
        raise ValueError('尖下巴 Rust 输入必须全部为有限数值')
    result.setflags(write=False)
    return result


def _parameters(params):
    if not -1 <= params[9] <= 1 or not -1 <= params[10] <= 1:
        raise ValueError('尖下巴左右强度必须在 [-1,1]；不截断强度')
    axes = canonical_frame(params[2:4], params[4:6])
    if params[6] <= 0:
        raise ValueError('尖下巴需要正的测量高度 H')
    if not 0 < params[7] < params[8] or params[8] != 2.0 * float(params[7]):
        raise ValueError('尖下巴需要正的 inner_x，且 outer_x 必须恰为 2*inner_x')
    return axes


def _pair(array):
    return array.ctypes.data_as(P), array.size


def _coordinates(points, params, axes):
    right, down = axes
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        offset = points - params[:2]
        u = offset[:, 0] * right[0] + offset[:, 1] * right[1]
        v = offset[:, 0] * down[0] + offset[:, 1] * down[1]
        t = v / params[6]
    if not np.isfinite(offset).all() or not np.isfinite(u).all() or not np.isfinite(v).all():
        raise RuntimeError('尖下巴 Rust 接受了溢出的坐标；结果已丢弃')
    return u, v, t


def evaluate(points, params):
    """Return owned writable float64 D[N,2]=q-source(q), never forward motion.

    Exact native float64 shapes: points[N,2], params[11], N=1..65536.
    Params: [ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,left,right].
    All geometry shares source-coordinate units. Require H>0, inner_x>0,
    outer_x==2*inner_x exactly; finite signed independent amounts in [-1,1].
    Positive narrows, negative expands; u>0 is subject left, u<0 subject right.
    Head-axis v and centerline u=0 stay fixed. Support is |u|<outer, 0<v/H<1.5.
    Unequal sides have a center derivative cusp, not blending or a dead zone.
    The host places the upper plane strictly below lips and centers u on tip152.
    It must check actual tip invariance within declared f64 measurement error.
    Native displacement-relative residual and coordinate-scale source roundtrip
    are distinct checks. Nonzero D can round away in q-D or float32 conversion;
    acceptance does not promise coordinate movement or changed pixels.
    Direct neutral calls still need native; no inputs are mutated or repaired.
    """
    if (type(points) is not np.ndarray or points.ndim != 2
            or points.shape[1] != 2 or not 1 <= len(points) <= MAX_POINTS):
        raise ValueError('尖下巴查询点必须为 [N,2]，N 在 [1,65536]')
    count = len(points)
    _shape(points, (count, 2), 'points')
    _shape(params, (PARAMS_LEN,), 'params')
    p, f = _snapshot(points), _snapshot(params)
    axes = _parameters(f)
    output = np.empty((count, 2), dtype=np.float64)
    status = native().lrt_chin_shape_evaluate_v1(
        *_pair(p), *_pair(f), count, *_pair(output))
    if status:
        reasons = {1: '无效 ABI、长度、指针或别名', 2: '非有限值或强度越界',
                   3: '无效头部坐标系或测量高度',
                   4: '支持范围、溢出、精度不足或逆映射残差超限',
                   5: '有界临时内存分配失败', 6: 'Rust 内部异常'}
        message = '尖下巴 Rust 拒绝几何：' + reasons.get(status, str(status))
        if status in (1, 2, 3, 4):
            raise ValueError(message)
        raise RuntimeError(message)
    with np.errstate(over='ignore', invalid='ignore'):
        source = p - output
    if not np.isfinite(output).all() or not np.isfinite(source).all():
        raise RuntimeError('尖下巴 Rust 返回非有限位移或源坐标；结果已丢弃')
    if f[9] == 0 and f[10] == 0:
        if np.any(output != 0) or np.any(np.signbit(output)):
            raise RuntimeError('尖下巴 Rust 改动中性查询点；结果已丢弃')
        return output
    u, v, t = _coordinates(p, f, axes)
    amounts = np.where(u > 0, f[9], f[10])
    unchanged = ((u == 0) | (np.abs(u) >= f[8]) | (v <= 0)
                 | (t >= 1.0 + TAIL) | (amounts == 0))
    if np.any(output[unchanged] != 0) or np.any(np.signbit(output[unchanged])):
        raise RuntimeError('尖下巴 Rust 改动中性侧、中线或支持范围外查询点；结果已丢弃')
    # Postconditions only, not a Python forward/inverse deformation evaluator.
    right, down = axes
    source_u, source_v, _ = _coordinates(source, f, axes)
    with np.errstate(over='ignore', invalid='ignore'):
        horizontal = output[:, 0] * right[0] + output[:, 1] * right[1]
        axial = output[:, 0] * down[0] + output[:, 1] * down[1]
        scale = np.maximum(np.abs(output[:, 0]), np.abs(output[:, 1]))
        tolerance = np.maximum(64 * np.finfo(np.float64).eps * scale,
                               8 * np.nextafter(0.0, 1.0))
        bound = (GAIN * float(f[8])) * np.abs(amounts)
        coordinate_scale = max(float(np.max(np.abs(p))), abs(float(f[0])),
                               abs(float(f[1])), float(f[6]), float(f[8]))
        coordinate_tolerance = max(256 * np.finfo(np.float64).eps * coordinate_scale,
                                   8 * np.nextafter(0.0, 1.0))
    moving = ~unchanged
    expected_negative = (u > 0) == (amounts > 0)
    if (not np.isfinite(horizontal).all() or not np.isfinite(axial).all()
            or np.any(np.abs(axial) > tolerance)
            or np.any(np.abs(horizontal) > bound + tolerance)
            or np.any(horizontal[moving & expected_negative] >= 0)
            or np.any(horizontal[moving & ~expected_negative] <= 0)
            or np.any(source_u[moving] == 0)
            or np.any((source_u[moving] > 0) != (u[moving] > 0))
            or np.any(np.abs(source_v - v) > coordinate_tolerance)):
        raise RuntimeError('尖下巴 Rust 违反头轴、方向、侧别或位移上界；结果已丢弃')
    return output
