"""Versioned Rust geometry ABI, no runtime compilation or fallback algorithm."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P = C.POINTER(C.c_double)

@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_brow_shape.so'
    if not path.is_file(): raise RuntimeError('眉形 Rust 核心未安装，请使用完整打包版本')
    lib = C.CDLL(str(path))
    lib.lrt_brow_shape_abi.argtypes = []; lib.lrt_brow_shape_abi.restype = C.c_uint32
    if lib.lrt_brow_shape_abi() != 1: raise RuntimeError('眉形 Rust ABI 不匹配')
    lib.lrt_brow_shape_controls.argtypes = [P,P,P,P,P]
    lib.lrt_brow_shape_controls.restype = C.c_int
    return lib


def controls(points, outward, up, values):
    arrays = [np.ascontiguousarray(v, dtype=np.float64) for v in (points,outward,up,values)]
    if [v.shape for v in arrays] != [(10,2),(2,),(2,),(7,)]: raise ValueError('眉形 Rust 输入尺寸不正确')
    if not all(np.isfinite(v).all() for v in arrays): raise ValueError('眉形 Rust 输入非有限')
    output = np.empty((10,2),dtype=np.float64)
    status = native().lrt_brow_shape_controls(*(a.ctypes.data_as(P) for a in arrays),output.ctypes.data_as(P))
    if status: raise ValueError(f'眉形 Rust 拒绝几何：{status}')
    return output
