"""Prepare an exact parked graph target through the shared full-source exporter.

The planner foundation does not admit generic batch commands. Original files
remain provenance anchors; a returned canvas supplies its own canonical pixels.
"""
def validate(engine,row,candidate):
    from copy import deepcopy
    from . import local_mask_state as M
    from . import creative_derived_source as SOURCE, virtual_copy_people as V
    from .creative_document_base import from_state, require_rebound_snapshot
    from .decode import load_full,is_raw,_source_bits
    from .cpu_memory_budget import available_estimate
    from .export_recipe import build_export_spec
    from .export import export_float
    from . import local_grade_source as groups,effect_recovery_runtime as recovery
    from . import manual_liquify_runtime as manual,studio_background_runtime as studio,sky_replacement_runtime as sky
    from PIL import Image
    path=row['path'];stamp=M.file_stamp(path);version=engine._document_versions().version(row)
    proof=SOURCE.row_proof(row);state=deepcopy(row['state']);context=V.row_context(engine,row)
    base=from_state(state)
    available=available_estimate();limit=min(32_000_000,max(0,(available-768*1024*1024)//300))
    if limit<4096:raise ValueError('Insufficient memory for complete people target preparation')
    if base is not None:
        h,w=base['height'],base['width']
        if h*w>limit:raise ValueError('Creative target exceeds the portrait preparation budget; no proxy fallback')
        SOURCE.verify_precompute(state,state.get('_precompute'))
        # The public exporter resolves spec.creative_base exactly once through
        # the packaged float32 bridge. This empty shape carrier is never read
        # as image pixels and avoids decoding or quantizing the original file.
        import numpy as np
        pixels=np.empty((0,0,3),dtype=np.uint8)
    else:
        if is_raw(path):
            from .ops import libraw
            dimensions=libraw.identify(path)
            if dimensions is None or dimensions['w']*dimensions['h']>limit:raise ValueError('Original RAW target exceeds the available portrait budget')
            bits=16
        else:
            with Image.open(path) as image:
                if image.width*image.height>limit:raise ValueError('Original target exceeds the portrait preparation budget')
                bits=16 if _source_bits(image)>8 else 8
        decoded=load_full(path,max_px=limit,device='cpu',want_bits=bits)
        if (decoded.h,decoded.w)!=(decoded.src_h,decoded.src_w) or decoded.draft_used or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size'):
            raise ValueError('People target preparation cannot use reduced source pixels')
        pixels=decoded.rgb;h,w=decoded.h,decoded.w
    snap=engine._state_to_export_snap(state,device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0.,source_path=path,people_graph=candidate,people_context=context)
    from .people_export import isolated_snapshot,verify_source
    verify_source(snap,path);snap=isolated_snapshot(snap,for_document=True)
    if base is not None:
        people=snap.get('people')
        if people is None or people['state']!=candidate or people['asset_sha256']!=proof['asset_sha256']:
            raise ValueError('Creative target preparation omitted its exact candidate portrait graph')
        frozen_base=from_state(snap)
        if frozen_base is None or frozen_base['id']!=base['id']:
            raise ValueError('Creative target snapshot replaced its immutable source')
        require_rebound_snapshot(snap)
    from . import body_pose_render as body_render, id_background_runtime as id_background
    for owner in (groups,recovery,manual,studio,sky,body_render,id_background):owner.check_export_decode(snap,path,stamp,(h,w))
    if snap.get('grade_scope')=='objects':
        M.verify_snapshot(snap,path,(h,w));snap['local_mask_source_path']=path
    spec,skipped=build_export_spec(snap,h,w,for_document=True)
    if skipped:raise ValueError('People target preparation cannot omit existing edits: '+str(skipped))
    export_float(pixels,spec,geometry=(snap['crop_rect'],snap['crop_rotation']))
    SOURCE.verify_row(row,proof)
    if M.file_stamp(path)!=stamp or engine._document_versions().version(row)!=version or V.row_context(engine,row)!=context:
        raise ValueError('People target changed during preparation')
