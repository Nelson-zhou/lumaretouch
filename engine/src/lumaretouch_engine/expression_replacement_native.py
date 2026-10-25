# SPDX-License-Identifier: GPL-3.0-or-later
"""Versioned installed Rust donor blend. No implicit build, download or fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import math

P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int32)
MAX_SIDE = 1024
REQUIRED_CAPABILITIES = 0x3f


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_expression_blend.so'
    if not path.is_file():
        raise RuntimeError('表情替换原生模块未安装；不会使用占位融合或自动下载')
    try:
        lib = C.CDLL(str(path))
        for name, result in [('lrt_expression_blend_abi', C.c_uint32),
                             ('lrt_expression_blend_capabilities_v1', C.c_uint64),
                             ('lrt_expression_blend_max_side_v1', C.c_size_t),
                             ('lrt_expression_blend_max_levels_v1', C.c_size_t)]:
            method = getattr(lib, name); method.argtypes = []; method.restype = result
        if (lib.lrt_expression_blend_abi() != 1
                or lib.lrt_expression_blend_capabilities_v1() != REQUIRED_CAPABILITIES
                or lib.lrt_expression_blend_max_side_v1() != MAX_SIDE
                or lib.lrt_expression_blend_max_levels_v1() != 5):
            raise RuntimeError('表情替换模块 ABI、算法能力或安全限额不匹配')
        lib.lrt_expression_blend_v1.argtypes = (
            [P,C.c_size_t,C.c_size_t,C.c_size_t]*2
            + [P,C.c_size_t]*8
            + [C.c_uint32,C.c_float,C.c_float,C.c_size_t]
            + [P,C.c_size_t]*3 + [CANCEL])
        lib.lrt_expression_blend_v1.restype = C.c_int32
        return lib
    except (OSError, AttributeError) as error:
        raise RuntimeError('表情替换原生接口不可用') from error


def capability():
    try:
        native()
        return {'protocol':1, 'operation_id':'lnx.expression_replacement.v1', 'available':True, 'reason':None}
    except (OSError, RuntimeError, AttributeError) as error:
        return {'protocol':1, 'operation_id':'lnx.expression_replacement.v1', 'available':False, 'reason':str(error)}


def blend(target, donor, target_landmarks, donor_landmarks, target_allowed,
          donor_allowed, target_protection, donor_protection, fusion, *,
          density, levels, reviews, max_bytes, cancelled=lambda: False):
    """Opaque linear SDR crop in, all three immutable outputs after success only.

    Colour offset is deliberately zero in the first public workflow, so the
    optional reference pointer is NULL rather than fabricated skin observations.
    Effective fusion is diagnostic coverage. Do not apply it a second time to
    the already blended opaque output patch.
    """
    import numpy as np
    if type(reviews) is not int or reviews != 127:
        raise ValueError('表情替换需要明确人物、场次、真实定位及可见性审核')
    if type(density) not in (int,float) or not math.isfinite(density) or not 0 <= density <= 1:
        raise ValueError('Invalid expression density')
    if type(levels) is not int or not 1 <= levels <= 5:
        raise ValueError('Invalid expression pyramid depth')
    def poll():
        if cancelled(): raise InterruptedError('Expression blend cancelled before publication')
    poll()
    shapes=[]
    for image in (target, donor):
        if (type(image) is not np.ndarray or image.dtype != np.float32 or image.ndim != 3
                or image.shape[2] != 4 or not all(2 <= n <= MAX_SIDE for n in image.shape[:2])):
            raise ValueError('Expression bridge requires genuine native float32 RGBA crops')
        shapes.append(image.shape[:2])
    estimate = sum(h*w for h,w in shapes)*192 + 32_000_000
    if type(max_bytes) is not int or estimate > max_bytes:
        raise MemoryError('Expression native crop working set exceeds remaining source budget')
    source_arrays=(target,donor,target_landmarks,donor_landmarks,target_allowed,
                   donor_allowed,target_protection,donor_protection,fusion)
    expected=(target.shape,donor.shape,(478,3),(478,3),shapes[0],shapes[1],shapes[0],shapes[1],shapes[0])
    frozen=[]
    for array, shape in zip(source_arrays, expected):
        if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
            raise ValueError('Expression source/support array does not match its owned crop')
        copy=np.array(array,dtype=np.float32,order='C',copy=True)
        if not np.isfinite(copy).all(): raise ValueError('Nonfinite expression input')
        copy.setflags(write=False);frozen.append(copy)
    target,donor,tl,dl,ta,da,tp,dp,fusion=frozen
    output=np.empty_like(target);effective=np.empty(shapes[0],np.float32);receipt=np.empty(16,np.float32)
    errors=[]
    def callback():
        try:return int(bool(cancelled()))
        except BaseException as error:errors.append(error);return 1
    cb=CANCEL(callback)
    def pair(array):return [array.ctypes.data_as(P),array.size]
    args=pair(target)+[target.shape[1],target.shape[0]]+pair(donor)+[donor.shape[1],donor.shape[0]]
    for array in (tl,dl,ta,da,tp,dp,fusion):args+=pair(array)
    args += [None,0,reviews,float(density),0.,levels]
    args += pair(output)+pair(effective)+pair(receipt)+[cb]
    poll()
    code=native().lrt_expression_blend_v1(*args)
    if errors:raise errors[0]
    poll()
    if code==9:raise InterruptedError('Expression native calculation cancelled')
    if code==8:raise MemoryError('Expression native allocation limit exceeded')
    if code:raise ValueError('Expression native source admission or fusion refused, code '+str(code))
    if (not np.isfinite(output).all() or not np.isfinite(effective).all() or not np.isfinite(receipt).all()
            or np.any(output[:,:,:3]<0) or np.any(output[:,:,:3]>1) or np.any(output[:,:,3]!=1)
            or np.any(effective<0) or np.any(effective>fusion+1e-6)):
        raise ValueError('Expression core returned an invalid opaque SDR result or fusion coverage')
    for array in (output,effective,receipt):array.setflags(write=False)
    return output,effective,receipt
