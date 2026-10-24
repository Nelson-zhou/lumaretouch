# SPDX-License-Identifier: GPL-3.0-or-later
"""Original complete-head-and-hair Rust ABI bridge. AUTHORED / UNRUN.

No Python warp, RGB sampler, inferred hairline, build/download or silent fallback.
All borrowed inputs are copied before native entry. Returned state and displacement
arrays use immutable bytes backing; setting WRITEABLE again is not supported.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path

import numpy as np


P = C.POINTER(C.c_double)
ABI_VERSION = 1
RECIPE_LEN = 2
SUPPORT_LEN = 10
STATE_LEN = 13
FACTS_LEN = 16
MAX_POINTS = 1_048_576
REASONS = {
    1: 'Invalid head size geometry, prepared state, buffer or recipe version',
    2: 'Head size shrink amount must be finite and within [0,1]',
    4: 'Required real head or shoulder observation is hidden, cropped or unreliable',
    5: 'Head size transition reaches shoulders or shoulder posture is unsupported',
    6: 'Complete head-and-hair support, pivot, contraction or displacement budget refused',
    8: 'Head size support or inverse leaves the original source domain; no clipping',
    9: 'Head size inverse residual or Jacobian bound check failed',
}


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_head_size.so'
    if not path.is_file():
        raise RuntimeError('Head size Rust core is not installed; explicit packaging is required')
    lib = C.CDLL(str(path))
    lib.lrt_head_size_abi.argtypes = []
    lib.lrt_head_size_abi.restype = C.c_uint32
    if lib.lrt_head_size_abi() != ABI_VERSION:
        raise RuntimeError('Head size Rust ABI mismatch')
    lib.lrt_head_size_prepare.argtypes = [P, C.c_size_t, P, C.c_size_t, P,
                                        C.c_size_t, C.c_double, C.c_double, P, C.c_size_t]
    lib.lrt_head_size_prepare.restype = C.c_int
    lib.lrt_head_size_describe.argtypes = [P, C.c_size_t, P, C.c_size_t]
    lib.lrt_head_size_describe.restype = C.c_int
    lib.lrt_head_size_evaluate.argtypes = [P, C.c_size_t, P, C.c_size_t, C.c_size_t,
                                         P, C.c_size_t, P, C.c_size_t]
    lib.lrt_head_size_evaluate.restype = C.c_int
    return lib


def available():
    """Installed ABI and symbol check only, not numerical/photographic acceptance."""
    try:
        native()
    except (RuntimeError, OSError, AttributeError):
        return False
    return True


def _bounded_shape(value, shape, label):
    """Reject unbounded iterators, wrong ranks and oversized inputs before copying."""
    if type(value) is np.ndarray:
        valid = value.shape == shape
    elif type(value) in (list, tuple):
        valid = len(value) == shape[0]
        if valid and len(shape) == 2:
            valid = all((type(row) in (list, tuple) and len(row) == shape[1])
                        or (type(row) is np.ndarray and row.shape == (shape[1],))
                        for row in value)
    else:
        valid = False
    if not valid:
        raise ValueError('Invalid head size ' + label)


def _snapshot(value, shape, label):
    _bounded_shape(value, shape, label)
    try:
        # An empty sequence has no data to infer its second dimension from.
        if shape == (0, 2):
            result = np.empty(shape, dtype=np.float64)
        else:
            result = np.array(value, dtype=np.float64, order='C', copy=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('Invalid head size ' + label) from error
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError('Invalid head size ' + label)
    return result


def _raise(code):
    if code:
        raise ValueError(REASONS.get(code, 'Unknown head size Rust refusal: ' + str(code)))


def _describe(state):
    out = np.empty(FACTS_LEN, dtype=np.float64)
    code = native().lrt_head_size_describe(state.ctypes.data_as(P), STATE_LEN,
                                          out.ctypes.data_as(P), FACTS_LEN)
    _raise(code)
    if (not np.isfinite(out).all()
            or not .92 <= out[10] <= 1.0 or not 0.0 <= out[11] <= 128.0
            or not 0.0 <= out[12] <= .45
            or abs(out[13] - (1.0 - out[12]) ** 2) > 1e-12
            or out[14] != 1e-7 or out[15] != 64.0):
        raise ValueError('Rust head size facts failed the ABI safety contract')
    return out


def prepare(points, values, support, shape):
    """Snapshot actual33, [1,amount], reviewed support10 and exact (height,width).

    Support is normalized head_box4 + transition_box4 + manually marked pivot2.
    Its complete hair coverage and source/person provenance require host review;
    these numeric buffers cannot attest them. No inferred support is generated.
    """
    p = _snapshot(points, (33, 5), 'actual33 observations')
    recipe = _snapshot(values, (RECIPE_LEN,), 'versioned shrink recipe')
    s = _snapshot(support, (SUPPORT_LEN,), 'reviewed head-and-hair support')
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(n) is not int or not 2 <= n <= 1_000_000 for n in shape)):
        raise ValueError('Head size needs the exact integer original-source shape')
    h, w = shape
    out = np.empty(STATE_LEN, dtype=np.float64)
    code = native().lrt_head_size_prepare(
        p.ctypes.data_as(P), p.size, recipe.ctypes.data_as(P), recipe.size,
        s.ctypes.data_as(P), s.size, w, h, out.ctypes.data_as(P), out.size)
    _raise(code)
    if not np.isfinite(out).all():
        raise ValueError('Rust prepared head size state is nonfinite')
    _describe(out)
    return np.frombuffer(out.tobytes(), dtype=np.float64)


def facts(state):
    s = _snapshot(state, (STATE_LEN,), 'prepared state')
    f = _describe(s)
    return {'support_box': f[:4].tolist(), 'plateau_box': f[4:8].tolist(),
            'pivot': f[8:10].tolist(), 'scale': float(f[10]),
            'plateau_scale': float(f[10]), 'max_displacement': float(f[11]),
            'gradient_bound': float(f[12]),
            'forward_jacobian_lower_bound': float(f[13]),
            'inverse_residual_tolerance': float(f[14]),
            'inverse_max_iterations': int(f[15]),
            'source_dimensions': [int(s[11]), int(s[12])],
            'runtime_quality_accepted': False}


def evaluate(state, points):
    """Return immutable source displacement delta: source_xy = query_xy - delta.

    Coordinates are exact original-source destination pixels, including off-grid
    samples. Refusals propagate; there is no identity replacement on failure.
    """
    if type(points) not in (np.ndarray, list, tuple):
        raise ValueError('Invalid head size off-grid band')
    if type(points) is np.ndarray and points.ndim != 2:
        raise ValueError('Invalid head size off-grid band')
    if len(points) > MAX_POINTS:
        raise ValueError('Invalid head size off-grid band')
    s = _snapshot(state, (STATE_LEN,), 'prepared state')
    p = _snapshot(points, (len(points), 2), 'off-grid band')
    f = _describe(s)  # Also validates forged/neutral state before an empty band.
    out = np.empty_like(p)
    jac = np.empty(len(p), dtype=np.float64)
    code = native().lrt_head_size_evaluate(
        s.ctypes.data_as(P), s.size, p.ctypes.data_as(P), p.size, len(p),
        out.ctypes.data_as(P), out.size, jac.ctypes.data_as(P), jac.size)
    _raise(code)
    bound = f[12]
    if (not np.isfinite(out).all() or not np.isfinite(jac).all()
            or np.any(np.hypot(out[:, 0], out[:, 1]) > f[11] + f[14])
            or np.any(jac < 1.0 / (1.0 + bound) ** 2 - 1e-12)
            or np.any(jac > 1.0 / (1.0 - bound) ** 2 + 1e-12)):
        raise ValueError('Rust head size output failed inverse displacement/Jacobian limits')
    source = p - out
    if (np.any(p[:, 0] < 0.0) or np.any(p[:, 0] > s[11] - 1.0)
            or np.any(p[:, 1] < 0.0) or np.any(p[:, 1] > s[12] - 1.0)
            or np.any(source[:, 0] < 0.0) or np.any(source[:, 0] > s[11] - 1.0)
            or np.any(source[:, 1] < 0.0) or np.any(source[:, 1] > s[12] - 1.0)):
        raise ValueError(REASONS[8])
    return np.frombuffer(out.tobytes(), dtype=np.float64).reshape(out.shape)
