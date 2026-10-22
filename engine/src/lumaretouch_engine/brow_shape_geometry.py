"""Source-domain anatomical checks and conservative visibility for eyebrow v1.

Topology verified against the fixed MediaPipe v1.1.1 official face_landmarker.py.
Subject left is MediaPipe LEFT, not the viewer's left. No face-template fallback.
"""
import numpy as np
from . import brow_shape_state as S
from .brow_shape_native import controls as native_controls
# Factual ordered topology; both chains ordered inner -> outer.
CHAINS = {'left': ((336,296,334,293,300),(285,295,282,283,276)),
          'right': ((107,66,105,63,70),(55,65,52,53,46))}
EYES = {'left': (263,249,390,373,374,380,381,382,362,398,384,385,386,387,388,466),
        'right': (33,7,163,144,145,153,154,155,133,173,157,158,159,160,161,246)}
IRISES = tuple(range(468,478))
BRIDGE = (168,6,197,195,5,4,1)
FOREHEAD = (10,109,67,103,54,338,297,332,284)
ANCHORS = tuple(sorted(set((*EYES['left'],*EYES['right'],*IRISES,*BRIDGE,*FOREHEAD))))


def pixels(landmarks, shape):
    h,w = shape
    lm = np.asarray(landmarks,dtype=np.float64)
    if lm.shape != (478,3) or not np.isfinite(lm).all() or np.any((lm[:,:2]<0)|(lm[:,:2]>1)):
        raise ValueError('眉形需要当前选中人物的真实归一化 478×3 网格')
    return lm[:,:2]*[w,h]


def head_frame(lm):
    lateral = lm[473]-lm[468]
    distance = float(np.linalg.norm(lateral))
    if distance<16: raise ValueError('眉形人脸分辨率不足')
    lateral /= distance
    up = np.array([lateral[1],-lateral[0]])
    if float((lm[10]-lm[1])@up)<0: up=-up
    return lateral,up


def polygon_inside(x,y,poly):
    inside=np.zeros(np.broadcast_shapes(np.shape(x),np.shape(y)),dtype=bool)
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        if abs(b[1]-a[1])<1e-12: continue
        inside ^= ((a[1]>y)!=(b[1]>y)) & (x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])
    return inside


def visibility(lm, source, excluded, side):
    """Veto geometry, known occluders and missing local dark-brow evidence.

    Not segmentation: glasses/hair can still fool photometric evidence. Blonde,
    low-contrast, clipped or heavily retouched brows may conservatively refuse.
    """
    h,w=source.shape[:2]; upper,lower=CHAINS[side]
    points=lm[list(upper+lower)]; mid=(points[:5]+points[5:])*.5
    width=float(np.linalg.norm(mid[4]-mid[0])); fact={'side':side,'reason':None,'support_px':0,
        'method':'known_occluder_veto_and_local_dark_brow_evidence',
        'limitation':'not_complete_brow_or_occlusion_segmentation'}
    def fail(reason): return {**fact,'reason':reason}
    if width<20: return fail('insufficient_resolution')
    if excluded is None: return fail('visibility_support_unavailable')
    _,up=head_frame(lm)
    thickness=(points[:5]-points[5:])@up
    if np.min(thickness)<.7 or np.max(thickness)>width*.55:
        return fail('degenerate_brow_chains')
    outward=(mid[4]-mid[0])/width
    if np.any(np.diff(mid@outward)<width*.03): return fail('folded_or_foreshortened')
    other='right' if side=='left' else 'left'
    eye_width=float(np.linalg.norm(lm[EYES[side][0]]-lm[EYES[side][8]]))
    other_eye=float(np.linalg.norm(lm[EYES[other][0]]-lm[EYES[other][8]]))
    if eye_width<8 or eye_width<.55*other_eye: return fail('sideface_or_foreshortened')
    if np.any(points<2) or np.any(points[:,0]>w-3) or np.any(points[:,1]>h-3):
        return fail('clipped_brow')
    # Compare to an actual adjacent forehead strip, not a skin-colour preset.
    poly=np.concatenate((points[:5],points[5:][::-1]))
    reference=poly+up*max(width*.16,float(np.max(thickness))*1.5)
    allp=np.concatenate((poly,reference))
    x0,y0=np.floor(allp.min(0)-1).astype(int); x1,y1=np.ceil(allp.max(0)+2).astype(int)
    if x0<0 or y0<0 or x1>w or y1>h: return fail('clipped_reference_support')
    yy,xx=np.mgrid[y0:y1,x0:x1]
    ring=polygon_inside(xx,yy,poly); skin=polygon_inside(xx,yy,reference)
    veto=excluded[y0:y1,x0:x1]
    valid=ring & (veto<.2); ref=skin & (veto<.2)
    if np.count_nonzero(valid)<max(16,.8*np.count_nonzero(ring)) or ref.sum()<16:
        return fail('occluded_or_insufficient_support')
    patch=source[y0:y1,x0:x1]
    luma=patch@np.array([.2126,.7152,.0722])
    background=float(np.median(luma[ref]))
    dark=valid & (luma<background-.025) & (luma>.005)
    fact['support_px']=int(dark.sum())
    if dark.sum()<max(12,.18*valid.sum()) or float(np.std(luma[valid]))<.008:
        return fail('no_reliable_visible_brow_evidence')
    # Require evidence across all three thirds; a single shadow/glasses corner
    # cannot alone authorize stretching an otherwise unseen eyebrow.
    t=((xx-mid[0,0])*outward[0]+(yy-mid[0,1])*outward[1])/width
    if any(np.count_nonzero(dark & (t>=a) & (t<b))<2 for a,b in ((0,.34),(.34,.67),(.67,1.05))):
        return fail('incomplete_visible_brow_support')
    return fact


