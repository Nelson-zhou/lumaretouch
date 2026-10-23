"""Checked Rust ABI; explicit packaging, never runtime compile or fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from .brow_makeup_catalogue import material
from .brow_makeup_state import check_brow
P=C.POINTER(C.c_float)
@lru_cache(maxsize=1)
def native():
    path=Path(__file__).with_name('bin')/'liblrt_brow_makeup.so'
    if not path.is_file():raise RuntimeError('眉妆 Rust 核心未安装；不能应用')
    lib=C.CDLL(str(path));lib.lrt_brow_makeup_abi.argtypes=[];lib.lrt_brow_makeup_abi.restype=C.c_uint32
    if lib.lrt_brow_makeup_abi()!=1:raise RuntimeError('眉妆 ABI 不匹配')
    lib.lrt_brow_makeup_delta.argtypes=[P,P,P,C.c_size_t,P,C.c_float,C.c_float,C.c_float,C.c_float,P];lib.lrt_brow_makeup_delta.restype=C.c_int
    return lib

def delta(source,uv,support,brow):
    r=check_brow(brow);h,w=support.shape
    for a,shape in ((source,(h,w,3)),(uv,(h,w,2)),(support,(h,w))):
        if not isinstance(a,np.ndarray) or a.shape!=shape or a.dtype!=np.float32 or not a.flags.c_contiguous or not np.isfinite(a).all():raise ValueError('眉妆核心要求连续有限 float32 场')
    if h*w>4_000_000:raise ValueError('眉妆区域超出预算')
    if r['strength']==0:return np.zeros_like(source)
    m=material(r['pattern']);profile=np.ascontiguousarray([*m['widths'],*m['offsets'],m['density'],m['grain'],m['tilt']],dtype=np.float32)
    rgb=[int(r['colour'][i:i+2],16)/255 for i in (1,3,5)];out=np.empty_like(source)
    status=native().lrt_brow_makeup_delta(source.ctypes.data_as(P),uv.ctypes.data_as(P),support.ctypes.data_as(P),h*w,profile.ctypes.data_as(P),r['strength'],*rgb,out.ctypes.data_as(P))
    if status or not np.isfinite(out).all():raise ValueError(f'眉妆核心拒绝输入或输出：{status}')
    return out
