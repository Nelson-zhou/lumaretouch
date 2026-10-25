# SPDX-License-Identifier: GPL-3.0-or-later
"""Private bounded allocation strategy for existing colour stages. AUTHORED / UNRUN.

No colour mathematics, native ABI or ordinary export default is changed. Input
storage, recipes and their external aliases must remain stable for the call.
This module owns no source/document fence and never publishes a partial result.
"""
from __future__ import annotations

from dataclasses import dataclass


FINISHING_VERSION = 'edited-capture-colour-finishing-v1'
BLOCK_PIXELS = 65_536
MAX_BLOCK_PIXELS = 65_536
MAX_SOURCE_PIXELS = 100_000_000
DEFAULT_WORK_BYTES = 512_000_000
MAX_WORK_BYTES = 4_000_000_000
ARRAY_WORKSPACE_RESERVE = 4 * 1024 * 1024
METADATA_RESERVE = 4 * 1024 * 1024
# Conservative simultaneous allowances, not a measured allocator/RSS limit.
SCRATCH_PER_PIXEL = (
    ('owning-rgb-input', 12),
    ('native-rgb-output', 12),
    ('float-validation', 12),
    ('finite-validation', 3),
    ('strided-copyback-reserve', 12),
    ('bounded-array-slack', 13),
)
ENCODING = 'extended-srgb-d65'


class ColourFinishingError(ValueError):
    """Unsupported source ownership, stage state or private finishing contract."""


class ColourFinishingBudgetExceeded(ColourFinishingError):
    """Declared simultaneous finishing owners exceed the supplied sub-budget."""


@dataclass(frozen=True, slots=True)
class ColourFinishingPlan:
    version: str
    source_shape: tuple[int, int, int]
    source_bytes: int
    source_owner_id: int
    source_storage_bytes: int
    active_stages: tuple[bool, bool]
    recipe_fingerprint: tuple
    output_allocation_bytes: int
    block_pixels: int
    scratch_components: tuple[tuple[str, int], ...]
    array_workspace_reserve: int
    metadata_reserve: int
    max_bytes: int
    bounds_kind: str = 'application-working-set-with-conservative-native-reserves'
    runtime_verified: bool = False

    @property
    def width(self):
        return self.source_shape[1]

    @property
    def height(self):
        return self.source_shape[0]

    @property
    def block_workspace_bytes(self):
        return sum(amount for _, amount in self.scratch_components)

    @property
    def peak_bytes(self):
        return (self.source_storage_bytes + self.output_allocation_bytes
                + self.block_workspace_bytes + self.array_workspace_reserve
                + self.metadata_reserve)


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Bounded edited-capture colour finishing cancelled')


def _stages(grading_stage, selective_stage):
    """Known instances only; a stale active bit must not silently omit a recipe."""
    from .colour_grading_stage import ColourGradingStage
    from .selective_colour_stage import SelectiveColourStage
    from . import colour_grading_state as CG, selective_colour_state as SC
    active, fingerprint = [], []
    for stage, cls, state in ((grading_stage, ColourGradingStage, CG),
                              (selective_stage, SelectiveColourStage, SC)):
        if (type(stage) is not cls
                or set(vars(stage)) != {'recipe', 'active', 'cancelled'}):
            raise ColourFinishingError('Finishing requires the exact existing colour stages')
        recipe = state.check(stage.recipe)
        enabled = state.active(recipe)
        if type(stage.active) is not bool or stage.active != enabled:
            raise ColourFinishingError('Colour stage recipe and active state disagree')
        active.append(enabled)
        # Keep original Python scalars. Native wrappers own their existing f32
        # conversion, including tiny active controls which round to native zero.
        fingerprint.append(tuple(state.scalars(recipe)))
    return tuple(active), tuple(fingerprint)


def _storage_owner(pixels, np):
    """Inspect known terminal allocation and signed-stride extent without a copy."""
    owner, seen = pixels, set()
    try:
        while True:
            identity = id(owner)
            if identity in seen or len(seen) >= 64:
                raise ColourFinishingError('Cyclic or excessive RGB backing-storage chain')
            seen.add(identity)
            if type(owner) is np.ndarray:
                if owner.dtype.hasobject or owner.dtype.fields is not None or owner.dtype.metadata is not None:
                    raise ColourFinishingError('Unsupported RGB backing-storage dtype')
                if owner.base is not None:
                    owner = owner.base
                    continue
                if not owner.flags.owndata or not (owner.flags.c_contiguous or owner.flags.f_contiguous):
                    raise ColourFinishingError('Unknown RGB backing-storage allocation')
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
                byte_view = None
                break
            raise ColourFinishingError('Unsupported RGB backing-storage owner')
        low = high = int(pixels.__array_interface__['data'][0])
        for extent, stride in zip(pixels.shape, pixels.strides):
            delta = (int(extent) - 1) * int(stride)
            low += min(0, delta)
            high += max(0, delta)
        high += int(pixels.itemsize)
        if low < start or high > start + size:
            raise ColourFinishingError('RGB view exceeds its known backing allocation')
        return identity, size
    finally:
        pixels = owner = None


