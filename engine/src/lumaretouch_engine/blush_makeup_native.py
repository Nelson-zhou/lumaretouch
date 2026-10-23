# SPDX-License-Identifier: GPL-3.0-or-later
"""Checked Rust boundary, no implicit install/compile or alternate renderer."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import blush_makeup_state as S
from .blush_makeup_catalogue import material
P=C.POINTER(C.c_float)

@lru_cache(maxsize=1)
def native():
    path=Path(__file__).with_name('bin')/'liblrt_blush_makeup.so'
    if not path.is_file():raise RuntimeError('腮红 Rust 核心未安装；请使用完整打包版本')
    lib=C.CDLL(str(path));lib.lrt_blush_makeup_abi.argtypes=[];lib.lrt_blush_makeup_abi.restype=C.c_uint32
    if lib.lrt_blush_makeup_abi()!=1:raise RuntimeError('腮红 Rust ABI 不匹配')
    lib.lrt_blush_makeup_delta.argtypes=[P,P,P,C.c_size_t,P,C.c_size_t,C.c_float,C.c_float,C.c_float,C.c_float,P]
    lib.lrt_blush_makeup_delta.restype=C.c_int
    return lib

def delta(source,uv,support,recipe):
    r=S.check(recipe);shape=source.shape[:2]
    for array,expected in ((source,(*shape,3)),(uv,(*shape,2)),(support,shape)):
        if type(array) is not np.ndarray or array.dtype!=np.float32 or array.shape!=expected or not array.flags.c_contiguous:
            raise ValueError('腮红核心需要连续、对齐的 float32 场')
    if not S.active(r):return np.zeros_like(source) # Never load native code for neutral.
    lobes=np.ascontiguousarray(material(r['pattern'])['lobes'],dtype=np.float32)
    rgb=[int(r['colour'][i:i+2],16)/255 for i in (1,3,5)]
    out=np.empty_like(source)
    status=native().lrt_blush_makeup_delta(source.ctypes.data_as(P),uv.ctypes.data_as(P),support.ctypes.data_as(P),support.size,
        lobes.ctypes.data_as(P),len(lobes),r['strength'],*rgb,out.ctypes.data_as(P))
    if status:raise ValueError(f'腮红 Rust 核心拒绝输入：{status}')
    return out
