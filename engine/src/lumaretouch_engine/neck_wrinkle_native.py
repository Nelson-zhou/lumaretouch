# SPDX-License-Identifier: GPL-3.0-or-later
"""Original ctypes boundary only; the numerical library is AGPL-3.0-only.

AUTHORED / UNRUN. No compilation, dependency installation, alternate numerical
implementation or cached-preview fallback. See core/neck_wrinkle/NOTICE.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path

ABI = 1
ALGORITHM = 1
P = C.POINTER(C.c_float)
BP = C.POINTER(C.c_uint8)
UP = C.POINTER(C.c_uint64)
DP = C.POINTER(C.c_double)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


class NeckWrinkleUnavailable(RuntimeError):
    """The separately built, installed, matching numerical ABI is unavailable."""


class NeckWrinkleContextError(ValueError):
    """No complete admitted source footprint, distinct from valid zero signal."""


class NeckWrinkleScaleError(ValueError):
    """The observed line scale is unsupported; never silently clamped."""


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_neck_wrinkle.so'
    if not path.is_file():
        raise NeckWrinkleUnavailable('Neck wrinkle native core is not installed; no fallback applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_neck_wrinkle_abi.argtypes = []
        lib.lrt_neck_wrinkle_abi.restype = C.c_uint32
        lib.lrt_neck_wrinkle_algorithm.argtypes = []
        lib.lrt_neck_wrinkle_algorithm.restype = C.c_uint32
        if lib.lrt_neck_wrinkle_abi() != ABI or lib.lrt_neck_wrinkle_algorithm() != ALGORITHM:
            raise NeckWrinkleUnavailable('Neck wrinkle ABI/algorithm mismatch; no fallback applied')
        lib.lrt_neck_wrinkle_measure_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, BP, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t,
            C.c_double, C.c_uint64, P, C.c_size_t, BP, C.c_size_t, UP, C.c_size_t, DP, C.c_size_t,
            CANCEL, C.c_void_p,
        ]
        lib.lrt_neck_wrinkle_measure_v1.restype = C.c_int32
        lib.lrt_neck_wrinkle_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t, C.c_double,
            P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_neck_wrinkle_apply_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise NeckWrinkleUnavailable('Neck wrinkle core cannot load the required ABI') from error
    return lib


def available():
    """Installed ABI/symbol compatibility only, never quality or support acceptance."""
    try:
        native()
        return True
    except NeckWrinkleUnavailable:
        return False


def callback(cancelled):
    errors = []
    def poll(_context):
        if errors:
            return 1
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1
    return CANCEL(poll), errors


def result(code, errors):
    if errors:
        raise errors[0]
    if code == 0:
        return
    if code == 3:
        raise NeckWrinkleScaleError('Neck fine-line half-width must be 1.4..12 source pixels')
    if code == 4:
        raise NeckWrinkleContextError('No complete admitted neck sampling footprint; no inferred context')
    if code == 5:
        raise MemoryError('Neck wrinkle memory admission refused; no proxy fallback')
    if code == 6:
        raise InterruptedError('Neck wrinkle cancelled; private output discarded')
    if code in (7, 8):
        raise RuntimeError('Neck wrinkle numerical failure or contained panic; private output discarded')
    if code in (1, 2):
        raise ValueError('Neck wrinkle rejected dimensions, buffer ownership, SDR pixels or settings')
    raise RuntimeError('Neck wrinkle returned an unknown status; private output discarded')
