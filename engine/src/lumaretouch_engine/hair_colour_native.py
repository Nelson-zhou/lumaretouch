"""Checked source-only Rust ABI. No runtime compile, download or silent fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import hair_colour_state as S

P = C.POINTER(C.c_float)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_hair_colour.so'
    if not path.is_file(): raise RuntimeError('头发调色 Rust 核心未安装；请使用完整打包版本')
    lib = C.CDLL(str(path))
    lib.lrt_hair_colour_abi.argtypes = []; lib.lrt_hair_colour_abi.restype = C.c_uint32
    if lib.lrt_hair_colour_abi() != 1: raise RuntimeError('头发调色 Rust ABI 不匹配')
    lib.lrt_hair_colour_apply.argtypes = [P, P, C.c_size_t, C.c_size_t, C.c_uint32, C.c_float, C.c_float, P, P]
    lib.lrt_hair_colour_apply.restype = C.c_int
    return lib


def solve(source, coverage, recipe):
    r = S.check(recipe)
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3 or source.shape[2] != 3
            or type(coverage) is not np.ndarray or coverage.dtype != np.float32 or coverage.shape != source.shape[:2]
            or not source.flags.c_contiguous or not coverage.flags.c_contiguous):
        raise ValueError('Hair native input requires contiguous source-frame float32 fields')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)) or not np.isfinite(coverage).all() or np.any((coverage < 0) | (coverage > 1)):
        raise ValueError('Hair source fields are outside working-sRGB / coverage ranges')
    if not S.active(r): return np.zeros_like(source), np.zeros_like(coverage)
    h, w = coverage.shape
    if not 1 <= h*w <= 64_000_000: raise ValueError('Hair field exceeds the 64 MP limit')
    delta = np.empty_like(source); highlights = np.empty_like(coverage)
    status = native().lrt_hair_colour_apply(source.ctypes.data_as(P), coverage.ctypes.data_as(P),
        w, h, S.STYLE_IDS.index(r['style']), r['strength'], r['gloss'], delta.ctypes.data_as(P), highlights.ctypes.data_as(P))
    if status: raise ValueError(f'头发调色 Rust 拒绝输入：{status}')
    if not np.isfinite(delta).all() or not np.isfinite(highlights).all(): raise ValueError('Hair native output contains nonfinite pixels')
    if np.any(delta[coverage == 0] != 0): raise ValueError('Hair native output changed zero-mask pixels')
    if np.any((highlights < 0) | (highlights > 1)): raise ValueError('Hair native highlight support is invalid')
    return delta, highlights
