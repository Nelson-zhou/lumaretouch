"""Versioned deterministic legacy key replay, not a neural/full-resolution claim.

The border reference is frozen from the actual source proxy grid to preserve
existing key appearance. Full exports evaluate that same key on genuine decoded
RGB8/RGB16 pixels. Old unversioned mattes remain explicitly proxy-bound.
"""
from copy import deepcopy
import math
import re
from . import local_mask_state as M

CONTRACT = 'legacy-color-key-frozen-reference-v1'
MAX_PIXELS = 32_000_000


def check(bg):
    if bg is None:return None
    if type(bg) is not dict:raise ValueError('Invalid common background state')
    value=bg.get('key_recipe')
    if value is None:return None
    if type(bg.get('active')) is not bool:raise ValueError('Invalid common background active state')
    if type(value) is not dict or set(value)!={'version','contract','source','reference','reference_grid','tol','softness'}:
        raise ValueError('Invalid versioned common background key')
    if type(value['version']) is not int or value['version']!=1 or value['contract']!=CONTRACT or bg.get('backend')!='color_key':
        raise ValueError('Unsupported common background replay contract')
    source=value['source']
    if type(source) is not dict or set(source)!={'sha256','width','height'} or type(source.get('sha256')) is not str or not re.fullmatch('[0-9a-f]{64}',source['sha256']):
        raise ValueError('Common background source identity missing')
    for key in ('width','height'):
        if type(source[key]) is not int or source[key]<1:raise ValueError('Invalid common background source dimensions')
    grid=value['reference_grid']
    if type(grid) is not list or len(grid)!=2 or any(type(v) is not int or v<1 for v in grid):
        raise ValueError('Invalid common background reference grid')
    ref=value['reference']
    if type(ref) is not list or len(ref)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in ref):
        raise ValueError('Invalid common background key reference')
    for key,lo in (('tol',0.),('softness',.001)):
        v=value[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=1 or bg.get(key)!=v:
            raise ValueError('Common background key parameters disagree with retained state')
    color=bg.get('bg')
    if type(color) not in (list,tuple) or len(color)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in color):
        raise ValueError('Invalid common background solid color')
    return deepcopy(value)


def capture(engine,source,*,tol,softness):
    if getattr(engine,'_creative_base',None) is not None:
        raise ValueError('Common background derived-source acquisition awaits reviewed transport')
    from .ops.matting import _edge_median,_to_unit
    return {'version':1,'contract':CONTRACT,'source':M.bind_source(engine),
        'reference':_edge_median(_to_unit(source)).tolist(),
        'reference_grid':[int(source.shape[1]),int(source.shape[0])],
        'tol':tol,'softness':softness}


def verify_snapshot(snap,path,shape=None):
    value=check(snap.get('_bg'))
    if value is None:return
    if snap.get('creative_base') is not None or snap.get('_creative_base') is not None:
        raise ValueError('Legacy key cannot reuse original analysis on a creative source')
    M.verify_source(value,path,shape)


def check_export_decode(snap,path,before,shape):
    if check(snap.get('_bg')) is None:return
    if before is None or M.file_stamp(path)!=before:raise ValueError('Common background source changed during decode')
    verify_snapshot(snap,path,shape)
    if M.file_stamp(path)!=before:raise ValueError('Common background source changed during verification')
    snap['common_background_path']=path;snap['common_background_stamp']=list(before)


def verify_live(engine):
    import json
    bg=getattr(engine,'_bg',None);value=check(bg)
    if value is None:return
    row=engine._docs[engine._doc_index];stamp=M.file_stamp(row['path'])
    if row.get('_local_source_stamp')!=stamp:raise ValueError('Common background source changed after preview decode')
    if getattr(engine,'_creative_base',None) is not None:raise ValueError('Legacy key is not a derived-source recipe')
    key=(json.dumps(value,sort_keys=True),stamp,id(engine._vram.src_f32))
    if getattr(engine._vram,'_common_background_source_key',None)!=key:
        M.verify_source(value,row['path'],(row['src_h'],row['src_w']))
        engine._vram._common_background_source_key=key


