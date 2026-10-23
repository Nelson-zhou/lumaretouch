"""Canonical LocalEffect adapter, same source preparation for preview and export."""
import numpy as np
from . import eyeliner_state as S,eyeliner_geometry as G,eyeliner_support as V
from .eyeliner_native import delta
from .eyeliner_catalogue import CATALOGUE_SHA256
def prepare(state,assets,face_ref,analysis,working_srgb,recipe,*,source_revision):
    r=S.check(recipe)
    if not S.active(r):return []
    from .people_render_runtime import verify_analysis
    from .people_effects import LocalEffect
    face=state['faces'][face_ref['face_instance_id']]
    if analysis['face_ref']!=face_ref:raise ValueError('眼线分析人物不匹配')
    lm=verify_analysis(face,analysis,working_srgb.shape[:2]);source=np.ascontiguousarray(working_srgb,dtype=np.float32)
    binding={'source_sha256':G.source_key(source),'face_sha256':G.signature(lm),'model_sha256':face['evidence']['detector_model_sha256'],'person_id':face_ref['face_instance_id'],'source_revision':source_revision,'backend':'mediapipe','working_space':'working-srgb'}
    supports=V.raster(state,assets,face_ref,source.shape[:2],binding)
    if analysis['excluded'] is None:raise ValueError('眼线需要实际遮挡场，不能默认无遮挡')
    for support in supports.values():support['mask']*=np.float32(1)-analysis['excluded'].astype(np.float32)
    pending=[]
    # Prepare both first: unsupported linked side rejects whole proposal.
    for side in ('left','right'):
        if r[side]['strength']==0:continue
        window,segments,mask=G.prepare(source,lm,binding,side,supports.get(side),r[side]['pattern'])
        pending.append((side,window,segments,mask))
    records=[]
    for side,(y,x,h,w),segments,mask in pending:
        result=delta(np.ascontiguousarray(source[y:y+h,x:x+w]),mask,segments,r[side]);result.setflags(write=False)
        count=int(np.count_nonzero(np.any(result!=0,axis=2)))
        records.append(LocalEffect(face_ref,'eyeliner',(y,x,h,w),delta=result,facts={'side':side,'changed_pixels':count,'reason':None if count else 'no_measurable_change','review_id':supports[side]['review_id'],'catalogue_sha256':CATALOGUE_SHA256,'working_space':'working-srgb'}))
    return records
