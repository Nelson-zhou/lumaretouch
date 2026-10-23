"""Original curved fibres attached to measured upper/lower eyelid roots.

Root review and extension-zone ownership are independent. Never infer hidden
portions or reuse eyeliner's skin-only band as lash extension permission.
"""
import numpy as np
from .eye_light_geometry import signature,source_key
UPPER={'right':(133,173,157,158,159,160,161,246,33),'left':(362,398,384,385,386,387,388,466,263)}
LOWER={'right':(133,155,154,153,145,144,163,7,33),'left':(362,382,381,380,374,373,390,249,263)}
def validate_binding(source,lm,binding):
    from . import people_state as P
    if binding.get('backend')!='mediapipe' or binding.get('working_space')!='working-srgb':raise ValueError('睫毛要求真实检测及 working-sRGB 源')
    for key in ('source_sha256','face_sha256','model_sha256'):P.digest(binding.get(key))
    if binding['source_sha256']!=source_key(source) or binding['face_sha256']!=signature(lm) or not binding.get('person_id') or type(binding.get('source_revision')) is not int:raise ValueError('睫毛来源或人物已改变')

from .eyelash_catalogue import material
from .eyelash_state import PARTS

def prepare(source,lm,binding,part,support,pattern):
    validate_binding(source,lm,binding)
    if part not in PARTS or not isinstance(support,dict) or support.get('reviewed') is not True or support.get('occluded') is not False:raise ValueError('需要此部位独立的可见根部及延伸区域审核')
    for key in ('source_sha256','face_sha256','person_id','source_revision'):
        if support.get(key)!=binding[key]:raise ValueError('睫毛审核已过期')
    if support.get('side')!=part or not support.get('review_id'):raise ValueError('睫毛审核部位不符')
    h,w=source.shape[:2];mask=support.get('mask');root_mask=support.get('root_mask')
    for m in (mask,root_mask):
        if not isinstance(m,np.ndarray) or m.dtype!=np.float32 or m.shape!=(h,w) or not np.isfinite(m).all() or np.any((m<0)|(m>1)):raise ValueError('睫毛审核场无效')
    side,lid=part.split('_');points=np.asarray(lm,np.float32)[:,:2]*[w-1,h-1]
    upper=points[list(UPPER[side])];lower=points[list(LOWER[side])];eye=np.concatenate((upper,lower));rim=upper if lid=='upper' else lower
    axis=upper[-1]-upper[0];width=float(np.linalg.norm(axis));centre=eye.mean(0)
    if width<14 or not np.isfinite(eye).all() or np.any(eye<0) or np.any(eye>=[w,h]):raise ValueError('眼部过小、非有限或被裁切')
    normal=np.array([-axis[1],axis[0]])/width
    aperture=float(np.mean(np.abs((lower[2:7]-upper[2:7])@normal)))
    if aperture<3 or aperture/width<.10:raise ValueError('闭眼或不可见部位拒绝生成，请解除联动并归零')
    lengths=np.linalg.norm(np.diff(rim,axis=0),axis=1)
    if np.any(lengths<.25):raise ValueError('睫毛根部曲线退化')
    cumulative=np.r_[0,np.cumsum(lengths)];arc=float(cumulative[-1]);profile=material(pattern);segments=[]
    # Fixed deterministic profiles, no random state, no texture/model download.
    for i,t in enumerate(np.linspace(.05,.95,profile['count'])):
        distance=t*arc;j=min(int(np.searchsorted(cumulative,distance,side='right')-1),len(lengths)-1)
        local=(distance-cumulative[j])/lengths[j];a=rim[j]*(1-local)+rim[j+1]*local
        tangent=(rim[j+1]-rim[j])/lengths[j];n=np.array([-tangent[1],tangent[0]])
        if np.dot(n,a-centre)<0:n=-n
        rx,ry=np.rint(a).astype(int)
        if rx<0 or ry<0 or rx>=w or ry>=h:continue
        if root_mask[ry,rx]<.8:continue # Unreviewed root never produces a fibre.
        variation=1+profile['variation']*np.sin(i*2.39996323)
        envelope=.55+.45*np.sin(np.pi*t)
        length=width*profile['length']*variation*envelope*(.64 if lid=='lower' else 1.)
        sweep=profile['sweep']*(t-.35)+profile['curl']*(2*t-1)
        b=a+n*length*.52+tangent*length*(sweep-profile['curl'])
        c=a+n*length+tangent*length*sweep
        # Quadratic fibres, sixteen tapered segments, all locations observed
        # in independently reviewed extension-zone ownership. Any forbidden
        # centre sample rejects the whole fibre, never invents through occluders.
        ts=np.linspace(0,1,17);curve=np.array([(1-q)**2*a+2*q*(1-q)*b+q*q*c for q in ts])
        dense=[]
        for start,end in zip(curve[:-1],curve[1:]):
            steps=int(np.ceil(np.linalg.norm(end-start)*2))+1
            if steps>4096:raise ValueError('睫毛分段超出安全预算')
            dense.extend(start*(1-f)+end*f for f in np.linspace(0,1,max(2,steps)))
        samples=np.rint(np.asarray(dense)).astype(int)
        if np.any(samples<0) or np.any(samples>=[w,h]):continue
        if np.any(mask[samples[:,1],samples[:,0]]<.8):continue
        thickness=max(.35,width*.009)*profile['width']*(.8 if lid=='lower' else 1.)
        for k,(p,q) in enumerate(zip(curve[:-1],curve[1:])):
            segments.append([*p,*q,thickness*(1-ts[k])+.03,thickness*(1-ts[k+1])+.03])
    if not segments:raise ValueError('没有完整可见且已审核的睫毛根部及延伸区域')
    segments=np.asarray(segments,np.float32);all_points=segments[:,:4].reshape(-1,2);margin=float(segments[:,4:].max())+2
    x,y=np.maximum(0,np.floor(all_points.min(0)-margin)).astype(int);x1,y1=np.minimum([w,h],np.ceil(all_points.max(0)+margin+1)).astype(int)
    segments[:,[0,2]]-=x;segments[:,[1,3]]-=y
    return (int(y),int(x),int(y1-y),int(x1-x)),np.ascontiguousarray(segments),np.ascontiguousarray(mask[y:y1,x:x1])
