"""Private tiled float reference computation, authored but entirely UNRUN.

The bounded offline worker calls this only after fixed model/runtime/source
admission. Source is authored but whole-frame/tile equivalence, photo quality
and hardware performance remain UNRUN; no acceptance is implied.

The native-size result is staged in full. Encoded input, generated scaled
pixels, antialias scratch and transfers are tile-local; the first admitted Swin
profile deliberately uses ONE full-frame tile, including full x2 RGB output.
This is an algorithmic
working-set structure, NOT proof of a hard allocator/VRAM/RAM bound. Explicit
runtime workspace measurements remain unperformed. The CPU child applies OS
address-space/CPU/file limits; this is not a claim of acceptable latency or quality.
"""

from dataclasses import dataclass
from hashlib import sha256
import sys
from typing import Callable

from .geometry import NativeCandidatePlan, NativeTile, iter_native_tiles
from .numeric import (
    NUMERIC_VERSION, _clamp_generated, _decode_generated_native,
    _encode_admitted_linear, native_axis_taps,
)
from .source import CanonicalSource, validate_source


@dataclass(frozen=True)
class UnadmittedNativeCandidate:
    rgba_f32le: bytes
    source_sha256: str
    result_sha256: str
    width: int
    height: int
    model_id: str
    network_scale: int
    tile_count: int
    maximum_generated_tile_pixels: int
    raw_generated_statistics: dict
    native_resample_statistics: dict
    numeric_version: str = NUMERIC_VERSION
    status: str = "unadmitted_reference_candidate_not_production_result"


def _merge_statistics(total: dict, current: dict) -> None:
    total["minimum"] = min(total["minimum"], current["minimum"])
    total["maximum"] = max(total["maximum"], current["maximum"])
    total["clipped_components"] += current["clipped_components"]
    total["components"] += current["components"]


def _extract_linear_model_tile(torch, np, source: CanonicalSource, tile: NativeTile, device):
    """Tile-local RGB copy with globally anchored reflect-to-window padding.

    Swin2SR needs modulo-eight window phase, not per-tile padding. Input starts
    are globally aligned by geometry; only actual right/bottom image borders
    reflect. RRDB's previous <=1 mod-padding is a subset of this operation.
    """
    rect = tile.model_input
    if rect.x1-source.width >= source.width or rect.y1-source.height >= source.height:
        raise ValueError("source too small for the global reflection extent")
    view = np.frombuffer(source.rgba_f32le, dtype="<f4").reshape(source.height, source.width, 4)
    xs = np.arange(rect.x0, rect.x1, dtype=np.int64)
    ys = np.arange(rect.y0, rect.y1, dtype=np.int64)
    xs = np.where(xs < source.width, xs, 2*source.width-2-xs)
    ys = np.where(ys < source.height, ys, 2*source.height-2-ys)
    rgb = np.ascontiguousarray(view[ys[:, None], xs[None, :], :3].transpose(2, 0, 1)[None])
    return torch.from_numpy(rgb).to(device=device, dtype=torch.float32)


def _downsample_global_core(torch, generated, tile: NativeTile, plan: NativeCandidatePlan,
                            check_cancelled: Callable[[], None]):
    """Evaluate full-image Lanczos taps, never a tile-relative resize.

Only needed vertical support rows enter the horizontal temporary. Index-select
and multiply allocate tile-sized intermediates; they must be included in the
future runtime resource envelope, not counted as free views.
"""
    rect, core, scale = tile.model_input, tile.core, plan.scale
    xtaps = [native_axis_taps(x, native_length=plan.width, scale=scale)
             for x in range(core.x0, core.x1)]
    ytaps = [native_axis_taps(y, native_length=plan.height, scale=scale)
             for y in range(core.y0, core.y1)]
    count = 6 * scale
    if any(len(taps) != count for taps in xtaps + ytaps):
        raise ValueError("unexpected Lanczos support count")
    min_y = min(tap.index for taps in ytaps for tap in taps)
    max_y = max(tap.index for taps in ytaps for tap in taps)
    if not rect.y0 * scale <= min_y <= max_y < rect.y1 * scale:
        raise ValueError("tile lacks global vertical reconstruction support")
    if any(not rect.x0 * scale <= tap.index < rect.x1 * scale
           for taps in xtaps for tap in taps):
        raise ValueError("tile lacks global horizontal reconstruction support")
    strip = generated[:, :, min_y - rect.y0 * scale:max_y - rect.y0 * scale + 1, :]
    horizontal = torch.zeros(
        (1, 3, max_y - min_y + 1, core.x1 - core.x0),
        dtype=torch.float32, device=generated.device,
    )
    for slot in range(count):
        check_cancelled()
        indices = torch.tensor([taps[slot].index - rect.x0 * scale for taps in xtaps],
                               dtype=torch.int64, device=generated.device)
        weights = torch.tensor([taps[slot].weight for taps in xtaps],
                               dtype=torch.float32, device=generated.device).reshape(1, 1, 1, -1)
        horizontal.add_(strip.index_select(3, indices) * weights)
    native = torch.zeros(
        (1, 3, core.y1 - core.y0, core.x1 - core.x0),
        dtype=torch.float32, device=generated.device,
    )
    for slot in range(count):
        check_cancelled()
        indices = torch.tensor([taps[slot].index - min_y for taps in ytaps],
                               dtype=torch.int64, device=generated.device)
        weights = torch.tensor([taps[slot].weight for taps in ytaps],
                               dtype=torch.float32, device=generated.device).reshape(1, 1, -1, 1)
        native.add_(horizontal.index_select(2, indices) * weights)
    return native


