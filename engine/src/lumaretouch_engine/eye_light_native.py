"""Checked native boundary; no runtime compiler and no fallback algorithm."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P=C.POINTER(C.c_float)
@lru_cache(maxsize=1)
def native():
    path=Path(__file__).resolve().parent/'bin'/'liblrt_eye_light.so'
    if not path.is_file(): raise RuntimeError('眼神光 Rust 核心尚未安装；不能应用')
    lib=C.CDLL(str(path)); lib.lrt_eye_light_abi.argtypes=[]; lib.lrt_eye_light_abi.restype=C.c_uint32
    if lib.lrt_eye_light_abi()!=1: raise RuntimeError('眼神光 ABI 不兼容')
    lib.lrt_eye_light_delta.argtypes=[C.c_size_t,C.c_size_t,P,P,P,C.c_size_t,P,C.c_uint32,P]
    lib.lrt_eye_light_delta.restype=C.c_int
    return lib

def delta(visibility,recovery,polygon,config,asset):
    arrays=[visibility,recovery,polygon,config]
    if any(a.dtype!=np.float32 or not a.flags.c_contiguous or not np.isfinite(a).all() for a in arrays): raise ValueError('眼神光输入必须为连续有限 float32')
    if visibility.ndim!=2 or recovery.shape!=visibility.shape or polygon.ndim!=2 or polygon.shape[1]!=2 or config.shape!=(10,): raise ValueError('眼神光输入尺寸无效')
    h,w=visibility.shape
    if not 0<h*w<=4_000_000: raise ValueError('眼神光区域超出内存预算')
    output=np.empty((h,w,3),np.float32)
    code=native().lrt_eye_light_delta(w,h,visibility.ctypes.data_as(P),recovery.ctypes.data_as(P),polygon.ctypes.data_as(P),len(polygon),config.ctypes.data_as(P),asset,output.ctypes.data_as(P))
    if code: raise ValueError(f'眼神光 Rust 拒绝输入：{code}')
    return output

def colour(source,light=None):
    if source.dtype!=np.float32 or not source.flags.c_contiguous or not np.isfinite(source).all(): raise ValueError('颜色转换需要连续 float32')
    if light is None: light=np.zeros_like(source); mode=0
    else: mode=1
    if light.shape!=source.shape or light.dtype!=np.float32 or not light.flags.c_contiguous: raise ValueError('眼神光颜色差分尺寸无效')
    lib=native(); lib.lrt_eye_light_colour.argtypes=[P,P,C.c_size_t,C.c_uint32,P]; lib.lrt_eye_light_colour.restype=C.c_int
    out=np.empty_like(source)
    if lib.lrt_eye_light_colour(source.ctypes.data_as(P),light.ctypes.data_as(P),source.size,mode,out.ctypes.data_as(P)): raise ValueError('眼神光颜色转换失败')
    return out
