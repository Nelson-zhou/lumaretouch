# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict ctypes adapter for the installed, versioned Rust glow kernel.

AUTHORED / UNRUN. No download, implicit compilation, NumPy glow algorithm or
successful identity fallback. Every tile reads the same immutable full source.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

OPERATION = 'lnx.light_glow.v1'
ABI = 1
MATH = 0x00010001
MODES = ('black_mist', 'white_mist', 'glow')
TILE_EDGE = 256
MAX_NATIVE_BYTES = 512 * 1024 * 1024
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int32, C.c_void_p)


class Settings(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in
                ('struct_bytes', 'abi_version', 'math_identity', 'mode', 'radius_px', 'reserved')] + [
                (name, C.c_float) for name in ('strength', 'threshold', 'exposure_ev', 'scattering',
                                               'hue_deg', 'saturation', 'lightness', 'reserved_f32')]


class Geometry(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in
                ('struct_bytes', 'full_width', 'full_height', 'tile_x', 'tile_y', 'tile_width', 'tile_height', 'reserved')]


class Plan(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in
                ('struct_bytes', 'region_x', 'region_y', 'region_width', 'region_height', 'halo_px', 'channels', 'reserved')] + [
                (name, C.c_uint64) for name in
                ('input_floats', 'output_floats', 'coverage_floats', 'scratch_bytes', 'required_bytes')]


class Unavailable(RuntimeError):
    pass


def recipe(value):
    keys = {'version', 'operation_id', 'math_identity', 'mode', 'strength', 'radius_px',
            'threshold', 'exposure_ev', 'scattering', 'tint'}
    if (type(value) is not dict or set(value) != keys
            or type(value['version']) is not int or value['version'] != 1
            or value['operation_id'] != OPERATION or type(value['math_identity']) is not int
            or value['math_identity'] != MATH or value['mode'] not in MODES
            or type(value['radius_px']) is not int or not 0 <= value['radius_px'] <= 512
            or type(value['tint']) is not dict or set(value['tint']) != {'hue_deg', 'saturation', 'lightness'}):
        raise ValueError('Glow requires the exact versioned local scalar recipe')
    def number(v, lo, hi):
        return type(v) in (int, float) and math.isfinite(v) and lo <= v <= hi
    for key, lo, hi in (('strength', 0, 1), ('threshold', 0, 1), ('exposure_ev', -4, 4), ('scattering', 0, 1)):
        if not number(value[key], lo, hi):
            raise ValueError('Invalid glow scalar ' + key)
    for key, lo, hi in (('hue_deg', -180, 180), ('saturation', -1, 1), ('lightness', -1, 1)):
        if not number(value['tint'][key], lo, hi):
            raise ValueError('Invalid glow tint ' + key)
    return Settings(C.sizeof(Settings), ABI, MATH, MODES.index(value['mode']), value['radius_px'], 0,
                    value['strength'], value['threshold'], value['exposure_ev'], value['scattering'],
                    value['tint']['hue_deg'], value['tint']['saturation'], value['tint']['lightness'], 0)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_light_glow.so'
    if not path.is_file():
        raise Unavailable('发光原生模块未安装；不会使用占位滤镜、自动下载或编译')
    try:
        lib = C.CDLL(str(path))
        expected = {'abi': ABI, 'math': MATH, 'settings_size': C.sizeof(Settings),
                    'geometry_size': C.sizeof(Geometry), 'plan_size': C.sizeof(Plan)}
        for suffix, value in expected.items():
            fn = getattr(lib, 'lrt_light_glow_' + suffix)
            fn.argtypes = []
            fn.restype = C.c_uint32
            if fn() != value:
                raise Unavailable('发光 ABI、算法版本或结构大小不匹配')
        lib.lrt_light_glow_plan.argtypes = [C.POINTER(Settings), C.POINTER(Geometry), C.c_uint64, C.POINTER(Plan)]
        lib.lrt_light_glow_plan.restype = C.c_int32
        lib.lrt_light_glow_render.argtypes = [C.POINTER(Settings), C.POINTER(Geometry),
            P, C.c_uint64, P, C.c_uint64, P, C.c_uint64, C.c_uint64, CANCEL, C.c_void_p]
        lib.lrt_light_glow_render.restype = C.c_int32
        return lib
    except (OSError, AttributeError) as error:
        raise Unavailable('发光原生接口不可用') from error


def capability():
    reason = None
    try:
        native()
        from .creative_layer_native import native as canonical_native
        canonical_native()  # Actual canonical display/return renderer gate too.
    except (OSError, RuntimeError, AttributeError) as error:
        reason = str(error)[:512]
    return {'version': 1, 'operation_id': OPERATION, 'status': 'available' if reason is None else 'unavailable',
            'abi': ABI, 'math_version': MATH, 'reason': reason, 'modes': list(MODES) if reason is None else []}


def _check(code):
    if code == 6:
        raise InterruptedError('Glow native work cancelled before output publication')
    if code in (5, 7):
        raise MemoryError('Glow full-source tile exceeds native working-set allocation budget')
    if code:
        raise ValueError('Glow native source/recipe/numeric admission refused, code ' + str(code))


