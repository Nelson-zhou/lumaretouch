"""Bounded small-outlier repair, not learned blemish/identity classification.

Every detected component is small, surrounded by same-face samples, and
correction is capped per channel. Pigmented/dark ambiguities are vetoed by
default. Explicit user protection always wins. UNRUN photographic quality.
"""
import math
import numpy as np
from .. import portrait_protection_state as S


def prepare(source, recipe, *, byte_budget, cancelled=lambda:False):
    recipe=S.check(recipe); c=recipe['controls']
    if not S.needs_analysis(recipe): return None
    if type(source) is not np.ndarray or source.dtype!=np.float32 or source.ndim!=3 or source.shape[2]!=3:
        raise ValueError('Portrait correction requires float32 working-sRGB source')
    h,w=source.shape[:2]
    # Admission BEFORE full-grid validation/support/candidate allocations.
    if type(byte_budget) is not int or h*w*160+16*1024**2>byte_budget:
        raise ValueError('Portrait full-source preparation exceeds admitted working budget')
    if not np.isfinite(source).all() or np.any((source<0)|(source>1)):
        raise ValueError('Bounded portrait correction refuses HDR/nonfinite source')
    if cancelled(): raise InterruptedError('Portrait preparation cancelled')
    import cv2
    from ..face_scope import selected_face_skin, FACE_OVAL
    ev=recipe['evidence']; lm=np.asarray(ev['landmarks'],dtype=np.float32)
    sw,sh=recipe['source']['width'],recipe['source']['height']
    if abs(w*sh-h*sw)>max(sw,sh): raise ValueError('Portrait evidence/source aspect mismatch')
    scale=min(w/sw,h/sh)
    mask=cv2.resize(S.decode_mask(ev),(w,h),interpolation=cv2.INTER_LINEAR)
    # Hard admission at neutral feather; anatomy excludes eyes/brows/lips.
    permitted=selected_face_skin(mask,lm)>.75
    ys=np.arange(h,dtype=np.float32)[:,None]+.5; xs=np.arange(w,dtype=np.float32)[None,:]+.5
    for left,top,right,bottom in c['protected_regions']:
        permitted &= ~((xs>=left*w-.5)&(xs<=right*w+.5)&(ys>=top*h-.5)&(ys<=bottom*h+.5))
    feather=c['feather']*scale if c['analysis_enabled'] else 0.
    support=permitted.astype(np.float32)
    if feather:
        # Padding supplies a true protected exterior even at the image boundary.
        distance=cv2.distanceTransform(np.pad(permitted.astype(np.uint8),1),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)[1:-1,1:-1]
        support*=np.clip((distance-.5)/feather,0,1)
    span=float(np.min(np.ptp(lm[list(FACE_OVAL),:2]*[w,h],axis=0)))
    radius=max(1,min(32,int(math.ceil(span*.015))))
    outer=4*radius+1; inner=2*radius+1
    # Annulus references exclude the candidate centre and all forbidden donors.
    weight=support
    total=cv2.boxFilter(weight,-1,(outer,outer),normalize=False,borderType=cv2.BORDER_CONSTANT)
    centre=cv2.boxFilter(weight,-1,(inner,inner),normalize=False,borderType=cv2.BORDER_CONSTANT)
    denom=total-centre
    reference=np.zeros_like(source)
    for channel in range(3):
        values=source[:,:,channel]*weight
        sums=cv2.boxFilter(values,-1,(outer,outer),normalize=False,borderType=cv2.BORDER_CONSTANT)-cv2.boxFilter(values,-1,(inner,inner),normalize=False,borderType=cv2.BORDER_CONSTANT)
        reference[:,:,channel]=sums/np.maximum(denom,1e-6)
    usable=(support>.5)&(denom>=max(4.,.7*(outer*outer-inner*inner)))
    residual=source-reference
    luminance=residual@np.array([.2126,.7152,.0722],np.float32)
    # Any locally darker pigmentation is ambiguous, regardless of red score.
    dark=(luminance < -.015)&permitted
    dark=cv2.dilate(dark.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
    protected=(~permitted)|dark
    smoothing_support=support*(~dark) if c['analysis_enabled'] else None
    delta=np.zeros_like(source)
    if c['enabled'] and c['strength']>0:
        red=residual[:,:,0]-(residual[:,:,1]+residual[:,:,2])*.5
        candidates=usable&((np.abs(luminance)>.035)|(red>.04))
        if c['protect_identity_marks']: candidates &= ~dark
        count,labels,stats,_=cv2.connectedComponentsWithStats(candidates.astype(np.uint8),connectivity=8)
        if count>4096: raise ValueError('Too many ambiguous portrait candidates; no blanket smoothing fallback')
        chosen=np.zeros((h,w),bool)
        # Reject large lesions/edges/tattoos and every boundary-touching component.
        for i in range(1,count):
            if cancelled(): raise InterruptedError('Portrait component preparation cancelled')
            area=int(stats[i,cv2.CC_STAT_AREA]); cw=int(stats[i,cv2.CC_STAT_WIDTH]); ch=int(stats[i,cv2.CC_STAT_HEIGHT])
            if not 1<=area<=max(2,radius*radius) or max(cw,ch)>2*radius: continue
            x=int(stats[i,cv2.CC_STAT_LEFT]);y=int(stats[i,cv2.CC_STAT_TOP])
            y0,x0=max(0,y-1),max(0,x-1);y1,x1=min(h,y+ch+1),min(w,x+cw+1)
            component=labels[y0:y1,x0:x1]==i
            halo=cv2.dilate(component.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
            if np.any(halo&~usable[y0:y1,x0:x1]) or (c['protect_identity_marks'] and np.any(halo&dark[y0:y1,x0:x1])): continue
            chosen[y0:y1,x0:x1] |= component
        alpha=chosen.astype(np.float32)*support*c['strength']
        delta=np.clip(reference-source,-.12,.12)*alpha[:,:,None]
    if cancelled(): raise InterruptedError('Portrait preparation cancelled')
    return {'delta':np.ascontiguousarray(delta,dtype=np.float32),
            'smoothing_support':None if smoothing_support is None else np.ascontiguousarray(smoothing_support,dtype=np.float32),
            'overlay':protected.astype(np.float32) if c['analysis_enabled'] and c['overlay_visible'] else None}


def apply_delta_t(pixels, delta):
    import torch
    if delta is None:return pixels
    if delta.shape!=pixels.shape or not torch.isfinite(delta).all():raise ValueError('Portrait source field mismatch')
    if not torch.any(delta!=0):return pixels
    # Current stage may include light/smoothing; bounded additive correction
    # preserves other layers rather than replacing pixels with an old source.
    changed=delta.ne(0).any(dim=1,keepdim=True)
    # A prior light stage can differ from the admitted SDR source. Refuse its
    # unsupported changed pixels instead of clipping an arbitrarily large value.
    if torch.any(changed & (~torch.isfinite(pixels) | (pixels<0) | (pixels>1))):
        raise ValueError('Portrait correction requires finite SDR current pixels inside its changed support')
    result=torch.clamp(pixels+delta,0,1)
    return torch.where(changed,result,pixels)
