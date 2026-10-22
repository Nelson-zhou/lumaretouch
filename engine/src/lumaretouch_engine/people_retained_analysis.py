"""Persist measured normalized landmarks, never inferred identity or proxy RGB.

Semantic fields are rebuilt by the admitted source/model producer. Reopening a
project reuses its frozen measured geometry rather than silently replacing its
ownership with whichever detection happens to appear at the same list index.
"""
from copy import deepcopy
import numpy as np
from . import people_state as S
from .people_binding import landmark_digest


def key(ref):return ref['face_instance_id']+':'+str(ref['analysis_revision'])


def retain(store,analyses):
    out=deepcopy(store)
    for row in analyses.values():
        ref=S.check_ref(row['face_ref']);ev=S.check_evidence(row['evidence'])
        points=np.asarray(row['landmarks'],dtype='<f4')
        if landmark_digest(points)!=ev['landmark_digest']:raise ValueError('Measured landmark evidence changed')
        record={'face_ref':ref,'evidence':ev,'landmarks':points.tolist()};ident=key(ref)
        if ident in out and out[ident]!=record:raise ValueError('Frozen analysis cannot be silently rewritten')
        out[ident]=record
    return out


def restore_missing(state,store,asset_sha256,pc,analyses):
    from .nose_shape_runtime import exclusion
    from .facial_wrinkle_runtime import skin_support
    result=dict(analyses)
    if pc is None:return result
    for face in state['faces'].values():
        if face['asset_sha256']!=asset_sha256 or face['face_instance_id'] in result:continue
        ref=S.face_ref(face);record=store.get(key(ref));ev=face['evidence']
        if record is None or record['face_ref']!=ref or record['evidence']!=ev:continue
        if (ev['backend'],ev['detector_model_sha256'],ev['semantic_model_sha256'])!=(pc.backend,getattr(pc,'detector_model_sha256',None),getattr(pc,'semantic_model_sha256',None)):
            continue # A different loaded model requires an explicit reanalysis decision.
        points=np.array(record['landmarks'],dtype='<f4');points.setflags(write=False)
        if landmark_digest(points)!=ev['landmark_digest']:raise ValueError('Saved landmark evidence is corrupt')
        masks={}
        for name,value in (('excluded',exclusion(pc)),('skin',skin_support(pc))):
            masks[name]=None if value is None else np.array(value,copy=True)
            if masks[name] is not None:masks[name].setflags(write=False)
        result[ref['face_instance_id']]={'face_ref':ref,'evidence':ev,'landmarks':points,**masks}
    return result


def check_store(store):
    if type(store) is not dict or len(store)>8192:raise ValueError('Invalid retained analysis store')
    for ident,row in store.items():
        if type(row) is not dict or set(row)!={'face_ref','evidence','landmarks'}:raise ValueError('Invalid retained analysis record')
        ref=S.check_ref(row['face_ref']);ev=S.check_evidence(row['evidence'])
        if ident!=key(ref) or landmark_digest(row['landmarks'])!=ev['landmark_digest']:raise ValueError('Retained analysis hash mismatch')
    return deepcopy(store)
