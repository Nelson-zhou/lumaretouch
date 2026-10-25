# SPDX-License-Identifier: GPL-3.0-or-later
"""Checked independent Rust ABI, without compile/download/algorithm fallback."""
import ctypes as C
from dataclasses import dataclass
from functools import lru_cache
import math
import os
from pathlib import Path
import numpy as np
from . import hair_unification_state as S

P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_uint32, C.c_void_p)
MAX_PIXELS = 64_000_000
MAX_TILE_PIXELS = 262_144
SCRATCH_BYTES = 8 * 1024 * 1024


class Limits(C.Structure):
    _fields_ = [(key, C.c_uint64) for key in ('max_source_pixels', 'max_tile_pixels', 'max_work_units', 'max_working_bytes')]


class Reference(C.Structure):
    _fields_ = [('abi_version', C.c_uint32), ('struct_size', C.c_uint32), ('direction', C.c_int32),
                ('reserved', C.c_uint32), ('source_width', C.c_uint32), ('source_height', C.c_uint32),
                ('selected_pixels', C.c_uint64), ('reliable_pixels', C.c_uint64),
                ('selected_weight', C.c_double), ('reliable_weight', C.c_double),
                ('effective_samples', C.c_double), ('retained_fraction', C.c_double),
                ('dispersion', C.c_double), ('chroma_ratio', C.c_double * 3)]


@dataclass(frozen=True)
class MeasuredReference:
    direction: int
    source_width: int
    source_height: int
    selected_pixels: int
    reliable_pixels: int
    selected_weight: float
    reliable_weight: float
    effective_samples: float
    retained_fraction: float
    dispersion: float
    chroma_ratio: tuple

    def checked(self):
        if (self.direction not in (-1, 1) or min(self.source_width, self.source_height) < 1
                or max(self.source_width, self.source_height) > 65536
                or self.source_width * self.source_height > MAX_PIXELS
                or not 32 <= self.reliable_pixels <= self.selected_pixels <= self.source_width * self.source_height):
            raise ValueError('Invalid measured hair reference dimensions/support')
        numbers = (self.selected_weight, self.reliable_weight, self.effective_samples,
                   self.retained_fraction, self.dispersion, *self.chroma_ratio)
        if (len(self.chroma_ratio) != 3 or any(not math.isfinite(v) for v in numbers)
                or not 16 <= self.selected_weight <= self.selected_pixels + 1e-8
                or not 16 <= self.reliable_weight <= self.selected_weight + 1e-8
                or self.reliable_weight / self.selected_weight < .25
                or self.effective_samples + 1e-9 < 32
                or self.effective_samples > self.reliable_pixels + 1e-7
                or not .7 <= self.retained_fraction <= 1 + 1e-12 or not 0 <= self.dispersion <= .06):
            raise ValueError('Invalid measured hair reference reliability')
        coefficients = (.2126, .7152, .0722)
        if (any(not -1 - 1e-12 <= q <= 1 / c - 1 + 1e-12 for q, c in zip(self.chroma_ratio, coefficients))
                or abs(sum(q*c for q, c in zip(self.chroma_ratio, coefficients))) > 1e-8):
            raise ValueError('Invalid normalized linear hair reference chroma')
        return self

    def abi(self):
        self.checked()
        return Reference(1, C.sizeof(Reference), self.direction, 0, self.source_width, self.source_height,
            self.selected_pixels, self.reliable_pixels, self.selected_weight, self.reliable_weight,
            self.effective_samples, self.retained_fraction, self.dispersion, (C.c_double * 3)(*self.chroma_ratio))


@lru_cache(maxsize=1)
def _library():
    path = Path(__file__).resolve().parent / 'bin/liblrt_hair_unification.so'
    if not path.is_file():
        raise RuntimeError('头发统一 Rust 核心未安装；不会替换为染发或伪造成功')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_hair_unification_abi.argtypes = []; lib.lrt_hair_unification_abi.restype = C.c_uint32
        if lib.lrt_hair_unification_abi() != 1 or C.sizeof(Reference) != 104:
            raise RuntimeError('Hair-unification native ABI mismatch')
        lib.lrt_hair_unification_measure_v1.argtypes = [P, C.c_uint64, P, C.c_uint64, P, C.c_uint64,
            P, C.c_uint64, C.c_uint32, C.c_uint32, C.c_float, C.POINTER(Limits), C.POINTER(Reference), CANCEL, C.c_void_p]
        lib.lrt_hair_unification_measure_v1.restype = C.c_int32
        lib.lrt_hair_unification_compose_v1.argtypes = [P, C.c_uint64, P, C.c_uint64,
            C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32, C.c_float, C.POINTER(Reference),
            C.POINTER(Limits), P, C.c_uint64, CANCEL, C.c_void_p]
        lib.lrt_hair_unification_compose_v1.restype = C.c_int32
        return lib
    except (OSError, AttributeError) as error:
        raise RuntimeError('Hair-unification required native symbols cannot load') from error


def native():
    if os.environ.get('LNX_DISABLE_HAIR_UNIFICATION') == '1':
        raise RuntimeError('Hair-unification module is disabled')
    return _library()


def available():
    try:
        native(); return True
    except (RuntimeError, OSError, AttributeError):
        return False


def _callback(cancelled):
    errors = []
    def poll(_):
        try:
            return int(bool(errors) or bool(cancelled()))
        except BaseException as error:
            errors.append(error); return 1
    return CANCEL(poll), errors


