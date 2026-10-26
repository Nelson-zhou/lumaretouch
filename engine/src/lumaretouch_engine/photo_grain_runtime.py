"""True-source preview render via the canonical export recipe and renderer.

No preview-sized grain. Decode/ICC and all source-bound recipe guards match export.
The private full canvas is sampled only after all editing, including monochrome.
"""
import numpy as np
from . import photo_grain_state as S
from . import fringe_repair_render as FR


def available():
    try:
        from .photo_grain_native import native
        native()
        return True
    except (OSError,RuntimeError,AttributeError):return False


def active(engine):
    recipe=getattr(engine,'_photo_grain_render_override',None)
    return S.active(recipe if recipe is not None else getattr(engine,S.KEY,S.neutral()))


def admit(w,h,scale=1):
    from .cpu_memory_budget import available_estimate
    if min(w,h)<1 or max(w,h)>1000000 or w*h>100000000:
        raise ValueError('Full-source grain exceeds 100MP bounds; no proxy fallback')
    # Conservative future source render + transformed canvas + delivery target.
    reserve=w*h*(160+24*scale*scale)+512*1024*1024
    if reserve>available_estimate():raise ValueError('Insufficient admitted memory for full-source grain; no silent proxy rendering')
    return reserve


def render_preview(engine, *, pack=True, editor_mode=None):
    from .decode import load_full
    from .local_mask_state import file_stamp
    from .export import export_image, export_image16, _srgb_bytes
    from .export_recipe import build_export_spec
    from . import local_mask_state as LM, local_grade_source as LG
    from . import effect_recovery_runtime as ER, manual_liquify_runtime as ML
    from . import studio_background_runtime as SB, optics_runtime as OP, sky_replacement_runtime as SK
    from .reference_color_runtime import verify_export
    from . import body_pose_render as BP
    import torch
    import torch.nn.functional as F
    path=engine._doc_path
    if not path:raise ValueError('Grain preview requires saved original source')
    row=engine._docs[engine._doc_index]
    w,h=row.get('src_w'),row.get('src_h')
    if not w or not h:raise ValueError('Grain preview missing verified original dimensions')
    admit(w,h)
    if FR.active(engine) or getattr(engine,'_fringe_repair_capture_coverage',False):
        FR.admit(w,h,(tuple(engine._crop_rect),float(engine._crop_rotation)))
    if getattr(engine,'_fringe_repair_capture_coverage',False):
        engine._fringe_repair_review_coverage=None
    before=file_stamp(path);document=str(engine._load_id)
    from .extended_tone_host import revision
    rev=revision(engine)
    def cancelled():
        if editor_mode=="input" and engine._colour_editor_service().capture_cancel.is_set():return True
        if getattr(engine,'_photo_grain_cancelled',lambda:False)():return True
        for key in ('_colour_editor_cancelled','_colour_grading_cancelled','_selective_colour_cancelled','_primary_calibration_cancelled','_photo_detail_cancelled','_extended_tone_cancelled','_fringe_repair_cancelled'):
            if getattr(engine,key,lambda:False)():return True
        return str(engine._load_id)!=document or revision(engine)!=rev
    def progress(*_):
        if cancelled():raise InterruptedError('Grain source preview superseded')
    progress()
    state=engine._capture_state()
    override=getattr(engine,'_photo_grain_render_override',None)
    if override is not None:state={**state,S.KEY:S.check(override)}
    fringe_override=getattr(engine,'_fringe_repair_render_override',None)
    if fringe_override is not None:
        from . import fringe_repair_state as FS
        state={**state,FS.KEY:FS.check(fringe_override)}
    # These existing temporary preview stages intentionally do not persist state.
    for name in ('colour_editor','colour_grading','selective_colour','primary_calibration'):
        if getattr(engine,'_'+name+'_preview_active',False):
            stage=getattr(engine._vram,name,None)
            recipe=getattr(stage,'recipe',None)
            if recipe is None:raise ValueError('Cannot resolve concurrent colour preview recipe')
            state={**state,'_'+name:recipe}
    snap=engine._state_to_export_snap(state,device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0,source_path=path)
    snap,for_doc=engine._prepare_export_snapshot(path,snap,True)
    from .creative_document_base import source_shape
    creative_base=snap.get('creative_base') is not None
    # The original file still owns source identity and decode guards. A baked
    # canvas separately owns the render dimensions and float working pixels.
    # RGB8 here is only an unused original-file decode, never the creative
    # source and never a fallback for its full-float asset.
    d=load_full(path,max_px=100000000,device='cpu',want_bits=8 if creative_base else 16)
    original_hw=(d.src_h,d.src_w)
    if (d.h,d.w)!=original_hw or d.draft_used or (d.raw or {}).get('used_preview'):
        raise ValueError('Grain requires original-resolution decode, not camera/display proxy')
    if source_shape(snap,original_hw)!=(h,w):
        raise ValueError('Grain render dimensions no longer match the current pixel source')
    if file_stamp(path)!=before:raise ValueError('Grain source changed during decode')
    from . import common_background_source as common_background
    for module in (LM,LG,ER,ML,SB,OP,SK,common_background):module.check_export_decode(snap,path,before,original_hw)
    BP.check_export_decode(snap,path,before,original_hw);verify_export(snap,path,original_hw)
    from .hand_shape_runtime import check_export_decode as hand_shape_decode
    hand_shape_decode(snap,path,before,original_hw)
    FR.check_export_decode(snap,path,before,original_hw)
    if snap.get("grade_scope")=="objects":snap["local_mask_source_path"]=path
    spec,skipped=build_export_spec(snap,h,w,for_document=for_doc)
    if skipped:raise ValueError('Full-source grain preview cannot omit layers: '+', '.join(map(str,skipped)))
    spec.float_output=True
    spec._fringe_repair_capture_coverage=bool(getattr(engine,'_fringe_repair_capture_coverage',False))
    if editor_mode is not None:
        spec._colour_editor_mode=editor_mode
        from .colour_editor_native import FullDomain
        domain=engine.__dict__.get('_colour_editor_domain_cache')
        if domain is None: domain=FullDomain();engine._colour_editor_domain_cache=domain
        spec._colour_editor_domain=domain
    geometry=(tuple(snap['crop_rect']),float(snap['crop_rotation']))
    source=d.rgb
    if source.dtype==np.uint16:
        if d.source_icc and not creative_base:
            from .color16 import convert_rgb16
            source=convert_rgb16(source,d.source_icc,_srgb_bytes())
        full,_=export_image16(source,spec,device='cpu',progress=progress,crop_rect=geometry[0],rotation_degrees=geometry[1],output_domain='final' if pack else 'processing')
    elif source.dtype==np.uint8:
        if not creative_base and ((d.raw or {}) or int(d.src_bits)>8):raise ValueError('High-bit-depth grain source cannot use RGB8')
        full,_=export_image(source,spec,device='cpu',progress=progress,geometry=geometry,output_domain='final' if pack else 'processing')
    else:raise ValueError('Unsupported original grain source precision')
    progress()
    if file_stamp(path)!=before:raise ValueError('Grain source changed during render')
    tensor=torch.from_numpy(np.ascontiguousarray(full,dtype=np.float32)).permute(2,0,1)[None]
    target=(engine._vram.h,engine._vram.w)
    if tuple(tensor.shape[-2:])!=target:
        # Area averages genuine full-source grain; never sample fresh proxy noise.
        tensor=F.interpolate(tensor,size=target,mode='area')
    progress()
    if editor_mode=='input':
        coverage=getattr(spec,'_colour_editor_capture_coverage',None)
        if coverage is None:raise ValueError('Verified editor input missing source coverage')
        coverage_t=torch.from_numpy(np.ascontiguousarray(coverage,dtype=np.float32))[None,None]
        if tuple(coverage_t.shape[-2:])!=target:coverage_t=F.interpolate(coverage_t,size=target,mode='area')
        engine._colour_editor_input_coverage=coverage_t.to(engine._vram.device)
    if spec._fringe_repair_capture_coverage:
        coverage=getattr(spec,'_fringe_repair_coverage',None)
        if coverage is not None:
            coverage_t=torch.from_numpy(np.ascontiguousarray(coverage,dtype=np.float32))[None,None]
            if tuple(coverage_t.shape[-2:])!=target:
                coverage_t=F.interpolate(coverage_t,size=target,mode='area')
            engine._fringe_repair_review_coverage=coverage_t.to(engine._vram.device)
            del spec._fringe_repair_coverage
        elif editor_mode not in ('input','view'):
            raise ValueError('Fringe review lacks its actual processing-eligibility mask')
    tensor=tensor.to(engine._vram.device)
    if pack:engine._vram.pack(tensor)
    engine._sky_proxy_suspended=None
    return tensor