def _execute_unadmitted_reference(
    torch, np, network, source: CanonicalSource, plan: NativeCandidatePlan,
    *, device, check_cancelled: Callable[[], None],
) -> UnadmittedNativeCandidate:
    """Actual private computation source; not called, admitted or tested here.

Future caller must admit and reserve the whole job, supply a strictly loaded
network and reviewed Torch/NumPy builds, and own staging/discard semantics.
Model halo can still differ from full-frame inference. This function neither
establishes semantic regions nor fuses strengths, edits a layer or records AI
completion. Any exception aborts without returning a partially filled raster.
"""
    if sys.byteorder != "little":
        raise ValueError("this unaccepted reference requires a reviewed little-endian runtime")
    if source.width != plan.width or source.height != plan.height:
        raise ValueError("source and tile-plan dimensions differ")
    target_device = torch.device(device)
    if target_device.type not in ("cpu", "cuda"):
        raise ValueError("no implicit device/backend fallback is supported")
    if target_device.type == "cuda" and target_device.index is None:
        raise ValueError("accelerator index must be explicit")
    if network.training or getattr(network, "scale", None) != plan.scale:
        raise ValueError("network must be an evaluation-mode graph at the declared scale")
    if any((parameter.is_floating_point() and parameter.dtype != torch.float32)
           or parameter.device != target_device
           for parameter in (*network.parameters(), *network.buffers())):
        raise ValueError("network device/dtype does not match the explicit request")
    # Materialize no tile list: iter_native_tiles validates the complete plan
    # when iterated. Validate once before allocating the native result as well.
    tiles = iter_native_tiles(plan)
    first_tile = next(tiles)
    validation = validate_source(source, check_cancelled=check_cancelled)
    check_cancelled()
    staged = bytearray(plan.staged_native_result_bytes)
    staged_view = memoryview(staged)
    total_raw = {"minimum": float("inf"), "maximum": float("-inf"),
                 "clipped_components": 0, "components": 0}
    total_native = dict(total_raw)
    tile_count = 0
    peak_generated_pixels = 0

    def process(tile: NativeTile) -> None:
        nonlocal tile_count, peak_generated_pixels
        check_cancelled()
        with torch.inference_mode():
            linear_input = _extract_linear_model_tile(torch, np, source, tile, target_device)
            encoded_input = _encode_admitted_linear(torch, linear_input)
            del linear_input
            check_cancelled()
            raw = network(encoded_input)
            del encoded_input
            check_cancelled()  # A running device kernel cannot be interrupted here.
            rect = tile.model_input
            expected_shape = (1, 3, (rect.y1 - rect.y0) * plan.scale,
                              (rect.x1 - rect.x0) * plan.scale)
            if tuple(raw.shape) != expected_shape or raw.device != target_device:
                raise ValueError("model result geometry/device does not match the pinned contract")
            generated, raw_stats = _clamp_generated(torch, raw)
            del raw
            _merge_statistics(total_raw, raw_stats)
            native_encoded = _downsample_global_core(torch, generated, tile, plan, check_cancelled)
            peak_generated_pixels = max(peak_generated_pixels, generated.numel() // 3)
            del generated
            linear, native_stats = _decode_generated_native(torch, native_encoded)
            del native_encoded
            _merge_statistics(total_native, native_stats)
            check_cancelled()
            host_rgb = linear.to(device="cpu").numpy()[0].transpose(1, 2, 0)
            core = tile.core
            rgba = np.empty((core.y1 - core.y0, core.x1 - core.x0, 4), dtype="<f4")
            rgba[:, :, :3] = host_rgb
            rgba[:, :, 3] = 1.0
            packed = memoryview(rgba).cast("B")
            row_bytes = (core.x1 - core.x0) * 16
            for row in range(core.y1 - core.y0):
                check_cancelled()
                offset = ((core.y0 + row) * source.width + core.x0) * 16
                staged_view[offset:offset + row_bytes] = packed[row * row_bytes:(row + 1) * row_bytes]
            tile_count += 1

    process(first_tile)
    for tile in tiles:
        process(tile)
    if tile_count != plan.tile_count:
        raise ValueError("incomplete native candidate")
    check_cancelled()
    # Hash in bounded chunks; final immutable-copy peak is already disclosed.
    digest = sha256()
    for offset in range(0, len(staged_view), 1_048_576):
        check_cancelled()
        digest.update(staged_view[offset:offset + 1_048_576])
    check_cancelled()
    result = bytes(staged)
    check_cancelled()
    return UnadmittedNativeCandidate(
        result, validation.sha256, digest.hexdigest(), source.width, source.height,
        plan.model_id, plan.scale, tile_count, peak_generated_pixels,
        total_raw, total_native,
    )
