"""Same-scene geometric evidence. 8-bit gray only for ORB, never RGB photometry.

No histogram fallback: changing clothing/foreground must not silently masquerade
as illumination. A homography can still fit the wrong plane or repeated texture;
this is deliberately reviewable evidence, not semantic certainty.
"""
import numpy as np
from .optional_dependencies import optional_module


def _cv():
    cv=optional_module('cv2')
    if cv is None: raise RuntimeError('参考色彩需要已打包 OpenCV；不回退为全图均值')
    return cv


def pixels(value):
    if not isinstance(value,np.ndarray) or value.ndim!=3 or value.shape[2]!=3:
        raise ValueError('参考色彩需要完整 RGB 编辑画布')
    if min(value.shape[:2])<64 or value.size>3*100_000_000: raise ValueError('参考色彩画布超出分析预算')
    if value.dtype in (np.dtype('uint8'),np.dtype('uint16')):
        return np.ascontiguousarray(value.astype(np.float32)/np.iinfo(value.dtype).max)
    if value.dtype not in (np.dtype('float32'),np.dtype('float64')) or not np.isfinite(value).all():
        raise ValueError('参考色彩需要 RGB8、RGB16 或有限浮点 sRGB')
    return np.ascontiguousarray(value,dtype=np.float32)


def _proxy(rgb,cv):
    h,w=rgb.shape[:2];scale=min(1.,1400/max(h,w))
    # Independent X/Y scales after integer rounding are retained for full-frame coordinates.
    small=cv.resize(rgb,(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv.INTER_AREA)
    gray=np.rint(np.clip(small@np.array([.2126,.7152,.0722],np.float32),0,1)*255).astype(np.uint8)
    return gray,np.array([w/gray.shape[1],h/gray.shape[0]],np.float64)


def _coverage(points,shape,cv):
    h,w=shape[:2];p=points/np.array([w,h])
    cells=np.minimum((p*4).astype(int),3)
    occupancy=len(set(map(tuple,cells.tolist())))
    area=float(cv.contourArea(cv.convexHull(points.astype(np.float32))))/(w*h)
    return occupancy,area


def paired_patches(reference,target,reference_mask,target_mask,*,cancelled=lambda:False):
    cv=_cv();r=pixels(reference);t=pixels(target)
    rg,rs=_proxy(r,cv);tg,ts=_proxy(t,cv)
    orb=cv.ORB_create(nfeatures=3000)
    def feature_mask(mask,gray):
        reduced=cv.resize(mask.astype(np.float32),(gray.shape[1],gray.shape[0]),interpolation=cv.INTER_AREA)
        return (reduced>=.999999).astype(np.uint8)*255
    rk,rd=orb.detectAndCompute(rg,feature_mask(reference_mask,rg))
    tk,td=orb.detectAndCompute(tg,feature_mask(target_mask,tg))
    if cancelled(): raise InterruptedError('参考色彩分析取消')
    if rd is None or td is None or min(len(rd),len(td))<64: raise ValueError('同场景特征不足；请改选参考图，不会按全图颜色猜测')
    matcher=cv.BFMatcher(cv.NORM_HAMMING)
    def good(a,b):
        return {m.queryIdx:m.trainIdx for pair in matcher.knnMatch(a,b,k=2) if len(pair)==2
                for m,n in [pair] if m.distance<.72*n.distance}
    tr=good(td,rd);rt=good(rd,td)
    candidates=sorted(((ti,ri) for ti,ri in tr.items() if rt.get(ri)==ti),key=lambda pair: -tk[pair[0]].response)
    # Multiple pyramid keypoints on one tiny patch are not independent support.
    pairs=[];seen_t=set();seen_r=set()
    for ti,ri in candidates:
        tc=tuple(int(v//10) for v in tk[ti].pt);rc=tuple(int(v//10) for v in rk[ri].pt)
        if tc in seen_t or rc in seen_r: continue
        seen_t.add(tc);seen_r.add(rc);pairs.append((ti,ri))
    if len(pairs)<64: raise ValueError('参考图与目标缺少足够双向对应特征')
    tp=np.float64([tk[i].pt for i,j in pairs]);rp=np.float64([rk[j].pt for i,j in pairs])
    H,mask=cv.findHomography(tp,rp,cv.RANSAC,2.5,maxIters=3000,confidence=.995)
    if H is None or mask is None or not np.isfinite(H).all(): raise ValueError('同场景几何对应不稳定')
    keep=mask.ravel().astype(bool)
    if keep.sum()<64 or keep.mean()<.65: raise ValueError('同场景几何内点不足；未应用颜色校正')
    tp=tp[keep]*ts;rp=rp[keep]*rs
    for p,shape in ((tp,t.shape),(rp,r.shape)):
        cells,area=_coverage(p,shape,cv)
        if cells<6 or area<.15: raise ValueError('对应特征集中于局部，无法代表整张照片的光照')
    # Proxy target -> proxy reference transformed to full-resolution coordinates.
    H=np.diag([*rs,1.])@H@np.diag([*(1/ts),1.])
    offsets=np.stack(np.meshgrid(np.arange(-2,3),np.arange(-2,3)),axis=-1).reshape(-1,2)
    q=tp[:,None,:]+offsets[None,:,:]*max(1.,float(max(ts)))
    hom=np.concatenate((q,np.ones((*q.shape[:-1],1))),axis=-1)@H.T
    if np.any(np.abs(hom[...,2])<1e-8): raise ValueError('对应投影退化')
    mapped=hom[...,:2]/hom[...,2:]
    inside=lambda p,im:np.all((p[...,0]>=1)&(p[...,0]<im.shape[1]-2)&(p[...,1]>=1)&(p[...,1]<im.shape[0]-2),axis=1)
    valid=inside(q,t)&inside(mapped,r);q=q[valid];mapped=mapped[valid]
    if len(q)<64: raise ValueError('边缘外对应区域过多')
    def sample(im,points):
        return cv.remap(im,points[...,0].astype(np.float32),points[...,1].astype(np.float32),cv.INTER_LINEAR)
    # Corresponding 5x5 patch medians are full-float encoded RGB; no image warp is retained.
    authentic=(sample(reference_mask.astype(np.float32),mapped).min(axis=1)>.999999)&(sample(target_mask.astype(np.float32),q).min(axis=1)>.999999)
    q=q[authentic];mapped=mapped[authentic]
    if len(q)<64: raise ValueError('排除替换/生成/来源不明区域后对应证据不足')
    a=np.median(sample(r,mapped),axis=1);b=np.median(sample(t,q),axis=1)
    if cancelled(): raise InterruptedError('参考色彩分析取消')
    return a,b,{'method':'orb-mutual-homography-patches-v1','opencv':str(cv.__version__),
        'matches':len(pairs),'geometric_inliers':int(keep.sum()),'patches':len(q),
        'target_coverage':_coverage(tp,t.shape,cv)[1],'reference_coverage':_coverage(rp,r.shape,cv)[1]},q[:,12,:],mapped[:,12,:]


def consensus_coverage(target_points,reference_points,inliers,target_shape,reference_shape):
    cv=_cv();facts={}
    for key,points,shape in (('target',target_points,target_shape),('reference',reference_points,reference_shape)):
        cells,area=_coverage(points[inliers],shape,cv)
        if cells<6 or area<.15: raise ValueError('光度一致区域缺少全图分布；不以局部/替换材质代表光照')
        facts[key+'_consensus_coverage']=area
        facts[key+'_consensus_cells']=cells
    return facts
