"""Bounded edited RGB to private canonical RGBA storage. AUTHORED / UNRUN.

The existing packaged Rust extended-sRGB ABI owns all transfer arithmetic. This
module does not render edits, freeze content, intern assets or publish state.
Source ownership and all external aliases remain the caller's responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import sys

from .creative_layer_native import MAX_SOURCE_PIXELS, MAX_TILE_PIXELS

BLOCK_PIXELS = MAX_TILE_PIXELS
DEFAULT_WORK_BYTES = 512_000_000
MAX_WORK_BYTES = 4_000_000_000
# Named admission allowances, not measured allocator or process-RSS limits.
# NumPy may buffer a strided/dtype-converting assignment; ctypes/Python objects
# and bytearray allocator overhead are not represented by their pixel lengths.
ARRAY_WORKSPACE_RESERVE = 4 * 1024 * 1024
METADATA_RESERVE = 4 * 1024 * 1024


class EditedCaptureBudgetExceeded(ValueError):
    """Declared simultaneous live conversion owners exceed max_bytes."""


@dataclass(frozen=True, slots=True)
class EditedCaptureMemoryPlan:
    width: int
    height: int
    source_bytes: int
    source_storage_bytes: int
    sink_bytes: int
    block_pixels: int
    block_workspace_bytes: int
    array_workspace_reserve: int
    metadata_reserve: int
    max_bytes: int
    bounds_kind: str = 'application-working-set-with-conservative-native-reserves'
    runtime_verified: bool = False

    @property
    def peak_bytes(self) -> int:
        return (self.source_storage_bytes + self.sink_bytes + self.block_workspace_bytes
                + self.array_workspace_reserve + self.metadata_reserve)

    @property
    def freeze_bytes_after_source_release(self) -> int:
        """Separate caller phase, NOT performed or admitted by this module.

        Add original bytes, retained assets and other owners. This estimate is
        valid only after the caller releases every RGB/export/block owner.
        """
        return 2 * self.sink_bytes + self.metadata_reserve


@dataclass(frozen=True, slots=True)
class EditedCaptureSink:
    """Completed private mutable storage, not an immutable persistent asset.

    bytes(result.sink) is a separate required ownership copy. Returning this
    object cannot consume the caller's source or release its external aliases.
    """
    width: int
    height: int
    sink: bytearray = field(repr=False, compare=False)
    plan: EditedCaptureMemoryPlan


def _cancel(cancelled):
    if cancelled():
        raise InterruptedError('Bounded edited creative capture cancelled')


def _storage_bytes(rgb, np):
    """Conservatively charge known backing storage, not only a visible crop.

    Plain ndarray/memoryview chains and terminal buffer owners are supported.
    Unknown chains fail closed. Unrelated allocations retained by external
    aliases are not discoverable here and remain the caller's budget concern.
    """
    owner = rgb
    charged = 0
    seen = set()
    while owner is not None:
        identity = id(owner)
        if identity in seen or len(seen) >= 64:
            raise ValueError('Edited RGB backing-owner chain is cyclic or excessive')
        seen.add(identity)
        if type(owner) is np.ndarray:
            charged = max(charged, int(owner.nbytes))
            owner = owner.base
        elif isinstance(owner, np.ndarray):
            # A subclass may hide a larger base or override accounting metadata.
            raise ValueError('Edited RGB has an unsupported ndarray backing-storage owner')
        elif isinstance(owner, memoryview):
            charged = max(charged, owner.nbytes)
            owner = owner.obj
        else:
            try:
                with memoryview(owner) as storage:
                    charged = max(charged, storage.nbytes)
            except (TypeError, ValueError) as exc:
                raise ValueError('Edited RGB has an unsupported backing-storage owner') from exc
            break
    return charged


def inspect_rgb_sink(rgb, *, max_bytes=DEFAULT_WORK_BYTES, cancelled=lambda: False):
    """Admit layout and memory without native loading or pixel conversion.

    Native-endian float32/float64 HWC3 arrays only. Inspection does not certify
    finite values, colour space, provenance or full-resolution renderer status.
    Existing geometry may return float64; the conversion preserves its old
    float32 assignment boundary, using bounded blocks instead of a full cast.
    """
    _cancel(cancelled)
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_WORK_BYTES:
        raise ValueError('Invalid bounded edited-capture working budget')
    import numpy as np
    if (type(rgb) is not np.ndarray or rgb.ndim != 3 or rgb.shape[2] != 3
            or rgb.dtype not in (np.dtype(np.float32), np.dtype(np.float64))
            or not rgb.dtype.isnative):
        raise ValueError('Edited capture requires native-endian float32/float64 RGB arrays')
    height, width = map(int, rgb.shape[:2])
    pixels = width * height
    if width < 1 or height < 1 or pixels > MAX_SOURCE_PIXELS:
        raise ValueError('Edited RGB dimensions exceed the canonical pixel budget')
    if type(BLOCK_PIXELS) is not int or not 1 <= BLOCK_PIXELS <= MAX_TILE_PIXELS:
        raise ValueError('Edited capture block bound exceeds the native ABI cap')
    block = min(BLOCK_PIXELS, pixels)
    plan = EditedCaptureMemoryPlan(
        width, height, int(rgb.nbytes), _storage_bytes(rgb, np), 16 * pixels,
        block, 48 * block, ARRAY_WORKSPACE_RESERVE, METADATA_RESERVE, max_bytes,
    )
    if plan.peak_bytes > max_bytes:
        raise EditedCaptureBudgetExceeded(
            f'Bounded edited capture requires declared working set {plan.peak_bytes} bytes; '
            f'budget is {max_bytes}')
    _cancel(cancelled)
    return plan


def capture_rgb_sink(rgb, *, max_bytes=DEFAULT_WORK_BYTES, cancelled=lambda: False):
    """Capture genuine edited extended-sRGB as opaque premultiplied linear f32.

    The source, its layout and every alias must remain stable during conversion.
    Only alpha=1 is introduced. Negative, signed-zero and above-one semantics
    remain those of the existing native transfer; invalid/unrepresentable RGB
    rejects instead of clipping. No unbounded RGBA input, extra linear raster,
    full-image float cast, immutable sink copy or Python transfer math is used.

    max_bytes covers source backing + one sink + bounded staging/allowances.
    Caller decode/render workspaces, retained assets, concurrency and the later
    immutable freeze require separate admission. No partial sink is returned.
    """
    plan = inspect_rgb_sink(rgb, max_bytes=max_bytes, cancelled=cancelled)
    import numpy as np
    from .creative_layer_native import native, P, CreativeLayerNativeRejected
    _cancel(cancelled)
    lib = native()
    _cancel(cancelled)
    sink = destination = rgba = immutable = target = None
    try:
        sink = bytearray(plan.sink_bytes)
        # This full-sized ndarray is only a view over the ONE output allocation.
        destination = np.frombuffer(sink, dtype='=f4').reshape(plan.height, plan.width, 4)
        rows = max(1, BLOCK_PIXELS // plan.width)
        for y in range(0, plan.height, rows):
            bottom = min(plan.height, y + rows)
            for x in range(0, plan.width, BLOCK_PIXELS):
                _cancel(cancelled)
                right = min(plan.width, x + BLOCK_PIXELS)
                rgba = np.empty((bottom - y, right - x, 4), dtype=np.float32)
                # Preserve the previous float32 RGBA assignment and rounding,
                # including native-f64 geometry output and negative zero.
                rgba[:, :, :3] = rgb[y:bottom, x:right]
                rgba[:, :, 3] = 1.0
                immutable = np.frombuffer(rgba.tobytes(order='C'), dtype='=f4')
                target = destination[y:bottom, x:right]
                if (not target.flags.c_contiguous or not target.flags.aligned
                        or not immutable.flags.aligned
                        or not 0 < immutable.size // 4 <= MAX_TILE_PIXELS):
                    raise ValueError('Edited capture native block is misaligned or exceeds the ABI cap')
                _cancel(cancelled)
                code = lib.lrt_creative_linearize_extended_rgba(
                    immutable.ctypes.data_as(P), target.ctypes.data_as(P), immutable.size)
                if code:
                    raise CreativeLayerNativeRejected(code, 'Bounded extended-sRGB edited capture')
                if sys.byteorder != 'little':
                    target.byteswap(inplace=True)
                # Do not retain old staging while allocating the next block.
                rgba = immutable = target = None
                _cancel(cancelled)
        _cancel(cancelled)
        return EditedCaptureSink(plan.width, plan.height, sink, plan)
    finally:
        # Avoid retaining private allocations in this frame's failure traceback.
        # Clearing these locals does NOT consume or release external aliases.
        rgba = immutable = target = destination = sink = rgb = None
