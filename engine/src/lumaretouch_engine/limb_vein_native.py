# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed Rust ABI only, no runtime compilation or numerical fallback. UNRUN."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
P = C.POINTER(C.c_float)
B = C.POINTER(C.c_uint8)
U = C.POINTER(C.c_uint64)
D = C.POINTER(C.c_double)
Z = C.c_size_t
CANCEL = C.CFUNCTYPE(C.c_int32, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_limb_vein.so'
    if not path.is_file():
        raise RuntimeError('Limb vein Rust library is not installed; no substitute applied')
    lib = C.CDLL(str(path))
    for name in ('lrt_limb_vein_abi', 'lrt_limb_vein_algorithm'):
        fn = getattr(lib, name); fn.argtypes = []; fn.restype = C.c_uint32
        if fn() != 1:
            raise RuntimeError('Limb vein native ABI or algorithm version mismatch')
    lib.lrt_limb_vein_measure_v1.argtypes = [P,Z,P,Z,P,Z,P,Z,B,Z,Z,Z,Z,C.c_uint64,P,Z,B,Z,U,Z,D,Z,CANCEL,C.c_void_p]
    lib.lrt_limb_vein_measure_v1.restype = C.c_int32
    lib.lrt_limb_vein_apply_v1.argtypes = [P,Z,P,Z,Z,Z,C.c_double,C.c_uint64,P,Z,CANCEL,C.c_void_p]
    lib.lrt_limb_vein_apply_v1.restype = C.c_int32
    return lib


def capability():
    try:
        native()
        return {'available': True, 'reason': None}
    except (OSError, RuntimeError, AttributeError) as error:
        return {'available': False, 'reason': str(error)}


def callback(cancelled):
    errors = []
    def call(_):
        try:
            return int(bool(errors or (cancelled and cancelled())))
        except BaseException as error:
            errors.append(error); return 1
    return CANCEL(call), errors


def checked(code, errors):
    if errors:
        raise errors[0]
    if code == 0:
        return
    if code == 5:
        raise MemoryError('Limb vein native resource budget refused')
    if code == 6:
        raise InterruptedError('Limb vein native processing cancelled')
    if code == 4:
        raise ValueError('Clean same-limb reference is too small, clipped, dark or heterogeneous')
    if code in (1, 2, 3):
        raise ValueError('Limb vein buffer, SDR domain, masks or settings are invalid')
    raise RuntimeError('Limb vein native numerical failure; private result discarded')
