"""RGB uint16 ICC conversion via the public LittleCMS 2 API, without uint8 staging.

API/format definitions: https://github.com/mm2/Little-CMS/blob/master/include/lcms2.h
LittleCMS is MIT licensed; use the distribution's liblcms2 runtime.
"""
from __future__ import annotations
import ctypes as C
import ctypes.util
import functools
import numpy as np

_RGB16 = (4 << 16) | (3 << 3) | 2
_RGB_SIGNATURE = 0x52474220
_MAX_PROFILE_BYTES = 16 * 1024 * 1024


@functools.lru_cache(maxsize=1)
def _library():
    name = ctypes.util.find_library('lcms2')
    if not name:
        raise ValueError('16-bit ICC转换需要系统LittleCMS 2；不会降到8-bit替代')
    lib = C.CDLL(name)
    for name, args, result in (
        ('cmsOpenProfileFromMem', [C.c_void_p,C.c_uint32], C.c_void_p),
        ('cmsCloseProfile', [C.c_void_p], C.c_int),
        ('cmsGetColorSpace', [C.c_void_p], C.c_uint32),
        ('cmsCreateTransform', [C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32], C.c_void_p),
        ('cmsDeleteTransform', [C.c_void_p], None),
        ('cmsDoTransform', [C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint32], None),
    ):
        fn = getattr(lib,name); fn.argtypes=args; fn.restype=result
    return lib


def convert_rgb16(rgb: np.ndarray, source_icc: bytes, target_icc: bytes,
                  *, intent: int = 1, blackpoint: bool = True) -> np.ndarray:
    """Convert encoded RGB16 profiles; caller names the source space explicitly.

    Profiles/transform are scoped to this call, so concurrent images never share
    mutable transform state. Only equal, validated RGB profiles bypass conversion.
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint16:
        raise ValueError('16-bit ICC输入必须是(H,W,3) uint16')
    if intent not in (0,1,2,3):
        raise ValueError('ICC rendering intent无效')
    for profile in (source_icc,target_icc):
        if not isinstance(profile,bytes) or not 0 < len(profile) <= _MAX_PROFILE_BYTES:
            raise ValueError('ICC profile为空、类型错误或超过16MiB')
    lib=_library(); profiles=[]; buffers=[]; transform=None
    try:
        for blob in (source_icc,target_icc):
            buf=C.create_string_buffer(blob); buffers.append(buf)
            handle=lib.cmsOpenProfileFromMem(buf,len(blob))
            if not handle: raise ValueError('无法打开ICC profile')
            profiles.append(handle)
            if lib.cmsGetColorSpace(handle) != _RGB_SIGNATURE:
                raise ValueError('16-bit三通道路径只接受RGB ICC profile')
        arr=np.ascontiguousarray(rgb)
        if source_icc == target_icc:
            return arr.copy()
        # NOOPTIMIZE avoids an optional coarse LUT approximation; both buffers
        # remain uint16. Blackpoint compensation matches the existing 8-bit path.
        flags=0x0100 | (0x2000 if blackpoint and intent != 3 else 0)
        transform=lib.cmsCreateTransform(profiles[0],_RGB16,profiles[1],_RGB16,intent,flags)
        if not transform: raise ValueError('无法创建16-bit RGB ICC转换')
        out=np.empty_like(arr)
        flat=arr.reshape(-1,3); dest=out.reshape(-1,3)
        for start in range(0,len(flat),1_000_000):
            n=min(1_000_000,len(flat)-start)
            lib.cmsDoTransform(transform,C.c_void_p(flat[start:].ctypes.data),
                               C.c_void_p(dest[start:].ctypes.data),n)
        return out
    finally:
        if transform: lib.cmsDeleteTransform(transform)
        for handle in reversed(profiles): lib.cmsCloseProfile(handle)
