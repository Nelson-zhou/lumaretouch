# SPDX-License-Identifier: GPL-3.0-or-later
import ctypes as C
from pathlib import Path
from functools import lru_cache
import numpy as np
from . import iris_makeup_state as S
P=C.POINTER(C.c_float)
@lru_cache(maxsize=1)
def native():
    path=Path(__file__).with_name('bin')/'liblrt_iris_makeup.so'
    if not path.is_file():raise RuntimeError('美瞳 Rust 核心未安装，未应用效果')
    lib=C.CDLL(str(path));lib.lrt_iris_makeup_abi.restype=C.c_uint32;lib.lrt_iris_makeup_abi.argtypes=[]
    if lib.lrt_iris_makeup_abi()!=1:raise RuntimeError('美瞳 ABI 不匹配')
    lib.lrt_iris_makeup_delta.argtypes=[P,P,P,C.c_size_t,C.c_uint32,C.c_float,P];lib.lrt_iris_makeup_delta.restype=C.c_int
    return lib

def delta(source,uv,support,recipe):
    r=S.check(recipe);shape=source.shape[:2]
    for a,expected in ((source,(*shape,3)),(uv,(*shape,2)),(support,shape)):
        if type(a) is not np.ndarray or a.dtype!=np.float32 or a.shape!=expected or not a.flags.c_contiguous or not a.flags.aligned or not np.isfinite(a).all():raise ValueError('美瞳需要连续对齐有限 float32 场')
    if not S.active(r):return np.zeros_like(source)
    out=np.empty_like(source);code=native().lrt_iris_makeup_delta(source.ctypes.data_as(P),uv.ctypes.data_as(P),support.ctypes.data_as(P),support.size,S.PATTERNS.index(r['pattern']),r['strength'],out.ctypes.data_as(P))
    if code:raise ValueError(f'美瞳 Rust 拒绝输入：{code}')
    return out
