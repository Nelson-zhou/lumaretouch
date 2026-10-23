"""Bounded packaged Rust FFI, no runtime compilation or numerical fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import primary_calibration_state as S
P = C.POINTER(C.c_float)
CHUNK = 65536


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_primary_calibration.so'
    if not path.is_file():
        raise RuntimeError('RGB 原色校准 Rust 核心未安装；请使用完整打包版本')
    lib = C.CDLL(str(path))
    lib.lrt_primary_calibration_abi.argtypes = []
    lib.lrt_primary_calibration_abi.restype = C.c_uint32
    if lib.lrt_primary_calibration_abi() != 1:
        raise RuntimeError('RGB 原色校准 Rust ABI 不匹配')
    lib.lrt_primary_calibration_apply.argtypes = [P, P, C.c_size_t, P, C.c_uint32]
    lib.lrt_primary_calibration_apply.restype = C.c_int
    lib.lrt_primary_calibration_admit.argtypes = [P]
    lib.lrt_primary_calibration_admit.restype = C.c_int
    return lib


def apply(pixels, recipe, *, encoding, cancelled=lambda: False):
    """HWC float32 input/output; never mutate caller input, never partial publish."""
    recipe = S.check(recipe)
    if encoding not in ('linear-srgb-d65', 'extended-srgb-d65'):
        raise ValueError('Explicit supported RGB encoding required')
    if not isinstance(pixels, np.ndarray) or pixels.dtype != np.float32 or pixels.ndim != 3 or pixels.shape[2] != 3 or min(pixels.shape[:2]) < 1 or pixels.size > 300_000_000:
        raise ValueError('Primary calibration requires bounded HWC float32 RGB')
    if cancelled():
        raise InterruptedError('Primary calibration cancelled')
    limit = 65504 if encoding == 'linear-srgb-d65' else 128
    if not np.isfinite(pixels).all() or np.max(np.abs(pixels)) > limit:
        raise ValueError('Primary calibration RGB contains unsupported values')
    if not S.active(recipe):
        return pixels  # bit exact identity; inactive requires no native library.
    src = np.ascontiguousarray(pixels).reshape(-1, 3)
    dst = np.empty_like(src)
    params = np.array(S.scalars(recipe), dtype=np.float32)
    lib = native()
    for start in range(0, len(src), CHUNK):
        if cancelled():
            raise InterruptedError('Primary calibration cancelled')
        inp, out = src[start:start + CHUNK], dst[start:start + CHUNK]
        code = lib.lrt_primary_calibration_apply(inp.ctypes.data_as(P), out.ctypes.data_as(P), len(inp), params.ctypes.data_as(P), int(encoding == 'extended-srgb-d65'))
        if code:
            raise ValueError(f'Primary calibration Rust rejected chunk: {code}')
    if cancelled():
        raise InterruptedError('Primary calibration cancelled')
    return dst.reshape(pixels.shape)


def admit(recipe):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return recipe
    params = np.array(S.scalars(recipe), dtype=np.float32)
    if native().lrt_primary_calibration_admit(params.ctypes.data_as(P)):
        raise ValueError('原色组合不可用：色度越界、白点权重或矩阵稳定性不满足要求；请减小调整')
    return recipe
