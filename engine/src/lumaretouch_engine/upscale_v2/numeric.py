"""Float-only numeric candidate primitives; compatibility/quality UNRUN.

These helpers are not a functioning restoration backend. They fix a reviewable
LumaRetouch policy rather than claiming equivalence to the integer-first demo.
"""

from dataclasses import dataclass
from math import ceil, floor, isfinite, pi, sin

NUMERIC_VERSION = "lrt.linear-srgb-f32.lanczos3-global.v1"


@dataclass(frozen=True)
class FilterTap:
    index: int
    weight: float


def native_axis_taps(output_index: int, *, native_length: int, scale: int) -> tuple[FilterTap, ...]:
    """Globally aligned Lanczos-3 antialias taps in scaled-image coordinates.

Pixel centers: (i + .5)*scale - .5. Support is abs(distance/scale)<3.
Normalize binary64 coefficients before one conversion to runtime float32.
Keep duplicate edge-clamped samples in ascending unclamped-index order; the
future executor must reduce horizontally then vertically in this fixed order.
No independent tile-relative resize or integer-image round trip is permitted.
"""
    if type(native_length) is not int or native_length < 2:
        raise ValueError("native_length must be >= 2")
    if type(scale) is not int or scale not in (2, 4):
        raise ValueError("only the pinned x2/x4 native reconstruction is supported")
    if type(output_index) is not int or not 0 <= output_index < native_length:
        raise ValueError("native output index is out of bounds")
    center = (output_index + 0.5) * scale - 0.5
    entries: list[tuple[int, float]] = []
    for sample in range(floor(center - 3 * scale) + 1, ceil(center + 3 * scale)):
        distance = (sample - center) / scale
        weight = 1.0 if distance == 0.0 else (
            sin(pi * distance) / (pi * distance)
            * sin(pi * distance / 3.0) / (pi * distance / 3.0)
        )
        entries.append((min(max(sample, 0), native_length * scale - 1), weight))
    total = sum(weight for _, weight in entries)
    if not isfinite(total) or total <= 0.0:
        raise ValueError("invalid antialias coefficient normalization")
    return tuple(FilterTap(index, weight / total) for index, weight in entries)


def _require_float_rgb(torch, rgb) -> None:
    if type(rgb) is not torch.Tensor or rgb.dtype != torch.float32:
        raise ValueError("RGB pixels must remain plain float32 tensors")
    if rgb.ndim != 4 or rgb.shape[0] != 1 or rgb.shape[1] != 3 or rgb.numel() == 0:
        raise ValueError("RGB pixels must have nonempty [1,3,H,W] geometry")
    if not bool(torch.isfinite(rgb).all().item()):
        raise ValueError("nonfinite model pixels are not a valid result")


def _encode_admitted_linear(torch, rgb):
    """No divide-by-255, source clipping, normalization or dtype coercion."""
    _require_float_rgb(torch, rgb)
    if bool(((rgb < 0.0) | (rgb > 1.0)).any().item()):
        raise ValueError("linear source pixels must already be admitted SDR")
    return torch.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * rgb.pow(1.0 / 2.4) - 0.055)


def _clamp_generated(torch, rgb):
    """Only generated pixels may be clamped, with pre-clamp statistics."""
    _require_float_rgb(torch, rgb)
    statistics = {
        "minimum": float(rgb.min().item()),
        "maximum": float(rgb.max().item()),
        "clipped_components": int(((rgb < 0.0) | (rgb > 1.0)).sum().item()),
        "components": rgb.numel(),
    }
    return rgb.clamp(0.0, 1.0), statistics


def _decode_generated_native(torch, encoded_native):
    """After Lanczos, explicitly count/clamp generated-only negative-lobe overshoot."""
    rgb, statistics = _clamp_generated(torch, encoded_native)
    linear = torch.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055).pow(2.4))
    return linear, statistics
