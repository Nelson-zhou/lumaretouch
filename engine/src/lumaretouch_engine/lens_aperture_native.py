# SPDX-License-Identifier: GPL-3.0-or-later
"""Original ABI-1 lens aperture numeric bridge. AUTHORED / UNRUN.

No module-import NumPy/native loading, compiler, model, download, pixel fallback,
recipe migration, document mutation or partial-result publication. The host owns
source/depth identities and atomic derived/history publication after this returns.
"""
from __future__ import annotations

import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

ABI = 1
ENCODING = 'linear-srgb-d65'
DEPTH_CONVENTION = 'near-zero-far-one'
APERTURES = ('circular_disk', 'rim_weighted_disk', 'regular_pentagon',
             'regular_octagon', 'cat_eye_intersection')
MAX_SOURCE_PIXELS = 100_000_000
MAX_TILE_PIXELS = 65_536
MAX_RADIUS_PX = 128.0
MAX_CANDIDATE_TAPS = 8_388_608
MAX_WORKING_BYTES = 6 * 1024**3
SCRATCH_ALLOWANCE_BYTES = 16 * 1024**2
COPY_PIXELS = 4096
HDR_STRAIGHT_LIMIT = 65_504.0
_FIELDS = ('max_radius_px', 'focus_near', 'focus_far', 'depth_falloff',
           'occlusion_tolerance', 'rotation_radians')
_KEYS = frozenset(('version', 'aperture', *_FIELDS))
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int32, C.c_void_p)


class LensApertureUnavailable(RuntimeError):
    """Missing/disabled/incompatible native module; saved intent must survive."""


class LensApertureRejected(ValueError):
    def __init__(self, code: int):
        self.code = code
        details = {1: 'invalid ABI, lengths, tile bounds or buffer overlap',
                   2: 'invalid aperture, focus, radius or visibility settings',
                   3: 'invalid RGBA, relative depth or refinement pixels',
                   6: 'contained native panic',
                   7: 'result violates finite premultiplied HDR bounds'}
        super().__init__('Lens aperture refused: ' + details.get(code, 'unknown native status')
                         + f' ({code}); no result was published')


class NativeSettings(C.Structure):
    _fields_ = [('aperture', C.c_uint32)] + [(name, C.c_float) for name in _FIELDS]


def normalize_settings(value):
    """Strict ABI-1 numeric intent; return a fresh dict without changing saved input.

    Unknown versions/keys/kernels are rejected, never reset to a default. JSON
    numbers are checked before conversion; ctypes rounds controls to native f32
    only when making a native request. No source/depth data belongs in this dict.
    """
    if type(value) is not dict or set(value) != _KEYS:
        raise ValueError('Lens aperture requires the exact version-1 setting keys')
    if type(value['version']) is not int or value['version'] != ABI:
        raise ValueError('Unsupported lens aperture recipe version; preserve saved intent')
    if type(value['aperture']) is not str or value['aperture'] not in APERTURES:
        raise ValueError('Unknown original aperture kernel; no substitute was selected')
    result = {'version': ABI, 'aperture': value['aperture']}
    for name in _FIELDS:
        number = value[name]
        if type(number) not in (int, float):
            raise ValueError(name + ' requires a finite JSON number, not a boolean')
        try:
            number = float(number)
        except (OverflowError, ValueError) as error:
            raise ValueError(name + ' is outside the finite numeric range') from error
        if not math.isfinite(number):
            raise ValueError(name + ' requires a finite number')
        result[name] = number
    if not 0 <= result['max_radius_px'] <= MAX_RADIUS_PX:
        raise ValueError('Lens radius must be in [0,128] source-grid pixels')
    if not 0 <= result['focus_near'] <= result['focus_far'] <= 1:
        raise ValueError('Lens focus requires 0 <= near <= far <= 1')
    if not 0.000001 <= result['depth_falloff'] <= 1:
        raise ValueError('Lens depth falloff must be in [0.000001,1]')
    if not 0 <= result['occlusion_tolerance'] <= 1:
        raise ValueError('Lens occlusion tolerance must be in [0,1]')
    if not -math.pi <= result['rotation_radians'] <= math.pi:
        raise ValueError('Lens aperture rotation must be in [-pi,pi] radians')
    return result


def _native_settings(settings):
    return NativeSettings(APERTURES.index(settings['aperture']),
                          *(settings[name] for name in _FIELDS))


