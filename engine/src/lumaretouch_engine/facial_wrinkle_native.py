"""Bounded Rust overlap composer. No runtime compilation or fallback algorithm."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
P = C.POINTER(C.c_float)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_facial_wrinkles.so'
    if not path.is_file():
        raise RuntimeError('面部祛纹 Rust 核心未安装；请使用打包构建，未生成替代效果')
    lib = C.CDLL(str(path))
    lib.lrt_wrinkles_abi.argtypes = []; lib.lrt_wrinkles_abi.restype = C.c_uint32
    if lib.lrt_wrinkles_abi() != 1:
        raise RuntimeError('面部祛纹 Rust 核心 ABI 不匹配')
    lib.lrt_wrinkles_merge.argtypes = [P, P, C.c_float, P, C.c_size_t]
    lib.lrt_wrinkles_merge.restype = C.c_int
    return lib


def merge(proposal, support, amount, output):
    arrays = (proposal, support, output)
    if any(type(a) is not np.ndarray or a.dtype != np.float32 or not a.flags.c_contiguous
           or a.ndim != 2 or a.shape != output.shape for a in arrays):
        raise ValueError('面部祛纹合成场必须是同尺寸连续 float32')
    if any(np.shares_memory(a, b) for a, b in ((proposal, output), (support, output))):
        raise ValueError('面部祛纹输出不能覆盖其源派生场')
    code = native().lrt_wrinkles_merge(proposal.ctypes.data_as(P), support.ctypes.data_as(P),
                                      amount, output.ctypes.data_as(P), output.size)
    if code:
        raise ValueError(f'Rust 面部祛纹合成拒绝参数：{code}')
