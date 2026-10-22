"""Versioned Rust eye ABI. No runtime compilation or algorithm fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P = C.POINTER(C.c_double)

@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_eye_shape.so'
    if not path.is_file(): raise RuntimeError('眼形 Rust 核心未安装，请使用完整打包版本')
    lib = C.CDLL(str(path))
    lib.lrt_eye_shape_abi.argtypes = []; lib.lrt_eye_shape_abi.restype = C.c_uint32
    if lib.lrt_eye_shape_abi() != 1: raise RuntimeError('眼形 Rust ABI 不匹配')
    lib.lrt_eye_shape_controls.argtypes = [P,P,C.c_size_t,P,P,P]
    lib.lrt_eye_shape_controls.restype = C.c_int
    return lib


def controls(points, roles, frame, values):
    p,r,f,v = [np.ascontiguousarray(a, dtype=np.float64) for a in (points,roles,frame,values)]
    if p.ndim!=2 or p.shape[1]!=2 or not 0<len(p)<=256 or r.shape!=(len(p),2) or f.shape!=(10,) or v.shape!=(10,):
        raise ValueError('眼形 Rust 输入尺寸不正确')
    if not all(np.isfinite(a).all() for a in (p,r,f,v)): raise ValueError('眼形 Rust 输入非有限')
    output = np.empty_like(p)
    status = native().lrt_eye_shape_controls(p.ctypes.data_as(P),r.ctypes.data_as(P),len(p),f.ctypes.data_as(P),v.ctypes.data_as(P),output.ctypes.data_as(P))
    if status: raise ValueError(f'眼形 Rust 拒绝几何：{status}')
    return output
