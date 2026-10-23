"""Bounded packaged Rust FFI, no runtime compilation or numerical fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import selective_colour_state as S
P = C.POINTER(C.c_float)
CHUNK = 65536


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_selective_colour.so'
    if not path.is_file():
        raise RuntimeError('可选颜色 Rust 核心未安装；请使用完整打包版本')
    lib = C.CDLL(str(path))
    lib.lrt_selective_colour_abi.argtypes = []
    lib.lrt_selective_colour_abi.restype = C.c_uint32
    if lib.lrt_selective_colour_abi() != 1:
        raise RuntimeError('可选颜色 Rust ABI 不匹配')
    lib.lrt_selective_colour_apply.argtypes = [P, P, C.c_size_t, P, C.c_uint32]
    lib.lrt_selective_colour_apply.restype = C.c_int
    return lib


def apply(pixels, recipe, *, encoding, cancelled=lambda: False):
    """HWC float32 input/output; never mutate caller input, never partial publish."""
    recipe = S.check(recipe)
    if encoding not in ('linear-srgb-d65', 'extended-srgb-d65'):
        raise ValueError('Explicit supported RGB encoding required')
    if not isinstance(pixels, np.ndarray) or pixels.dtype != np.float32 or pixels.ndim != 3 or pixels.shape[2] != 3 or min(pixels.shape[:2]) < 1 or pixels.size > 300_000_000:
        raise ValueError('Selective colour requires bounded HWC float32 RGB')
    if cancelled():
        raise InterruptedError('Selective colour cancelled')
    limit = 65504 if encoding == 'linear-srgb-d65' else 128
    if not np.isfinite(pixels).all() or np.max(np.abs(pixels)) > limit:
        raise ValueError('Selective colour RGB contains unsupported values')
    if not S.active(recipe):
        return pixels  # bit exact identity; inactive requires no native library.
    src = np.ascontiguousarray(pixels).reshape(-1, 3)
    dst = np.empty_like(src)
    params = np.array(S.scalars(recipe), dtype=np.float32)
    lib = native()
    for start in range(0, len(src), CHUNK):
        if cancelled():
            raise InterruptedError('Selective colour cancelled')
        inp, out = src[start:start + CHUNK], dst[start:start + CHUNK]
        code = lib.lrt_selective_colour_apply(inp.ctypes.data_as(P), out.ctypes.data_as(P), len(inp), params.ctypes.data_as(P), int(encoding == 'extended-srgb-d65'))
        if code:
            raise ValueError(f'Selective colour Rust rejected chunk: {code}')
    if cancelled():
        raise InterruptedError('Selective colour cancelled')
    return dst.reshape(pixels.shape)