def plans(width, height, settings, *, max_work_bytes, cancelled=lambda: False):
    if (any(type(n) is not int or not 1 <= n <= 12000 for n in (width, height))
            or width * height > 100_000_000 or type(max_work_bytes) is not int
            or not 1 <= max_work_bytes <= MAX_NATIVE_BYTES):
        raise ValueError('Glow source dimensions or explicit native budget exceed supported bounds')
    result = []
    lib = native()
    for y in range(0, height, TILE_EDGE):
        for x in range(0, width, TILE_EDGE):
            if cancelled():
                raise InterruptedError('Glow tile admission cancelled')
            geometry = Geometry(C.sizeof(Geometry), width, height, x, y,
                                min(TILE_EDGE, width-x), min(TILE_EDGE, height-y), 0)
            plan = Plan()
            _check(lib.lrt_light_glow_plan(C.byref(settings), C.byref(geometry), max_work_bytes, C.byref(plan)))
            if (plan.struct_bytes != C.sizeof(Plan) or plan.channels != 9 or plan.reserved != 0
                    or plan.region_width < geometry.tile_width or plan.region_height < geometry.tile_height
                    or plan.region_x > x or plan.region_y > y
                    or plan.region_x + plan.region_width < x + geometry.tile_width
                    or plan.region_y + plan.region_height < y + geometry.tile_height
                    or plan.region_x + plan.region_width > width or plan.region_y + plan.region_height > height
                    or plan.input_floats != plan.region_width * plan.region_height * 4
                    or plan.output_floats != geometry.tile_width * geometry.tile_height * 4
                    or plan.coverage_floats != geometry.tile_width * geometry.tile_height
                    or plan.required_bytes > max_work_bytes or plan.required_bytes < plan.scratch_bytes):
                raise ValueError('Glow core returned an inconsistent full-source region plan')
            result.append((geometry, plan))
    return result


def render(content, width, height, value, *, max_bytes, cancelled=lambda: False):
    """Full-grid output + actual affected coverage, with only bounded tile copies.

    max_bytes is remaining workspace after all retained source/provenance and
    final immutable/display reserves. Output remains private on any exception.
    """
    import numpy as np
    if type(content) is not bytes or len(content) != width * height * 16:
        raise ValueError('Glow requires immutable canonical full-grid float32 RGBA bytes')
    if type(max_bytes) is not int:
        raise ValueError('Glow requires an explicit remaining workspace budget')
    settings = recipe(value)
    output_bytes = width * height * 20
    remaining = max_bytes - output_bytes - 8 * 1024 * 1024
    if remaining <= 0:
        raise MemoryError('Glow full-resolution output does not fit the admitted budget')
    # Extra external tile outputs are separate from the core's transactional
    # private result. Conservatively reserve them even if the core counts both.
    external_tile_bytes = TILE_EDGE * TILE_EDGE * 20
    limit = min(MAX_NATIVE_BYTES, remaining - external_tile_bytes)
    if limit <= 0:
        raise MemoryError('Glow tile working set has no available reservation')
    schedule = plans(width, height, settings, max_work_bytes=limit, cancelled=cancelled)
    source = np.frombuffer(content, dtype='<f4').reshape(height, width, 4)
    output = np.empty((height, width, 4), dtype=np.float32)
    coverage = np.empty((height, width), dtype=np.float32)
    errors = []
    def stop(_user):
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1
    callback = CANCEL(stop)
    lib = native()
    for geometry, plan in schedule:
        if cancelled():
            raise InterruptedError('Glow full-source render cancelled')
        x, y = geometry.tile_x, geometry.tile_y
        w, h = geometry.tile_width, geometry.tile_height
        rx, ry = plan.region_x, plan.region_y
        region = np.array(source[ry:ry+plan.region_height, rx:rx+plan.region_width],
                          dtype=np.float32, order='C', copy=True)
        tile = np.empty((h, w, 4), dtype=np.float32)
        affected = np.empty((h, w), dtype=np.float32)
        code = lib.lrt_light_glow_render(C.byref(settings), C.byref(geometry),
            region.ctypes.data_as(P), region.size, tile.ctypes.data_as(P), tile.size,
            affected.ctypes.data_as(P), affected.size, limit, callback, None)
        if errors:
            raise errors[0]
        _check(code)
        if cancelled():
            raise InterruptedError('Glow tile completed after cancellation; output discarded')
        alpha = tile[:, :, 3]
        if (not np.isfinite(tile).all() or not np.isfinite(affected).all()
                or np.any(affected < 0) or np.any(affected > 1)
                or not np.array_equal(alpha, source[y:y+h, x:x+w, 3])
                or np.any(tile[:, :, :3] < 0) or np.any(tile[:, :, :3] > alpha[:, :, None])):
            raise ValueError('Glow core returned invalid SDR pixels, alpha or actual coverage')
        expected_coverage = np.max(np.abs(tile[:, :, :3] - source[y:y+h, x:x+w, :3]), axis=2)
        if not np.array_equal(affected, expected_coverage):
            raise ValueError('Glow coverage differs from its actual float32 RGB result')
        if settings.strength == 0 and tile.astype('<f4', copy=False).tobytes() != source[y:y+h, x:x+w].tobytes():
            raise ValueError('Neutral glow failed the bit-exact source preservation contract')
        del expected_coverage
        output[y:y+h, x:x+w] = tile
        coverage[y:y+h, x:x+w] = affected
        del region, tile, affected, alpha
    if cancelled():
        raise InterruptedError('Glow result cancelled before full-grid publication')
    output.setflags(write=False)
    coverage.setflags(write=False)
    return output, coverage
