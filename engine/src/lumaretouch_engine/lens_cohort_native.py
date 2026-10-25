# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit ABI-2 cohort lens bridge. AUTHORED / UNRUN.

Only immutable, canonical little-endian f32 opaque-SDR source bytes are accepted.
The original ABI-1 bridge is neither imported nor used as a fallback. No NumPy,
full-source snapshot, inference, runtime build or document mutation occurs here.
"""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import sys
from types import MappingProxyType
from typing import Mapping

ABI = 2
MATH_IDENTITY = 0x00020001
ENCODING = 'linear-srgb-d65'
DEPTH_CONVENTION = 'near-zero-far-one'
APERTURES = ('circular_disk', 'rim_weighted_disk', 'regular_pentagon',
             'regular_octagon', 'cat_eye_intersection')
MAX_SOURCE_PIXELS = 100_000_000
TILE_SIDE = 254
MAX_DIRECT_PAIRS = 250_000_000
MAX_FFT_BUTTERFLIES = 24_000_000_000
DEFAULT_NATIVE_SCRATCH_BYTES = 256 * 1024**2
DEFAULT_MAX_LIVE_BYTES = 6 * 1024**3
# Separate from the native planner's own allowance. These are admission
# allowances, not measured allocator/RSS counters or process-wide guarantees.
PYTHON_OVERHEAD_ALLOWANCE_BYTES = 1024**2
DEFAULT_WORK_BUDGETS = MappingProxyType({
    'max_fft_butterflies': MAX_FFT_BUTTERFLIES,
    'max_kernel_quadrature_evals': 32_000_000_000,
    'max_classification_pixels': 4_000_000_000,
    'max_support_probes': 800_000_000,
    'max_direct_pairs': MAX_DIRECT_PAIRS,
    'reserved_repair_pairs': 8_388_608,
})
_SCALAR_FIELDS = ('max_radius_px', 'focus_near', 'focus_far', 'depth_falloff',
                  'occlusion_tolerance', 'rotation_radians')
_SETTING_KEYS = frozenset(('version', 'aperture', *_SCALAR_FIELDS))
_BUDGET_FIELDS = (*DEFAULT_WORK_BUDGETS, 'max_scratch_bytes', 'max_sink_bytes')
_PLAN_COUNTS = (
    'width', 'height', 'source_pixels', 'validation_pixels',
    'classification_pixels', 'repeated_halo_classification_pixels',
    'tile_width', 'tile_height', 'tile_columns', 'tile_count', 'fft_width',
    'fft_height', 'kernel_quadrature_evals', 'fft_transform_count',
    'fft_butterflies', 'residual_emitters', 'residual_candidate_pairs',
    'residual_quadrature_upper_bound', 'support_probe_upper_bound',
    'repair_candidate_reservation', 'direct_pair_upper_bound',
    'owned_plan_bytes', 'required_scratch_bytes', 'borrowed_source_bytes',
    'borrowed_refinement_bytes', 'sink_bytes', 'output_tile_bytes',
)
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int32, C.c_void_p)


class LensCohortUnavailable(RuntimeError):
    """Disabled/missing/incompatible implementation; never replace saved intent."""


class LensCohortRejected(ValueError):
    def __init__(self, code: int):
        self.code = code
        detail = {
            1: 'ABI, buffer extent, alignment or overlap',
            2: 'aperture settings or explicit manual constant depth',
            3: 'unsupported pixels: requires opaque SDR and valid refinement',
            6: 'contained native panic',
            7: 'numerical result did not pass the declared arithmetic checks',
            8: 'ordered job lifecycle violation',
        }.get(code, 'unknown native status')
        super().__init__(f'Lens cohort refused {detail} ({code}); no result published')


class NativeSettings(C.Structure):
    _fields_ = [('abi_version', C.c_uint32), ('struct_size', C.c_uint32),
                ('aperture', C.c_uint32)] + [
                    (name, C.c_float) for name in (*_SCALAR_FIELDS, 'manual_depth')
                ] + [('manual_depth_ack', C.c_uint32)]


class NativeBudget(C.Structure):
    _fields_ = [('abi_version', C.c_uint32), ('struct_size', C.c_uint32)] + [
        (name, C.c_uint64) for name in _BUDGET_FIELDS]


class NativePlan(C.Structure):
    _fields_ = [('abi_version', C.c_uint32), ('struct_size', C.c_uint32),
                ('math_identity', C.c_uint32), ('non_delta_cohort_count', C.c_uint32)] + [
                    (name, C.c_uint64) for name in _PLAN_COUNTS]


@dataclass(frozen=True)
class CohortResult:
    """An unpublished derived candidate, not a document/history commit.

    Plan values are exact derived counts or explicitly named upper bounds and
    reservations. Neither plan nor memory values are measured timing/RSS.
    """
    rgba: bytes
    width: int
    height: int
    plan: Mapping[str, int]
    memory: Mapping[str, int]
    abi: int = ABI
    math_identity: int = MATH_IDENTITY


def _integer(value, name, *, minimum=0, maximum=(1 << 64) - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} requires an integer in [{minimum},{maximum}]')
    return value


def _extent(width, height):
    _integer(width, 'width', minimum=1)
    _integer(height, 'height', minimum=1)
    pixels = width * height
    if pixels > MAX_SOURCE_PIXELS:
        raise MemoryError('Lens cohort source exceeds 100 million pixels; no proxy fallback')
    return pixels


def _number(value, name):
    if type(value) not in (int, float):
        raise ValueError(name + ' requires a finite JSON number, not a boolean')
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(name + ' is outside the finite numeric range') from error
    if not math.isfinite(result):
        raise ValueError(name + ' requires a finite number')
    return result


def normalize_settings(value):
    """Same version-1 scalar dictionary, NOT authorization to migrate a recipe.

    The host must explicitly select the version-2 render recipe. Keeping the
    scalar vocabulary does not assert ABI-1 pixel identity or inspect old recipes.
    """
    if type(value) is not dict or set(value) != _SETTING_KEYS:
        raise ValueError('Lens cohort requires the exact version-1 scalar setting keys')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Unknown scalar settings version; saved intent was not changed')
    if type(value['aperture']) is not str or value['aperture'] not in APERTURES:
        raise ValueError('Unknown original aperture; no substitute was selected')
    result = {'version': 1, 'aperture': value['aperture']}
    result.update((key, _number(value[key], key)) for key in _SCALAR_FIELDS)
    if not 0 <= result['max_radius_px'] <= 128:
        raise ValueError('Lens radius must be in [0,128] source-grid pixels')
    if not 0 <= result['focus_near'] <= result['focus_far'] <= 1:
        raise ValueError('Lens focus requires 0 <= near <= far <= 1')
    if not 0.000001 <= result['depth_falloff'] <= 1:
        raise ValueError('Lens depth falloff must be in [0.000001,1]')
    if not 0 <= result['occlusion_tolerance'] <= 1:
        raise ValueError('Lens occlusion tolerance must be in [0,1]')
    if not -math.pi <= result['rotation_radians'] <= math.pi:
        raise ValueError('Lens rotation must be in [-pi,pi] radians')
    return result


def _normalize_budgets(value):
    if type(value) is not dict or set(value) != set(_BUDGET_FIELDS):
        raise ValueError('Lens cohort requires every explicit native work/memory budget')
    result = {name: _integer(value[name], name) for name in _BUDGET_FIELDS}
    if result['max_fft_butterflies'] > MAX_FFT_BUTTERFLIES:
        raise ValueError('FFT budget exceeds the native hard ceiling')
    if not result['reserved_repair_pairs'] <= result['max_direct_pairs'] <= MAX_DIRECT_PAIRS:
        raise ValueError('Repair reservation must fit the direct-pair hard ceiling')
    return result


def default_budgets(width, height, *, max_scratch_bytes=DEFAULT_NATIVE_SCRATCH_BYTES,
                    reserved_repair_pairs=8_388_608):
    """Pure opt-in ceilings, not a feasibility, image-quality or runtime promise.

    Callers still pass the returned dictionary AND max_live_bytes to render.
    Pixel-dependent planning and unsupported-source checks happen in create.
    """
    pixels = _extent(width, height)
    result = dict(DEFAULT_WORK_BUDGETS)
    result.update(max_support_probes=8 * pixels,
                  reserved_repair_pairs=reserved_repair_pairs,
                  max_scratch_bytes=max_scratch_bytes, max_sink_bytes=16 * pixels)
    return _normalize_budgets(result)


def memory_estimate(width, height, *, with_refinement=False,
                    native_scratch_bytes=DEFAULT_NATIVE_SCRATCH_BYTES):
    """Pure phase-aware payload arithmetic plus an explicitly named allowance.

    Source/refinement are retained, never duplicated. Native scratch includes
    the native plan and its own allowance. The tile and native job are destroyed
    before the one unavoidable bytearray-to-bytes copy. Other live documents,
    original/ICC/display caches and concurrency must be admitted by the host.
    """
    pixels = _extent(width, height)
    if type(with_refinement) is not bool:
        raise ValueError('with_refinement must be a boolean')
    _integer(native_scratch_bytes, 'native_scratch_bytes')
    source = pixels * 16
    refinement = pixels * 4 if with_refinement else 0
    retained = source + refinement
    tile = min(width, TILE_SIDE) * min(height, TILE_SIDE) * 16
    overhead = PYTHON_OVERHEAD_ALLOWANCE_BYTES
    create = retained + native_scratch_bytes + overhead
    rendering = retained + source + tile + native_scratch_bytes + overhead
    conversion = retained + 2 * source + overhead
    return {
        'borrowed_source_bytes': source, 'borrowed_refinement_bytes': refinement,
        'borrowed_input_bytes': retained, 'source_copy_bytes': 0,
        'private_sink_bytes': source, 'final_bytes_copy_bytes': source,
        'output_tile_bytes': tile, 'native_scratch_bytes': native_scratch_bytes,
        'python_overhead_allowance_bytes': overhead,
        'create_peak_bytes': create, 'render_peak_bytes': rendering,
        'freeze_peak_bytes': conversion,
        'peak_live_bytes': max(create, rendering, conversion),
        'additional_peak_bytes': max(create, rendering, conversion) - retained,
    }


def _host_support():
    if sys.implementation.name != 'cpython' or sys.byteorder != 'little':
        raise LensCohortUnavailable('Lens cohort requires little-endian CPython borrowed bytes')
    if (C.sizeof(C.c_float) != 4 or C.sizeof(C.c_size_t) != 8
            or C.sizeof(NativeSettings) != 44 or C.sizeof(NativeBudget) != 72
            or C.sizeof(NativePlan) != 232 or C.alignment(C.c_uint64) != 8):
        raise LensCohortUnavailable('Lens cohort C ABI layout is unsupported')


@lru_cache(maxsize=1)
def _query_runtime():
    """Load only the fixed packaged artifact, only on an explicit query/render."""
    _host_support()
    package = Path(__file__).resolve().parent
    path = package / 'bin' / 'liblrt_lens_cohort.so'
    try:
        # No alternate library search and no symlink escape to an external build.
        if not path.is_file() or path.resolve().parent != (package / 'bin').resolve():
            raise LensCohortUnavailable('Packaged lens cohort module is not installed; no fallback')
        if (package / 'bin').resolve().parent != package:
            raise LensCohortUnavailable('Lens cohort package bin directory must remain inside the package')
        lib = C.CDLL(str(path))
        lib.lrt_lens_cohort_abi.argtypes = []
        lib.lrt_lens_cohort_abi.restype = C.c_uint32
        lib.lrt_lens_cohort_math_identity.argtypes = []
        lib.lrt_lens_cohort_math_identity.restype = C.c_uint32
        if (lib.lrt_lens_cohort_abi() != ABI
                or lib.lrt_lens_cohort_math_identity() != MATH_IDENTITY):
            raise LensCohortUnavailable('Lens cohort ABI/math identity mismatch; no downgrade')
        lib.lrt_lens_cohort_create_v2.argtypes = [P, C.c_size_t, P, C.c_size_t,
            C.c_size_t, C.c_size_t, NativeSettings, NativeBudget,
            C.POINTER(C.c_void_p), C.POINTER(NativePlan), CANCEL, C.c_void_p]
        lib.lrt_lens_cohort_create_v2.restype = C.c_int32
        lib.lrt_lens_cohort_render_next_v2.argtypes = [
            C.c_void_p, C.c_uint64, P, C.c_size_t, CANCEL, C.c_void_p]
        lib.lrt_lens_cohort_render_next_v2.restype = C.c_int32
        lib.lrt_lens_cohort_finish_v2.argtypes = [C.c_void_p]
        lib.lrt_lens_cohort_finish_v2.restype = C.c_int32
        lib.lrt_lens_cohort_destroy_v2.argtypes = [C.c_void_p]
        lib.lrt_lens_cohort_destroy_v2.restype = None
    except (OSError, AttributeError) as error:
        raise LensCohortUnavailable('Packaged lens cohort ABI could not be loaded') from error
    return lib


def capability(*, enabled=True):
    if type(enabled) is not bool:
        raise ValueError('enabled must be a boolean')
    reason = None
    if not enabled:
        reason = 'Module explicitly disabled'
    else:
        try:
            _query_runtime()
        except LensCohortUnavailable as error:
            reason = str(error)
    return {'available': reason is None, 'reason': reason, 'abi': ABI,
            'math_identity': MATH_IDENTITY, 'kernels': APERTURES if reason is None else (),
            'quality_status': 'authored_unrun', 'input_scope': 'opaque_sdr_manual_constant_depth'}


@dataclass(frozen=True)
class _BorrowedBytes:
    owner: bytes
    pointer: object
    float_count: int


def _borrow(value, byte_count, label):
    if type(value) is not bytes or len(value) != byte_count:
        raise ValueError(label + ' requires exact immutable canonical bytes and full-grid length')
    # PyBytes_AsString is CPython's documented borrowed pointer. c_void_p is
    # intentional: c_char_p restype would manufacture/truncate a Python copy.
    # The owner is strongly held until after destroy, including GIL-releasing
    # CDLL calls and callback exceptions. No writable Python alias is created.
    # A private PYFUNCTYPE wrapper avoids mutating pythonapi's cached function
    # prototype, and keeps the GIL for this borrowed-address lookup.
    function = C.PYFUNCTYPE(C.c_void_p, C.py_object)(('PyBytes_AsString', C.pythonapi))
    address = function(value)
    if not address or address % C.alignment(C.c_float):
        raise LensCohortUnavailable('CPython source bytes are not suitably aligned for this ABI')
    return _BorrowedBytes(value, C.cast(address, P), byte_count // 4)


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Lens cohort cancelled; all private output discarded')


def _callback(cancelled):
    errors = []
    def check(_context):
        if errors:
            return 1
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1
    return CANCEL(check), errors


def _status(code, cancelled, errors):
    if errors:
        raise errors[0]
    if code == 4:
        raise InterruptedError('Lens cohort cancelled; all private output discarded')
    if code == 5:
        raise MemoryError('Lens cohort work/memory admission refused; no quality reduction')
    if code:
        raise LensCohortRejected(int(code))
    _poll(cancelled)


def _verify_plan(plan, width, height, refinement, budgets):
    pixels = width * height
    tw, th = min(width, TILE_SIDE), min(height, TILE_SIDE)
    columns, rows = (width + tw - 1) // tw, (height + th - 1) // th
    exact = {
        'abi_version': ABI, 'struct_size': C.sizeof(NativePlan),
        'math_identity': MATH_IDENTITY, 'width': width, 'height': height,
        'source_pixels': pixels, 'validation_pixels': pixels,
        'tile_width': tw, 'tile_height': th, 'tile_columns': columns,
        'tile_count': columns * rows, 'borrowed_source_bytes': pixels * 16,
        'borrowed_refinement_bytes': pixels * 4 if refinement is not None else 0,
        'sink_bytes': pixels * 16, 'output_tile_bytes': tw * th * 16,
        'repair_candidate_reservation': budgets['reserved_repair_pairs'],
    }
    if any(int(getattr(plan, name)) != value for name, value in exact.items()):
        raise LensCohortUnavailable('Lens cohort returned an incompatible full-source plan')
    bounded = {
        'fft_butterflies': 'max_fft_butterflies',
        'kernel_quadrature_evals': 'max_kernel_quadrature_evals',
        'classification_pixels': 'max_classification_pixels',
        'support_probe_upper_bound': 'max_support_probes',
        'direct_pair_upper_bound': 'max_direct_pairs',
        'required_scratch_bytes': 'max_scratch_bytes', 'sink_bytes': 'max_sink_bytes',
    }
    if (any(int(getattr(plan, count)) > budgets[limit] for count, limit in bounded.items())
            or plan.owned_plan_bytes > plan.required_scratch_bytes
            or plan.non_delta_cohort_count > 2
            or plan.residual_emitters > pixels
            or plan.direct_pair_upper_bound != (
                plan.residual_candidate_pairs + plan.repair_candidate_reservation)):
        raise LensCohortUnavailable('Lens cohort plan violates admitted resource bounds')
    return {name: int(getattr(plan, name)) for name, _kind in NativePlan._fields_}


def render(source_rgba, width, height, settings, *, manual_depth,
           manual_depth_acknowledged, budgets, max_live_bytes, refinement=None,
           encoding=ENCODING, premultiplied=True, depth_convention=DEPTH_CONVENTION,
           enabled=True, cancelled=lambda: False):
    """Return canonical private bytes only after every tile and finish succeed.

    manual_depth is the actual retained constant-u16-plane value / 65535,
    rounded to f32 here, not the pre-quantized UI slider. The host authenticates
    that provenance and the user's explicit manual-depth acknowledgement.
    There is no AI/depth inference, changing-depth path or version-1 fallback.

    max_live_bytes bounds this job's retained input plus phase-aware allocations
    and named allowances, not total process RSS. Create validates the ENTIRE
    source/refinement and plans all work before any private sink/tile allocation.
    Cancellation, any error or failed finish destroys the job and discards the
    candidate. No partial sink, mutable pointer, or document write is published.
    """
    normalized = normalize_settings(settings)
    pixels = _extent(width, height)
    limits = _normalize_budgets(budgets)
    _integer(max_live_bytes, 'max_live_bytes', minimum=1)
    depth = _number(manual_depth, 'manual_depth')
    if not 0 <= depth <= 1 or manual_depth_acknowledged is not True:
        raise ValueError('Explicitly acknowledged manual constant depth in [0,1] is required')
    if (type(encoding) is not str or encoding != ENCODING or premultiplied is not True
            or type(depth_convention) is not str or depth_convention != DEPTH_CONVENTION):
        raise ValueError('Lens cohort requires canonical linear-sRGB-D65 premultiplied RGBA')
    if type(enabled) is not bool:
        raise ValueError('enabled must be a boolean')
    if not enabled:
        raise LensCohortUnavailable('Lens cohort explicitly disabled; preserve saved recipe')
    if not callable(cancelled):
        raise TypeError('cancelled must be callable')
    if type(source_rgba) is not bytes or len(source_rgba) != pixels * 16:
        raise ValueError('Source requires immutable canonical bytes for the exact full grid')
    if refinement is not None and (type(refinement) is not bytes or len(refinement) != pixels * 4):
        raise ValueError('Refinement requires immutable canonical bytes for the exact full grid')
    _poll(cancelled)
    admission = memory_estimate(width, height, with_refinement=refinement is not None,
                                native_scratch_bytes=limits['max_scratch_bytes'])
    if (limits['max_sink_bytes'] < pixels * 16
            or max(admission['create_peak_bytes'], admission['freeze_peak_bytes']) > max_live_bytes):
        raise MemoryError('Lens cohort retained inputs/create/final-copy peak exceeds host admission')
    _host_support()
    lib = _query_runtime()
    source = _borrow(source_rgba, pixels * 16, 'Source')
    correction = None if refinement is None else _borrow(refinement, pixels * 4, 'Refinement')
    native_settings = NativeSettings(ABI, C.sizeof(NativeSettings),
        APERTURES.index(normalized['aperture']),
        *(normalized[name] for name in _SCALAR_FIELDS), depth, 1)
    native_budget = NativeBudget(ABI, C.sizeof(NativeBudget),
                                 *(limits[name] for name in _BUDGET_FIELDS))
    callback, errors = _callback(cancelled)
    job, native_plan = C.c_void_p(), NativePlan()
    sink = tile = sink_alias = None
    try:
        code = lib.lrt_lens_cohort_create_v2(
            source.pointer, source.float_count,
            P() if correction is None else correction.pointer,
            0 if correction is None else correction.float_count,
            width, height, native_settings, native_budget,
            C.byref(job), C.byref(native_plan), callback, None)
        _status(code, cancelled, errors)
        if not job.value:
            raise LensCohortUnavailable('Lens cohort create did not return a live job')
        plan = _verify_plan(native_plan, width, height, refinement, limits)
        memory = memory_estimate(width, height, with_refinement=refinement is not None,
                                 native_scratch_bytes=plan['required_scratch_bytes'])
        memory['create_admission_peak_bytes'] = admission['create_peak_bytes']
        memory['host_max_live_bytes'] = max_live_bytes
        if memory['peak_live_bytes'] > max_live_bytes:
            raise MemoryError('Lens cohort planned render/final-copy peak exceeds host admission')
        # One full mutable output, one bounded tile, and a zero-copy private
        # ctypes view. Never use from_buffer_copy or an ndarray source snapshot.
        sink = bytearray(plan['sink_bytes'])
        sink_alias = (C.c_ubyte * len(sink)).from_buffer(sink)
        tile = (C.c_float * (plan['output_tile_bytes'] // 4))()
        tile_address, sink_address = C.addressof(tile), C.addressof(sink_alias)
        copied = 0
        for index in range(plan['tile_count']):
            _poll(cancelled)
            x = (index % plan['tile_columns']) * plan['tile_width']
            y = (index // plan['tile_columns']) * plan['tile_height']
            tw, th = min(plan['tile_width'], width - x), min(plan['tile_height'], height - y)
            code = lib.lrt_lens_cohort_render_next_v2(
                job, index, tile, tw * th * 4, callback, None)
            _status(code, cancelled, errors)
            for row in range(th):
                _poll(cancelled)
                count = tw * 16
                C.memmove(sink_address + ((y + row) * width + x) * 16,
                          tile_address + row * count, count)
                copied += count
        if copied != plan['sink_bytes']:
            raise RuntimeError('Lens cohort tiles did not cover the exact source grid')
        _status(lib.lrt_lens_cohort_finish_v2(job), cancelled, errors)
    finally:
        # source/correction and callback remain strongly referenced throughout.
        # Even failed postchecks, allocation, polling or finish release the job.
        if job.value:
            lib.lrt_lens_cohort_destroy_v2(job)
            job.value = None
        tile = sink_alias = None
    _poll(cancelled)
    rgba = bytes(sink)  # Peak explicitly includes sink + this immutable copy.
    sink = None
    _poll(cancelled)
    memory['tiles_completed'] = plan['tile_count']
    memory['tile_payload_bytes_copied'] = copied
    return CohortResult(rgba, width, height, MappingProxyType(plan), MappingProxyType(memory))
