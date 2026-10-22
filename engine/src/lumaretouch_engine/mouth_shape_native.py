"""Versioned original Rust mouth math; never runtime compilation or fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P = C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_mouth_shape.so'
    if not path.is_file(): raise RuntimeError('嘴形 Rust 核心未安装，请使用完整打包版本')
    lib = C.CDLL(str(path))
    lib.lrt_mouth_shape_abi.argtypes = []
    lib.lrt_mouth_shape_abi.restype = C.c_uint32
    if lib.lrt_mouth_shape_abi() != 1: raise RuntimeError('嘴形 Rust ABI 不匹配')
    lib.lrt_mouth_shape_controls.argtypes = [P,P,C.c_size_t,P,P,P]
    lib.lrt_mouth_shape_controls.restype = C.c_int
    return lib


def controls(points, roles, frame, values):
    p,r,f,v = [np.ascontiguousarray(a,dtype=np.float64) for a in (points,roles,frame,values)]
    if p.ndim != 2 or p.shape[1] != 2 or not 0 < len(p) <= 256 or r.shape != (len(p),4) or f.shape != (10,) or v.shape != (10,):
        raise ValueError('嘴形 Rust 输入尺寸错误')
    if not all(np.isfinite(a).all() for a in (p,r,f,v)): raise ValueError('嘴形 Rust 输入非有限')
    out = np.empty_like(p)
    status = native().lrt_mouth_shape_controls(p.ctypes.data_as(P),r.ctypes.data_as(P),len(p),f.ctypes.data_as(P),v.ctypes.data_as(P),out.ctypes.data_as(P))
    if status: raise ValueError(f'嘴形 Rust 拒绝几何：{status}')
    return out
