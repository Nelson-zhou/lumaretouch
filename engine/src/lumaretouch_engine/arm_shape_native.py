# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged original Rust evaluation only; never compile or substitute on load."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P=C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path=Path(__file__).resolve().parent/'bin/liblrt_arm_shape.so'
    if not path.is_file(): raise RuntimeError('Arm Rust field is not packaged; no Python deformation fallback')
    lib=C.CDLL(str(path));lib.lrt_arm_shape_abi.argtypes=[];lib.lrt_arm_shape_abi.restype=C.c_uint32
    if lib.lrt_arm_shape_abi()!=1: raise RuntimeError('Arm Rust ABI mismatch')
    lib.lrt_arm_shape_evaluate.argtypes=[P,P,C.c_size_t,P,P];lib.lrt_arm_shape_evaluate.restype=C.c_int
    return lib


def evaluate(state,points):
    state=np.ascontiguousarray(state,np.float64);points=np.ascontiguousarray(points,np.float64)
    if state.shape!=(25,) or points.ndim!=2 or points.shape[1]!=2 or len(points)>1048576 or not np.isfinite(state).all() or not np.isfinite(points).all():
        raise ValueError('Arm evaluation requires finite bounded off-grid coordinates')
    out=np.empty_like(points);jac=np.empty(len(points),np.float64)
    code=native().lrt_arm_shape_evaluate(state.ctypes.data_as(P),points.ctypes.data_as(P),len(points),out.ctypes.data_as(P),jac.ctypes.data_as(P))
    if code or not np.isfinite(out).all() or not np.isfinite(jac).all() or np.any(jac<.77) or np.any(jac>1.23):
        raise ValueError('Arm inverse/Jacobian or contour geometry rejected: '+str(code))
    return out
