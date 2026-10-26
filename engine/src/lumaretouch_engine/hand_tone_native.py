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
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_hand_tone.so'
    if not path.is_file():
        raise RuntimeError('Hand tone Rust library is not installed; no substitute applied')
    lib = C.CDLL(str(path))
    for name in ('lrt_hand_tone_abi', 'lrt_hand_tone_algorithm'):
        fn = getattr(lib, name); fn.argtypes = []; fn.restype = C.c_uint32
        if fn() != 1:
            raise RuntimeError('Hand tone native ABI or algorithm version mismatch')
    lib.lrt_hand_tone_measure_v1.argtypes = [P,Z,P,Z,P,Z,B,Z,Z,Z,Z,C.c_uint64,P,Z,B,Z,U,Z,D,Z,CANCEL,C.c_void_p]
    lib.lrt_hand_tone_measure_v1.restype = C.c_int32
    lib.lrt_hand_tone_apply_v1.argtypes = [P,Z,P,Z,Z,Z,C.c_double,C.c_uint64,P,Z,CANCEL,C.c_void_p]
    lib.lrt_hand_tone_apply_v1.restype = C.c_int32
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
        raise MemoryError('Hand tone native resource budget refused')
    if code == 6:
        raise InterruptedError('Hand tone native processing cancelled')
    if code == 4:
        raise ValueError('手部局部上下文不足或对比过强；请扩大明确手部范围、缩小原图半径，并避开保护区、暗部和剪切高光')
    if code in (1, 2, 3):
        raise ValueError('Hand tone buffer, SDR domain, masks or settings are invalid')
    raise RuntimeError('Hand tone native numerical failure; private result discarded')
