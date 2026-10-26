"""Shared single/batch export watermark delivery, using existing verified writers."""
from __future__ import annotations

import os
import time

from . import watermark as WM


class DeliveryError(ValueError):
    def __init__(self, message, outputs):
        super().__init__(message)
        self.outputs = outputs


def _deliver(frame, path, watermark, write):
    outputs = []
    # Render before writing either version: missing/invalid marks never silently
    # produce an apparently complete clean-only delivery.
    marked, facts = WM.composite(frame, watermark)
    def deliver(pixels, target):
        from .export_destination_runtime import reuse_output
        previous = reuse_output(target)
        return previous if previous is not None else write(pixels, target)
    try:
        if watermark and watermark["alsoClean"]:
            clean_dir = os.path.join(os.path.dirname(path), "无水印")
            from .export_destination_runtime import active, variant_target
            if not active(): os.makedirs(clean_dir, exist_ok=True)
            clean = deliver(frame, variant_target(os.path.join(clean_dir, os.path.basename(path)), "clean"))
            outputs.append({**clean, "variant": "clean"})
        result = deliver(marked, path)
        outputs.append({**result, "variant": "watermarked" if watermark else "clean"})
    except Exception as error:
        outputs.extend(getattr(error, "outputs", []))
        raise DeliveryError(f"导出失败；已处理的副本保留，见逐项记录：{error}", outputs) from error
    # One source-image task is skipped only if every requested variant skipped.
    result = {**result, "skipped": all(o.get("skipped", False) for o in outputs)}
    return {**result, "watermark": facts, "outputs": outputs}


def write_delivery8(frame, path, *, watermark=None, **kwargs):
    from .export import write_file
    if not watermark:
        return write_file(frame, path, **kwargs)
    return _deliver(frame, path, watermark, lambda pixels, target: write_file(pixels, target, **kwargs))


def export_delivery16(decoded, spec, path, *, watermark, device="cpu", tile=1024,
                      crop_rect=(0, 0, 1, 1), rotation_degrees=0, output_profile="srgb",
                      conflict_policy="skip_and_report", metadata_include_gps=False,
                      tiff_compression="none", decode_ms=0):
    from .export import render_edited_rgb16, _profile_bytes, _srgb_bytes, _write_verified_rgb16
    from .color16 import convert_rgb16
    started = time.perf_counter()
    # Composite in working sRGB BEFORE output conversion. Converting the entire
    # photo through Pillow just to place a logo would destroy native RGB16 data.
    frame, working_icc, facts = render_edited_rgb16(decoded, spec, device=device,
        tile=tile, crop_rect=crop_rect, rotation_degrees=rotation_degrees, output_profile="srgb")
    target_icc = _profile_bytes(output_profile, decoded.source_icc)
    conversion_ms = 0.0
    def write(pixels, target):
        nonlocal conversion_ms
        color_start = time.perf_counter()
        if target_icc and target_icc != working_icc:
            pixels = convert_rgb16(pixels, working_icc or _srgb_bytes(), target_icc)
        conversion_ms += (time.perf_counter() - color_start) * 1000
        return _write_verified_rgb16(pixels, target, target_icc=target_icc,
            conflict_policy=conflict_policy, metadata_include_gps=metadata_include_gps,
            tiff_compression=tiff_compression)
    info = _deliver(frame, path, watermark, write)
    return {**facts, **info, "icc_source": output_profile,
            "color_converted": facts["color_converted"] or bool(target_icc and target_icc != working_icc),
            "color_conversion_ms": facts["color_conversion_ms"] + conversion_ms,
            "decode_ms": decode_ms, "total_ms": decode_ms + (time.perf_counter()-started)*1000}
