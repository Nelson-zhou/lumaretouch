"""Rust C ABI adapter; missing core refuses, never compiles or substitutes math."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P=C.POINTER(C.c_double)
REASONS={1:'invalid geometry input',2:'amount outside implementation range',3:'body too small to verify',4:'occluded or unreliable anchor',5:'extreme or ambiguous pose',6:'requested movement exceeds safe visible support',7:'shoulder supports overlap',8:'visible support is cropped by image edge',9:'inverse or Jacobian safety gate failed'}


@lru_cache(maxsize=1)
def native():
    path=Path(__file__).resolve().parent/'bin/liblrt_shoulder_shape.so'
    if not path.is_file():raise RuntimeError('Shoulder Rust core is not installed; explicit packaging is required')
    lib=C.CDLL(str(path));lib.lrt_shoulder_shape_abi.argtypes=[];lib.lrt_shoulder_shape_abi.restype=C.c_uint32
    if lib.lrt_shoulder_shape_abi()!=1:raise RuntimeError('Shoulder Rust ABI mismatch')
    lib.lrt_shoulder_shape_prepare.argtypes=[P,P,C.c_double,C.c_double,P];lib.lrt_shoulder_shape_prepare.restype=C.c_int
    lib.lrt_shoulder_shape_evaluate.argtypes=[P,P,C.c_size_t,P,P];lib.lrt_shoulder_shape_evaluate.restype=C.c_int
    return lib


def prepare(points,values,shape):
    p=np.ascontiguousarray(points,dtype=np.float64);v=np.ascontiguousarray(values,dtype=np.float64)
    if p.shape!=(33,5) or v.shape!=(4,) or not np.isfinite(p).all() or not np.isfinite(v).all():raise ValueError('Invalid real shoulder inputs')
    h,w=shape;out=np.empty(10,np.float64)
    code=native().lrt_shoulder_shape_prepare(p.ctypes.data_as(P),v.ctypes.data_as(P),w,h,out.ctypes.data_as(P))
    if code:raise ValueError(REASONS.get(code,'unknown Rust shoulder refusal'))
    out.setflags(write=False)
    return out


def evaluate(state,points):
    s=np.ascontiguousarray(state,dtype=np.float64);p=np.ascontiguousarray(points,dtype=np.float64)
    if s.shape!=(10,) or p.ndim!=2 or p.shape[1]!=2 or len(p)>1048576 or not np.isfinite(p).all():raise ValueError('Shoulder evaluation band is invalid')
    out=np.empty_like(p);jac=np.empty(len(p),np.float64)
    code=native().lrt_shoulder_shape_evaluate(s.ctypes.data_as(P),p.ctypes.data_as(P),len(p),out.ctypes.data_as(P),jac.ctypes.data_as(P))
    if code or not np.isfinite(out).all() or not np.isfinite(jac).all() or np.any(jac<=.15):raise ValueError(REASONS.get(code,'Shoulder inverse Jacobian refused'))
    return out
