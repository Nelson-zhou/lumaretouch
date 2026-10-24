# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict standalone Rust eye-makeup ABI. AUTHORED / UNRUN, no Python fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import eye_makeup_enhance_state as S
from .cpu_memory_budget import available_estimate

ENCODING = 'encoded-working-srgb-d65-sdr'
MAX_PIXELS = 4_000_000
MAX_DIMENSION = 65_536
MAX_RADIUS = 64
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_eye_makeup_enhance.so'
    if not path.is_file():
        raise RuntimeError('已有眼妆增强 Rust 核心未安装；没有替代算法')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_eye_makeup_enhance_abi.argtypes = []
        lib.lrt_eye_makeup_enhance_abi.restype = C.c_uint32
        if lib.lrt_eye_makeup_enhance_abi() != 1:
            raise RuntimeError('已有眼妆增强 Rust ABI 不匹配')
        lib.lrt_eye_makeup_enhance_apply_v1.argtypes = [
            P,C.c_size_t,P,C.c_size_t,P,C.c_size_t,P,C.c_size_t,C.c_size_t,C.c_size_t,
            C.c_float,C.c_float,C.c_float,C.c_float,C.c_size_t,P,C.c_size_t,CANCEL,C.c_void_p]
        lib.lrt_eye_makeup_enhance_apply_v1.restype = C.c_int
        return lib
    except (OSError, AttributeError) as error:
        raise RuntimeError('已有眼妆增强 Rust 核心缺少必需 ABI') from error


def available():
    try:
        native(); return True
    except (OSError, AttributeError, RuntimeError):
        return False


def memory_estimate(shape):
    if (type(shape) not in (tuple,list) or len(shape) != 2
            or any(type(v) is not int or not 1 <= v <= MAX_DIMENSION for v in shape)):
        raise ValueError('眼妆原尺寸窗口尺寸无效')
    h,w = shape
    if h*w > MAX_PIXELS:
        raise MemoryError('眼妆原尺寸窗口超预算；不会降采样代替')
    # Independent Python inputs 24B, output 12B, Rust Lab 24B + integral 40B
    # and private result 12B per pixel. Extra row/column and allocator allowance.
    return 112*h*w + 40*(h+w+1) + 16*1024**2


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('眼妆增强已取消，未发布部分结果')


def _snapshot(value, shape, label, cancelled):
    if type(value) is not np.ndarray or value.dtype != np.float32 or value.shape != shape:
        raise ValueError(label+'必须为精确 float32 源网格；不接受 alpha 或隐式转换')
    _poll(cancelled)
    result = np.empty(shape, dtype=np.float32, order='C')
    for y in range(shape[0]):
        for x in range(0,shape[1],4096):
            _poll(cancelled)
            block = result[y,x:x+4096]; block[...] = value[y,x:x+4096]
            if not np.isfinite(block).all() or np.any((block<0)|(block>1)):
                raise ValueError(label+'必须为有限 SDR [0,1]；不裁切 HDR')
    result.setflags(write=False)
    return result


def apply(source_rgb, coverage, controls, *, reference_a, reference_b, radius, cancelled=lambda:False):
    """Complete immutable source window only, never tile-local or previous output.

    All arrays are independent snapshots; caller inputs stay immutable while
    copying. Explicit opacity/colour-profile admission belongs to source owner.
    Controls are scalar-only; support/reference identities belong to host review.
    No masked sample, protected pixel or missing halo is synthesized.
    """
    if not callable(cancelled):
        raise TypeError('cancelled must be callable')
    if type(controls) is not dict or set(controls) != set(S.CONTROL_KEYS):
        raise ValueError('眼妆 Rust 调用需要四项当前侧别数值')
    values = [S.amount(controls[key]) for key in S.CONTROL_KEYS]
    if type(radius) is not int or not 1 <= radius <= MAX_RADIUS:
        raise ValueError('眼妆结构半径须从真实眼宽测得且为 1–64 整数')
    if type(source_rgb) is not np.ndarray or source_rgb.ndim != 3 or source_rgb.shape[-1] != 3:
        raise ValueError('眼妆需要 HWC float32 working-sRGB SDR RGB，不接受 alpha')
    h,w,_ = source_rgb.shape
    extra = memory_estimate((h,w)); _poll(cancelled)
    if extra > available_estimate():
        raise MemoryError('眼妆完整源窗口与 Rust 临时数据超可用内存')
    source = _snapshot(source_rgb,(h,w,3),'源图',cancelled)
    target = _snapshot(coverage,(h,w),'可见眼妆支撑',cancelled)
    a = _snapshot(reference_a,(h,w),'第一皮肤参考',cancelled)
    b = _snapshot(reference_b,(h,w),'第二皮肤参考',cancelled)
    if np.any((target>0)&((a>0)|(b>0))) or np.any((a>0)&(b>0)):
        raise ValueError('妆区和两块独立皮肤参考不能重叠')
    output = np.empty_like(source); errors = []
    def poll(_context):
        if errors: return 1
        try: return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error); return 1
    callback = CANCEL(poll); lib = native(); _poll(cancelled)
    code = lib.lrt_eye_makeup_enhance_apply_v1(source.ctypes.data_as(P),source.size,
        target.ctypes.data_as(P),target.size,a.ctypes.data_as(P),a.size,b.ctypes.data_as(P),b.size,
        w,h,*values,radius,output.ctypes.data_as(P),output.size,callback,None)
    if errors: raise errors[0]
    if code == 4: raise InterruptedError('眼妆增强已取消，私有结果已丢弃')
    _poll(cancelled)
    if code == 5: raise MemoryError('眼妆 Rust 源窗口或分配超预算')
    if code == 6: raise RuntimeError('眼妆 Rust 异常已隔离，未发布结果')
    if code:
        reasons = {1:'ABI、尺寸、长度或缓冲别名无效',2:'控件或半径无效',3:'源像素或数值无效',
                   7:'两块干净参考不一致、过少或无可靠原有妆色差；不能据此增强或减淡',
                   8:'可见妆区完整采样范围不足或没有可测立体结构'}
        raise ValueError('眼妆增强拒绝：'+reasons.get(code,str(code)))
    for y in range(h):
        for x in range(0,w,4096):
            _poll(cancelled); block=output[y,x:x+4096]; original=source[y,x:x+4096]
            if not np.isfinite(block).all() or np.any((block<0)|(block>1)):
                raise RuntimeError('眼妆 Rust 返回无效 SDR 结果，已丢弃')
            protected = np.ones(block.shape[:1],bool) if not any(values) else target[y,x:x+4096] == 0
            if not np.array_equal(block[protected].view(np.uint32),original[protected].view(np.uint32)):
                raise RuntimeError('眼妆 Rust 改动中性或受保护源像素，已丢弃')
    return output