@lru_cache(maxsize=1)
def _query_runtime():
    """An explicit runtime availability query; successful handles remain resident.

    This is never called at module import. Failure is not cached, but no runtime
    build, installation, download, ABI downgrade or alternative DLL search occurs.
    """
    path = Path(__file__).resolve().parent / 'bin' / 'liblrt_lens_aperture.so'
    try:
        present = path.is_file()
    except OSError as error:
        raise LensApertureUnavailable('Cannot inspect the packaged lens aperture artifact') from error
    if not present:
        raise LensApertureUnavailable('Lens aperture Rust module is not installed; no fallback')
    if C.sizeof(NativeSettings) != 28 or C.alignment(NativeSettings) != C.alignment(C.c_float):
        raise LensApertureUnavailable('Lens aperture C settings layout is unsupported')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_lens_aperture_abi.argtypes = []
        lib.lrt_lens_aperture_abi.restype = C.c_uint32
        if lib.lrt_lens_aperture_abi() != ABI:
            raise LensApertureUnavailable('Lens aperture ABI mismatch; saved settings were not changed')
        lib.lrt_lens_aperture_kernel_mask_v1.argtypes = []
        lib.lrt_lens_aperture_kernel_mask_v1.restype = C.c_uint32
        mask = int(lib.lrt_lens_aperture_kernel_mask_v1())
        if mask == 0 or mask & ~31:
            raise LensApertureUnavailable('Lens aperture kernel capability mask is incompatible')
        lib.lrt_lens_aperture_validate_v1.argtypes = [P, C.c_size_t] * 3 + [
            C.c_size_t, C.c_size_t, CANCEL, C.c_void_p]
        lib.lrt_lens_aperture_validate_v1.restype = C.c_int32
        lib.lrt_lens_aperture_render_tile_v1.argtypes = [P, C.c_size_t] * 3 + [
            C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t,
            C.c_size_t, C.c_size_t, NativeSettings,
            P, C.c_size_t, CANCEL, C.c_void_p]
        lib.lrt_lens_aperture_render_tile_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise LensApertureUnavailable('Lens aperture Rust module cannot load its required ABI') from error
    return lib, mask


def capability(*, enabled=True):
    """Actual ABI/symbol/kernel query, not depth readiness or feature acceptance."""
    if type(enabled) is not bool:
        raise ValueError('enabled must be a boolean')
    if not enabled:
        return {'lens_aperture_available': False, 'lens_aperture_reason': 'Module explicitly disabled',
                'abi': ABI, 'kernels': (), 'quality_status': 'authored_unrun'}
    try:
        _lib, mask = _query_runtime()
    except LensApertureUnavailable as error:
        return {'lens_aperture_available': False, 'lens_aperture_reason': str(error),
                'abi': ABI, 'kernels': (), 'quality_status': 'authored_unrun'}
    return {'lens_aperture_available': True, 'lens_aperture_reason': None, 'abi': ABI,
            'kernels': tuple(name for index, name in enumerate(APERTURES) if mask & (1 << index)),
            'quality_status': 'authored_unrun'}


def available():
    return capability()['lens_aperture_available']


def _numpy():
    import numpy as np
    return np


def _available_memory():
    from .cpu_memory_budget import available_estimate
    return available_estimate()


def _shape(shape):
    if type(shape) not in (tuple, list) or len(shape) != 2:
        raise ValueError('Lens extent requires exact (height,width)')
    height, width = shape
    if type(height) is not int or type(width) is not int or min(height, width) < 1:
        raise ValueError('Lens dimensions require positive integers')
    if height * width > MAX_SOURCE_PIXELS:
        raise MemoryError('Lens source exceeds 100 million pixels; no proxy substitution')
    return height, width


