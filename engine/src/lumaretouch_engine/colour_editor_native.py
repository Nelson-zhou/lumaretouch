"""Packaged Rust only; full-domain statistics, bounded chunk work and cancellation."""
import ctypes as C
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import numpy as np
from . import colour_editor_state as S
P = C.POINTER(C.c_float)
D = C.POINTER(C.c_double)
CHUNK = 65536
@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_colour_editor.so'
    if not path.is_file(): raise RuntimeError('色彩编辑器 Rust 核心未安装；不能以 HSL 替代')
    lib = C.CDLL(str(path)); lib.lrt_colour_editor_abi.restype = C.c_uint32
    if lib.lrt_colour_editor_abi() != 1: raise RuntimeError('Colour editor ABI mismatch')
    lib.lrt_colour_editor_stats.argtypes = [P, P, C.c_size_t, P, D]
    lib.lrt_colour_editor_stats.restype = C.c_int
    lib.lrt_colour_editor_apply.argtypes = [P, P, P, C.c_size_t, P, D, C.c_uint32]
    lib.lrt_colour_editor_apply.restype = C.c_int
    return lib

def checked_input(pixels, mask, cancelled):
    if not isinstance(pixels, np.ndarray) or pixels.dtype != np.float32 or pixels.ndim != 3 or pixels.shape[2] != 3 or min(pixels.shape[:2]) < 1 or pixels.size > 300_000_000:
        raise ValueError('Colour editor requires bounded HWC float32 RGB')
    if not pixels.flags.c_contiguous: raise ValueError('Host must provide contiguous frozen operator input')
    if mask is not None and (not isinstance(mask, np.ndarray) or mask.dtype != np.float32 or mask.shape != pixels.shape[:2] or not mask.flags.c_contiguous): raise ValueError('External mask must match operator domain')
    src = pixels.reshape(-1, 3); m = None if mask is None else mask.reshape(-1)
    digest = sha256(str(pixels.shape).encode())
    for start in range(0, len(src), CHUNK):
        if cancelled(): raise InterruptedError('Colour editor cancelled')
        a = src[start:start + CHUNK]
        if not np.isfinite(a).all() or np.max(np.abs(a)) > 128: raise ValueError('Colour editor RGB exceeds headroom')
        digest.update(memoryview(a).cast('B'))
        if m is not None:
            b = m[start:start + CHUNK]
            if not np.isfinite(b).all() or np.any(b < 0) or np.any(b > 1): raise ValueError('External mask outside [0,1]')
            digest.update(memoryview(b).cast('B'))
    return src, m, digest.hexdigest()

class FullDomain:
    """Per-stage stats cache, never a tile mean. Host supplies full operator input.

    FullDomain is document-local, never serialized/copied to preset or batch.
    A content digest covers RGB + mask + dimensions; selection parameters cover
    inversion and smoothing. Any upstream edits therefore invalidate the target.
    """
    def __init__(self): self.key = None; self.stats = None
    def clear(self): self.key = None; self.stats = None
    def apply(self, pixels, recipe, *, mask=None, view=False, cancelled=lambda: False, canonical=None, prepare_only=False):
        recipe = S.check(recipe)
        if not prepare_only and not view and not S.active(recipe): return pixels
        src, m, digest = checked_input(pixels, mask, cancelled)
        # Budget includes destination, bounded validation scratch, excludes already
        # admitted immutable host input. No full-frame HSL/mask allocation.
        from .cpu_memory_budget import available_estimate
        if pixels.nbytes + 8 * CHUNK * 4 > max(0, available_estimate() - 256 * 1024**2): raise MemoryError('Colour editor destination exceeds memory budget')
        params = np.asarray(S.scalars(recipe), dtype=np.float32)
        key = (digest, tuple(params[:8]), bool(recipe['invert']), S.ALGORITHM)
        lib = native()
        if canonical is not None:
            if not isinstance(canonical, dict) or canonical.get('selection') != key[1:]: raise ValueError('Canonical colour selection changed')
            sums = np.asarray(canonical['stats'], dtype=np.float64)
            if sums.shape != (5,) or not np.isfinite(sums).all() or sums[0] < 0: raise ValueError('Invalid full-domain statistics')
            self.key, self.stats = key, sums
        elif self.key != key:
            sums = np.zeros(5, dtype=np.float64)
            for start in range(0, len(src), CHUNK):
                if cancelled(): raise InterruptedError('Colour editor stats cancelled')
                a = src[start:start + CHUNK]; b = None if m is None else m[start:start + CHUNK]
                code = lib.lrt_colour_editor_stats(a.ctypes.data_as(P), None if b is None else b.ctypes.data_as(P), len(a), params.ctypes.data_as(P), sums.ctypes.data_as(D))
                if code: raise ValueError(f'Colour editor statistics rejected: {code}')
            if cancelled(): raise InterruptedError('Colour editor stats cancelled')
            self.key, self.stats = key, sums
        if prepare_only:
            return {'source_digest': digest, 'selection': key[1:], 'stats': self.stats.copy()}
        dst = np.empty_like(src)
        for start in range(0, len(src), CHUNK):
            if cancelled(): raise InterruptedError('Colour editor render cancelled')
            a = src[start:start + CHUNK]; b = None if m is None else m[start:start + CHUNK]; out = dst[start:start + CHUNK]
            code = lib.lrt_colour_editor_apply(a.ctypes.data_as(P), None if b is None else b.ctypes.data_as(P), out.ctypes.data_as(P), len(a), params.ctypes.data_as(P), self.stats.ctypes.data_as(D), int(view))
            if code: raise ValueError(f'Colour editor render rejected: {code}')
        if cancelled(): raise InterruptedError('Colour editor publication cancelled')
        return dst.reshape(pixels.shape)
