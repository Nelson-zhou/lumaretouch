# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual full rendered input after geometry + PC32455, before this AI group.

Deliberately does NOT call reference_color_engine.render: that path clears
PC32455 and uses original-scene provenance for a different same-scene feature.
"""
from copy import deepcopy
from . import semantic_colour_state as S, local_mask_state as M
from .optics_candidate_identity import fingerprint


def candidate_key(state,people=None):
    return fingerprint({'state':{k:v for k,v in state.items() if k not in (S.KEY,'_semantic_colour_bundle','_semantic_colour_mask_assets')},'people':people})

def material_key(state):
    """Pixel-source ownership changes, distinct from ordinary colour sliders."""
    out={'repairs':state.get('_repair_ops',[])}
    bg=state.get('_bg') or {}
    out['background']=({k:bg.get(k) for k in ('active','matte','backend','tol','softness')}
                       if bg.get('active') else None)  # Uniform bg colour is editable.
    sky=state.get('_sky_replacement') or {}
    if sky.get('enabled'):
        out['sky']={k:deepcopy(sky.get(k)) for k in ('enabled','source','regions','person_mode','horizon','recovery','semantic')}
        out['sky']['asset']={k:v for k,v in (sky.get('asset') or {}).items() if k!='path'}
        # Temperature/tint/saturation/brightness/scene/person are ordinary colour.
        out['sky']['placement']={k:sky['parameters'][k] for k in ('vertical','horizontal','angle','scale','flip','edge','gradient','blur','opacity','reflection','reflection_blur')}
    else:out['sky']=None
    studio=state.get('_studio_background') or {};params=studio.get('parameters') or {}
    removal={k:params.get(k,0.) for k in ('intrusions','blemish_background','blemish_floor')}
    if any(removal.values()):
        out['studio_removal']={k:studio.get(k) for k in ('source','region_mode','semantic_owner')}
        out['studio_removal']['parameters']=removal
        out['studio_removal']['strokes']=[s for s in studio.get('strokes',[]) if s.get('target') in
            ('background','floor','protect','intrusion','blemish','recover_intrusions','recover_blemishes')]
    else:out['studio_removal']=None
    return out


def geometry_key(state,people=None):
    # Ordinary colour/texture edits and the editing cursor are not geometry.
    geometry={k:state.get(k) for k in ('_crop_rect','_crop_rotation','_manual_liquify')}
    optics=deepcopy(state.get('_optics'))
    if optics:
        optics['lens'].pop('vignette',None);optics['lens'].pop('midpoint',None)
        for key in ('show_guides','guides','analysis'):optics['perspective'].pop(key,None)
    geometry['optics']=optics;geometry['source_material']=material_key(state)
    from .body_pose_render import geometry_record
    body_geometry=geometry_record(state)
    if body_geometry is not None:geometry['body_pose']=body_geometry
    if people is not None:
        from .people_geometry_identity import record
        geometry['people']=record(people)
    else:
        for key in ('_deform','_deform_default','_deform_overrides','_brow_shape','_nose_shape','_eye_shape','_mouth_shape'):
            value=deepcopy(state.get(key))
            if key=='_deform' and value:value.pop('built',None)
            geometry[key]=value
        pc=state.get('_precompute');geometry['landmarks']=getattr(pc,'landmarks',None)
    return fingerprint(geometry)

def render(engine,row,state,document_id,revision,*,cancelled=lambda:False):
    from .decode import load_full,is_raw,_source_bits
    from .export_recipe import build_export_spec
    from .cpu_memory_budget import available_estimate
    from .export import _export_image_impl,DEFAULT_TILE
    from . import local_grade_source as groups,effect_recovery_runtime as recovery,manual_liquify_runtime as manual,studio_background_runtime as studio,sky_replacement_runtime as sky
    from .semantic_colour_canvas import freeze
    from PIL import Image
    if cancelled():raise InterruptedError('AI 追色冻结已取消')
    versions=engine._document_versions();version=versions.version(row)
    if document_id!=version.document_id or str(version.revision)!=str(revision):raise ValueError('AI 追色冻结目标版本改变')
    path=row['path'];stamp=M.file_stamp(path)
    # The actual renderer's original-resolution peak is admitted BEFORE decode.
    # Reserve reference ownership + frozen target + export temporary buffers.
    limit=min(S.MAX_PIXELS,max(0,(available_estimate()-768*1024*1024)//180))
    if limit<4096:raise ValueError('AI 追色完整双图冻结内存不足；不会改用代理图')
    if is_raw(path):
        from .ops import libraw
        dimensions=libraw.identify(path)
        if dimensions is None or dimensions['w']*dimensions['h']>limit:raise ValueError('AI 追色 RAW 原尺寸超出可验证内存预算')
        bits=16
    else:
        with Image.open(path) as image:
            if image.width*image.height>limit:raise ValueError('AI 追色原尺寸超出双图冻结预算')
            bits=16 if _source_bits(image)>8 else 8
    if cancelled():raise InterruptedError('AI 追色冻结已取消')
    decoded=load_full(path,max_px=limit,device='cpu',want_bits=bits)
    if cancelled():raise InterruptedError('AI 追色冻结已取消')
    if (decoded.h,decoded.w)!=(decoded.src_h,decoded.src_w) or decoded.draft_used or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size'):
        raise ValueError('AI 追色要求完整原片渲染，不能使用嵌入预览')
    if bits==16 and str(decoded.rgb.dtype)!='uint16':raise ValueError('AI 追色高位深原图未保留 RGB16')
    if M.file_stamp(path)!=stamp:raise ValueError('AI 追色原图在解码时变化')
    source={'sha256':M.source_digest(path),'width':decoded.w,'height':decoded.h}
    snap=engine._state_to_export_snap(state,device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0.,source_path=path)
    people=snap.get('people');key=candidate_key(state,people);geometry=geometry_key(state,people)
    snap['semantic_colour']=S.empty();snap['semantic_colour_mask_assets']={}  # Only our previous contribution is removed.
    from . import body_pose_render as body_render, id_background_runtime as id_background
    for owner in (groups,recovery,manual,studio,sky,body_render,id_background):owner.check_export_decode(snap,path,stamp,(decoded.h,decoded.w))
    if snap.get('grade_scope')=='objects':
        M.verify_source(M.check(snap.get('local_masks')),path,(decoded.h,decoded.w));snap['local_mask_source_path']=path
    spec,skipped=build_export_spec(snap,decoded.h,decoded.w,for_document=True)
    if skipped:raise ValueError('AI 追色不能省略上游效果：'+', '.join(map(str,skipped)))
    from .reference_color_runtime import verify_export
    verify_export(snap,path,(decoded.h,decoded.w))
    spec.float_output=True;spec.provenance_output=False
    def progress(*_):
        if cancelled():raise InterruptedError('AI 追色冻结已取消')
    rgb,_=_export_image_impl(decoded.rgb,spec,device='cpu',tile=DEFAULT_TILE,progress=progress,bits=bits,geometry=(snap['crop_rect'],snap['crop_rotation']))
    if cancelled() or M.file_stamp(path)!=stamp or str(versions.version(row).revision)!=str(revision):raise ValueError('AI 追色冻结期间目标或源图改变')
    return freeze(rgb,source=source,geometry_sha256=geometry,state_key=key,document_id=document_id,revision=revision,owned=True)
