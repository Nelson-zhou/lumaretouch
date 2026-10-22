# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixed Rust ABI, no runtime build/download or Python optimization fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import semantic_colour_state as S
D = C.POINTER(C.c_double)
F = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int)

@lru_cache(maxsize=1)
def library():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_semantic_colour.so'
    if not path.is_file(): raise RuntimeError('AI 追色 Rust 核心未打包；不会使用占位或直方图回退')
    lib = C.CDLL(str(path)); lib.lrt_semantic_colour_abi.restype = C.c_uint32
    if lib.lrt_semantic_colour_abi() != 1: raise RuntimeError('AI 追色 Rust ABI 不匹配')
    lib.lrt_sc_fit.argtypes = [D, C.c_size_t, D, C.c_size_t, C.c_uint32, CANCEL, D, D]
    lib.lrt_sc_fit.restype = C.c_int
    lib.lrt_sc_apply.argtypes = [F, C.c_size_t, D, D, F, F]
    lib.lrt_sc_apply.restype = C.c_int
    return lib

def fit(reference, target, mode, cancelled=lambda: False):
    r, t = [np.ascontiguousarray(v, dtype=np.float64) for v in (reference, target)]
    if mode not in ('extreme', 'harmonious') or any(a.ndim != 2 or a.shape[1] != 5 or not 32 <= len(a) <= 6144 for a in (r, t)):
        raise ValueError('AI 追色需要有界 RGB/类别/权重样本')
    p = np.empty((7, S.PARAMS), np.float64); stats = np.empty((7, 10), np.float64)
    callback = CANCEL(lambda: 1 if cancelled() else 0)
    code = library().lrt_sc_fit(r.ctypes.data_as(D), len(r), t.ctypes.data_as(D), len(t), int(mode == 'harmonious'), callback, p.ctypes.data_as(D), stats.ctypes.data_as(D))
    if code == 9: raise InterruptedError('AI 追色已取消，未应用任何参数')
    if code: raise ValueError(f'AI 语义拟合拒绝：{code}（语义支持不足、OT 未稳定或参数无效）')
    if not np.isfinite(p).all() or not np.isfinite(stats).all(): raise ValueError('AI 追色核心返回非有限结果')
    return [S.parameters(row.tolist()) for row in p], stats.tolist()

def apply(rgb, parameters, strengths, mask=None):
    # Actual float32 point evaluation also backs fit. RGB16 is normalized only
    # here and quantized once by the caller at its delivery boundary.
    a = np.ascontiguousarray(rgb, dtype=np.float32)
    if a.ndim != 3 or a.shape[-1] != 3 or not np.isfinite(a).all(): raise ValueError('AI 追色需要有限 H×W×3 浮点 RGB')
    p = np.asarray(S.parameters(parameters), np.float64)
    s = np.asarray([S.number(v, 0, 200) / 100 for v in strengths], np.float64)
    if s.shape != (3,): raise ValueError('AI 追色程度字段无效')
    if not s[0] or not np.any(s[1:]) or parameters == S.neutral(): return rgb
    m = None if mask is None else np.ascontiguousarray(mask, dtype=np.float32)
    if m is not None and (m.shape != a.shape[:2] or not np.isfinite(m).all() or np.any(m < 0) or np.any(m > 1)):
        raise ValueError('AI 追色画布蒙版形状/数值不匹配')
    if m is not None and not np.any(m): return rgb
    out = np.empty_like(a)
    for y in range(0, a.shape[0], max(1, 1_000_000 // a.shape[1])):
        h = min(a.shape[0] - y, max(1, 1_000_000 // a.shape[1]))
        tile = a[y:y+h]; dest = out[y:y+h]; field = None if m is None else m[y:y+h]
        code = library().lrt_sc_apply(tile.ctypes.data_as(F), h*a.shape[1], p.ctypes.data_as(D), s.ctypes.data_as(D), None if field is None else field.ctypes.data_as(F), dest.ctypes.data_as(F))
        if code: raise ValueError(f'AI 追色渲染拒绝：{code}；未发布部分画布')
    return out
