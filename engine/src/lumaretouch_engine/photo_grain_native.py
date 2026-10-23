"""Packaged std-only Rust, bounded row transfer, no runtime compile/fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import photo_grain_state as S
P = C.POINTER(C.c_float)
CHUNK = 65536


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_photo_grain.so'
    if not path.is_file():
        raise RuntimeError('颗粒 Rust 核心未安装；请使用完整打包版本')
    lib = C.CDLL(str(path))
    lib.lrt_photo_grain_abi.argtypes = []
    lib.lrt_photo_grain_abi.restype = C.c_uint32
    if lib.lrt_photo_grain_abi() != 1:
        raise RuntimeError('Photo grain ABI mismatch')
    lib.lrt_photo_grain_apply.argtypes = [P, P, C.c_size_t, P, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32]
    lib.lrt_photo_grain_apply.restype = C.c_int
    lib.lrt_photo_grain_apply_mapped.argtypes = [P, P, C.c_size_t, P, C.c_uint32, P, C.c_uint32]
    lib.lrt_photo_grain_apply_mapped.restype = C.c_int
    return lib


def apply(pixels, recipe, *, encoding, source_origin, cancelled=lambda: False):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return pixels
    if encoding not in ('linear-srgb-d65', 'extended-srgb-d65'):
        raise ValueError('Photo grain requires explicit supported RGB encoding')
    if not isinstance(pixels, np.ndarray) or pixels.dtype != np.float32 or pixels.ndim != 3 or pixels.shape[2] != 3 or min(pixels.shape[:2]) < 1 or pixels.size > 300_000_000:
        raise ValueError('Photo grain requires bounded HWC float32 source RGB')
    if not isinstance(source_origin, tuple) or len(source_origin) != 2 or any(type(v) is not int or v < 0 for v in source_origin):
        raise ValueError('Photo grain requires exact integer source origin (x,y)')
    ox, oy = source_origin
    height, width = pixels.shape[:2]
    if ox + width > 1000000 or oy + height > 1000000:
        raise ValueError('Photo grain source dimensions exceed supported domain')
    params = np.array(S.scalars(recipe), dtype=np.float32)
    if cancelled():
        raise InterruptedError('Photo grain cancelled')
    lib = native()
    dst = np.empty(pixels.shape, dtype=np.float32)
    for y in range(height):
        for x in range(0, width, CHUNK):
            if cancelled():
                raise InterruptedError('Photo grain cancelled')
            # Only one bounded input row copy beyond caller input and output.
            src = np.ascontiguousarray(pixels[y, x:x + CHUNK])
            out = dst[y, x:x + CHUNK]
            code = lib.lrt_photo_grain_apply(src.ctypes.data_as(P), out.ctypes.data_as(P), len(src), params.ctypes.data_as(P), recipe['seed'], ox+x, oy+y, int(encoding == 'extended-srgb-d65'))
            if code:
                raise ValueError(f'Photo grain Rust rejected source row: {code}')
    if cancelled():
        raise InterruptedError('Photo grain cancelled')
    return dst


def apply_canvas(pixels, recipe, *, source_size, geometry, cancelled=lambda: False):
    """In-place private render target, one immutable row copy, mapped source field."""
    from .photo_grain_geometry import mapping
    recipe = S.check(recipe)
    if not S.active(recipe):return pixels
    if pixels.dtype != np.float32 or pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError('Grain canvas must be private float32 RGB')
    h,w = pixels.shape[:2]
    if h*w > 100000000:raise ValueError('Grain canvas exceeds 100MP budget')
    coordinate_row = mapping(source_size, geometry, (w,h))
    params = np.array(S.scalars(recipe), dtype=np.float32);lib = native()
    for y in range(h):
        for x in range(0,w,CHUNK):
            if cancelled():raise InterruptedError('Photo grain cancelled')
            out = pixels[y,x:x+CHUNK]
            src = np.array(out, dtype=np.float32, copy=True, order='C')
            coords = coordinate_row(x,y,len(src))
            code = lib.lrt_photo_grain_apply_mapped(src.ctypes.data_as(P),out.ctypes.data_as(P),len(src),params.ctypes.data_as(P),recipe['seed'],coords.ctypes.data_as(P),1)
            if code:raise ValueError(f'Grain mapped source row rejected: {code}')
    if cancelled():raise InterruptedError('Photo grain cancelled')
    return pixels
