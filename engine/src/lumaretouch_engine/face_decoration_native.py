# SPDX-License-Identifier: GPL-3.0-or-later
"""Checked Rust boundary. No runtime compiler, silent fallback or RGB8 round trip."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import face_decoration_state as S
from .face_decoration_catalogue import material

P = C.POINTER(C.c_float)
MAX_PIXELS = 4_000_000


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).with_name('bin') / 'liblrt_face_decoration.so'
    if not path.is_file():
        raise RuntimeError('面部装饰 Rust 核心未安装；请使用完整打包版本')
    lib = C.CDLL(str(path))
    lib.lrt_face_decoration_abi.argtypes = []
    lib.lrt_face_decoration_abi.restype = C.c_uint32
    if lib.lrt_face_decoration_abi() != 1:
        raise RuntimeError('面部装饰 Rust ABI 不匹配')
    lib.lrt_face_decoration_delta.argtypes = [P, P, P, C.c_size_t, C.c_size_t, P, C.c_size_t, C.c_float, P]
    lib.lrt_face_decoration_delta.restype = C.c_int
    return lib


def available():
    """Probe the loaded ABI, not merely whether a binary path exists."""
    try:
        native()
    except (OSError, RuntimeError, AttributeError):
        return False
    return True


def delta(source, frame, support, recipe):
    recipe = S.check(recipe)
    if (type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3
            or min(source.shape[:2]) < 1 or source.shape[0] * source.shape[1] > MAX_PIXELS):
        raise ValueError('面部装饰源窗口无效或超出预算')
    shape = source.shape[:2]
    for array, expected in ((source, (*shape, 3)), (frame, (3, 2)), (support, shape)):
        if (type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != expected
                or not array.flags.c_contiguous or not array.flags.aligned
                or not np.isfinite(array).all()):
            raise ValueError('面部装饰核心需要连续、对齐、有限的 float32 场')
    if np.any((source < 0) | (source > 1)) or np.any((support < 0) | (support > 1)):
        raise ValueError('面部装饰只接受 SDR working-sRGB 与有界支持；不偷裁切 HDR')
    if not S.active(recipe):
        return np.zeros_like(source)
    marks = np.ascontiguousarray(material(recipe['pattern'])['marks'], dtype=np.float32)
    out = np.empty_like(source)
    status = native().lrt_face_decoration_delta(
        source.ctypes.data_as(P), frame.ctypes.data_as(P), support.ctypes.data_as(P),
        shape[1], shape[0], marks.ctypes.data_as(P), len(marks), recipe['strength'], out.ctypes.data_as(P))
    if status:
        raise ValueError(f'面部装饰 Rust 核心拒绝输入：{status}')
    return out
