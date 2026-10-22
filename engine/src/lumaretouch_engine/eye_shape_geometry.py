"""Full 16-point lid contours and 5-point iris groups, MediaPipe 1.1.1.

Source pixels can veto, never prove visibility. Known semantic occluders plus
regional contrast checks are conservative heuristics, not an eye/glasses model.
"""
import numpy as np
from . import eye_shape_state as S
from .eye_shape_native import controls as native_controls
from .brow_shape_geometry import EYES,CHAINS,pixels,head_frame,polygon_inside
from .nose_shape_geometry import NOSE,LIPS
NOSE_PROTECTION=(168,193,122,196,3,51,45,220,115,48,64,98,97,2,326,327,294,278,344,440,275,281,248,419,351,417)
from .nose_shape_field import edge_distance
IRIS={'left':(473,474,475,476,477),'right':(468,469,470,471,472)}
BROWS=tuple(i for chains in CHAINS.values() for chain in chains for i in chain)
ANCHORS=tuple(sorted(set((*NOSE,*LIPS,*BROWS,10,109,338))))


def evidence(lm,source,excluded,side):
    h,w=source.shape[:2]; eye=lm[list(EYES[side])]; iris=lm[list(IRIS[side])]
    width=float(np.linalg.norm(eye[0]-eye[8])); other='right' if side=='left' else 'left'
    common=None
    try: lateral,up=head_frame(lm)
    except ValueError: lateral,up=np.array([1.,0.]),np.array([0.,-1.]); common='insufficient_resolution'
    height=float(np.ptp(eye@up)); outward=lateral if side=='left' else -lateral
    if width<24 or height<4: common='closed_or_insufficient_resolution'
    if height<width*.10: common='closed_or_unobservable_opening'
    if height>width*.65 or (eye[0]-eye[8])@outward<width*.75: common='degenerate_eye_geometry'
    lower=eye[:9]@outward
    upper=np.concatenate((eye[8:],eye[:1]))@outward
    gaps=(eye[9:16]-eye[7:0:-1])@up
    if np.any(np.diff(lower)>width*.025) or np.any(np.diff(upper)<-width*.025):
        common='degenerate_eye_geometry'
    if np.min(gaps)<.5 or np.median(gaps)<2.5:
        common='closed_or_unobservable_opening'
    other_width=float(np.linalg.norm(lm[EYES[other][0]]-lm[EYES[other][8]]))
    if width<.70*other_width or min(width,other_width)<12: common='sideface_or_foreshortened'
    if excluded is None: common='visibility_support_unavailable'
    facts={k:{'control':k,'side':side,'reason':common,'support_px':0,
        'method':'known_occluder_veto_and_regional_rgb_evidence',
        'limitation':'not_complete_eye_glasses_or_occlusion_segmentation'} for k in S.KEYS}
    if common: return facts,outward,up,width,height
    pad=max(3.,width*.12); x0,y0=np.floor(eye.min(0)-pad).astype(int); x1,y1=np.ceil(eye.max(0)+pad+1).astype(int)
    if min(x0,y0)<1 or x1>w-1 or y1>h-1:
        for fact in facts.values(): fact['reason']='clipped_support'
        return facts,outward,up,width,height
    yy,xx=np.mgrid[y0:y1,x0:x1]; X=np.stack((xx.ravel(),yy.ravel()),axis=1)
    inside=polygon_inside(xx,yy,eye); distance=edge_distance(X,eye).reshape(xx.shape)
    luma=source[y0:y1,x0:x1]@np.array([.2126,.7152,.0722]); veto=excluded[y0:y1,x0:x1]
    usable=(veto<.2)&(luma>.008)&(luma<.985)
    center=(eye[0]+eye[8])*.5
    x=(xx-center[0])*outward[0]+(yy-center[1])*outward[1]
    y=(xx-center[0])*up[0]+(yy-center[1])*up[1]
    lid=distance<max(1.5,width*.045)
    regions={'opening':inside,'upper':lid&(y>=0),'lower':lid&(y<0),
        'inner':(inside|lid)&(x<-width*.27),'outer':(inside|lid)&(x>width*.27)}
    checks={}
    for name,mask in regions.items():
        valid=mask&usable; n=int(valid.sum()); reason=None
        if n<max(6,.90*mask.sum()): reason='occluded_or_insufficient_support'
        elif float(np.std(luma[valid]))<.012: reason='no_reliable_visible_eye_evidence'
        checks[name]=(reason,n)
    required={k:tuple(regions) for k in S.KEYS}
    required.update(inner_corner=('inner','upper','lower'),outer_corner=('outer','upper','lower'),
                    lower_lid=('lower','opening'),iris_size=('opening',))
    for k,names in required.items():
        facts[k]['reason']=next((checks[n][0] for n in names if checks[n][0]),None)
        facts[k]['support_px']=sum(checks[n][1] for n in names)
    # A full visible ring is required for iris resizing. We never infer hidden
    # iris behind a lid, reflection or occluder, nor generate new sclera.
    radius=float(np.linalg.norm(iris[1:]-iris[0],axis=1).mean())
    ring_visible=polygon_inside(iris[1:,0],iris[1:,1],eye)
    inner=((xx-iris[0,0])**2+(yy-iris[0,1])**2)<(radius*.8)**2
    reference=inside&(((xx-iris[0,0])**2+(yy-iris[0,1])**2)>(radius*1.1)**2)&usable
    ir=inner&usable
    if radius<3 or not ring_visible.all() or ir.sum()<12 or reference.sum()<8:
        facts['iris_size']['reason']='iris_not_fully_observable'
    elif np.median(luma[ir])>np.median(luma[reference])-.025 or np.std(luma[ir])<.01:
        facts['iris_size']['reason']='iris_texture_evidence_missing'
    facts['iris_size']['support_px']=int(ir.sum())
    return facts,outward,up,width,height


