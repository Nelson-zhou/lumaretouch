# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicitly packaged Rust ABI only. No runtime compiler or Python math fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P = C.POINTER(C.c_double)
REASONS = {1:'invalid length geometry/state',2:'length amount outside local range',4:'hidden or cropped required hip/knee/ankle/heel/toe',5:'unsupported bent, foreshortened or foot-transition pose',6:'length support, contraction or displacement budget exceeded',7:'opposite length support corridors overlap',8:'length support is cropped',9:'length inverse residual or Jacobian gate failed'}


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent/'bin/liblrt_leg_length.so'
    if not path.is_file():
        raise RuntimeError('Leg length Rust core is not installed; explicit packaging is required')
    lib = C.CDLL(str(path))
    lib.lrt_leg_length_abi.argtypes = []; lib.lrt_leg_length_abi.restype = C.c_uint32
    if lib.lrt_leg_length_abi() != 1:
        raise RuntimeError('Leg length Rust ABI mismatch')
    lib.lrt_leg_length_prepare.argtypes = [P, P, P, C.c_double, C.c_double, P]
    lib.lrt_leg_length_prepare.restype = C.c_int
    lib.lrt_leg_length_evaluate.argtypes = [P, P, C.c_size_t, P, P]
    lib.lrt_leg_length_evaluate.restype = C.c_int
    return lib


def prepare(points, values, support, shape):
    p = np.ascontiguousarray(points, dtype=np.float64)
    v = np.ascontiguousarray(values, dtype=np.float64)
    s = np.ascontiguousarray(support, dtype=np.float64)
    if p.shape != (33, 5) or v.shape != (2,) or s.shape != (12,) or any(not np.isfinite(a).all() for a in (p,v,s)):
        raise ValueError('Leg length prepare needs real33 observations and reviewed visible support')
    h, w = shape; out = np.empty(26, np.float64)
    code = native().lrt_leg_length_prepare(p.ctypes.data_as(P), v.ctypes.data_as(P), s.ctypes.data_as(P), w, h, out.ctypes.data_as(P))
    if code: raise ValueError(REASONS.get(code, 'Unknown Rust leg length refusal'))
    out.setflags(write=False)
    return out


def evaluate(state, points):
    s = np.ascontiguousarray(state, dtype=np.float64)
    p = np.ascontiguousarray(points, dtype=np.float64)
    if s.shape != (26,) or p.ndim != 2 or p.shape[1] != 2 or len(p) > 1048576 or not np.isfinite(p).all() or not np.isfinite(s).all():
        raise ValueError('Invalid leg length evaluation band')
    out = np.empty_like(p); jac = np.empty(len(p), np.float64)
    code = native().lrt_leg_length_evaluate(s.ctypes.data_as(P), p.ctypes.data_as(P), len(p), out.ctypes.data_as(P), jac.ctypes.data_as(P))
    if code or not np.isfinite(out).all() or not np.isfinite(jac).all() or np.any(jac < .15) or np.any(jac > 6):
        raise ValueError(REASONS.get(code, 'Leg length inverse Jacobian refused'))
    return out
