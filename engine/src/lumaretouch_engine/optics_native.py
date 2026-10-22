"""ABI-versioned Rust geometry/sampling; no runtime build or download."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np

P = C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent/'bin'/'liblrt_optics.so'
    if not path.is_file(): raise RuntimeError('镜头/透视 Rust 核心未安装；请由打包流程构建 build-optics.sh，不会自动编译或下载')
    lib = C.CDLL(str(path))
    lib.lrt_optics_abi.argtypes = []; lib.lrt_optics_abi.restype = C.c_uint32
    if lib.lrt_optics_abi() != 1: raise RuntimeError('镜头/透视 Rust 核心 ABI 不匹配')
    lib.lrt_optics_map.argtypes = [C.c_uint32]*4+[P,C.c_double,C.c_double,P,C.c_size_t]
    lib.lrt_optics_map.restype = C.c_int
    lib.lrt_optics_sample.argtypes = [P,C.c_uint32,C.c_uint32,C.c_uint32,C.c_size_t,P,C.c_size_t,P,C.c_size_t]
    lib.lrt_optics_sample.restype = C.c_int
    return lib


def grid(shape, inverse, distortion, zoom=1., *, y0=0, rows=None):
    h, w = shape; rows = h-y0 if rows is None else rows
    if not 1 <= w*h <= 64_000_000 or not 0 <= y0 < h or not 1 <= rows <= h-y0: raise ValueError('镜头映射尺寸/预算无效')
    matrix = np.ascontiguousarray(inverse, dtype=np.float64).reshape(9)
    output = np.empty((rows,w,2), np.float64)
    code = native().lrt_optics_map(w,h,y0,rows,matrix.ctypes.data_as(P),float(distortion),float(zoom),output.ctypes.data_as(P),output.size)
    if code: raise ValueError(f'Rust 镜头/透视映射拒绝参数：{code}')
    return output


def sample(source, xy):
    src = np.ascontiguousarray(source, dtype=np.float64)
    if src.ndim == 2: src = src[...,None]
    coords = np.ascontiguousarray(xy, dtype=np.float64)
    if src.ndim != 3 or coords.ndim < 2 or coords.shape[-1] != 2: raise ValueError('镜头采样形状无效')
    h,w,c = src.shape; out = np.empty((*coords.shape[:-1],c), np.float64)
    code = native().lrt_optics_sample(src.ctypes.data_as(P),w,h,c,src.size,coords.ctypes.data_as(P),coords.size//2,out.ctypes.data_as(P),out.size)
    if code: raise ValueError(f'Rust 镜头/透视采样拒绝参数：{code}')
    return out
