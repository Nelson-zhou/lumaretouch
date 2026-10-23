"""Ordinary RGB8 delivery with genuine PNG16 retained until final quantization.

The existing writer remains the sole owner of watermarking, destination ICC,
EXIF filtering, target-size search and publication. This boundary returns working
sRGB RGB8, never source-encoded pixels mislabeled as working sRGB.
"""
from copy import copy
from time import perf_counter

import numpy as np


def decode_for_delivery8(path, *, device, creative_base=None):
    """Select native PNG precision before any RGB8 display decode can lose it.

    Other formats retain their established ordinary-export decoder. A creative
    base is resolved by the editing pipeline and does not consume carrier pixels.
    """
    from .decode import load_full
    from .png16_source import source_header
    header = source_header(path) if creative_base is None else None
    bits = 16 if header is not None and header.bits == 16 else 8
    return load_full(path, device=device, want_bits=bits)


def check_source_profile(decoded, output_profile):
    """A decoder provenance record is not itself proof of camera RAW input."""
    if (output_profile == "source" and (decoded.raw or {}).get("source")
            in ("self_dng", "libraw", "libraw_preview")):
        from .export import ExportError
        raise ExportError(
            "RAW 源暂不携带源 ICC：这条通道没读元数据，不是文件里没有。"
            "请改选 srgb，或把一个真实的 .icc 文件路径当 output_profile 递进来")


def _internal_geometry(spec):
    """Keep ordinary RGB8 late-canvas operators in their established order."""
    from . import reference_color_state as reference, semantic_colour_state as semantic
    from . import colour_grading_state as grading, colour_editor_state as editor
    from . import selective_colour_state as selective, photo_detail_state as detail
    from . import photo_grain_state as grain, fringe_repair_state as fringe
    return (reference.active(spec.reference_color) or semantic.active(spec.semantic_colour)
        or grading.active(spec.colour_grading) or editor.active(spec.colour_editor)
        or selective.active(spec.selective_colour) or detail.active(spec.photo_detail)
        or grain.active(spec.photo_grain) or fringe.active(spec.fringe_repair))


def _final_rgb8(frame):
    """Finite float RGB -> RGB8 once, with bounded quantization temporaries.

    Match existing integer export's [0,1] clamp and nearest-even rounding. This
    is not an HDR encoder; creative-source admissibility is owned upstream.
    """
    from .export import ExportError
    from .quant import quantize_np
    if (type(frame) is not np.ndarray or frame.ndim != 3 or frame.shape[2] != 3
            or frame.dtype.kind != "f" or min(frame.shape[:2]) < 1):
        raise ExportError("PNG16 ordinary export requires final floating RGB before RGB8 quantization")
    height, width = frame.shape[:2]
    columns = min(width, 1 << 18)
    rows = max(1, (1 << 18) // columns)
    out = np.empty(frame.shape, dtype=np.uint8)
    for y in range(0, height, rows):
        for x in range(0, width, columns):
            block = frame[y:y + rows, x:x + columns]
            if not np.isfinite(block).all():
                raise ExportError("Nonfinite PNG16 edited RGB cannot be delivered")
            out[y:y + rows, x:x + columns] = quantize_np(block)
    return out


def render_delivery8(decoded, spec, *, device, tile,
                     crop_rect=(0., 0., 1., 1.), rotation_degrees=0.):
    """Apply the frozen per-image recipe and geometry, returning working RGB8."""
    from .export import ExportError, export_image, export_image16, _srgb_bytes
    raw = decoded.raw or {}
    native_png = spec.creative_base is None and raw.get("source") == "png16"
    if native_png:
        if (decoded.rgb.dtype != np.uint16 or decoded.src_bits != 16
                or decoded.draft_used or raw.get("used_preview")
                or raw.get("half_size", False) not in (False, 0, None)
                or (decoded.w, decoded.h) != (decoded.src_w, decoded.src_h)):
            raise ExportError("PNG16 ordinary export requires genuine full-resolution uint16 source")
        from .full_source_working import working_rgb
        started = perf_counter()
        source = working_rgb(decoded)
        color_ms = (perf_counter() - started) * 1000
        # Do not mutate the caller's spec or let an analysis-provenance flag
        # constrain delivery scaling. Native source and editing remain full
        # precision; export_image16 skips its integer pack for this private copy.
        floating = copy(spec)
        floating.float_output = True
        floating.provenance_output = False
        floating.provenance_result = None
        frame, stats = export_image16(source, floating, device=device, tile=tile,
            crop_rect=crop_rect, rotation_degrees=rotation_degrees)
        frame = _final_rgb8(frame)
        stats = {**stats, "bits": 8, "decoded_bits": 16, "source_bits": 16,
            "source": "png16", "pipeline": "png16_float_rgb8",
            "working_color_space": "sRGB", "quantization": "final_rgb8",
            "input_color_converted": bool(decoded.source_icc
                and decoded.source_icc != _srgb_bytes()),
            "input_color_conversion_ms": round(color_ms, 2),
            "notes": list(decoded.notes) + [
                "真实 PNG16 源经高精度输入色彩转换与浮点编辑/几何，仅交付边界量化为 RGB8"]}
    else:
        internal = _internal_geometry(spec)
        frame, stats = export_image(decoded.rgb, spec, device=device, tile=tile,
            geometry=(crop_rect, rotation_degrees) if internal else None)
        if not internal:
            from .ops.geometry import crop_rotate_np, is_identity
            started = perf_counter()
            frame = crop_rotate_np(frame, crop_rect, rotation_degrees)
            stats = {**stats, "geometry_ms": round((perf_counter() - started) * 1000, 2),
                "crop_applied": not is_identity(crop_rect, rotation_degrees)}
    height, width = frame.shape[:2]
    return frame, {**stats, "w": width, "h": height, "px": width * height}
