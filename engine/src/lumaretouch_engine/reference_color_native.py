"""Packaged Rust paired-patch fit. No runtime build/network/models/fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P=C.POINTER(C.c_double)


@lru_cache(maxsize=1)
def native():
    path=Path(__file__).resolve().parent/'bin'/'liblrt_reference_color.so'
    if not path.is_file(): raise RuntimeError('参考色彩 Rust 核心未安装；请使用完整打包版本')
    lib=C.CDLL(str(path))
    lib.lrt_reference_color_abi.argtypes=[]
    lib.lrt_reference_color_abi.restype=C.c_uint32
    if lib.lrt_reference_color_abi()!=1: raise RuntimeError('参考色彩 Rust ABI 不匹配')
    lib.lrt_reference_color_fit.argtypes=[P,P,C.c_size_t,P,C.POINTER(C.c_uint8)]
    lib.lrt_reference_color_fit.restype=C.c_int
    return lib


def fit(reference,target):
    r,t=(np.ascontiguousarray(v,dtype=np.float64) for v in (reference,target))
    if r.shape!=t.shape or r.ndim!=2 or r.shape[1]!=3 or not 64<=len(r)<=4096:
        raise ValueError('参考色彩需要 64–4096 个对应区域的全精度 RGB 样本')
    out=np.empty(7,np.float64)
    inliers=np.empty(len(r),np.uint8)
    code=native().lrt_reference_color_fit(r.ctypes.data_as(P),t.ctypes.data_as(P),len(r),out.ctypes.data_as(P),inliers.ctypes.data_as(C.POINTER(C.c_uint8)))
    if code: raise ValueError(f'参考色彩拟合拒绝：{code}（对应区域不足、不一致或超过两档校正）')
    return {'log2_gains':out[:3].tolist(),'residual_p90_stops':float(out[3]),
        'consensus_count':int(out[4]),'consensus_fraction':float(out[5]),'usable_fraction':float(out[6]),'inliers':np.flatnonzero(inliers).tolist()}
