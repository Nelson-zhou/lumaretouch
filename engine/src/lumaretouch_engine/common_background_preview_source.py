"""Disposable preview fields and content proofs for common replacement."""
import json
import numpy as np
from . import local_mask_state as M,creative_derived_source as D
from .creative_derived_common_background import hash_pixels,preview_pixels,validate_state


def field_proof(pipe):
    def tensor(value):
        if value is None:return None
        return hash_pixels(value.detach().cpu().numpy())
    return (bool(pipe.has_background()),tensor(pipe.bg_matte),tensor(pipe.bg_ref),
        bool(getattr(pipe,'_common_background_preserve',False)))


def source_key(engine):
    from .common_background_source import check
    bg=engine._bg;value=check(bg);pipe=engine._vram
    row=engine._docs[engine._doc_index];stamp=M.file_stamp(row['path'])
    if row.get('_local_source_stamp')!=stamp:raise ValueError('Common source changed after preview decode')
    derived=D.record(engine) is not None
    if derived:
        validate_state(engine);preview_pixels(engine)
        if value is not None:
            candidate=(json.dumps(value,sort_keys=True),stamp,id(pipe.src_f32))
            if getattr(pipe,'_common_verified_original',None)!=candidate:
                if M.source_digest(row['path'])!=value['original_sha256']:
                    raise ValueError('Common original provenance changed')
                pipe._common_verified_original=candidate
    elif value is not None:
        if value['version']!=1:raise ValueError('Common derived recipe cannot bind original source')
        # Hash on recipe/pipeline changes, not every slider frame.
        candidate=(json.dumps(value,sort_keys=True),stamp,id(pipe.src_f32))
        if getattr(pipe,'_common_verified_original',None)!=candidate:
            M.verify_source(value,row['path'],(row['src_h'],row['src_w']))
            pipe._common_verified_original=candidate
    return (json.dumps({'recipe':value,'active':bg.get('active'),'bg':bg.get('bg')},sort_keys=True,allow_nan=False),
        stamp,id(pipe.src_f32),int(pipe.src_f32._version))


def install(engine):
    from .common_background_source import check
    from .ops.matting import key_matte_np
    bg=engine._bg;value=check(bg);pipe=engine._vram
    if value is None:
        if D.record(engine) is not None:validate_state(engine)
        if not bg.get('active'):pipe.clear_background()
        elif bg.get('matte') is not None:pipe.set_background(bg['matte'],bg['bg'])
        else:raise ValueError('Common background retained matte is missing')
        return
    key=source_key(engine)
    if bg['active']:
        pixels=preview_pixels(engine) if value['version']==2 else engine._src_rgb
        if pixels is None or pixels.shape[:2]!=(pipe.h,pipe.w):raise ValueError('Common source preview grid unavailable')
        alpha=key_matte_np(pixels,ref=value['reference'],tol=value['tol'],softness=value['softness'])
        matte=alpha.astype(np.float32) if value['version']==2 else np.rint(alpha*255.).astype(np.uint8)
        pipe.set_background(matte,bg['bg'],preserve_extended=value['version']==2);engine._bg=dict(bg,matte=matte)
    else:pipe.clear_background()
    if key!=source_key(engine):raise ValueError('Common preview source changed during preparation')
    pipe._common_background_source_key=key
    pipe._common_background_field_proof=field_proof(pipe)


def verify_live(engine):
    from .common_background_source import check
    value=check(getattr(engine,'_bg',None))
    if value is None:
        if D.record(engine) is not None:validate_state(engine)
        return
    pipe=engine._vram;key=source_key(engine)
    if getattr(pipe,'_common_background_source_key',None)!=key:install(engine)
    elif getattr(pipe,'_common_background_field_proof',None)!=field_proof(pipe):
        raise ValueError('Common prepared matte or background changed after installation')


def consumer_proof(engine):
    from .common_background_source import check
    verify_live(engine);bg=engine._bg;pipe=engine._vram
    value=check(bg);source=D.binding(engine)
    pixels=preview_pixels(engine) if D.record(engine) is not None else pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy()
    if not np.isfinite(pixels).all():raise ValueError('Invalid common recovery input pixels')
    proof=field_proof(pipe)
    if bool(bg.get('active'))!=proof[0]:raise ValueError('Common recipe and installed activity disagree')
    return {'source':source,'recipe':value,'color':bg.get('bg'),'active':proof[0],
        'input_sha256':hash_pixels(pixels),'matte_sha256':proof[1],'background_sha256':proof[2],
        'shape':[pipe.h,pipe.w],'preserve_extended':proof[3]}