def configure_export(spec,snap,*,for_document):
    value=check(snap.get('_bg'))
    if value is None or not snap['_bg'].get('active'):return False
    if not for_document:raise ValueError('Common background key belongs to one source, not another batch target')
    if spec.creative_base is not None:raise ValueError('Common background derived replay is not yet supported')
    spec.common_background_key=value
    spec.common_background_path=snap.get('common_background_path')
    spec.common_background_stamp=snap.get('common_background_stamp')
    # The disposable matte is produced only after full source pixels arrive.
    spec.common_background_color=tuple(snap['_bg']['bg'])
    return True


def prepare_export(spec,pixels,*,cancelled=lambda:False):
    value=spec.common_background_key
    if value is None:return
    value=check({'active':True,'key_recipe':value,'backend':'color_key','tol':value.get('tol'),'softness':value.get('softness'),'bg':spec.common_background_color})
    if spec.creative_base is not None:raise ValueError('Common background cannot consume a derived source yet')
    import numpy as np
    from .ops.matting import key_matte_np
    from .cpu_memory_budget import available_estimate
    spec.bg_matte=None;spec.bg_ref=None
    if pixels.ndim!=3 or pixels.shape[2]!=3 or pixels.dtype not in (np.uint8,np.uint16):
        raise ValueError('Common background requires genuine decoded RGB8/RGB16, not clipped float/HDR')
    h,w=pixels.shape[:2]
    if h*w>MAX_PIXELS or h*w*4+w*256*96>max(0,available_estimate()-256*1024*1024):
        raise ValueError('Full common background matte exceeds memory budget; no proxy fallback')
    finish_export(spec)
    M.verify_source(value,spec.common_background_path,(h,w))
    matte=np.empty((h,w),dtype=np.float32)
    divisor=65535. if pixels.dtype==np.uint16 else 255.
    for y in range(0,h,256):
        if cancelled():raise InterruptedError('Common background replay cancelled')
        stripe=pixels[y:y+256].astype(np.float64)/divisor
        matte[y:y+256]=key_matte_np(stripe,ref=value['reference'],tol=value['tol'],softness=value['softness'])
    finish_export(spec)
    spec.bg_matte=matte;spec.bg_ref=spec.common_background_color


def finish_export(spec):
    if spec.common_background_key is None:return
    if not spec.common_background_path or spec.common_background_stamp is None or list(M.file_stamp(spec.common_background_path))!=spec.common_background_stamp:
        raise ValueError('Common background full-source decode identity missing or changed')


def preserve_proxy_recipe(state,out):
    """Retain durable intent across proxy changes; never retain its old bitmap."""
    value=check(state.get('_bg'))
    if value is not None:
        out['_bg']=dict(state['_bg'],key_recipe=value,matte=None)


def rehang(engine,pipe,emit):
    bg=engine._bg;value=check(bg)
    if value is not None:
        verify_live(engine)
        if not bg.get('active'):return
        import numpy as np
        from .ops.matting import key_matte_np
        pixels=engine._src_rgb
        if pixels is None or pixels.shape[:2]!=(pipe.h,pipe.w):raise ValueError('Common background preview source grid unavailable')
        alpha=key_matte_np(pixels,ref=value['reference'],tol=value['tol'],softness=value['softness'])
        matte=np.rint(alpha*255.).astype(np.uint8)
        pipe.set_background(matte,bg['bg'])
        engine._bg=dict(bg,matte=matte)
        return
    # Historical proxy records keep their prior migration behavior. They are
    # not silently reinterpreted as new deterministic source recipes.
    if bg.get('active') and bg.get('matte') is not None:
        try:pipe.set_background(bg['matte'],bg['bg'])
        except (RuntimeError,ValueError) as error:
            emit({'event':'engine_warn','warn':f'旧代理换底重挂失败，已整层清除：{error}'})
            engine._bg=dict(active=False,matte=None,bg=None,backend=None,tol=None,softness=None)