def inspect_colour_finishing(pixels, grading_stage, selective_stage, *,
                             block_pixels=BLOCK_PIXELS, max_bytes=DEFAULT_WORK_BYTES,
                             cancelled=None):
    """Admit structure and known owners, without scanning pixels/native loading.

    The budget covers input backing, one private result, bounded scratch and
    named reserves. Original/ICC, caller state, decoder, export tiles and other
    simultaneous owners are the coordinator's separate responsibility.
    """
    try:
        if cancelled is not None and not callable(cancelled):
            raise ColourFinishingError('Cancellation must be callable or absent')
        _poll(cancelled)
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_WORK_BYTES:
            raise ColourFinishingError('Invalid finishing working budget')
        if type(block_pixels) is not int or not 1 <= block_pixels <= MAX_BLOCK_PIXELS:
            raise ColourFinishingError('Finishing block exceeds the native ABI cap')
        active, fingerprint = _stages(grading_stage, selective_stage)
        import numpy as np
        if (type(pixels) is not np.ndarray or pixels.ndim != 3 or pixels.shape[2] != 3
                or pixels.dtype != np.dtype('float32') or not pixels.dtype.isnative
                or pixels.dtype.metadata is not None):
            raise ColourFinishingError('Finishing requires native-endian float32 HWC3 RGB')
        height, width = map(int, pixels.shape[:2])
        count = height * width
        if min(height, width) < 1 or count > MAX_SOURCE_PIXELS:
            raise ColourFinishingError('Finishing source exceeds the RGB pixel budget')
        owner_id, storage_bytes = _storage_owner(pixels, np)
        block = min(block_pixels, count) if any(active) else 0
        plan = ColourFinishingPlan(FINISHING_VERSION, (height, width, 3),
            int(pixels.nbytes), owner_id, storage_bytes, active, fingerprint,
            12 * count if any(active) else 0, block,
            tuple((name, multiplier * block) for name, multiplier in SCRATCH_PER_PIXEL),
            ARRAY_WORKSPACE_RESERVE, METADATA_RESERVE, max_bytes)
        if plan.peak_bytes > max_bytes:
            raise ColourFinishingBudgetExceeded(
                f'Bounded colour finishing requires declared working set {plan.peak_bytes} '
                f'bytes; budget is {max_bytes}')
        _poll(cancelled)
        return plan
    finally:
        pixels = None


def _boxes(height, width, cap):
    rows = max(1, cap // width)
    for y in range(0, height, rows):
        bottom = min(height, y + rows)
        for x in range(0, width, cap):
            yield y, bottom, x, min(width, x + cap)


def _validate_pixels(pixels, plan, cancelled, np):
    """Complete an active stage's finite/headroom checks before its first call."""
    block = None
    try:
        for y, bottom, x, right in _boxes(plan.height, plan.width, plan.block_pixels):
            _poll(cancelled)
            block = pixels[y:bottom, x:right]
            if not np.isfinite(block).all() or np.max(np.abs(block)) > 128:
                raise ColourFinishingError('Colour finishing RGB contains unsupported values')
            block = None
            _poll(cancelled)
    finally:
        # A failed SC preflight must not keep its full private CG result in a
        # validation frame's traceback through either argument or block view.
        block = pixels = None


def finish_colour_np_bounded(pixels, grading_stage, selective_stage, *,
                             block_pixels=BLOCK_PIXELS, max_bytes=DEFAULT_WORK_BYTES,
                             cancelled=None):
    """Reuse complete CG then SC on bounded, disjoint, owning f32 blocks.

    Both neutral stages return the original object. Otherwise one fresh private
    full-canvas output is returned only after all stages and cancellation gates.
    SC replaces only this private output, after each non-overlapping native call.
    No integer/f64 conversion, clipping, changed formula or source mutation.
    """
    output = current = owned = result = None
    try:
        plan = inspect_colour_finishing(pixels, grading_stage, selective_stage,
            block_pixels=block_pixels, max_bytes=max_bytes, cancelled=cancelled)
        if not any(plan.active_stages):
            return pixels
        import numpy as np
        # Always pass an explicit callable so Stage.apply_np cannot silently use
        # a different stage-local cancellation source.
        def stop():
            _poll(cancelled)
            return False
        current = pixels
        for index, stage in enumerate((grading_stage, selective_stage)):
            if _stages(grading_stage, selective_stage) != (plan.active_stages, plan.recipe_fingerprint):
                raise ColourFinishingError('Colour stages changed after finishing admission')
            if not plan.active_stages[index]:
                continue
            _validate_pixels(current, plan, cancelled, np)
            _poll(cancelled)
            if output is None:
                output = np.empty(plan.source_shape, dtype=np.float32)
            for y, bottom, x, right in _boxes(plan.height, plan.width, plan.block_pixels):
                _poll(cancelled)
                # Do not pass a view into the full source/private output. An
                # exception inside the existing stage may retain its argument.
                owned = np.empty((bottom - y, right - x, 3), dtype=np.float32)
                owned[...] = current[y:bottom, x:right]
                if not (owned.flags.owndata and owned.flags.c_contiguous and owned.flags.aligned):
                    raise ColourFinishingError('Finishing input block lacks owned aligned storage')
                _poll(cancelled)
                result = stage.apply_np(owned, encoding=ENCODING, cancelled=stop)
                if (type(result) is not np.ndarray or result.shape != owned.shape
                        or result.dtype != np.dtype('float32') or not result.dtype.isnative):
                    raise ColourFinishingError('Existing colour stage changed its float32 block contract')
                _poll(cancelled)
                output[y:bottom, x:right] = result
                owned = result = None
                _poll(cancelled)
            current = output
        if _stages(grading_stage, selective_stage) != (plan.active_stages, plan.recipe_fingerprint):
            raise ColourFinishingError('Colour stages changed during finishing')
        _poll(cancelled)
        return output
    finally:
        # Nested stage frames can retain only bounded owning inputs/results;
        # our frames must not retain the private full output on failure.
        output = current = owned = result = pixels = None
