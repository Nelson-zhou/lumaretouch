"""Rust-only math. No runtime compilation, fallback, model or silent precision downgrade."""
import ctypes as C
from pathlib import Path
from functools import lru_cache
import numpy as np
from . import extended_tone_state as S
P = C.POINTER(C.c_float)
D = C.POINTER(C.c_double)
CANCEL = C.CFUNCTYPE(C.c_int)

@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_extended_tone.so'
    if not path.is_file(): raise RuntimeError('Extended tone Rust core is not installed; build/package explicitly')
    lib = C.CDLL(str(path))
    lib.lrt_extended_tone_abi.restype = C.c_uint32
    if lib.lrt_extended_tone_abi() != 2: raise RuntimeError('Extended tone Rust ABI mismatch')
    lib.lrt_extended_tone_render.argtypes = [P, C.c_size_t, C.c_size_t, P, D, C.c_double, P, CANCEL]
    lib.lrt_extended_tone_render.restype = C.c_int
    lib.lrt_extended_tone_monochrome.argtypes=[P,C.c_size_t,P,CANCEL]
    lib.lrt_extended_tone_monochrome.restype=C.c_int
    return lib

def render(pixels, spec, mask=None, scale=1., monochrome=False, cancelled=lambda: False):
    spec = S.check(spec)
    if not isinstance(pixels, np.ndarray) or pixels.ndim != 3 or pixels.shape[2] != 3 or min(pixels.shape[:2]) <= 0 or pixels.shape[0]*pixels.shape[1] > 100_000_000:
        raise ValueError('Extended tone requires nonempty H×W×3 RGB within 100 MP')
    if pixels.dtype not in (np.dtype('uint8'), np.dtype('uint16'), np.dtype('float32')): raise ValueError('Extended tone supports RGB8/RGB16/float32; float64 is not silently downgraded')
    if not np.isfinite(pixels).all() or type(scale) not in (int, float) or not np.isfinite(scale) or not 0 < scale <= 1: raise ValueError('Invalid pixels/preview scale')
    m = None
    if mask is not None:
        m = np.asarray(mask)
        if m.shape != pixels.shape[:2] or not np.isfinite(m).all() or np.any(m < 0) or np.any(m > 1): raise ValueError('Mask must be full-frame H×W in [0,1]')
        m = np.ascontiguousarray(m, dtype=np.float32)
    if not any(S.effective(spec, monochrome)) or (m is not None and not np.any(m)): return pixels
    admit(pixels.shape[0]*pixels.shape[1])
    errors = []
    def poll():
        try: return int(bool(cancelled()))
        except BaseException as error: errors.append(error); return 1
    callback = CANCEL(poll)
    integer = pixels.dtype.kind == 'u'
    maximum = float(np.iinfo(pixels.dtype).max) if integer else 1.
    src = np.ascontiguousarray(pixels, dtype=np.float32) / maximum
    out = np.empty_like(src)
    params = np.array(S.effective(spec, monochrome), dtype=np.float64)
    code = native().lrt_extended_tone_render(src.ctypes.data_as(P), src.shape[1], src.shape[0], None if m is None else m.ctypes.data_as(P), params.ctypes.data_as(D), float(scale), out.ctypes.data_as(P), callback)
    if errors: raise errors[0]
    if code == 4: raise InterruptedError("Extended tone cancelled; no output committed")
    if code or not np.isfinite(out).all(): raise RuntimeError(f'Extended tone Rust refused operation ({code})')
    if integer: out = np.clip(np.rint(out * maximum), 0, maximum).astype(pixels.dtype)
    if m is not None: out[m == 0] = pixels[m == 0]
    return out


def admit(pixels):
    """Conservative working-memory budget before copying a full frame; no silent proxy."""
    import os
    try: available = int(os.sysconf('SC_AVPHYS_PAGES')) * int(os.sysconf('SC_PAGE_SIZE'))
    except (ValueError, OSError): available = 2 * 1024**3
    budget = min(8 * 1024**3, available // 2)
    required = int(pixels) * 256 + 32 * 1024**2
    if required > budget:
        raise MemoryError(f'扩展影调完整精度需要约 {required // 1024**2} MiB 工作内存，安全预算 {budget // 1024**2} MiB；未降采样、未跳过效果')
    return required

def monochrome(pixels, cancelled=lambda:False):
    if not isinstance(pixels,np.ndarray) or pixels.ndim!=3 or pixels.shape[-1]!=3 or pixels.dtype not in (np.dtype('float32'),np.dtype('uint8'),np.dtype('uint16')):
        raise ValueError('Monochrome output requires RGB8/RGB16/float32')
    if not np.isfinite(pixels).all() or not 0<pixels.shape[0]*pixels.shape[1]<=100_000_000:raise ValueError('Invalid monochrome frame')
    maximum=float(np.iinfo(pixels.dtype).max) if pixels.dtype.kind=='u' else 1.
    src=np.ascontiguousarray(pixels,dtype=np.float32)/maximum;out=np.empty_like(src)
    errors=[]
    def poll():
        try:return int(bool(cancelled()))
        except BaseException as error:errors.append(error);return 1
    callback=CANCEL(poll)
    code=native().lrt_extended_tone_monochrome(src.ctypes.data_as(P),pixels.shape[0]*pixels.shape[1],out.ctypes.data_as(P),callback)
    if errors:raise errors[0]
    if code==4:raise InterruptedError('Monochrome output cancelled')
    if code:raise RuntimeError(f'Monochrome native failure ({code})')
    if pixels.dtype.kind=='u':out=np.clip(np.rint(out*maximum),0,maximum).astype(pixels.dtype)
    return out
