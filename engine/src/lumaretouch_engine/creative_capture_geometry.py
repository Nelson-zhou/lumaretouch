"""Versioned, bounded legacy-NumPy geometry for edited capture. AUTHORED / UNRUN.

This is an allocation strategy, not a replacement interpolation algorithm.
The ordinary export geometry remains untouched. Only native f32/f64 HWC RGB
with known backing storage is admitted. Caller-owned source/aliases must remain
stable throughout inspection and execution; this module never publishes state.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


GEOMETRY_VERSION = 'edited-capture-numpy-geometry-v1'
BLOCK_PIXELS = 65_536
MAX_BLOCK_PIXELS = 65_536
MAX_SOURCE_PIXELS = 100_000_000
DEFAULT_WORK_BYTES = 512_000_000
MAX_WORK_BYTES = 4_000_000_000
ARRAY_WORKSPACE_RESERVE = 4 * 1024 * 1024
METADATA_RESERVE = 4 * 1024 * 1024
# Shared with pre-decode admission. Sum is 640 bytes per block pixel; this
# includes the singleton branch and simultaneous ufunc/gather intermediates.
ARBITRARY_SCRATCH_PER_PIXEL = (
    ('integer-grids-and-f64-affine', 128),
    ('sampler-indices-weights-and-clamps', 160),
    ('sampler-validity-masks', 16),
    ('four-f64-rgb-gathers', 4 * 3 * 8),
    ('one-input-gather-cast-transient', 3 * 8),
    ('bilinear-and-where-intermediates', 8 * 3 * 8),
    ('strided-output-assignment', 3 * 8),
)


class GeometryCaptureError(ValueError):
    """The source layout/owner or requested bounded plan is not supported."""


class GeometryCaptureBudgetExceeded(GeometryCaptureError):
    """The declared geometry working set exceeds the supplied budget."""


@dataclass(frozen=True, slots=True)
class GeometryCapturePlan:
    version: str
    path: str
    source_shape: tuple[int, int, int]
    source_bytes: int
    source_owner_id: int
    source_storage_bytes: int
    crop_bounds: tuple[int, int, int, int]  # x start/stop, y start/stop
    rotation_degrees: float
    output_shape: tuple[int, int, int]
    output_dtype: str
    output_bytes: int
    output_storage_bytes: int
    output_allocation_bytes: int
    output_storage_kind: str
    quarter_turns: int | None
    block_pixels: int
    scratch_components: tuple[tuple[str, int], ...]
    array_workspace_reserve: int
    metadata_reserve: int
    bounds_kind: str = 'application-working-set-with-conservative-native-reserves'
    runtime_verified: bool = False

    @property
    def width(self) -> int:
        return self.output_shape[1]

    @property
    def height(self) -> int:
        return self.output_shape[0]

    @property
    def block_workspace_bytes(self) -> int:
        return sum(amount for _, amount in self.scratch_components)

    @property
    def additional_work_bytes(self) -> int:
        return (self.output_allocation_bytes + self.block_workspace_bytes
                + self.array_workspace_reserve + self.metadata_reserve)

    @property
    def peak_bytes(self) -> int:
        # A source-alias output is NOT a second allocation.
        return self.source_storage_bytes + self.additional_work_bytes


def _cancel(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Bounded edited-capture geometry cancelled')


def _budget(max_bytes):
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_WORK_BYTES:
        raise GeometryCaptureError('Invalid bounded geometry working budget')


def _owner(array, np):
    """Return actual terminal storage identity/size, never just view.nbytes.

    Known plain ndarray/memoryview/bytes/bytearray chains only. A byte view of
    the terminal buffer is metadata-only and permits signed-stride bounds checks.
    No dtype-converted or contiguous copy is needed to inspect source storage.
    """
    owner, seen = array, set()
    while True:
        identity = id(owner)
        if identity in seen or len(seen) >= 64:
            raise GeometryCaptureError('Cyclic or excessive geometry backing-storage chain')
        seen.add(identity)
        if type(owner) is np.ndarray:
            if owner.dtype.hasobject or owner.dtype.fields is not None or owner.dtype.metadata is not None:
                raise GeometryCaptureError('Unsupported geometry backing-storage dtype')
            if owner.base is not None:
                owner = owner.base
                continue
            if not owner.flags.owndata or not (owner.flags.c_contiguous or owner.flags.f_contiguous):
                raise GeometryCaptureError('Unknown geometry backing-storage allocation')
            size = int(owner.nbytes)
            start = int(owner.__array_interface__['data'][0])
            break
        if type(owner) is memoryview:
            owner = owner.obj
            continue
        if type(owner) in (bytes, bytearray):
            size = len(owner)
            byte_view = np.frombuffer(owner, dtype=np.uint8)
            start = int(byte_view.__array_interface__['data'][0])
            break
        raise GeometryCaptureError('Unsupported geometry backing-storage owner: ' + type(owner).__name__)

    pointer = int(array.__array_interface__['data'][0])
    low = high = pointer
    for extent, stride in zip(array.shape, array.strides):
        delta = (int(extent) - 1) * int(stride)
        low += min(0, delta)
        high += max(0, delta)
    high += int(array.itemsize)
    if low < start or high > start + size:
        raise GeometryCaptureError('Geometry view exceeds its known backing-storage allocation')
    return identity, size


def _rect(rect, np):
    # Avoid the legacy validator's asarray/ravel allocating an unbounded input.
    # These are the common export descriptor forms; nested/custom objects reject.
    if type(rect) is np.ndarray:
        if rect.shape != (4,) or rect.dtype.kind not in 'iuf':
            raise GeometryCaptureError('Geometry crop descriptor must contain four numeric scalars')
        return tuple(float(value) for value in rect)
    if type(rect) not in (tuple, list) or len(rect) != 4:
        raise GeometryCaptureError('Geometry crop descriptor must contain four numeric scalars')
    if any(type(value) not in (int, float) for value in rect):
        raise GeometryCaptureError('Geometry crop descriptor must contain four numeric scalars')
    return tuple(rect)


def _view_for_plan(array, plan, np):
    xa, xb, ya, yb = plan.crop_bounds
    view = array[ya:yb, xa:xb]
    if plan.path == 'quarter-turn':
        view = np.rot90(view, k=-plan.quarter_turns, axes=(0, 1))
    return view


def inspect_crop_rotate_np(array, rect, rotation_degrees, *, block_pixels=BLOCK_PIXELS,
                           max_bytes=None, cancelled=None) -> GeometryCapturePlan:
    """Plan without sampling, scanning pixels, copying a raster or native loading.

    max_bytes, when present, covers this source owner + output + block scratch
    and fixed reserves, NOT other caller roots/render phases or process RSS.
    A crop can retain a much larger source owner. Unknown ownership fails closed.
    """
    _cancel(cancelled)
    if max_bytes is not None:
        _budget(max_bytes)
    if type(block_pixels) is not int or not 1 <= block_pixels <= MAX_BLOCK_PIXELS:
        raise GeometryCaptureError('Geometry block size exceeds the bounded pixel cap')
    import numpy as np
    from .ops import geometry
    if (type(array) is not np.ndarray or array.ndim != 3 or array.shape[2] != 3
            or array.dtype not in (np.dtype(np.float32), np.dtype(np.float64))
            or not array.dtype.isnative or array.dtype.metadata is not None):
        raise GeometryCaptureError('Bounded geometry requires native-endian float32/float64 RGB')
    height, width = map(int, array.shape[:2])
    if width < 1 or height < 1 or width * height > MAX_SOURCE_PIXELS:
        raise GeometryCaptureError('Geometry source exceeds the supported pixel budget')
    owner_id, storage_bytes = _owner(array, np)
    rect = _rect(rect, np)
    x0, y0, x1, y1, r = geometry.check(rect, rotation_degrees)
    xa, xb = geometry._cut(width, x0, x1)
    ya, yb = geometry._cut(height, y0, y1)
    cropped = array[ya:yb, xa:xb]
    identity = geometry.is_identity(rect, r)
    k = geometry._snapped_quarter_turn(r)
    if identity:
        path, shape, alias = 'identity', tuple(array.shape), True
        xa, xb, ya, yb = 0, width, 0, height
    elif r == 0.0 or abs(r) < geometry.EPS:
        path, shape, alias = 'crop', tuple(cropped.shape), bool(cropped.flags.c_contiguous)
    elif k is not None:
        turned = np.rot90(cropped, k=-k, axes=(0, 1))
        path, shape = 'quarter-turn', tuple(turned.shape)
        # Legacy crop_np materializes before rotation. Preserve whether it can
        # return an alias, but eliminate its intermediate full crop allocation.
        alias = bool(cropped.flags.c_contiguous and turned.flags.c_contiguous)
    else:
        ow, oh = geometry.out_size(width, height, rect, r)
        path, shape, alias = 'arbitrary', (oh, ow, 3), False
    pixels = int(shape[0]) * int(shape[1])
    if pixels > MAX_SOURCE_PIXELS:
        raise GeometryCaptureError('Geometry output exceeds the supported pixel budget')
    itemsize = 8 if path == 'arbitrary' else int(array.itemsize)
    output_bytes = pixels * 3 * itemsize
    block = min(block_pixels, pixels)
    if path == 'arbitrary':
        # Source-audited generous upper bounds. Values include simultaneously
        # live ufunc intermediates and the singleton sampler branch. NOT RSS.
        per_pixel = ARBITRARY_SCRATCH_PER_PIXEL
    elif not alias:
        per_pixel = (('strided-source-output-assignment', 2 * 3 * itemsize),)
    else:
        per_pixel = ()
    plan = GeometryCapturePlan(
        GEOMETRY_VERSION, path, tuple(array.shape), int(array.nbytes), owner_id,
        storage_bytes, (xa, xb, ya, yb), r, shape,
        'float64' if path == 'arbitrary' else array.dtype.name,
        output_bytes, storage_bytes if alias else output_bytes,
        0 if alias else output_bytes,
        'source-alias' if alias else 'owned-c-contiguous', k, block,
        tuple((name, multiplier * block) for name, multiplier in per_pixel),
        ARRAY_WORKSPACE_RESERVE, METADATA_RESERVE,
    )
    if max_bytes is not None and plan.peak_bytes > max_bytes:
        raise GeometryCaptureBudgetExceeded(
            f'Bounded geometry requires declared working set {plan.peak_bytes} bytes; '
            f'budget is {max_bytes}')
    _cancel(cancelled)
    return plan


class _Float64Gathers:
    """Minimal sampler input: source.shape and f64 advanced-index reads.

    _sample_bilinear_np only uses these operations. Every gathered value is
    promoted BEFORE p10-p00 and all other arithmetic, exactly as if the entire
    legacy source had been promoted. No pixel arithmetic is reimplemented here.
    """
    __slots__ = ('source', 'shape')

    def __init__(self, source):
        self.source = source
        self.shape = source.shape

    def __getitem__(self, indices):
        import numpy as np
        return np.asarray(self.source[indices], dtype=np.float64)


def _sample_block(source, y, bottom, x, right, width, height, ca, sa, geometry, np):
    ys = xs = dx = dy = sx = sy = None
    try:
        # Global indices, not tile-local centers or an affine recurrence. Keep
        # the original integer mgrid -> f64 conversion and expression ordering.
        ys, xs = np.mgrid[y:bottom, x:right].astype(np.float64)
        dx = xs - (width - 1) / 2.0
        dy = ys - (height - 1) / 2.0
        h, w, _ = source.shape
        sx = ca * dx - sa * dy + (w - 1) / 2.0
        sy = sa * dx + ca * dy + (h - 1) / 2.0
        return geometry._sample_bilinear_np(source, sx, sy)
    finally:
        ys = xs = dx = dy = sx = sy = None


def crop_rotate_np_bounded(array, rect, rotation_degrees, *, max_bytes=DEFAULT_WORK_BYTES,
                           cancelled=None, block_pixels=BLOCK_PIXELS):
    """Return legacy crop_rotate_np(..., uint8=False) pixels in bounded blocks.

    Identity returns the exact input object. Other outputs preserve legacy dtype,
    including native f64 for arbitrary angles, with no clipping/downsampling.
    Cancellation is checked before allocation, before/after each block and before
    return. No partial output is returned. The caller still owns every source alias.
    """
    _cancel(cancelled)
    _budget(max_bytes)
    plan = inspect_crop_rotate_np(
        array, rect, rotation_degrees, block_pixels=block_pixels,
        max_bytes=max_bytes, cancelled=cancelled,
    )
    import numpy as np
    from .ops import geometry
    output = view = gathers = block = target = None
    try:
        _cancel(cancelled)
        if plan.path == 'identity':
            return array
        view = _view_for_plan(array, plan, np)
        if plan.output_storage_kind == 'source-alias':
            _cancel(cancelled)
            return view
        output = np.empty(plan.output_shape, dtype=plan.output_dtype, order='C')
        _cancel(cancelled)
        if plan.path == 'arbitrary':
            gathers = _Float64Gathers(view)
            a = math.radians(plan.rotation_degrees)
            ca, sa = math.cos(-a), math.sin(-a)
        rows = max(1, plan.block_pixels // plan.width)
        for y in range(0, plan.height, rows):
            bottom = min(plan.height, y + rows)
            for x in range(0, plan.width, plan.block_pixels):
                _cancel(cancelled)
                right = min(plan.width, x + plan.block_pixels)
                if plan.path == 'arbitrary':
                    block = _sample_block(gathers, y, bottom, x, right,
                                          plan.width, plan.height, ca, sa, geometry, np)
                else:
                    block = view[y:bottom, x:right]
                _cancel(cancelled)
                target = output[y:bottom, x:right]
                target[...] = block
                # Release the previous block before allocating its successor.
                block = target = None
                _cancel(cancelled)
        _cancel(cancelled)
        return output
    finally:
        if gathers is not None:
            gathers.source = None
        output = view = gathers = block = target = array = None