def _result(status, errors, cancelled):
    if errors: raise errors[0]
    if status == 4 or cancelled(): raise InterruptedError('Hair unification cancelled; private output discarded')
    if status:
        messages = {1: 'ABI/length/alias mismatch', 2: 'invalid values', 3: 'resource budget exceeded',
            5: 'allocation refused', 6: 'native panic contained', 7: 'insufficient reliable selected reference',
            8: 'overlapping or chromatically ambiguous reference', 9: 'numerical result refused'}
        raise ValueError('Hair unification refused: ' + messages.get(status, str(status)))


def _array(value, shape, label):
    if (type(value) is not np.ndarray or value.dtype != np.float32 or value.shape != shape
            or not value.flags.c_contiguous or not np.isfinite(value).all()
            or np.any(value < 0) or np.any(value > 1)):
        raise ValueError(label + ' must be contiguous finite source-frame float32 SDR')


def measure(source, hair, roots, tips, recipe, *, byte_budget, cancelled=lambda: False):
    recipe = S.check(recipe)
    if not S.active(recipe): return None
    if type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3:
        raise ValueError('Hair unification needs actual immutable source RGB')
    h, w = source.shape[:2]
    if min(h, w) < 1 or max(h, w) > 65536 or h*w > MAX_PIXELS:
        raise ValueError('Hair-unification source dimensions exceed admission')
    if type(byte_budget) is not int or byte_budget < h*w*24 + SCRATCH_BYTES:
        raise MemoryError('Hair-unification source measurement exceeds admitted memory')
    _array(source, (h, w, 3), 'Source RGB')
    for mask in (hair, roots, tips): _array(mask, (h, w), 'Owned hair/sample mask')
    if np.any(roots > hair) or np.any(tips > hair) or np.any((roots > 0) & (tips > 0)):
        raise ValueError('Root/tip samples must be disjoint subsets of reviewed real hair')
    source = np.array(source, dtype=np.float32, order='C', copy=True)
    hair, roots, tips = (np.array(mask, dtype=np.float32, order='C', copy=True) for mask in (hair, roots, tips))
    for array in (source, hair, roots, tips): array.setflags(write=False)
    if cancelled(): raise InterruptedError('Hair-unification measurement cancelled')
    reference = Reference(); callback, errors = _callback(cancelled)
    limits = Limits(MAX_PIXELS, MAX_TILE_PIXELS, 1_000_000_000, SCRATCH_BYTES)
    status = native().lrt_hair_unification_measure_v1(source.ctypes.data_as(P), source.size,
        hair.ctypes.data_as(P), hair.size, roots.ctypes.data_as(P), roots.size, tips.ctypes.data_as(P), tips.size,
        w, h, recipe['amount'], C.byref(limits), C.byref(reference), callback, None)
    _result(status, errors, cancelled)
    if reference.abi_version != 1 or reference.struct_size != 104 or reference.reserved != 0:
        raise RuntimeError('Hair-unification returned an incompatible measured reference')
    return MeasuredReference(reference.direction, reference.source_width, reference.source_height,
        reference.selected_pixels, reference.reliable_pixels, reference.selected_weight, reference.reliable_weight,
        reference.effective_samples, reference.retained_fraction, reference.dispersion,
        tuple(reference.chroma_ratio)).checked()


def compose(current, coverage, reference, recipe, *, origin=(0, 0), cancelled=lambda: False):
    """Tile pointwise only: full-source reference already measured and authenticated."""
    recipe = S.check(recipe)
    if not S.active(recipe): return current
    if not isinstance(reference, MeasuredReference): raise ValueError('Missing actual measured hair reference')
    ref = reference.abi()
    if type(current) is not np.ndarray or current.ndim != 3 or current.shape[2] != 3:
        raise ValueError('Hair-unification composition needs current RGB')
    h, w = current.shape[:2]; x, y = origin
    if (type(x) is not int or type(y) is not int or min(x, y) < 0 or min(h, w) < 1
            or h*w > MAX_TILE_PIXELS or x+w > ref.source_width or y+h > ref.source_height):
        raise ValueError('Hair-unification tile differs from measured full-source coordinates')
    _array(current, (h, w, 3), 'Current RGB'); _array(coverage, (h, w), 'Owned target coverage')
    current = np.array(current, dtype=np.float32, order='C', copy=True)
    coverage = np.array(coverage, dtype=np.float32, order='C', copy=True)
    current.setflags(write=False); coverage.setflags(write=False)
    if cancelled(): raise InterruptedError('Hair-unification composition cancelled')
    output = np.empty_like(current); callback, errors = _callback(cancelled)
    limits = Limits(MAX_PIXELS, MAX_TILE_PIXELS, 1_000_000_000, SCRATCH_BYTES)
    status = native().lrt_hair_unification_compose_v1(current.ctypes.data_as(P), current.size,
        coverage.ctypes.data_as(P), coverage.size, x, y, w, h, recipe['amount'], C.byref(ref), C.byref(limits),
        output.ctypes.data_as(P), output.size, callback, None)
    _result(status, errors, cancelled)
    if not np.isfinite(output).all() or np.any((output < 0) | (output > 1)):
        raise RuntimeError('Hair-unification returned invalid current RGB')
    if not np.array_equal(output[coverage == 0].view(np.uint32), current[coverage == 0].view(np.uint32)):
        raise RuntimeError('Hair-unification changed protected/zero-coverage pixels')
    for row in range(h):
        before, after = current[row].astype(np.float64), output[row].astype(np.float64)
        before = np.where(before <= .04045, before/12.92, ((before+.055)/1.055)**2.4)
        after = np.where(after <= .04045, after/12.92, ((after+.055)/1.055)**2.4)
        if np.any(np.abs((before-after) @ np.array((.2126, .7152, .0722))) > 2e-7):
            raise RuntimeError('Hair-unification changed current linear luminance')
    return output
