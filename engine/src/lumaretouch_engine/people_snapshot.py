"""Frozen snapshot materialization shared by preview and original-resolution export."""
from copy import deepcopy
import numpy as np
from . import people_state as S
from .people_render_runtime import verify_analysis


def capture(state,asset_sha256,analyses):
    """Plain dict/array payload accepted by the existing bounded snapshot owner."""
    state=S.check(state);S.digest(asset_sha256)
    copied={}
    for key,face in state['faces'].items():
        if face['asset_sha256']!=asset_sha256:continue
        raw=analyses.get(key)
        if raw is None:continue # Render plan reports missing evidence; never substitute.
        arrays={name:None if raw[name] is None else np.array(raw[name],copy=True) for name in ('landmarks','excluded','skin')}
        for a in arrays.values():
            if a is not None:a.setflags(write=False)
        copied[key]={'face_ref':S.check_ref(raw['face_ref']),'evidence':deepcopy(raw['evidence']),**arrays}
    return {'state':state,'asset_sha256':asset_sha256,'analyses':copied}


def at_dimensions(snapshot,shape):
    """Resize measured semantic coverage only; landmarks retain normalized source coordinates.

    Geometry and every source-derived effect are rebuilt at requested dimensions.
    Neither a proxy displacement nor a proxy corrected RGB image is enlarged.
    """
    state=S.check(snapshot['state']);asset=snapshot['asset_sha256'];S.digest(asset)
    h,w=shape
    if type(h) is not int or type(w) is not int or min(h,w)<1:raise ValueError('Invalid render dimensions')
    out={}
    for key,raw in snapshot['analyses'].items():
        face=state['faces'].get(key)
        if face is None or face['asset_sha256']!=asset:raise ValueError('Snapshot contains another source face')
        masks={}
        for name in ('excluded','skin'):
            value=raw[name]
            if value is not None:
                if value.ndim!=2 or not np.isfinite(value).all() or np.any((value<0)|(value>1)):
                    raise ValueError('Invalid frozen semantic coverage')
                if value.shape!=(h,w):
                    import cv2
                    value=cv2.resize(value,(w,h),interpolation=cv2.INTER_LINEAR)
                value=np.array(value,dtype=np.float32,copy=True);value.setflags(write=False)
            masks[name]=value
        row={**raw,**masks}
        verify_analysis(face,row,(h,w));out[key]=row
    return state,asset,out
