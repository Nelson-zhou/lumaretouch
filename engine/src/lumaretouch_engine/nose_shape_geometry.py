"""Source-domain nose controls, fixed MediaPipe 1.1.1 topology and admission.

Official FACE_LANDMARKS_NOSE provides the central chain and lower outline.
Bridge cross-sections and nostril triangles are our conservative anatomical use
of its tessellation, not upstream semantic segmentation or visibility truth.
"""
import numpy as np
from . import nose_shape_state as S
from .nose_shape_native import controls as native_controls
from .brow_shape_geometry import EYES,IRISES,polygon_inside,pixels,head_frame

CENTERLINE = (168,6,197,195,5,4,1,19,94,2)
OUTLINE = (98,97,2,326,327,294,278,344,440,275,4,45,220,115,48,64)
BRIDGE_PAIRS = ((193,417),(122,351),(196,419),(3,248),(51,281),(45,275))
NOSTRILS = ((98,97,99),(327,326,328))
TIP = (4,1,19,44,274)
WINGS = (98,97,99,64,48,115,327,326,328,294,278,344)
LIPS = (61,185,40,39,37,0,267,269,270,409,291,375,321,405,314,17,84,181,91,146)
NOSE = tuple(dict.fromkeys((*CENTERLINE,*OUTLINE,*(i for pair in BRIDGE_PAIRS for i in pair),*TIP,*WINGS)))
# No nose-tip / bridge identity anchors from automatic deformation or eyebrows.
ANCHORS = tuple(sorted(set((*EYES['left'],*EYES['right'],*IRISES,*LIPS,10,109,338,50,280))))


def region_evidence(lm, source, excluded, indices, radius, *, dark=False):
    """Actual RGB support and known-occluder veto, never mesh-only visibility.

    This is a conservative photometric heuristic, not a nose/occlusion model.
    Masks, spectacles and low-contrast retouching remain explicit limitations.
    """
    h,w=source.shape[:2]; points=lm[list(indices)]
    center=points.mean(0)
    radius=max(radius,float(np.linalg.norm(points-center,axis=1).max())+1)
    x0,y0=np.floor(center-radius*1.5).astype(int)
    x1,y1=np.ceil(center+radius*1.5+1).astype(int)
    if min(x0,y0)<1 or x1>w-1 or y1>h-1: return 'clipped_support',0
    yy,xx=np.mgrid[y0:y1,x0:x1]
    rr=np.hypot(xx-center[0],yy-center[1]); core=rr<=radius; ring=(rr>radius)&(rr<radius*1.5)
    veto=excluded[y0:y1,x0:x1]
    valid=core&(veto<.2); reference=ring&(veto<.2)
    if valid.sum()<max(12,.95*core.sum()) or reference.sum()<12: return 'occluded_or_insufficient_support',int(valid.sum())
    luma=source[y0:y1,x0:x1]@np.array([.2126,.7152,.0722])
    usable=valid&(luma>.008)&(luma<.985)
    if usable.sum()<.8*valid.sum() or float(np.std(luma[usable]))<.006:
        return 'no_reliable_visible_nose_evidence',int(usable.sum())
    if dark:
        evidence=usable&(luma<float(np.median(luma[reference]))-.025)
        if evidence.sum()<max(3,.08*usable.sum()): return 'nostril_evidence_missing',int(evidence.sum())
    return None,int(usable.sum())


def support(lm,source,excluded):
    try:
        right,up=head_frame(lm)
    except ValueError:
        facts={k:{'control':k,'reason':'insufficient_resolution','support_px':0,
                  'method':'geometry_veto','limitation':'no_visibility_claim'} for k in S.KEYS}
        return facts,np.zeros(2),np.zeros(2),0.,0.
    width=float((lm[327]-lm[98])@right)
    height=float((lm[168]-lm[2])@up)
    common=None
    if width<14 or height<20: common='insufficient_resolution'
    if excluded is None: common='visibility_support_unavailable'
    left_eye=float(np.linalg.norm(lm[263]-lm[362])); right_eye=float(np.linalg.norm(lm[33]-lm[133]))
    # Frontal/mild yaw only. Mesh geometry may veto but never establish visibility.
    wings=np.array([(lm[1]-lm[98])@right,(lm[327]-lm[1])@right])
    if min(left_eye,right_eye)<8 or min(left_eye,right_eye)<.7*max(left_eye,right_eye) or min(wings)<.20*max(width,1):
        common='sideface_or_foreshortened'
    if width>height*1.8 or height>width*3.8: common='degenerate_nose_geometry'
    for indices in NOSTRILS:
        a,b,c=lm[list(indices)];u=b-a;v=c-a
        if abs(u[0]*v[1]-u[1]*v[0])<max(1.,width*width*.001): common='degenerate_nose_geometry'
    positions=lm[list((168,6,197,195,5,4,2))]@up
    if np.any(np.diff(positions)>max(.7,height*.025)): common='degenerate_nose_geometry'
    facts={k:{'control':k,'reason':common,'support_px':0,'method':'known_occluder_veto_and_local_rgb_evidence',
              'limitation':'not_complete_nose_or_occlusion_segmentation'} for k in S.KEYS}
    if common: return facts,right,up,width,height
    regions={'bridge':tuple(i for pair in BRIDGE_PAIRS for i in pair),'tip':TIP,
             'nostril_right':NOSTRILS[0],'nostril_left':NOSTRILS[1]}
    evidence={name:region_evidence(lm,source,excluded,ids,width*.09,dark=name.startswith('nostril')) for name,ids in regions.items()}
    requires={'size':tuple(regions),'height':tuple(regions),'position':tuple(regions),
              'bridge':('bridge',),'wing':('nostril_right','nostril_left'),'tip':('tip','nostril_right','nostril_left')}
    for key,names in requires.items():
        facts[key]['reason']=next((evidence[n][0] for n in names if evidence[n][0]),None)
        facts[key]['support_px']=sum(evidence[n][1] for n in names)
    return facts,right,up,width,height


