"""Full-source export-quality inspection core, not yet a UI/transport feature.

Process the whole edited image before cropping. Cropping the source first changes
repair, deformation and semantic statistics. Callers must enforce memory admission
before decoding, freeze the recipe, and reject stale results before publication.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .export import ExportError, ExportSpec, DEFAULT_TILE, render_edited_rgb16, export_image, export_image16
from .ops.geometry import check as check_geometry, out_size, crop_rotate_np


class RefinementCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionPixels:
    rgba: np.ndarray
    canvas_width: int
    canvas_height: int
    roi: tuple[int, int, int, int]
    decoded_bits: int
    source_bits: int | None = None
    display_profile: str = 'sRGB'
    quality_mode: str = 'full_source_export'


def render_inspection_roi(decoded, spec: ExportSpec, roi, *, max_source_pixels: int,
                          max_display_pixels: int, device='cpu', tile=DEFAULT_TILE,
                          crop_rect=(0., 0., 1., 1.), rotation_degrees=0.,
                          skipped_layers=(), cancelled=lambda: False):
    """ROI coordinates are x,y,width,height in the FINAL edited canvas, not proxy pixels.

    Source precision is retained until the final display conversion. This shares
    current export parameter semantics, not a claim of resolution-normalized radii
    or calibrated monitor management. It never writes an export file or edits state.
    """
    def check_cancel():
        if cancelled():raise RefinementCancelled('full-source inspection cancelled')
    check_cancel()
    if skipped_layers:
        raise ExportError('Accurate inspection cannot silently omit layers: '+', '.join(map(str,skipped_layers)))
    if type(max_source_pixels) is not int or type(max_display_pixels) is not int or min(max_source_pixels,max_display_pixels)<=0:
        raise ValueError('Explicit positive source/display pixel budgets required')
    from .creative_document_base import check as check_base, require_rebound_spec
    base = check_base(spec.creative_base)
    if base is not None:
        require_rebound_spec(spec)
        height, width = base['height'], base['width']
        source = None
        raw = {}
    else:
        source=decoded.rgb
        if source.ndim!=3 or source.shape[2]!=3 or source.dtype not in (np.dtype('uint8'),np.dtype('uint16')):
            raise ExportError('Full-source RGB8 or RGB16 required')
        height,width=source.shape[:2]
        raw=decoded.raw or {}
        if (width,height)!=(decoded.src_w,decoded.src_h) or decoded.draft_used or raw.get('used_preview') is True or raw.get('source')=='libraw_preview' or raw.get('half_size',False) not in (False,0,None):
            raise ExportError('Display proxies/camera previews cannot become full-quality source')
        if source.dtype==np.uint8 and (raw or int(decoded.src_bits)>8):
            raise ExportError('High-bit-depth source requires its true RGB16 decode')
    if width*height>max_source_pixels:
        raise ExportError('Source exceeds admitted full-quality pixel budget; no silent downscale')
    if spec.scale!=1 or spec.sharpen_amount!=0:
        raise ExportError('100% inspection excludes export-only resizing/sharpening')
    check_geometry(crop_rect,rotation_degrees)
    canvas_width,canvas_height=out_size(width,height,crop_rect,rotation_degrees)
    if not isinstance(roi,(tuple,list)) or len(roi)!=4 or any(type(v) is not int for v in roi):
        raise ValueError('ROI must contain integer x,y,width,height')
    x,y,w,h=roi
    if min(x,y)<0 or min(w,h)<=0 or x+w>canvas_width or y+h>canvas_height:
        raise ValueError('ROI is outside final edited canvas')
    if w*h>max_display_pixels:
        raise ExportError('ROI exceeds display pixel budget; no silent downscale')
    spec.check()
    def progress(*_):check_cancel()
    if base is not None:
        # Public export resolver owns the single canonical float32 conversion.
        # Empty carrier is never rendered and does not impersonate original
        # pixels. Crop/rotation are applied exactly once at baked dimensions.
        full,_=export_image16(np.empty((0,0,3),np.uint16),spec,device=device,tile=tile,
            progress=progress,crop_rect=crop_rect,rotation_degrees=rotation_degrees)
    elif source.dtype==np.uint16:
        full,_,_=render_edited_rgb16(decoded,spec,device=device,tile=tile,crop_rect=crop_rect,
                                    rotation_degrees=rotation_degrees,output_profile='srgb',progress=progress)
    else:
        # load_full RGB8 already converts embedded ICC into working sRGB.
        from .reference_color_state import active as reference_active
        from .photo_detail_state import active as detail_active
        from .photo_grain_state import active as grain_active
        from .fringe_repair_state import active as fringe_active
        from .colour_editor_state import active as editor_active, neutral as editor_neutral
        from .final_canvas_flip_state import active as flip_active
        matching=flip_active(spec.final_canvas_flip) or editor_active(spec.colour_editor if spec.colour_editor is not None else editor_neutral()) or reference_active(spec.reference_color) or detail_active(spec.photo_detail) or grain_active(spec.photo_grain) or fringe_active(spec.fringe_repair)
        full,_=export_image(source,spec,device=device,tile=tile,progress=progress,geometry=(crop_rect,rotation_degrees) if matching else None)
        check_cancel()
        if not matching:full=crop_rotate_np(full,crop_rect,rotation_degrees)
    check_cancel()
    if full.shape[:2]!=(canvas_height,canvas_width):
        raise ExportError('Rendered canvas dimensions differ from ROI coordinate contract')
    if full.dtype not in (np.dtype('uint8'), np.dtype('uint16')):
        raise ExportError('Inspection display conversion requires final RGB8/RGB16, not unchecked float output')
    patch=full[y:y+h,x:x+w]
    rgb=((patch.astype(np.uint32)+128)//257).astype(np.uint8) if patch.dtype==np.uint16 else patch
    rgba=np.empty((h,w,4),np.uint8);rgba[...,:3]=rgb;rgba[...,3]=255
    check_cancel()
    return InspectionPixels(rgba,canvas_width,canvas_height,(x,y,w,h),
        decoded_bits=32 if base is not None else 16 if source.dtype==np.uint16 else 8,
        source_bits=None if base is not None else int(decoded.src_bits) if raw.get("source") in (None,"tiff16","png16") else None)