def build_controls(landmarks,shape,recipe,source,excluded,*,backend):
    r=S.check(recipe); lm=pixels(landmarks,shape)
    if backend!='mediapipe': raise ValueError('眉形拒绝模板/占位人脸')
    source=np.asarray(source)
    if source.shape!=(*shape,3) or not np.isfinite(source).all() or np.any((source<0)|(source>1)):
        raise ValueError('眉形可见性需要同尺寸原始 RGB 浮点源图')
    if excluded is not None:
        excluded=np.asarray(excluded)
        if excluded.shape!=shape or not np.isfinite(excluded).all() or np.any((excluded<0)|(excluded>1)):
            raise ValueError('眉形遮挡排除场无效')
    lateral,up=head_frame(lm); P=[]; D=[]; windows=[]; facts={}
    # Inactive/unavailable opposite brow is still pinned, never silently moved.
    for side in S.SIDES:
        upper,lower=CHAINS[side]; points=lm[list(upper+lower)]
        fact=visibility(lm,source,excluded,side); facts[side]=fact
        delta=np.zeros_like(points)
        requested=S.side_active(r,side)
        if requested and fact['reason'] is None:
            outward=lateral if side=='left' else -lateral
            delta=native_controls(points,outward,up,[r[k][side] for k in S.KEYS])
            width=float(np.linalg.norm((points[4]+points[9]-points[0]-points[5])*.5))
            if float(np.max(np.linalg.norm(delta,axis=1)))>width*.4:
                raise ValueError(f'眉形 {side} 组合幅度过大，请减少叠加强度')
            target=points+delta
            # Avoid moving controls into eyelids/bridge or outside the source.
            eye=lm[list(EYES[side])]
            if np.min(np.linalg.norm(target[:,None,:]-eye[None,:,:],axis=2))<width*.06:
                raise ValueError(f'眉形 {side} 与眼睑距离不足')
            if np.any(target<1) or np.any(target[:,0]>=shape[1]-1) or np.any(target[:,1]>=shape[0]-1):
                raise ValueError(f'眉形 {side} 超出图像边界')
            center=np.mean(np.concatenate((points,target)),axis=0)
            flat=float(np.max(np.linalg.norm(np.concatenate((points,target))-center,axis=1)))+width*.08
            windows.append((center,flat,flat+width*.35))
        fact['requested']=requested
        fact['applied']=requested and fact['reason'] is None
        P.extend(points+delta); D.extend(delta)
    P.extend(lm[list(ANCHORS)]); D.extend(np.zeros((len(ANCHORS),2)))
    # Existing exact border and identity anchors are retained in the brow stage.
    from .ops.deform import BORDER_ANCHORS,dedupe_controls
    P.extend(np.asarray(BORDER_ANCHORS)*[shape[1],shape[0]]); D.extend(np.zeros((len(BORDER_ANCHORS),2)))
    P=np.asarray(P); D=np.asarray(D)
    # Do not let deduplication average conflicting eyebrow and protection requests.
    tolerance=max(.02,min(shape)*1e-5)
    for i in range(len(P)):
        close=np.linalg.norm(P[i+1:]-P[i],axis=1)<tolerance
        if np.any(np.linalg.norm(D[i+1:][close]-D[i],axis=1)>tolerance):
            raise ValueError('眉形控制点与保护锚冲突')
    P,D,merged=dedupe_controls(P,D,tol=tolerance)
    return P,D,{'sides':facts,'merged':merged,'windows':windows,'landmarks':lm}
