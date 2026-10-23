"""Checked Rust ABI; no runtime build, fallback or implicit package installation."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P=C.POINTER(C.c_float)
@lru_cache(maxsize=1)
def native():
    path=Path(__file__).with_name('bin')/'liblrt_eyelash.so'
    if not path.is_file():raise RuntimeError('睫毛 Rust 核心未安装；不能应用')
    lib=C.CDLL(str(path));lib.lrt_eyelash_abi.argtypes=[];lib.lrt_eyelash_abi.restype=C.c_uint32
    if lib.lrt_eyelash_abi()!=1:raise RuntimeError('睫毛 ABI 不匹配')
    lib.lrt_eyelash_delta.argtypes=[P,P,C.c_size_t,C.c_size_t,P,C.c_size_t,C.c_float,C.c_float,C.c_float,C.c_float,P];lib.lrt_eyelash_delta.restype=C.c_int
    return lib
def delta(source,support,segments,eye):
    h,w=support.shape
    if source.shape!=(h,w,3) or segments.ndim!=2 or segments.shape[1]!=6 or any(a.dtype!=np.float32 or not a.flags.c_contiguous or not np.isfinite(a).all() for a in (source,support,segments)):raise ValueError('睫毛核心需要对齐连续有限 float32 场')
    if h*w>4_000_000:raise ValueError('睫毛区域超出预算')
    rgb=[int(eye['colour'][i:i+2],16)/255 for i in (1,3,5)];out=np.empty_like(source)
    status=native().lrt_eyelash_delta(source.ctypes.data_as(P),support.ctypes.data_as(P),w,h,segments.ctypes.data_as(P),len(segments),eye['strength'],*rgb,out.ctypes.data_as(P))
    if status:raise ValueError(f'睫毛核心拒绝输入：{status}')
    return out
