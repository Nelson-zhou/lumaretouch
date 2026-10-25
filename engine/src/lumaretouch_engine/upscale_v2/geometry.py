"""Planning only: globally phased native-size output and explicit payload costs.

These formulas are NOT a peak-RAM/VRAM bound. Unknown model/runtime workspaces,
live host assets, allocation caching, capture and serialization must be admitted
separately before the presently unavailable executor can be implemented/enabled.
"""

from dataclasses import dataclass
from typing import Iterator

from .architecture import architecture_for, parameter_payload_bytes
from .source import validate_dimensions

FILTER_RADIUS_NATIVE = 3


@dataclass(frozen=True)
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def pixels(self) -> int:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


@dataclass(frozen=True)
class NativeTile:
    core: Rect
    model_input: Rect
    # Coordinates refer to the same globally right/bottom-mod-padded source.
    # At true image borders, output is cropped to width*scale / height*scale
    # before the globally clamped Lanczos taps are evaluated.


@dataclass(frozen=True)
class NativeCandidatePlan:
    model_id: str
    width: int
    height: int
    scale: int
    input_alignment: int
    padded_width: int
    padded_height: int
    core_size: int
    halo: int
    tile_count: int
    maximum_input_tile_pixels: int
    source_bytes: int
    staged_native_result_bytes: int
    final_immutable_result_copy_bytes: int
    known_host_payload_lower_bound: int
    device_payload_terms_at_tile_bound: int
    model_parameter_bytes: int
    maximum_generated_tile_bytes: int
    full_scaled_rgb_bytes_if_allocated: int
    peak_host_bytes: None = None
    peak_device_bytes: None = None
    memory_admitted: bool = False
    halo_quality_accepted: bool = False
    reference_stream_source_authored: bool = True
    production_executor_available: bool = False


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def plan_native_candidate(
    width: int, height: int, *, model_id: str, core_size: int, halo: int,
) -> NativeCandidatePlan:
    """Plan geometry without pixel allocation, optional imports or admission.

Caller must choose halo explicitly. An arbitrary halo is NOT evidence that
23 RRDB blocks have enough context; there is no quality-accepted default.
Tile lists are generated lazily, avoiding a pixel-count-sized planning object.
"""
    validate_dimensions(width, height)
    spec = architecture_for(model_id)
    alignment = spec.input_unshuffle
    if type(core_size) is not int or not 16 <= core_size <= 1024 or core_size % alignment:
        raise ValueError("core_size must be a phase-aligned integer in [16,1024]")
    if type(halo) is not int or not 1 <= halo <= 2048:
        raise ValueError("halo must be an explicit source-pixel integer in [1,2048]")
    padded_width = _align_up(width, alignment)
    padded_height = _align_up(height, alignment)
    margin = halo + FILTER_RADIUS_NATIVE
    # Two alignment adjustments can each add at most alignment-1 pixels.
    extent = core_size + 2 * margin + 2 * (alignment - 1)
    tile_pixels = min(padded_width, extent) * min(padded_height, extent)
    canonical_bytes = width * height * 16
    parameter_bytes = parameter_payload_bytes(model_id)
    generated_tile_bytes = tile_pixels * spec.scale ** 2 * 3 * 4
    return NativeCandidatePlan(
        model_id=model_id, width=width, height=height, scale=spec.scale,
        input_alignment=alignment, padded_width=padded_width,
        padded_height=padded_height, core_size=core_size, halo=halo,
        tile_count=((width + core_size - 1) // core_size)
        * ((height + core_size - 1) // core_size),
        maximum_input_tile_pixels=tile_pixels,
        source_bytes=canonical_bytes,
        staged_native_result_bytes=canonical_bytes,
        final_immutable_result_copy_bytes=canonical_bytes,
        known_host_payload_lower_bound=3 * canonical_bytes,
        device_payload_terms_at_tile_bound=parameter_bytes + tile_pixels * 3 * 4 + generated_tile_bytes,
        model_parameter_bytes=parameter_bytes,
        maximum_generated_tile_bytes=generated_tile_bytes,
        full_scaled_rgb_bytes_if_allocated=width * height * spec.scale ** 2 * 3 * 4,
    )


def iter_native_tiles(plan: NativeCandidatePlan) -> Iterator[NativeTile]:
    """Disjoint native output cores, with model halo plus downsample support."""
    if type(plan) is not NativeCandidatePlan:
        raise ValueError("expected a native-candidate plan")
    canonical = plan_native_candidate(
        plan.width, plan.height, model_id=plan.model_id,
        core_size=plan.core_size, halo=plan.halo,
    )
    if plan != canonical:
        raise ValueError("native-candidate plan has been altered")
    alignment = plan.input_alignment
    margin = plan.halo + FILTER_RADIUS_NATIVE
    for y0 in range(0, plan.height, plan.core_size):
        y1 = min(y0 + plan.core_size, plan.height)
        for x0 in range(0, plan.width, plan.core_size):
            x1 = min(x0 + plan.core_size, plan.width)
            model_input = Rect(
                max(0, (x0 - margin) // alignment * alignment),
                max(0, (y0 - margin) // alignment * alignment),
                min(plan.padded_width, _align_up(x1 + margin, alignment)),
                min(plan.padded_height, _align_up(y1 + margin, alignment)),
            )
            yield NativeTile(Rect(x0, y0, x1, y1), model_input)