def build_controls(landmarks,shape,recipe,source,excluded,*,backend):
    r=S.check(recipe); lm=pixels(landmarks,shape); source=np.asarray(source)
    if backend!='mediapipe': raise ValueError('眼形拒绝模板/占位人脸')
    if source.shape!=(*shape,3) or not np.isfinite(source).all() or np.any((source<0)|(source>1)):
        raise ValueError('眼形需要同尺寸原始 RGB 浮点源图')
    if excluded is not None:
        excluded=np.asarray(excluded)
        if excluded.shape!=shape or not np.isfinite(excluded).all() or np.any((excluded<0)|(excluded>1)):
            raise ValueError('眼形遮挡排除场无效')
    P=[]; D=[]; windows=[]; facts={}; iris_only=[]; protected=[lm[list(NOSE_PROTECTION)],lm[list(LIPS)]]
    protected.extend(lm[list(a+tuple(reversed(b)))] for a,b in CHAINS.values())
    for side in S.SIDES:
        side_facts,outward,up,width,height=evidence(lm,source,excluded,side)
        for key,fact in side_facts.items():
            fact['requested']=r[key][side]!=0
            fact['applied']=fact['requested'] and fact['reason'] is None
            facts[f'{side}:{key}']=fact
        ids=EYES[side]+IRIS[side]; points=lm[list(ids)]; delta=np.zeros_like(points)
        values=[r[k][side] if side_facts[k]['applied'] else 0. for k in S.KEYS]
        if any(values):
            eye=points[:16]; center=(eye[0]+eye[8])*.5
            frame=np.r_[outward,up,center,points[16],width,height]
            # Ordered lower contour is indices 1..7, endpoints remain corners.
            roles=np.array([[float(j>=16),float(0<j<8)*np.sin(np.pi*j/8)**2] for j in range(len(ids))])
            delta=native_controls(points,roles,frame,values)
            target=points+delta
            if np.any(target<1) or np.any(target[:,0]>=shape[1]-1) or np.any(target[:,1]>=shape[0]-1):
                raise ValueError(f'眼形 {side} 超出图像边界')
            # Iris may move within an opening, never across the actual moved lid.
            if values[1]!=0 and not polygon_inside(target[17:,0],target[17:,1],target[:16]).all():
                raise ValueError(f'眼形 {side} 虹膜大小超出可见眼裂，未合成眼白或隐藏虹膜')
            anchors=lm[list(ANCHORS)]
            if np.min(np.linalg.norm(target[:,None]-anchors[None],axis=2))<max(.8,width*.035):
                raise ValueError(f'眼形 {side} 与眉鼻保护区距离不足')
            c=np.mean(np.concatenate((points,target)),axis=0)
            flat=float(np.linalg.norm(np.concatenate((points,target))-c,axis=1).max())+width*.04
            windows.append((c,flat,flat+width*.25))
            if values[1]!=0 and all(v==0 for j,v in enumerate(values) if j!=1):
                iris_only.append((eye,c,flat+width*.25))
        else: protected.append(points[:16])
        P.extend(points+delta); D.extend(delta)
    from .ops.deform import BORDER_ANCHORS,dedupe_controls
    P.extend(lm[list(ANCHORS)]); D.extend(np.zeros((len(ANCHORS),2)))
    P.extend(np.asarray(BORDER_ANCHORS)*[shape[1],shape[0]]); D.extend(np.zeros((len(BORDER_ANCHORS),2)))
    P,D=np.asarray(P),np.asarray(D); tolerance=max(.02,min(shape)*1e-5)
    for i in range(len(P)):
        close=np.linalg.norm(P[i+1:]-P[i],axis=1)<tolerance
        if np.any(np.linalg.norm(D[i+1:][close]-D[i],axis=1)>tolerance):
            raise ValueError('眼形控制点与保护锚冲突')
    P,D,merged=dedupe_controls(P,D,tol=tolerance)
    return P,D,{'controls':facts,'merged':merged,'windows':windows,'landmarks':lm,'protected':protected,'iris_only':iris_only}
