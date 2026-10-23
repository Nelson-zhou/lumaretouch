# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned Rust ABI; no runtime compiler, fallback renderer, or RGB8 conversion."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import lipstick_state as S
from .lipstick_catalogue import material
P=C.POINTER(C.c_float)
@lru_cache(maxsize=1)
def native():
    path=Path(__file__).with_name('bin')/'liblrt_lipstick.so'
    if not path.is_file():raise RuntimeError('口红 Rust 核心未安装，请使用完整打包版本')
    lib=C.CDLL(str(path));lib.lrt_lipstick_abi.argtypes=[];lib.lrt_lipstick_abi.restype=C.c_uint32
    if lib.lrt_lipstick_abi()!=1:raise RuntimeError('口红 Rust ABI 不匹配')
    lib.lrt_lipstick_delta.argtypes=[P,P,P,P,C.c_size_t,C.c_uint32,C.c_uint32,C.c_float,C.c_float,C.c_float,C.c_float,P]
    lib.lrt_lipstick_delta.restype=C.c_int
    return lib

def delta(source,uv,support,base,recipe):
    r=S.check(recipe);shape=source.shape[:2]
    for array,expected in ((source,(*shape,3)),(uv,(*shape,3)),(support,shape),(base,shape)):
        if type(array) is not np.ndarray or array.dtype!=np.float32 or array.shape!=expected or not array.flags.c_contiguous:
            raise ValueError('口红核心需要连续对齐 float32 场')
    if not S.active(r):return np.zeros_like(source)
    rgb=[int(r['colour'][i:i+2],16)/255 for i in (1,3,5)];out=np.empty_like(source)
    code=native().lrt_lipstick_delta(source.ctypes.data_as(P),uv.ctypes.data_as(P),support.ctypes.data_as(P),base.ctypes.data_as(P),support.size,
        material(r['pattern'])['kernel'],S.TEXTURES.index(r['texture']),r['strength'],*rgb,out.ctypes.data_as(P))
    if code:raise ValueError(f'口红 Rust 核心拒绝输入：{code}')
    return out
