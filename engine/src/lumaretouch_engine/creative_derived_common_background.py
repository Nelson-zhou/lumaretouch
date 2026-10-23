"""Canonical-source ownership for deterministic common replacement only."""
from copy import deepcopy
from hashlib import sha256
import json
import numpy as np
from . import creative_derived_source as D, local_mask_state as M

CONTRACT='legacy-color-key-effective-v2'


def hash_pixels(value):
    x=np.asarray(value);digest=sha256()
    digest.update(str((tuple(x.shape),str(x.dtype))).encode())
    for row in x:digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return digest.hexdigest()


def sdr(pixels):
    if (type(pixels) is not np.ndarray or pixels.dtype!=np.float32 or pixels.ndim!=3 or pixels.shape[2]!=3
            or not np.isfinite(pixels).all() or np.any(pixels<0) or np.any(pixels>1)):
        raise ValueError('Common replacement requires genuine opaque SDR float32 pixels; no clipping or flattening')
    return pixels


def preview_pixels(engine):
    from .creative_document_host import require_photo_return
    from .creative_derived_repair_runtime import verify_pipeline
    require_photo_return(D.record(engine));source=D.binding(engine)
    verify_pipeline(engine._vram,source)
    pixels=engine._vram.src_f32[0].permute(1,2,0).detach().cpu().numpy()
    return sdr(pixels)


def validate_state(owner):
    from .common_background_source import check
    bg=owner.get('_bg',{}) if isinstance(owner,dict) else getattr(owner,'_bg',{})
    value=check(bg)
    if D.record(owner) is None:
        if value is not None and value['version']==2:raise ValueError('Derived common recipe cannot bind an original source')
        return value
    if value is None:
        if bg.get('active'):raise ValueError('Derived common background needs its own canonical-source recipe, not a proxy/neural matte')
        return None
    if value['version']!=2 or value['source']!=D.binding(owner):
        raise ValueError('Common replacement belongs to a different effective source')
    from .creative_document_host import require_photo_return
    require_photo_return(D.record(owner))
    return value


def verify_snapshot(snap,path=None,shape=None):
    value=validate_state(snap)
    if value is None:return None
    source=D.binding(snap)
    if shape is not None and tuple(shape)!=(source['height'],source['width']):
        raise ValueError('Common replacement export requires its complete canonical grid')
    if path is not None and M.source_digest(path)!=value['original_sha256']:
        raise ValueError('Common replacement original-file provenance changed')
    return value


def capture(engine,*,tol,softness):
    from .ops.matting import _edge_median
    pixels=preview_pixels(engine);source=D.binding(engine)
    row=engine._docs[engine._doc_index];stamp=M.file_stamp(row['path'])
    if row.get('_local_source_stamp')!=stamp:raise ValueError('Original provenance changed after decode')
    value={'version':2,'contract':CONTRACT,'source':source,'original_sha256':M.source_digest(row['path']),
        'reference':_edge_median(pixels).tolist(),'reference_grid':[int(pixels.shape[1]),int(pixels.shape[0])],
        'tol':tol,'softness':softness}
    if M.file_stamp(row['path'])!=stamp:raise ValueError('Original provenance changed during capture')
    return value


def spec_state(spec):
    from .common_background_source import check
    key=getattr(spec,'common_background_key',None)
    color=getattr(spec,'common_background_color',None)
    matte=getattr(spec,'bg_matte',None);background=getattr(spec,'bg_ref',None)
    retained=getattr(spec,'_common_background_retained',None)
    if retained is not None:
        recipe=check(retained)
        if recipe is None:raise ValueError('Common retained export identity lacks its versioned recipe')
        if key!=(recipe if retained['active'] else None):
            raise ValueError('Common active export key disagrees with retained intent')
        if retained['active']:
            if type(color) not in (list,tuple) or list(color)!=list(retained['bg']):
                raise ValueError('Common active export color disagrees with retained intent')
        elif color is not None or matte is not None or background is not None:
            raise ValueError('Inactive common intent cannot retain an active export compositor')
        return {'creative_base':getattr(spec,'creative_base',None),'_bg':deepcopy(retained)}
    if key is not None and type(key) is not dict:
        raise ValueError('Invalid direct common export recipe')
    return {'creative_base':getattr(spec,'creative_base',None),'_bg':{
        'active':key is not None or matte is not None or background is not None,
        'backend':'color_key','key_recipe':key,'bg':color,
        'tol':key.get('tol') if key is not None else None,
        'softness':key.get('softness') if key is not None else None}}


def pixel_proof(spec,pixels):
    value=verify_snapshot(spec_state(spec),spec.common_background_path,pixels.shape[:2])
    if value is None:raise ValueError('No canonical common replacement intent')
    sdr(pixels)
    return (json.dumps(value,sort_keys=True,allow_nan=False),hash_pixels(pixels))


def stamp_pixels(spec,pixels):
    # Only called immediately after export_source resolves canonical float bytes.
    spec._common_canonical_pixels=pixel_proof(spec,pixels)


def verify_pixels(spec,pixels):
    if getattr(spec,'_common_canonical_pixels',None)!=pixel_proof(spec,pixels):
        raise ValueError('Common replacement input is not the resolved canonical source')
