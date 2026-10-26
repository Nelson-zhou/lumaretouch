# SPDX-License-Identifier: GPL-3.0-or-later
"""Checked boundary to the separately built original Rust core. AUTHORED / UNRUN.

No runtime compilation, downloads, alternate algorithm, inference or proxy fit.
Availability reports exact ABI/symbol compatibility, not photographic quality.
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
CANCEL = C.CFUNCTYPE(C.c_int32, C.c_void_p)


class HairSmoothingUnavailable(RuntimeError):
    pass


class HairSmoothingContextError(ValueError):
    """Missing complete ownership/context is not successful absent direction."""


class HairSmoothingScaleError(ValueError):
    pass


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_hair_smoothing.so'
    if not path.is_file():
        raise HairSmoothingUnavailable('Visible-hair directional core is not installed; no fallback')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_hair_smoothing_abi.argtypes = []
        lib.lrt_hair_smoothing_abi.restype = C.c_uint32
        lib.lrt_hair_smoothing_algorithm.argtypes = []
        lib.lrt_hair_smoothing_algorithm.restype = C.c_uint32
        if lib.lrt_hair_smoothing_abi() != ABI or lib.lrt_hair_smoothing_algorithm() != ALGORITHM:
            raise HairSmoothingUnavailable('Visible-hair core ABI/algorithm mismatch')
        lib.lrt_hair_smoothing_plan_v1.argtypes = [C.c_size_t, C.c_size_t, C.c_double, UP, C.c_size_t]
        lib.lrt_hair_smoothing_plan_v1.restype = C.c_int32
        lib.lrt_hair_smoothing_measure_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, P, C.c_size_t, BP, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_double, C.c_uint64,
            P, C.c_size_t, BP, C.c_size_t, UP, C.c_size_t, DP, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_hair_smoothing_measure_v1.restype = C.c_int32
        lib.lrt_hair_smoothing_compose_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t, C.c_double, C.c_uint64,
            P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_hair_smoothing_compose_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise HairSmoothingUnavailable('Visible-hair core cannot load its complete checked ABI') from error
    return lib


def available():
    try:
        native()
        return True
    except HairSmoothingUnavailable:
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


def result(code, errors=()):
    if errors:
        raise errors[0]
    if code == 0:
        return
    if code == 1:
        raise ValueError('Hair smoothing rejected dimensions, layout, alignment or aliased buffers')
    if code == 2:
        raise ValueError('Hair smoothing needs finite SDR pixels, owned context and bounded settings')
    if code == 3:
        raise HairSmoothingScaleError('Observed hair texture scale must be 1..8 native source pixels')
    if code == 4:
        raise HairSmoothingContextError('No complete owned unprotected source dependency halo; no inferred context')
    if code == 5:
        raise MemoryError('Hair smoothing memory admission refused; no proxy or smaller-scale fallback')
    if code == 6:
        raise InterruptedError('Hair smoothing canceled; private result discarded')
    if code in (7, 8):
        raise RuntimeError('Hair smoothing numerical failure or contained panic; private result discarded')
    raise RuntimeError('Unknown hair smoothing status; private result discarded')
