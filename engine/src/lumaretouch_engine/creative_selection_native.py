# SPDX-License-Identifier: GPL-3.0-or-later
"""ctypes ABI1 port to the original selection core. AUTHORED / UNRUN.

Missing/mismatched native code fails closed. No compiler, fallback rasterizer,
model inference, library search path or pixel rescaling is used at runtime.
"""
from __future__ import annotations
import ctypes as C
from functools import lru_cache
from pathlib import Path
from .creative_selection_recipe import validate

TILE_EDGE = 256
MAX_NATIVE_BYTES = 67_108_864
MAX_RECIPE_WORK = 2_000_000_000
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_uint32, C.c_void_p)


class Point(C.Structure):
    _fields_ = [('x', C.c_double), ('y', C.c_double)]


class Operation(C.Structure):
    _fields_ = [(k, C.c_uint32) for k in ('kind', 'combine', 'point_offset', 'point_count')] + [
        (k, C.c_double) for k in ('x0', 'y0', 'x1', 'y1', 'diameter', 'hardness', 'opacity')]


class Recipe(C.Structure):
    _fields_ = [(k, C.c_uint32) for k in ('abi_version', 'struct_size', 'source_width', 'source_height',
                                        'operation_count', 'point_count', 'feather_radius', 'reserved')] + [
        ('operations', C.POINTER(Operation)), ('points', C.POINTER(Point))]


class Tile(C.Structure):
    _fields_ = [(k, C.c_uint32) for k in ('x', 'y', 'width', 'height')]


class Limits(C.Structure):
    _fields_ = [(k, C.c_uint64) for k in ('max_working_bytes', 'max_output_pixels', 'max_work_units')]


class Stats(C.Structure):
    _fields_ = [(k, C.c_uint64) for k in ('working_bytes', 'work_units', 'output_pixels')]


class SelectionNativeUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin' / 'liblumaretouch_creative_selection.so'
    if not path.is_file():
        raise SelectionNativeUnavailable('手动选区原生核心未安装；不会用代理图放大、推理或运行时编译替代')
    try:
        lib = C.CDLL(str(path))
        lib.lr_selection_abi_version.argtypes = []
        lib.lr_selection_abi_version.restype = C.c_uint32
        if lib.lr_selection_abi_version() != 1:
            raise SelectionNativeUnavailable('Creative selection ABI is not version 1')
        lib.lr_selection_evaluate_v1.argtypes = [C.POINTER(Recipe), C.POINTER(Tile), C.POINTER(Limits),
                                               CANCEL, C.c_void_p, P, C.c_uint64, C.POINTER(Stats)]
        lib.lr_selection_evaluate_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise SelectionNativeUnavailable('Creative selection native component is incompatible or unloadable') from error
    return lib


def capability():
    try:
        native()
        from .creative_layer_native import native as compositor
        compositor()
        return {'available': True, 'abi': 1, 'reason': None, 'manual_only': True}
    except (OSError, RuntimeError, AttributeError) as error:
        return {'available': False, 'abi': 1, 'reason': str(error), 'manual_only': True}


class Evaluator:
    """Owned immutable vector arrays stay live for all native tiled evaluations."""
    def __init__(self, recipe, *, cancelled=lambda: False):
        self.value = validate(recipe, recipe['canvas'])
        self.cancelled = cancelled
        self.work_units = 0
        operations, points = [], []
        kinds = {'rectangle': 1, 'ellipse': 2, 'lasso': 3, 'brush': 4, 'invert': 5}
        combines = {'new': 0, 'add': 1, 'subtract': 2, 'intersect': 3}
        for op in self.value['operations']:
            path = op.get('points', [])
            operations.append(Operation(kinds[op['kind']], combines.get(op.get('combine'), 0),
                                        len(points) if path else 0, len(path), *[float(op.get(k, 0)) for k in
                                        ('x0', 'y0', 'x1', 'y1', 'diameter', 'hardness', 'opacity')]))
            points.extend(Point(float(x), float(y)) for x, y in path)
        self.operations = (Operation * len(operations))(*operations)
        self.points = (Point * len(points))(*points)
        c = self.value['canvas']
        self.recipe = Recipe(1, C.sizeof(Recipe), c['width'], c['height'], len(operations), len(points),
                             self.value['feather_radius'], 0, self.operations, self.points)
        def stop(_):
            try:
                return int(bool(self.cancelled()))
            except Exception:
                return 1
        self.callback = CANCEL(stop)

    def tile(self, x, y, width, height):
        import numpy as np
        if self.cancelled():
            raise InterruptedError('Selection rasterization cancelled')
        if self.work_units >= MAX_RECIPE_WORK:
            raise ValueError('Selection full-recipe native work budget exceeded')
        c = self.value['canvas']
        if (any(type(v) is not int for v in (x, y, width, height)) or min(x, y) < 0
                or not 1 <= width <= TILE_EDGE or not 1 <= height <= TILE_EDGE
                or x + width > c['width'] or y + height > c['height']):
            raise ValueError('Selection native tile is outside the authoritative canvas')
        output = np.empty((height, width), dtype=np.float32)
        tile = Tile(x, y, width, height)
        limits = Limits(MAX_NATIVE_BYTES, TILE_EDGE * TILE_EDGE, 100_000_000)
        stats = Stats()
        code = native().lr_selection_evaluate_v1(C.byref(self.recipe), C.byref(tile), C.byref(limits),
                                               self.callback, None, output.ctypes.data_as(P), output.size,
                                               C.byref(stats))
        if code == 4 or self.cancelled():
            raise InterruptedError('Selection rasterization cancelled')
        if code:
            reasons = {1: 'ABI mismatch', 2: 'invalid geometry', 3: 'full-resolution work budget exceeded',
                       5: 'allocation refused', 6: 'contained native failure'}
            raise ValueError('Selection native evaluation rejected: ' + reasons.get(code, str(code)))
        self.work_units += stats.work_units
        if self.work_units > MAX_RECIPE_WORK:
            raise ValueError('Selection full-recipe native work budget exceeded')
        if not np.isfinite(output).all() or not ((output >= 0) & (output <= 1)).all():
            raise ValueError('Selection native output is not finite coverage')
        return output
