# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured visible brows; no warp, original-brow removal or hidden reconstruction."""
import numpy as np
from .eye_light_geometry import signature,source_key
from .face_scope import _polygon_field
CHAINS={'left':((336,296,334,293,300),(285,295,282,283,276)),
        'right':((107,66,105,63,70),(55,65,52,53,46))}

def prepare(source,lm,binding,side,support):
    from . import people_state as P
    if binding.get('backend')!='mediapipe' or binding.get('working_space')!='working-srgb':raise ValueError('眉妆需要真实人物和 working-sRGB 源')
    for k in ('source_sha256','face_sha256','model_sha256'):P.digest(binding.get(k))
    if source.dtype!=np.float32 or source.ndim!=3 or source.shape[2]!=3 or not np.isfinite(source).all() or np.any((source<0)|(source>1)):raise ValueError('眉妆源像素无效；不裁切 HDR')
    if binding['source_sha256']!=source_key(source) or binding['face_sha256']!=signature(lm):raise ValueError('眉妆来源已改变')
    if side not in CHAINS or not isinstance(support,dict) or support.get('reviewed') is not True or support.get('occluded') is not False:raise ValueError('需要独立眉毛及额头审核')
    for k in ('source_sha256','face_sha256','person_id','source_revision'):
        if support.get(k)!=binding[k]:raise ValueError('眉妆审核已过期')
    if support.get('side')!=side or not support.get('review_id'):raise ValueError('眉妆审核侧不符')
    h,w=source.shape[:2]
    for k in ('mask','forehead'):
        m=support.get(k)
        if not isinstance(m,np.ndarray) or m.dtype!=np.float32 or m.shape!=(h,w) or not np.isfinite(m).all() or np.any((m<0)|(m>1)):raise ValueError('独立眉毛/额头审核场无效')
    lm=np.asarray(lm,np.float32)
    if lm.shape!=(478,3) or not np.isfinite(lm).all() or np.any((lm[:,:2]<0)|(lm[:,:2]>1)):raise ValueError('眉妆需要真实 478 点网格')
    points=lm[:,:2]*[w-1,h-1];a,b=CHAINS[side];upper=points[list(a)];lower=points[list(b)];mid=(upper+lower)*.5
    width=float(np.linalg.norm(mid[-1]-mid[0]));axis=(mid[-1]-mid[0])/max(width,1)
    normal=np.array([-axis[1],axis[0]])
    if np.dot(normal,points[10]-mid.mean(0))<0:normal=-normal
    thick=(upper-lower)@normal
    if width<20 or np.min(thick)<1 or np.max(thick)>width*.5 or np.any(np.diff(mid@axis)<width*.03):raise ValueError('眉毛太小、退化或侧脸过强')
    other='right' if side=='left' else 'left';oa,ob=CHAINS[other]
    other_mid=(points[list(oa)]+points[list(ob)])*.5
    if width<.55*np.linalg.norm(other_mid[-1]-other_mid[0]):raise ValueError('眉毛侧脸过强')
    polygon=np.concatenate((upper,lower[::-1]));reference=polygon+normal*max(width*.16,float(thick.max())*1.5)
    allp=np.concatenate((polygon,reference));margin=max(3.,float(thick.max()))
    x,y=np.floor(allp.min(0)-margin).astype(int);x1,y1=np.ceil(allp.max(0)+margin).astype(int)
    if x<1 or y<1 or x1>w-1 or y1>h-1:raise ValueError('眉毛或额头参考被裁切')
    if (x1-x)*(y1-y)>4_000_000:raise ValueError('眉妆源窗口超预算')
    yy,xx=np.mgrid[y:y1,x:x1].astype(np.float32);xx+=.5;yy+=.5
    inside,_=_polygon_field(xx,yy,polygon);forehead,_=_polygon_field(xx,yy,reference)
    mask=support['mask'][y:y1,x:x1];fm=support['forehead'][y:y1,x:x1]
    valid=inside&(mask>.5);ref=forehead&(fm>.5)&~inside
    if valid.sum()<max(16,.65*inside.sum()) or ref.sum()<16:raise ValueError('独立可见眉毛或额头支持不足')
    luma=source[y:y1,x:x1]@np.array([.2126,.7152,.0722]);background=float(np.median(luma[ref]))
    dark=valid&(luma<background-.025)&(luma>.005)
    if dark.sum()<max(12,.18*valid.sum()) or float(np.std(luma[valid]))<.008:raise ValueError('未观察到可靠原有眉毛；不重建隐藏眉毛')
    uv=np.zeros((*xx.shape,2),np.float32);nearest=np.full(xx.shape,np.inf);allowed=np.zeros(xx.shape,bool)
    lengths=np.linalg.norm(np.diff(mid,axis=0),axis=1);total=float(lengths.sum());offset=0.
    for i,(start,end) in enumerate(zip(mid[:-1],mid[1:])):
        tangent=(end-start)/lengths[i];n=np.array([-tangent[1],tangent[0]])
        if np.dot(n,normal)<0:n=-n
        t=((xx-start[0])*tangent[0]+(yy-start[1])*tangent[1])/lengths[i]
        v=((xx-start[0])*n[0]+(yy-start[1])*n[1])/(.5*(thick[i]*(1-np.clip(t,0,1))+thick[i+1]*np.clip(t,0,1)))
        pick=(t>=0)&(t<=1)&(np.abs(v)<1.35)&(np.abs(v)<nearest)
        uv[...,0][pick]=(offset+t[pick]*lengths[i])/total;uv[...,1][pick]=v[pick];nearest[pick]=np.abs(v[pick]);allowed|=pick;offset+=lengths[i]
    coverage=np.ascontiguousarray(mask*allowed,dtype=np.float32)
    return (int(y),int(x),int(y1-y),int(x1-x)),np.ascontiguousarray(uv),coverage,{'visible_brow_pixels':int(dark.sum()),'forehead_pixels':int(ref.sum()),'limitation':'conservative_dark_brow_evidence_not_complete_occlusion_segmentation'}
