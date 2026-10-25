# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable bounded bridge to the original Rust field. AUTHORED / UNRUN.

No build, installation, inference, alternate Python warp or silent fallback.
The bridge cannot certify manual source ownership: support/runtime do that.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np

P = C.POINTER(C.c_double)
ABI_VERSION = 1
RECIPE_LEN, SUPPORT_LEN, STATE_LEN, FACTS_LEN = 4, 24, 30, 19
MAX_POINTS = 1_048_576
REASONS = {
    1: 'Invalid hair geometry buffer, recipe, prepared state or version',
    2: 'Hair geometry amounts require the original finite signed [-1,1] range',
    6: 'Hair strip margins, separation, derivative or displacement budget refused',
    8: 'Hair geometry query/support/inverse leaves the original source; no clipping',
    9: 'Hair geometry inverse residual or analytic Jacobian check failed',
}


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_hair_volume.so'
    if not path.is_file():
        raise RuntimeError('Hair geometry Rust core is not installed; explicit packaging is required')
    lib = C.CDLL(str(path))
    lib.lrt_hair_volume_abi.argtypes = []
    lib.lrt_hair_volume_abi.restype = C.c_uint32
    if lib.lrt_hair_volume_abi() != ABI_VERSION:
        raise RuntimeError('Hair geometry Rust ABI mismatch')
    lib.lrt_hair_volume_prepare.argtypes = [P, C.c_size_t, P, C.c_size_t,
                                           C.c_double, C.c_double, P, C.c_size_t]
    lib.lrt_hair_volume_prepare.restype = C.c_int
    lib.lrt_hair_volume_describe.argtypes = [P, C.c_size_t, P, C.c_size_t]
    lib.lrt_hair_volume_describe.restype = C.c_int
    lib.lrt_hair_volume_evaluate.argtypes = [P, C.c_size_t, P, C.c_size_t, C.c_size_t,
                                           P, C.c_size_t, P, C.c_size_t]
    lib.lrt_hair_volume_evaluate.restype = C.c_int
    return lib


def available():
    """Installed symbols/ABI only, not numerical or photographic acceptance."""
    try:
        native()
    except (RuntimeError, OSError, AttributeError):
        return False
    return True


def _snapshot(value, shape, label):
    if type(value) is np.ndarray:
        valid = value.shape == shape
    elif type(value) in (list, tuple):
        valid = len(value) == shape[0]
        if valid and len(shape) == 2:
            valid = all((type(row) in (list, tuple) and len(row) == shape[1])
                        or (type(row) is np.ndarray and row.shape == (shape[1],)) for row in value)
    else:
        valid = False
    if not valid:
        raise ValueError('Invalid bounded hair geometry ' + label)
    try:
        out = (np.empty(shape, np.float64) if shape == (0, 2)
               else np.array(value, np.float64, order='C', copy=True))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError('Invalid hair geometry ' + label) from exc
    if out.shape != shape or not np.isfinite(out).all():
        raise ValueError('Nonfinite or malformed hair geometry ' + label)
    return out


def _raise(code):
    if code:
        raise ValueError(REASONS.get(code, 'Unknown Rust hair geometry refusal: ' + str(code)))


def _describe(state):
    out = np.empty(FACTS_LEN, np.float64)
    _raise(native().lrt_hair_volume_describe(state.ctypes.data_as(P), STATE_LEN,
                                            out.ctypes.data_as(P), FACTS_LEN))
    if (not np.isfinite(out).all() or not 0 <= out[12] <= 128
            or not 0 <= out[13] <= .45 or abs(out[14]-(1-out[13])**2) > 1e-12
            or out[15] != 1e-7 or out[16] != 64 or not np.array_equal(out[17:19], state[1:3])):
        raise ValueError('Rust hair geometry facts violate the admitted ABI contract')
    return out


def prepare(values, support, shape):
    recipe = _snapshot(values, (RECIPE_LEN,), 'recipe')
    regions = _snapshot(support, (SUPPORT_LEN,), 'reviewed source profiles')
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(v) is not int or not 2 <= v <= 65536 for v in shape)
            or shape[0]*shape[1] > 64_000_000):
        raise ValueError('Hair geometry requires the exact bounded integer source shape')
    h, w = shape; state = np.empty(STATE_LEN, np.float64)
    _raise(native().lrt_hair_volume_prepare(recipe.ctypes.data_as(P), recipe.size,
                                           regions.ctypes.data_as(P), regions.size,
                                           w, h, state.ctypes.data_as(P), state.size))
    _describe(state)
    return np.frombuffer(state.tobytes(), np.float64)


def facts(state):
    state = _snapshot(state, (STATE_LEN,), 'prepared state'); out = _describe(state)
    return {'support_boxes': out[:12].reshape(3, 4).tolist(),
            'max_displacement': float(out[12]), 'gradient_bound': float(out[13]),
            'forward_jacobian_lower_bound': float(out[14]),
            'inverse_residual_tolerance': float(out[15]), 'inverse_max_iterations': int(out[16]),
            'source_dimensions': [int(out[17]), int(out[18])], 'runtime_quality_accepted': False}


def evaluate(state, points):
    """Return immutable delta in source pixels: inverse source = query - delta."""
    if (type(points) not in (np.ndarray, list, tuple)
            or (type(points) is np.ndarray and points.ndim != 2) or len(points) > MAX_POINTS):
        raise ValueError('Hair geometry queries exceed the bounded off-grid band')
    state = _snapshot(state, (STATE_LEN,), 'prepared state')
    points = _snapshot(points, (len(points), 2), 'off-grid points')
    description = _describe(state)  # Also validates neutral state/empty calls.
    out = np.empty_like(points); jacobian = np.empty(len(points), np.float64)
    _raise(native().lrt_hair_volume_evaluate(state.ctypes.data_as(P), state.size,
                                            points.ctypes.data_as(P), points.size, len(points),
                                            out.ctypes.data_as(P), out.size,
                                            jacobian.ctypes.data_as(P), jacobian.size))
    k = description[13]
    if (not np.isfinite(out).all() or not np.isfinite(jacobian).all()
            or np.any(np.hypot(out[:, 0], out[:, 1]) > description[12]+description[15])
            or np.any(jacobian < 1/(1+k)**2-1e-12) or np.any(jacobian > 1/(1-k)**2+1e-12)):
        raise ValueError('Rust hair geometry output violates inverse displacement/Jacobian bounds')
    limit = state[1:3]-1; source_points = points-out
    if np.any(points < 0) or np.any(points > limit) or np.any(source_points < 0) or np.any(source_points > limit):
        raise ValueError(REASONS[8])
    return np.frombuffer(out.tobytes(), np.float64).reshape(out.shape)
