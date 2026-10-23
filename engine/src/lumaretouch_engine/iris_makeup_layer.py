# SPDX-License-Identifier: GPL-3.0-or-later
"""One frozen source-coordinate contribution for canonical preview/export tiling."""
import numpy as np
from . import iris_makeup_state as S, iris_makeup_support as V, people_state as P
from .iris_makeup_geometry import fields
from .iris_makeup_native import delta

def prepare_record(face_ref,landmarks,recipe,source,*,excluded,backend,reviewed):
    r=S.check(recipe)
    if not S.active(r):return None
    from .people_effects import LocalEffect
    ref=P.check_ref(face_ref);record=V.check_record(reviewed)
    if record['face_ref']!=ref:raise ValueError('美瞳审核属于其他人物')
    if type(source) is not np.ndarray or source.dtype!=np.float32 or source.ndim!=3 or source.shape[2]!=3 or not np.isfinite(source).all() or np.any((source<0)|(source>1)):raise ValueError('美瞳需要 working-sRGB float32 源像素')
    h,w=source.shape[:2];lm=np.asarray(landmarks,np.float32)
    from .lip_makeup_runtime import identity
    if identity(lm)!=record['row']['landmark_digest']:raise ValueError('美瞳审核关键点已改变')
    if excluded is None or excluded.shape!=(h,w):raise ValueError('美瞳遮挡证据尺寸不符')
    # Both eyes and every reviewed vector fit a single bounded ROI, then the
    # canonical LocalEffect compositor maps it through the SAME geometry field.
    pts=np.concatenate([lm[[33,133,263,362,468,469,470,471,472,473,474,475,476,477],:2],
        *[np.asarray(e[k],np.float32) for e in record['row']['eyes'].values() for k in ('iris','pupil')],
        *[np.asarray(p,np.float32) for e in record['row']['eyes'].values() for p in e['highlights']]])*[w-1,h-1]
    x,y=np.maximum(np.floor(pts.min(0)-12),0).astype(int);x1,y1=np.minimum(np.ceil(pts.max(0)+12)+1,[w,h]).astype(int)
    rh,rw=int(y1-y),int(x1-x)
    if min(rh,rw)<8 or rh*rw>4_000_000:raise ValueError('美瞳源窗口无效或超出内存预算')
    local_lm=lm.copy();local_lm[:,:2]=(lm[:,:2]*[w-1,h-1]-[x,y])/[rw-1,rh-1]
    eyes={}
    for side,e in record['row']['eyes'].items():
        def local(p):return ((np.asarray(p)*[w-1,h-1]-[x,y])/[rw-1,rh-1]).tolist()
        eyes[side]={'iris':local(e['iris']),'pupil':local(e['pupil']),'highlights':[local(p) for p in e['highlights']]}
    src=np.ascontiguousarray(source[y:y1,x:x1]);veto=np.ascontiguousarray(excluded[y:y1,x:x1])
    uv,support,protected,counts=fields(src,local_lm,eyes,veto,backend=backend)
    result=delta(src,uv,support,r)
    if not np.isfinite(result).all() or np.any(result[protected]!=0) or np.any(result[support==0]!=0):raise ValueError('美瞳保护区不变量失败，未发布')
    result.setflags(write=False)
    return LocalEffect(ref,'iris_makeup',(int(y),int(x),rh,rw),delta=result,facts={'recipe':r,'changed_pixels':int(np.count_nonzero(np.any(result!=0,axis=2))),
        'visible_ring_pixels':counts,'pupil_source':'independently_reviewed_measured_polygon','review_sha256':V.content_digest(record),
        'limitation':'manual_boundary_accuracy_requires_visual_QA; no_automatic_pupil_segmentation'})
