"""Explicit Rust-only bridge; no runtime build, fallback, inference or hidden downsample."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import photo_detail_state as S
P=C.POINTER(C.c_float)
CANCEL=C.CFUNCTYPE(C.c_int)
@lru_cache(maxsize=1)
def native():
    path=Path(__file__).parent/'bin/liblrt_photo_detail.so'
    if not path.is_file():raise RuntimeError('Photo detail Rust core not installed; build/package explicitly')
    lib=C.CDLL(str(path));lib.lrt_photo_detail_abi.restype=C.c_uint32
    if lib.lrt_photo_detail_abi()!=1:raise RuntimeError('Photo detail ABI mismatch')
    lib.lrt_photo_detail_render.argtypes=[P,C.c_size_t,C.c_size_t,P,C.c_float,P,CANCEL]
    lib.lrt_photo_detail_render.restype=C.c_int
    return lib
def admit(pixels):
    import os
    try:available=int(os.sysconf('SC_AVPHYS_PAGES'))*int(os.sysconf('SC_PAGE_SIZE'))
    except (ValueError,OSError):available=2*1024**3
    budget=min(8*1024**3,available//2);required=int(pixels)*160+32*1024**2
    if required>budget:raise MemoryError(f'细节完整精度需要约 {required//1024**2} MiB，预算 {budget//1024**2} MiB；未降采样或跳过效果')
    return required
def render(pixels,spec,*,scale=1.,cancelled=lambda:False):
    spec=S.check(spec)
    if not isinstance(pixels,np.ndarray) or pixels.ndim!=3 or pixels.shape[2]!=3 or not 0<pixels.shape[0]*pixels.shape[1]<=100_000_000:raise ValueError('Requires nonempty whole-frame H×W×3 RGB within 100 MP')
    if pixels.dtype not in (np.dtype('uint8'),np.dtype('uint16'),np.dtype('float32')):raise ValueError('Requires RGB8/RGB16/float32, no silent precision downgrade')
    if type(scale) not in (int,float) or not np.isfinite(scale) or not 0<scale<=8:raise ValueError('Explicit source preview scale required')
    if cancelled():raise InterruptedError('Photo detail cancelled')
    if not S.active(spec):return pixels
    admit(pixels.shape[0]*pixels.shape[1])
    if not np.isfinite(pixels).all() or (pixels.dtype.kind=='f' and np.any(np.abs(pixels)>65504)):raise ValueError('Invalid or unsupported HDR values')
    maximum=float(np.iinfo(pixels.dtype).max) if pixels.dtype.kind=='u' else 1.
    src=np.ascontiguousarray(pixels,dtype=np.float32)/maximum;out=np.empty_like(src)
    params=np.asarray(S.effective(spec),dtype=np.float32);errors=[]
    def poll():
        try:return int(bool(cancelled()))
        except BaseException as error:errors.append(error);return 1
    callback=CANCEL(poll)
    code=native().lrt_photo_detail_render(src.ctypes.data_as(P),src.shape[1],src.shape[0],params.ctypes.data_as(P),scale,out.ctypes.data_as(P),callback)
    if errors:raise errors[0]
    if code==4:raise InterruptedError('Photo detail cancelled; no output published')
    if code or not np.isfinite(out).all():raise RuntimeError(f'Photo detail Rust refused operation ({code})')
    if pixels.dtype.kind=='u':out=np.clip(np.rint(out*maximum),0,maximum).astype(pixels.dtype)
    return out
