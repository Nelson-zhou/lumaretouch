# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed original Rust ABI only. AUTHORED / UNRUN; no Python warp fallback.

All borrowed inputs are copied before C entry. Prepared state is backed by an
immutable bytes object, not merely an owned ndarray with a reversible flag.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np

P = C.POINTER(C.c_double)
ABI_VERSION = 1
STATE_LEN = 11
MIN_SUPPORT_LEN = 20
MAX_SUPPORT_LEN = 260
FACTS_LEN = 16
MAX_POINTS = 1_048_576
REASONS = {
    1: 'Invalid whole-body width geometry, state, buffer or numeric input',
    2: 'Whole-body width amount is outside [-1,1]',
    4: 'Required real complete-person observation is hidden or cropped',
    5: 'Unsupported bent, tilted, tiny or foreshortened whole person',
    6: 'Whole-body width support, contraction or displacement budget exceeded',
    8: 'Whole-body width support or inverse leaves the original source domain; no clipping',
    9: 'Whole-body width inverse residual or Jacobian certificate failed',
}


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_body_slim.so'
    if not path.is_file():
        raise RuntimeError('Whole-body width Rust core is not installed; explicit packaging is required')
    lib = C.CDLL(str(path))
    lib.lrt_body_slim_abi.argtypes = []
    lib.lrt_body_slim_abi.restype = C.c_uint32
    if lib.lrt_body_slim_abi() != ABI_VERSION:
        raise RuntimeError('Whole-body width Rust ABI mismatch')
    lib.lrt_body_slim_prepare.argtypes = [P, C.c_size_t, P, C.c_size_t, P,
                                           C.c_size_t, C.c_double, C.c_double,
                                           P, C.c_size_t]
    lib.lrt_body_slim_prepare.restype = C.c_int
    lib.lrt_body_slim_describe.argtypes = [P, C.c_size_t, P, C.c_size_t]
    lib.lrt_body_slim_describe.restype = C.c_int
    lib.lrt_body_slim_evaluate.argtypes = [P, C.c_size_t, P, C.c_size_t,
                                            C.c_size_t, P, C.c_size_t,
                                            P, C.c_size_t]
    lib.lrt_body_slim_evaluate.restype = C.c_int
    return lib


def available():
    """Installed binary ABI/symbol check only; not numerical/image acceptance."""
    try:
        native()
    except (RuntimeError, OSError, AttributeError):
        return False
    return True


def _bounded_shape(value, shape, label):
    """Admit only bounded materialized inputs before any dtype copy/allocation."""
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
        raise ValueError('Invalid whole-body width ' + label)


def _snapshot(value, shape, label):
    _bounded_shape(value, shape, label)
    try:
        result = np.array(value, dtype=np.float64, order='C', copy=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('Invalid whole-body width ' + label) from error
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError('Invalid whole-body width ' + label)
    return result


def _raise(code):
    if code:
        raise ValueError(REASONS.get(code, 'Unknown whole-body width Rust refusal: ' + str(code)))


def _describe(state):
    out = np.empty(FACTS_LEN, np.float64)
    code = native().lrt_body_slim_describe(state.ctypes.data_as(P), STATE_LEN,
                                             out.ctypes.data_as(P), FACTS_LEN)
    _raise(code)
    if not np.isfinite(out).all():
        raise ValueError('Rust whole-body width facts are nonfinite')
    return out


def prepare(points, values, support, shape):
    """Prepare in exact source pixels, never in a crop/display/proxy coordinate system."""
    p = _snapshot(points, (33, 5), 'actual33 observations')
    v = _snapshot(values, (1,), 'signed amount')
    if (type(support) not in (list, tuple, np.ndarray)
            or (type(support) is np.ndarray and support.ndim != 1) or not MIN_SUPPORT_LEN <= len(support) <= MAX_SUPPORT_LEN or len(support) % 2):
        raise ValueError('Whole-body width requires the actual measured polygon and collar')
    s = _snapshot(support, (len(support),), 'reviewed source silhouette and collar')
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(n) is not int or not 2 <= n <= 1_000_000 for n in shape)):
        raise ValueError('Whole-body width needs the exact integer original-source shape')
    h, w = shape
    out = np.empty(STATE_LEN, np.float64)
    code = native().lrt_body_slim_prepare(
        p.ctypes.data_as(P), p.size, v.ctypes.data_as(P), v.size,
        s.ctypes.data_as(P), s.size, w, h, out.ctypes.data_as(P), out.size)
    _raise(code)
    if not np.isfinite(out).all():
        raise ValueError('Rust prepared whole-body width state is nonfinite')
    _describe(out)  # State certificate is also verified by the Rust reader.
    return np.frombuffer(out.tobytes(), dtype=np.float64)


def facts(state):
    s = _snapshot(state, (STATE_LEN,), 'prepared state')
    f = _describe(s)
    return {'support_box': f[0:4].tolist(), 'plateau_box': f[4:8].tolist(),
            'max_displacement': float(f[8]), 'gradient_bound': float(f[9]),
            'forward_jacobian_bounds': f[10:12].tolist(),
            'whole_person_width_factor': float(f[12]), 'measured_width_center_x': float(f[13]),
            'measured_person_width': float(f[14]), 'inverse_residual_tolerance': float(f[15]),
            'source_dimensions': [int(s[9]), int(s[10])],
            'runtime_quality_accepted': False}


def evaluate(state, points):
    s = _snapshot(state, (STATE_LEN,), 'prepared state')
    if type(points) not in (np.ndarray, list, tuple):
        raise ValueError('Invalid whole-body width off-grid band')
    if type(points) is np.ndarray and points.ndim != 2:
        raise ValueError('Invalid whole-body width off-grid band')
    if len(points) > MAX_POINTS:
        raise ValueError('Invalid whole-body width off-grid band')
    p = _snapshot(points, (len(points), 2), 'off-grid band')
    out = np.empty_like(p)
    jac = np.empty(len(p), np.float64)
    code = native().lrt_body_slim_evaluate(
        s.ctypes.data_as(P), s.size, p.ctypes.data_as(P), p.size, len(p),
        out.ctypes.data_as(P), out.size, jac.ctypes.data_as(P), jac.size)
    _raise(code)
    if (not np.isfinite(out).all() or not np.isfinite(jac).all()
            or np.any(out[:, 1] != 0.0)
            or np.any(jac < 1 / 1.45 - 1e-12) or np.any(jac > 1 / .55 + 1e-12)
            or np.any(np.abs(out[:, 0]) > _describe(s)[8] + 1e-7)):
        raise ValueError('Rust whole-body width output failed inverse displacement/Jacobian limits')
    source_x = p[:, 0] - out[:, 0]
    if (np.any(p[:, 0] < 0) or np.any(p[:, 0] > s[9] - 1)
            or np.any(p[:, 1] < 0) or np.any(p[:, 1] > s[10] - 1)
            or np.any(source_x < 0) or np.any(source_x > s[9] - 1)):
        raise ValueError(REASONS[8])
    return out
