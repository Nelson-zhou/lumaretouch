# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict analytic whole-face inverse-field boundary. AUTHORED / UNRUN.

No fallback, runtime compilation/download, RGB sampling or anatomy inference.
The caller establishes measured-face geometry, evidence and compositing order.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path

import numpy as np

MAX_POINTS = 65536
PARAMS_LEN = 11
MIN_SCALE = 0.94
MAX_SCALE = 1.06
FRAME_TOLERANCE = 1.0e-6
MIN_INVERSE_DERIVATIVE = 0.2
P = C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_face_size.so'
    if not path.is_file():
        raise RuntimeError('小脸 Rust 核心未安装；未应用替代算法')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_face_size_abi.argtypes = []
        lib.lrt_face_size_abi.restype = C.c_uint32
        if lib.lrt_face_size_abi() != 1:
            raise RuntimeError('小脸 Rust ABI 不匹配')
        lib.lrt_face_size_evaluate_v1.argtypes = (
            [P, C.c_size_t] * 2 + [C.c_size_t, P, C.c_size_t])
        lib.lrt_face_size_evaluate_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise RuntimeError('小脸 Rust 核心不能加载所需 ABI') from error
    return lib


def available():
    """Check actual loading, ABI and the versioned evaluator symbol."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float64 or array.shape != shape:
        raise ValueError(label + ' requires exact native float64 shape ' + str(shape))


def _snapshot(array):
    # Never preserve caller aliases, even for a contiguous/read-only view. The
    # caller must not mutate while copying; native receives independent storage.
    result = np.array(array, dtype=np.float64, order='C', copy=True)
    if not np.isfinite(result).all():
        raise ValueError('小脸 Rust 输入必须全部为有限数值')
    result.setflags(write=False)
    return result


def _parameters(params):
    if not MIN_SCALE <= params[10] <= MAX_SCALE:
        raise ValueError('小脸缩放比例超出原始策略 [0.94,1.06]；不截断强度')
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        right_norm = float(np.hypot(params[2], params[3]))
        up_norm = float(np.hypot(params[4], params[5]))
        dot = float(params[2] * params[4] + params[3] * params[5])
    if (not np.isfinite(right_norm) or not np.isfinite(up_norm) or not np.isfinite(dot)
            or abs(right_norm - 1.0) > FRAME_TOLERANCE
            or abs(up_norm - 1.0) > FRAME_TOLERANCE or abs(dot) > FRAME_TOLERANCE
            or params[6] <= 0 or params[7] <= 0):
        raise ValueError('小脸需要单位正交头部坐标系和正的测量半宽/半高')
    inner, outer, scale = (float(params[i]) for i in (8, 9, 10))
    if not 0 < inner < outer:
        raise ValueError('小脸支持范围必须满足 0 < inner < outer')
    inverse = 1.0 / scale
    coefficient = (scale - 1.0) / scale
    floor = (1.0 if coefficient == 0.0 else
             min(1.0, inverse) - abs(coefficient) * 1.875 * (outer / (outer - inner)))
    if not np.isfinite(floor) or floor < MIN_INVERSE_DERIVATIVE:
        raise ValueError('小脸过渡范围的保守逆映射导数下界低于 0.2；拒绝折叠风险')


def _pair(array):
    return array.ctypes.data_as(P), array.size


def _unchanged_queries(points, params):
    """Postcondition mask only, not another deformation evaluator."""
    if params[10] == 1.0:
        return np.ones(len(points), dtype=bool)
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        offset = points - params[:2]
        x = (offset[:, 0] * params[2] + offset[:, 1] * params[3]) / params[6]
        y = (offset[:, 0] * params[4] + offset[:, 1] * params[5]) / params[7]
        radius = np.hypot(x, y)
    if not np.isfinite(offset).all() or np.isnan(x).any() or np.isnan(y).any():
        raise RuntimeError('小脸 Rust 接受了溢出的坐标；结果已丢弃')
    return (radius >= params[9]) | np.all(offset == 0.0, axis=1)


def evaluate(points, params):
    """Return owned writable float64 D[N,2] = q - source(q), not a source grid.

    Exact NumPy native float64 inputs: points[N,2], params[11] ordered
    [cx,cy,right_x,right_y,up_x,up_y,hx,hy,inner,outer,scale]. N is 1..65536.
    Coordinates, center and measured half-extents use the same source units;
    inner/outer are dimensionless elliptical radii. No points are identity pins.
    Positive recipe amount maps to scale < 1, shrinking the WHOLE measured face.
    Noncontiguous arrays are independently copied, never dtype-coerced. Callers
    must not mutate inputs during snapshot copying. Larger grids are batched by
    the caller. Even a neutral direct call requires native; neutral state does not.
    """
    if (type(points) is not np.ndarray or points.ndim != 2
            or points.shape[1] != 2 or not 1 <= len(points) <= MAX_POINTS):
        raise ValueError('小脸查询点必须为 [N,2]，N 在 [1,65536]')
    count = len(points)
    # Every shape/dtype must pass before copying anything or loading native code.
    _shape(points, (count, 2), 'points')
    _shape(params, (PARAMS_LEN,), 'params')
    p, f = _snapshot(points), _snapshot(params)
    _parameters(f)
    output = np.empty((count, 2), dtype=np.float64)
    status = native().lrt_face_size_evaluate_v1(
        *_pair(p), *_pair(f), count, *_pair(output))
    if status:
        reasons = {1: '无效 ABI、长度、指针或别名', 2: '非有限值或缩放比例越界',
                   3: '无效头部坐标系或测量半宽/半高',
                   4: '支持范围、折叠风险或数值溢出', 5: '有界临时内存分配失败', 6: 'Rust 内部异常'}
        message = '小脸 Rust 拒绝几何：' + reasons.get(status, str(status))
        if status not in (1, 2, 3, 4):
            raise RuntimeError(message)
        raise ValueError(message)
    with np.errstate(over='ignore', invalid='ignore'):
        source = p - output
    if not np.isfinite(output).all() or not np.isfinite(source).all():
        raise RuntimeError('小脸 Rust 返回非有限位移或源坐标；结果已丢弃')
    unchanged = _unchanged_queries(p, f)
    if np.any(output[unchanged] != 0) or np.any(np.signbit(output[unchanged])):
        raise RuntimeError('小脸 Rust 改动中性、中心或支持范围外查询点；结果已丢弃')
    return output
