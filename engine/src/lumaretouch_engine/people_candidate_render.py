"""Prepare a parked graph target with the existing original-source export path."""
def validate(engine,row,candidate):
    # Returned pixels already contain the original portrait intent. That graph
    # is dormant for undo, not a target for a new cross-document mutation. Fail
    # before original-file decode or snapshot capture can ignore the candidate
    # and incorrectly certify an unchanged baked canvas as a successful edit.
    if (row.get('state') or {}).get('_creative_base') is not None:
        raise ValueError('People transfer target is a creative baseline; derived-source portrait preflight is required')
    from . import local_mask_state as M
    from .decode import load_full,is_raw,_source_bits
    from .cpu_memory_budget import available_estimate
    from .export_recipe import build_export_spec
    from .export import export_float
    from . import local_grade_source as groups,effect_recovery_runtime as recovery
    from . import manual_liquify_runtime as manual,studio_background_runtime as studio,sky_replacement_runtime as sky
    from PIL import Image
    path=row['path'];stamp=M.file_stamp(path);version=engine._document_versions().version(row)
    available=available_estimate();limit=min(32_000_000,max(0,(available-768*1024*1024)//300))
    if limit<4096:raise ValueError('Insufficient memory for complete people target preparation')
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
    snap=engine._state_to_export_snap(row['state'],device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0.,source_path=path,people_graph=candidate)
    from .people_export import isolated_snapshot,verify_source
    verify_source(snap,path);snap=isolated_snapshot(snap,for_document=True)
    from . import body_pose_render as body_render, id_background_runtime as id_background
    for owner in (groups,recovery,manual,studio,sky,body_render,id_background):owner.check_export_decode(snap,path,stamp,(decoded.h,decoded.w))
    if snap.get('grade_scope')=='objects':
        M.verify_source(M.check(snap.get('local_masks')),path,(decoded.h,decoded.w));snap['local_mask_source_path']=path
    spec,skipped=build_export_spec(snap,decoded.h,decoded.w,for_document=True)
    if skipped:raise ValueError('People target preparation cannot omit existing edits: '+str(skipped))
    export_float(decoded.rgb,spec,geometry=(snap['crop_rect'],snap['crop_rotation']))
    if M.file_stamp(path)!=stamp or engine._document_versions().version(row)!=version:
        raise ValueError('People target changed during preparation')
