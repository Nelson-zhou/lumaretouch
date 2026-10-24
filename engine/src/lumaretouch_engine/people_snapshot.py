"""Frozen snapshot materialization shared by preview and original-resolution export."""
from copy import deepcopy
import numpy as np
from . import people_state as S
from .people_render_runtime import verify_analysis
from .skin_colour_support import check_analysis_fields


def capture(state,asset_sha256,analyses):
    """Plain dict/array payload accepted by the existing bounded snapshot owner."""
    state=S.check(state);S.digest(asset_sha256)
    copied={}
    for key,face in state['faces'].items():
        if face['asset_sha256']!=asset_sha256:continue
        raw=analyses.get(key)
        if raw is None:continue # Render plan reports missing evidence; never substitute.
        check_analysis_fields(raw)
        names=('landmarks','excluded','skin') + (('face_skin',) if 'face_skin' in raw else ())
        arrays={name:None if raw[name] is None else np.array(raw[name],copy=True) for name in names}
        for a in arrays.values():
            if a is not None:a.setflags(write=False)
        copied[key]={'face_ref':S.check_ref(raw['face_ref']),'evidence':deepcopy(raw['evidence']),**arrays}
        if 'face_skin_observation' in raw:
            copied[key]['face_skin_observation']=deepcopy(raw['face_skin_observation'])
    return {'state':state,'asset_sha256':asset_sha256,'analyses':copied}


def _admit_dimensions(snapshot, shape, byte_budget):
    """Count every planned semantic copy before a resize or target allocation.

    This is conservative admission, not measured peak memory. Arrays are counted
    per planned copy, including repeated references; no source/face identity is
    inferred to deduplicate them. Landmarks remain the already frozen arrays.
    """
    if byte_budget is None:
        return
    if type(byte_budget) is not int or byte_budget < 0:
        raise ValueError('People semantic resampling needs a nonnegative remaining byte budget')
    h,w=shape;retained=0;scratch=0
    for raw in snapshot['analyses'].values():
        for name in ('excluded','skin','face_skin'):
            value=raw.get(name)
            if value is None:continue
            if type(value) is not np.ndarray or value.ndim!=2 or not value.size or value.dtype.kind not in 'uif':
                raise ValueError('Invalid frozen semantic coverage before resampling')
            retained+=h*w*4
            # Float32 destination + bounded interpolation/copy/validation scratch.
            # The latter is temporary for one plane, not repeated per face.
            if value.shape!=shape:
                scratch=max(scratch,h*w*max(16,2*value.dtype.itemsize))
            else:
                scratch=max(scratch,h*w*4)
    if retained+scratch > byte_budget:
        raise ValueError('Frozen people semantic copies exceed memory budget before allocation')


def at_dimensions(snapshot,shape,*,byte_budget=None):
    """Resize measured semantic coverage only; landmarks retain normalized source coordinates.

    Geometry and every source-derived effect are rebuilt at requested dimensions.
    Neither a proxy displacement nor a proxy corrected RGB image is enlarged.
    Optional face-skin weights keep their original producer-grid observation;
    resampling does not claim new full-resolution semantic edge information.
    """
    state=S.check(snapshot['state']);asset=snapshot['asset_sha256'];S.digest(asset)
    h,w=shape
    if type(h) is not int or type(w) is not int or min(h,w)<1:raise ValueError('Invalid render dimensions')
    _admit_dimensions(snapshot,(h,w),byte_budget)
    out={}
    for key,raw in snapshot['analyses'].items():
        face=state['faces'].get(key)
        if face is None or face['asset_sha256']!=asset:raise ValueError('Snapshot contains another source face')
        check_analysis_fields(raw)
        masks={}
        names=('excluded','skin') + (('face_skin',) if 'face_skin' in raw else ())
        for name in names:
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
        if 'face_skin_observation' in raw:
            row['face_skin_observation']=deepcopy(raw['face_skin_observation'])
        verify_analysis(face,row,(h,w));out[key]=row
    return state,asset,out