def work_estimate(shape, settings):
    """Pure conservative neighbour count, tile limit and true-source halo."""
    height, width = _shape(shape)
    native = _native_settings(normalize_settings(settings))
    halo = 0 if native.max_radius_px <= 0.5 else math.ceil(native.max_radius_px + 0.5)
    taps_per_pixel = min(width, 2 * halo + 1) * min(height, 2 * halo + 1)
    tile_pixels = min(MAX_TILE_PIXELS, MAX_CANDIDATE_TAPS // taps_per_pixel)
    if tile_pixels < 1:
        raise MemoryError('Even one lens output pixel exceeds native work admission')
    return {'halo_pixels': halo, 'candidate_taps': height * width * taps_per_pixel,
            'candidate_taps_per_pixel': taps_per_pixel, 'tile_pixels': tile_pixels,
            'quadrature_evaluations_upper_bound': height * width * taps_per_pixel * 16,
            'quadrature_evaluations_per_candidate_max': 16}


def memory_estimate(shape, *, with_refinement=False):
    """Pure conservative peak accounting; no live cgroup read or allocation.

    Includes borrowed inputs, independent snapshots, one full private output,
    Python/native tile payloads and bounded validation/allocator allowance.
    Additional excludes already-live caller input bytes. Host aggregate admission
    must separately include other documents, depth inference and concurrent jobs.
    """
    height, width = _shape(shape)
    if type(with_refinement) is not bool:
        raise ValueError('with_refinement must be a boolean')
    n = height * width
    source_bytes = n * (24 if with_refinement else 20)
    scratch = 32 * MAX_TILE_PIXELS + SCRATCH_ALLOWANCE_BYTES
    additional = source_bytes + 16 * n + scratch
    total = source_bytes + additional
    if total > MAX_WORKING_BYTES:
        raise MemoryError('Lens snapshots/output exceed the 6 GiB working-data budget')
    return {'additional_bytes': additional, 'total_bytes': total,
            'borrowed_input_bytes': source_bytes, 'scratch_allowance_bytes': scratch}


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Lens aperture cancelled; private full-image output discarded')


def _array(np, value, shape, label):
    if (type(value) is not np.ndarray or value.dtype != np.dtype('=f4')
            or not value.dtype.isnative or value.shape != shape):
        raise ValueError(label + ' requires exact native float32 shape ' + str(shape))


def _blocks(height, width):
    for row in range(height):
        for left in range(0, width, COPY_PIXELS):
            yield row, slice(left, min(left + COPY_PIXELS, width))


def _validate_block(np, block, kind):
    if not np.isfinite(block).all():
        raise ValueError('Lens ' + kind + ' contains nonfinite values')
    if kind == 'RGBA':
        alpha = block[..., 3].astype(np.float64)
        if np.any(alpha < 0) or np.any(alpha > 1):
            raise ValueError('Lens alpha must be in [0,1], without flattening')
        rgb = block[..., :3].astype(np.float64)
        if np.any(np.abs(rgb) > HDR_STRAIGHT_LIMIT * alpha[..., None]):
            raise ValueError('Lens RGB must be premultiplied with |RGB| <= 65504*alpha; no clipping')
    elif kind == 'depth':
        if np.any(block < 0) or np.any(block > 1):
            raise ValueError('Lens relative depth must be finite [0,1], near-zero-far-one')
    elif kind == 'refinement':
        if np.any(block < -1) or np.any(block > 1):
            raise ValueError('Lens refinement must be finite [-1,1]')
    else:
        raise ValueError('Unknown lens input kind')


def _snapshot(np, value, shape, kind, cancelled):
    _array(np, value, shape, kind)
    _poll(cancelled)
    result = np.empty(shape, dtype=np.float32, order='C')
    for row, columns in _blocks(shape[0], shape[1]):
        _poll(cancelled)
        block = result[row, columns]
        block[...] = value[row, columns]
        _validate_block(np, block, kind)
    result.setflags(write=False)
    _poll(cancelled)
    return result


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
        raise InterruptedError('Lens aperture cancelled; private full-image output discarded')
    if code == 5:
        raise MemoryError('Lens aperture native resource/allocation admission rejected the tile')
    if code:
        raise LensApertureRejected(int(code))
    _poll(cancelled)


def _pair(value):
    return (P(), 0) if value is None else (value.ctypes.data_as(P), value.size)


def _tiles(width, height, limit):
    tile_width = min(width, limit, 256)
    tile_height = min(height, limit // tile_width, 256)
    for y in range(0, height, tile_height):
        for x in range(0, width, tile_width):
            yield x, y, min(tile_width, width-x), min(tile_height, height-y)


def _verify_tile(np, tile, source, refinement, x, y, native, cancelled):
    for row, columns in _blocks(tile.shape[0], tile.shape[1]):
        _poll(cancelled)
        block = tile[row, columns]
        _validate_block(np, block, 'RGBA')
        original = source[y+row, x+columns.start:x+columns.stop]
        if native.max_radius_px <= 0.5:
            unchanged = np.array_equal(block.view(np.uint32), original.view(np.uint32))
        elif refinement is not None:
            clear = refinement[y+row, x+columns.start:x+columns.stop] == -1.0
            unchanged = np.array_equal(block[clear].view(np.uint32), original[clear].view(np.uint32))
        else:
            unchanged = True
        if not unchanged:
            raise RuntimeError('Lens aperture changed an exact neutral/clear pixel; output discarded')


def apply(source_rgba, relative_depth, settings, *, refinement=None,
          encoding=ENCODING, premultiplied=True, depth_convention=DEPTH_CONVENTION,
          enabled=True, max_candidate_taps=None, cancelled=lambda: False):
    """Return an independently owned full-source float32 RGBA image, or no result.

    All settings, layout, values and native availability are validated even when
    neutral. Native/source/depth absence never becomes a successful identity or
    Gaussian fallback. Inputs must not change DURING snapshotting; private copies
    have no caller alias while ctypes releases the GIL. Host authenticates matching
    source/depth/refinement identity, revision, geometry and model provenance.

    Every native tile receives the complete frozen source grid, with source-space
    integer coordinates. Only true image edges clip the native halo. Full output
    remains private until all tiles, callbacks and postchecks pass. No callbacks
    receive output buffers. Returning output is not a document/history commit.

    Optional max_candidate_taps is an explicit host job-work limit. Rejection
    never reduces strength, size or kernel. Without it, source/radius bounds still
    make work finite but do NOT promise interactive timing. Host should admit a
    timeout/cancellation and concurrent-job budget using work_estimate().
    """
    normalized = normalize_settings(settings)
    if (type(encoding) is not str or encoding != ENCODING or premultiplied is not True
            or type(depth_convention) is not str or depth_convention != DEPTH_CONVENTION):
        raise ValueError('Lens requires explicit linear-sRGB-D65 premultiplied RGBA and near-zero-far-one depth')
    if type(enabled) is not bool:
        raise ValueError('enabled must be a boolean')
    if not enabled:
        raise LensApertureUnavailable('Lens module explicitly disabled; preserve the saved recipe')
    if not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    # Explicit runtime availability query only; never load at module import.
    lib, mask = _query_runtime()
    native = _native_settings(normalized)
    if not mask & (1 << native.aperture):
        raise LensApertureUnavailable('Requested aperture is not implemented by this module; no substitute')
    np = _numpy()
    if type(source_rgba) is not np.ndarray or source_rgba.ndim != 3 or source_rgba.shape[2] != 4:
        raise ValueError('Lens source must be a full-grid HWC4 float32 array')
    height, width = _shape(tuple(source_rgba.shape[:2]))
    _array(np, source_rgba, (height,width,4), 'RGBA')
    _array(np, relative_depth, (height,width), 'depth')
    if refinement is not None:
        _array(np, refinement, (height,width), 'refinement')
    work = work_estimate((height,width), normalized)
    if max_candidate_taps is not None:
        if type(max_candidate_taps) is not int or max_candidate_taps < 1:
            raise ValueError('Host candidate-work budget requires a positive integer')
        if work['candidate_taps'] > max_candidate_taps:
            raise MemoryError('Lens job exceeds the explicit host work budget; no lower-quality fallback')
    memory = memory_estimate((height,width), with_refinement=refinement is not None)
    if memory['additional_bytes'] > _available_memory():
        raise MemoryError('Insufficient admitted CPU memory for lens snapshots and full output')
    source = _snapshot(np, source_rgba, (height,width,4), 'RGBA', cancelled)
    depth = _snapshot(np, relative_depth, (height,width), 'depth', cancelled)
    correction = None if refinement is None else _snapshot(
        np, refinement, (height,width), 'refinement', cancelled)
    callback, errors = _callback(cancelled)
    code = lib.lrt_lens_aperture_validate_v1(
        *_pair(source), *_pair(depth), *_pair(correction), width, height, callback, None)
    _status(code, cancelled, errors)
    output = np.empty((height,width,4), dtype=np.float32, order='C')
    scratch = np.empty((work['tile_pixels'] * 4,), dtype=np.float32)
    for x, y, tw, th in _tiles(width, height, work['tile_pixels']):
        _poll(cancelled)
        tile = scratch[:tw*th*4].reshape(th,tw,4)
        code = lib.lrt_lens_aperture_render_tile_v1(
            *_pair(source), *_pair(depth), *_pair(correction), width, height,
            x, y, tw, th, native, *_pair(tile), callback, None)
        _status(code, cancelled, errors)
        _verify_tile(np, tile, source, correction, x, y, native, cancelled)
        for row, columns in _blocks(th, tw):
            _poll(cancelled)
            output[y+row, x+columns.start:x+columns.stop] = tile[row, columns]
    _poll(cancelled)
    return output
