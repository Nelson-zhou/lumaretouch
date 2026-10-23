"""Concrete LocalEffect preparation for the existing canonical people graph."""
import numpy as np
from . import eye_light_state as S, eye_light_geometry as G, eye_light_support as V
from .eye_light_native import colour
from .eye_light_runtime import solve

def prepare(state,assets,face_ref,analysis,working_srgb,recipe,*,source_revision):
    """Called inside people_render_runtime.prepare using its effect_source.

    This entry decodes ACTUAL existing working-sRGB source to linear with the
    native transfer function, renders, then returns encoded working deltas for
    the host LocalEffect stage. It never pretends source dtype implies linear.
    """
    if not S.active(recipe): return []
    from .people_render_runtime import verify_analysis
    from .people_effects import LocalEffect
    face=state['faces'][face_ref['face_instance_id']]
    if analysis['face_ref']!=face_ref: raise ValueError('眼神光分析人物不匹配')
    lm=verify_analysis(face,analysis,working_srgb.shape[:2])
    source=np.ascontiguousarray(working_srgb,dtype=np.float32)
    linear=colour(source)
    binding={'source_sha256':G.source_key(linear),'face_sha256':G.signature(lm),'model_sha256':face['evidence']['detector_model_sha256'],
        'person_id':face_ref['face_instance_id'],'source_revision':source_revision,'backend':'mediapipe','working_space':'linear-rgb'}
    supports=V.raster(state,assets,face_ref,source.shape[:2],binding)
    excluded=analysis['excluded']
    if excluded is not None:
        for support in supports.values():support['mask']*=np.float32(1)-excluded.astype(np.float32)
    layer=solve(linear,lm,binding,supports,recipe)
    records=[]
    for index,(window,d) in enumerate(layer.tiles):
        y,x,h,w=window; encoded=colour(np.ascontiguousarray(source[y:y+h,x:x+w]),d)
        encoded.setflags(write=False)
        records.append(LocalEffect(face_ref,'eye_light',window,delta=encoded,facts=layer.facts[index]))
    return records

def specification(): return S.OPERATION,(S.neutral(),S.check)
