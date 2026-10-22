"""Checked Rust ABI, with no runtime compile or silent substitute."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P = C.POINTER(C.c_float)

@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_lip_makeup.so'
    if not path.is_file(): raise RuntimeError('唇妆 Rust 核心未安装，请使用完整打包版本')
    lib = C.CDLL(str(path))
    lib.lrt_lip_makeup_abi.argtypes = []; lib.lrt_lip_makeup_abi.restype = C.c_uint32
    if lib.lrt_lip_makeup_abi() != 1: raise RuntimeError('唇妆 Rust ABI 不匹配')
    lib.lrt_lip_makeup_propose.argtypes = [P,P,C.c_size_t,C.c_float,C.c_float,C.c_float,P]
    lib.lrt_lip_makeup_propose.restype = C.c_int
    return lib

def propose(lab, shading, recipe):
    if (lab.dtype != np.float32 or shading.dtype != np.float32 or lab.ndim != 3
            or lab.shape[2] != 3 or shading.shape != lab.shape[:2]
            or not lab.flags.c_contiguous or not shading.flags.c_contiguous):
        raise ValueError('唇妆 Rust 输入必须为连续 float32 同尺寸场')
    from .lip_makeup_state import check
    r = check(recipe)
    output = np.empty_like(lab)
    status = native().lrt_lip_makeup_propose(lab.ctypes.data_as(P),shading.ctypes.data_as(P),shading.size,
        r['saturation'],r['brightness'],r['dimensionality'],output.ctypes.data_as(P))
    if status: raise ValueError(f'唇妆 Rust 拒绝参数：{status}')
    return output
