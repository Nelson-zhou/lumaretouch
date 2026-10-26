# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed Rust-only off-grid hand solver; never compile or substitute Python."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P=C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path=Path(__file__).resolve().parent/'bin/liblrt_hand_shape.so'
    if not path.is_file():raise RuntimeError('手部几何 Rust 核心未安装；请使用显式打包流程，不会回退成伪 AI')
    lib=C.CDLL(str(path));lib.lrt_hand_shape_abi.argtypes=[];lib.lrt_hand_shape_abi.restype=C.c_uint32
    if lib.lrt_hand_shape_abi()!=1:raise RuntimeError('Hand shape Rust ABI mismatch')
    lib.lrt_hand_shape_evaluate.argtypes=[P,C.c_size_t,C.c_size_t,C.c_uint32,C.c_uint32,C.c_double,P,C.c_size_t,C.c_size_t,P,C.c_size_t,P,C.c_size_t]
    lib.lrt_hand_shape_evaluate.restype=C.c_int
    return lib


def capability():
    try:native();return {'available':True,'reason':None}
    except (RuntimeError,OSError,AttributeError) as error:return {'available':False,'reason':str(error)}


def evaluate(primitives,points,source,max_displacement):
    if type(primitives) is not np.ndarray or primitives.ndim!=2 or primitives.shape[1]!=7 or len(primitives)>32:raise ValueError('Invalid bounded hand primitive state')
    if type(points) is not np.ndarray or points.ndim!=2 or points.shape[1]!=2 or len(points)>1_048_576:raise ValueError('Invalid bounded hand off-grid query')
    p=np.array(primitives,dtype=np.float64,order='C',copy=True);q=np.array(points,dtype=np.float64,order='C',copy=True)
    if not np.isfinite(p).all() or not np.isfinite(q).all():raise ValueError('Nonfinite hand state/query')
    out=np.empty_like(q);jac=np.empty(len(q),np.float64)
    code=native().lrt_hand_shape_evaluate(p.ctypes.data_as(P),p.size,len(p),source['width'],source['height'],max_displacement,q.ctypes.data_as(P),q.size,len(q),out.ctypes.data_as(P),out.size,jac.ctypes.data_as(P),jac.size)
    if code:raise ValueError('Rust hand geometry refused source/support/Jacobian/budget (code '+str(code)+')')
    if not np.isfinite(out).all() or not np.isfinite(jac).all() or np.any(jac<.25) or np.any(jac>4):raise ValueError('Hand native output lacks finite positive Jacobian')
    return out
