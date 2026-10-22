"""Bind detector outputs by exact retained evidence, never face list position.

A fresh asset may create new stable instances once. Existing assets only reuse
exact evidence, including loaded detector bytes; changed analysis is unresolved
until explicit reanalysis. Reordering identical retained outputs is safe.
"""
import hashlib
import numpy as np
from . import people_state as S, people_associations as G
from .nose_shape_runtime import exclusion
from .facial_wrinkle_runtime import skin_support


def landmark_digest(points):
    value = np.asarray(points,dtype='<f4')
    if value.shape != (478,3) or not np.isfinite(value).all(): raise ValueError('Invalid detector landmarks')
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def evidence(pc, points, source_dimensions):
    width,height = source_dimensions
    detector = getattr(pc,'detector_model_sha256',None)
    backend = getattr(pc,'backend','unknown')
    return S.check_evidence({'backend':backend,'detector_model_sha256':detector,
        'semantic_model_sha256':getattr(pc,'semantic_model_sha256',None),
        'landmark_digest':landmark_digest(points),'status':'verified' if backend=='mediapipe' and detector else 'synthetic' if backend in ('synthetic','template') else 'unresolved',
        'source_width':width,'source_height':height,'orientation':'exif_normalized_once'})


def bind(state, asset_sha256, pc, *, source_dimensions, initialize=False):
    out = S.check(state); S.digest(asset_sha256)
    if pc is None: return out, {}, [{'reason':'No face analysis available'}]
    pool = pc.all_landmarks or [pc.landmarks]
    if len(pool) > S.MAX_FACES: raise ValueError('Detector output exceeds instance budget')
    candidates = [(points,evidence(pc,points,source_dimensions)) for points in pool]
    existing = [face for face in out['faces'].values() if face['asset_sha256']==asset_sha256]
    if initialize and existing: raise ValueError('Existing face ownership cannot be initialized again')
    fresh = []
    if initialize:
        for index,(points,ev) in enumerate(candidates):
            xy = np.asarray(points)[:,:2]
            low = np.clip(xy.min(0),0,1); high = np.clip(xy.max(0),0,1)
            fresh.append(S.new_face(asset_sha256,[float(v) for v in (*low,*high)],ev,manual=index in getattr(pc,'manual',())))
        limit = getattr(pc,'detection_limit',max(1,len(pool)))
        truncated = getattr(pc,'detection_limit_reached',len(pool)>=limit)
        out = G.add_faces(out,asset_sha256,fresh,detector_limit=limit,limit_reached=truncated)
        existing = fresh
    analysis = {}; unresolved = []
    veto = exclusion(pc); skin = skin_support(pc)
    if veto is not None: veto=np.array(veto,copy=True); veto.setflags(write=False)
    if skin is not None: skin=np.array(skin,copy=True); skin.setflags(write=False)
    for face in existing:
        matches = [(lm,ev) for lm,ev in candidates if ev == face['evidence']]
        # Two indistinguishable outputs are ambiguous, not two different people.
        duplicates = sum(other['evidence']==face['evidence'] for other in existing)
        if len(matches)!=1 or duplicates!=1:
            unresolved.append({'face_instance_id':face['face_instance_id'],'reason':'Retained analysis unavailable or ambiguous; keep old edits and explicitly review reanalysis'})
            continue
        lm,ev=matches[0]; points=np.array(lm,dtype='<f4',copy=True); points.setflags(write=False)
        analysis[face['face_instance_id']]={'face_ref':S.face_ref(face),'evidence':ev,'landmarks':points,'excluded':veto,'skin':skin}
    return out,analysis,unresolved
