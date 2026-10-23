"""Only the installed original Rust evaluator; never compile/import fallback math."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P=C.POINTER(C.c_double)
@lru_cache(maxsize=1)
def native():
    path=Path(__file__).resolve().parent/'bin/liblrt_neck_shape.so'
    if not path.is_file():raise RuntimeError('Neck Rust core not installed; explicit packaging required')
    lib=C.CDLL(str(path));lib.lrt_neck_shape_abi.restype=C.c_uint32
    if lib.lrt_neck_shape_abi()!=1:raise RuntimeError('Neck Rust ABI mismatch')
    lib.lrt_neck_shape_evaluate.argtypes=[P,P,C.c_size_t,P,P];lib.lrt_neck_shape_evaluate.restype=C.c_int
    return lib

def evaluate(state,points):
    s=np.ascontiguousarray(state,dtype=np.float64);p=np.ascontiguousarray(points,dtype=np.float64)
    if s.shape!=(24,) or p.ndim!=2 or p.shape[1]!=2 or len(p)>1048576 or not np.isfinite(s).all() or not np.isfinite(p).all():raise ValueError('Invalid neck inverse inputs')
    out=np.empty_like(p);jac=np.empty(len(p),np.float64)
    code=native().lrt_neck_shape_evaluate(s.ctypes.data_as(P),p.ctypes.data_as(P),len(p),out.ctypes.data_as(P),jac.ctypes.data_as(P))
    if code or not np.isfinite(out).all() or not np.isfinite(jac).all() or np.any(jac<=.25):raise ValueError('Neck continuous inverse refused geometry, contraction, Jacobian or displacement gate: '+str(code))
    return out
