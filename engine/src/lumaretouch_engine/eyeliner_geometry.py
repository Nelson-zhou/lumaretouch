"""Measured upper eyelid only. Width curves never extend beyond observed corners."""
import numpy as np
from .eye_light_geometry import signature,source_key
from .eyeliner_catalogue import material
# Anatomical inner -> outer. Positive normal always points away from eye centre.
UPPER={'right':(133,173,157,158,159,160,161,246,33),'left':(362,398,384,385,386,387,388,466,263)}
LOWER={'right':(133,155,154,153,145,144,163,7,33),'left':(362,382,381,380,374,373,390,249,263)}
def validate_binding(source,lm,binding):
    from . import people_state as P
    if binding.get('backend')!='mediapipe' or binding.get('working_space')!='working-srgb':raise ValueError('眼线要求真实检测及 working-sRGB 源')
    for key in ('source_sha256','face_sha256','model_sha256'):P.digest(binding.get(key))
    if binding['source_sha256']!=source_key(source) or binding['face_sha256']!=signature(lm) or not binding.get('person_id') or type(binding.get('source_revision')) is not int:raise ValueError('眼线来源或人物已改变')
def prepare(source,lm,binding,side,support,pattern):
    validate_binding(source,lm,binding)
    if side not in UPPER or not isinstance(support,dict) or support.get('reviewed') is not True or support.get('occluded') is not False:raise ValueError('需要此眼独立的可见眼睑审核')
    for key in ('source_sha256','face_sha256','person_id','source_revision'):
        if support.get(key)!=binding[key]:raise ValueError('眼睑审核已过期')
    if support.get('side')!=side or not support.get('review_id'):raise ValueError('眼睑审核眼侧不符')
    mask=support.get('mask');h,w=source.shape[:2]
    if not isinstance(mask,np.ndarray) or mask.dtype!=np.float32 or mask.shape!=(h,w) or not np.isfinite(mask).all() or np.any((mask<0)|(mask>1)):raise ValueError('眼睑审核场无效')
    points=np.asarray(lm,np.float32)[:,:2]*[w-1,h-1];upper=points[list(UPPER[side])];lower=points[list(LOWER[side])]
    eye=np.concatenate((upper,lower));axis=upper[-1]-upper[0];width=float(np.linalg.norm(axis));centre=eye.mean(0)
    if width<14 or np.any(eye<0) or np.any(eye>=[w,h]):raise ValueError('眼部过小或被裁切')
    normal=np.array([-axis[1],axis[0]])/width
    aperture=float(np.mean(np.abs((lower[2:7]-upper[2:7])@normal)))
    if aperture<3 or aperture/width<.10:raise ValueError('闭眼或不可靠眼部拒绝绘制；可解除联动并将此眼归零')
    widths=np.interp(np.linspace(0,1,len(upper)),np.linspace(0,1,8),material(pattern)['widths'])*width
    margin=max(widths)+2;x,y=np.maximum(0,np.floor(upper.min(0)-margin)).astype(int);x1,y1=np.minimum([w,h],np.ceil(upper.max(0)+margin+1)).astype(int)
    segments=[]
    for i,(a,b) in enumerate(zip(upper[:-1],upper[1:])):
        tangent=b-a;length=float(np.linalg.norm(tangent))
        if length<.25:raise ValueError('眼睑曲线退化')
        n=np.array([-tangent[1],tangent[0]])/length
        if np.dot(n,(a+b)*.5-centre)<0:n=-n
        segments.append([*(a-[x,y]),*(b-[x,y]),*n,widths[i],widths[i+1]])
    coverage=np.ascontiguousarray(mask[y:y1,x:x1])
    if np.count_nonzero(coverage>.5)<8:raise ValueError('此眼可见眼睑支持不足')
    return (int(y),int(x),int(y1-y),int(x1-x)),np.ascontiguousarray(segments,dtype=np.float32),coverage
