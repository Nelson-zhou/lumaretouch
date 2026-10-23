"""True-source preview render via the canonical export recipe and renderer.

No preview-sized grain. Decode/ICC and all source-bound recipe guards match export.
The private full canvas is sampled only after all editing, including monochrome.
"""
import numpy as np
from . import photo_grain_state as S


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


def render_preview(engine, *, pack=True):
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
    before=file_stamp(path);document=str(engine._load_id)
    from .extended_tone_host import revision
    rev=revision(engine)
    def cancelled():
        if getattr(engine,'_photo_grain_cancelled',lambda:False)():return True
        for key in ('_colour_grading_cancelled','_selective_colour_cancelled','_primary_calibration_cancelled','_photo_detail_cancelled','_extended_tone_cancelled'):
            if getattr(engine,key,lambda:False)():return True
        return str(engine._load_id)!=document or revision(engine)!=rev
    def progress(*_):
        if cancelled():raise InterruptedError('Grain source preview superseded')
    progress()
    state=engine._capture_state()
    override=getattr(engine,'_photo_grain_render_override',None)
    if override is not None:state={**state,S.KEY:S.check(override)}
    # These existing temporary preview stages intentionally do not persist state.
    for name in ('colour_grading','selective_colour','primary_calibration'):
        if getattr(engine,'_'+name+'_preview_active',False):
            stage=getattr(engine._vram,name,None)
            recipe=getattr(stage,'recipe',None)
            if recipe is None:raise ValueError('Cannot resolve concurrent colour preview recipe')
            state={**state,'_'+name:recipe}
    snap=engine._state_to_export_snap(state,device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0,source_path=path)
    snap,for_doc=engine._prepare_export_snapshot(path,snap,True)
    d=load_full(path,max_px=100000000,device='cpu',want_bits=16)
    if (d.w,d.h)!=(w,h) or (d.src_w,d.src_h)!=(w,h) or d.draft_used or (d.raw or {}).get('used_preview'):
        raise ValueError('Grain requires original-resolution decode, not camera/display proxy')
    if file_stamp(path)!=before:raise ValueError('Grain source changed during decode')
    for module in (LM,LG,ER,ML,SB,OP,SK):module.check_export_decode(snap,path,before,(h,w))
    BP.check_export_decode(snap,path,before,(h,w));verify_export(snap,path,(h,w))
    if snap.get("grade_scope")=="objects":snap["local_mask_source_path"]=path
    spec,skipped=build_export_spec(snap,h,w,for_document=for_doc)
    if skipped:raise ValueError('Full-source grain preview cannot omit layers: '+', '.join(map(str,skipped)))
    spec.float_output=True
    geometry=(tuple(snap['crop_rect']),float(snap['crop_rotation']))
    source=d.rgb
    if source.dtype==np.uint16:
        if d.source_icc:
            from .color16 import convert_rgb16
            source=convert_rgb16(source,d.source_icc,_srgb_bytes())
        full,_=export_image16(source,spec,device='cpu',progress=progress,crop_rect=geometry[0],rotation_degrees=geometry[1])
    elif source.dtype==np.uint8:
        if (d.raw or {}) or int(d.src_bits)>8:raise ValueError('High-bit-depth grain source cannot use RGB8')
        full,_=export_image(source,spec,device='cpu',progress=progress,geometry=geometry)
    else:raise ValueError('Unsupported original grain source precision')
    progress()
    if file_stamp(path)!=before:raise ValueError('Grain source changed during render')
    tensor=torch.from_numpy(np.ascontiguousarray(full,dtype=np.float32)).permute(2,0,1)[None]
    target=(engine._vram.h,engine._vram.w)
    if tuple(tensor.shape[-2:])!=target:
        # Area averages genuine full-source grain; never sample fresh proxy noise.
        tensor=F.interpolate(tensor,size=target,mode='area')
    progress()
    tensor=tensor.to(engine._vram.device)
    if pack:engine._vram.pack(tensor)
    engine._sky_proxy_suspended=None
    return tensor