def build_controls(landmarks,shape,recipe,source,excluded,*,backend):
    r=S.check(recipe)
    if backend!='mediapipe': raise ValueError('鼻形拒绝模板/占位人脸')
    lm=pixels(landmarks,shape); source=np.asarray(source)
    if source.shape!=(*shape,3) or not np.isfinite(source).all() or np.any((source<0)|(source>1)):
        raise ValueError('鼻形可见性需要同尺寸原始 RGB 浮点源图')
    if excluded is not None:
        excluded=np.asarray(excluded)
        if excluded.shape!=shape or not np.isfinite(excluded).all() or np.any((excluded<0)|(excluded>1)):
            raise ValueError('鼻形遮挡排除场无效')
    facts,right,up,width,height=support(lm,source,excluded)
    for key in S.KEYS:
        facts[key]['requested']=r[key]!=0
        facts[key]['applied']=r[key]!=0 and facts[key]['reason'] is None
    # Atomic transaction owner reports all refused controls; no partial application.
    values=[r[k] if facts[k]['applied'] else 0. for k in S.KEYS]
    points=lm[list(NOSE)]; delta=np.zeros_like(points); nostrils=[]; windows=[]
    if any(values):
        center=(lm[168]+lm[2])*.5
        frame=np.r_[right,up,center,lm[1],width,height]
        bridges={i for pair in BRIDGE_PAIRS for i in pair}
        roles=np.array([[float(i in bridges),float(i in WINGS),float(i in TIP)] for i in NOSE])
        delta=native_controls(points,roles,frame,values)
        for indices in NOSTRILS:
            # Preserve each aperture triangle by rigid translation, not shrinkage.
            # Global size/position and wing move its center; bridge/tip do not.
            p=lm[list(indices)]; c=p.mean(0)
            move=native_controls(c[None],np.array([[0.,1.,0.]]),frame,values)[0]
            for i in indices: delta[NOSE.index(i)]=move
            nostrils.append((p+move,move))
        target=points+delta
        if np.any(target<1) or np.any(target[:,0]>=shape[1]-1) or np.any(target[:,1]>=shape[0]-1):
            raise ValueError('鼻形超出图像边界')
        # Explicit spacing check before any protection feather can cancel motion.
        protected=lm[list(ANCHORS)]
        if np.min(np.linalg.norm(target[:,None]-protected[None],axis=2))<max(.8,width*.025):
            raise ValueError('鼻形与眼部或上唇保护区距离不足')
        center=np.mean(np.concatenate((points,target)),axis=0)
        flat=float(np.linalg.norm(np.concatenate((points,target))-center,axis=1).max())+width*.10
        windows=[(center,flat,flat+width*.45)]
    from .ops.deform import BORDER_ANCHORS,dedupe_controls
    P=np.concatenate((points+delta,lm[list(ANCHORS)],np.asarray(BORDER_ANCHORS)*[shape[1],shape[0]]))
    D=np.concatenate((delta,np.zeros((len(ANCHORS)+len(BORDER_ANCHORS),2))))
    tolerance=max(.02,min(shape)*1e-5)
    for i in range(len(P)):
        close=np.linalg.norm(P[i+1:]-P[i],axis=1)<tolerance
        if np.any(np.linalg.norm(D[i+1:][close]-D[i],axis=1)>tolerance):
            raise ValueError('鼻形控制点与保护锚冲突')
    P,D,merged=dedupe_controls(P,D,tol=tolerance)
    return P,D,{'controls':facts,'merged':merged,'windows':windows,'landmarks':lm,'nostrils':nostrils,'width':width}
