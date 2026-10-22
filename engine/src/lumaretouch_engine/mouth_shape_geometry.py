"""Observed full lip rings for mouth2D; fixed MediaPipe 1.1.1 topology.

Reuse the PC-32471 lip evidence, not its cosmetic parameters. Known semantic
occluders and local RGB only veto; this is not full mouth/occlusion segmentation.
"""
import numpy as np
from . import mouth_shape_state as S
from .mouth_shape_native import controls as native_controls
from .lip_makeup_geometry import OUTER, INNER, geometry as lip_evidence, _crossed
from .brow_shape_geometry import EYES, IRISES, pixels, head_frame, polygon_inside
from .ops.enhance import LIP_CHAIN_UPPER, LIP_CHAIN_LOWER

INNER_UPPER = INNER[:11]
INNER_LOWER = (INNER[0], *reversed(INNER[10:]))
RING = tuple(dict.fromkeys((*OUTER, *INNER)))
# Never inherit eye/nose mouth anchors. Only distant upper-face anchors pin here.
ANCHORS = tuple(sorted(set((*EYES['left'], *EYES['right'], *IRISES, 168, 6, 4, 10))))


def evidence(lm, shape, source, excluded, backend):
    mask, base, width = lip_evidence(lm, shape, source, excluded, backend=backend)
    right, up = head_frame(lm)
    center = (lm[61]+lm[291])*.5
    upper = float((lm[0]-lm[13])@up)
    lower = float((lm[14]-lm[17])@up)
    aperture = float((lm[13]-lm[14])@up)
    common = base['reason']
    if width < 24 or upper < 1.2 or lower < 1.2:
        common = common or 'insufficient_lip_resolution'
    if aperture < -.5 or upper > width*.3 or lower > width*.3:
        common = 'degenerate_lip_geometry'
    yy,xx = np.mgrid[:shape[0],:shape[1]]
    local_x = (xx-center[0])*right[0]+(yy-center[1])*right[1]
    local_y = (xx-lm[13,0])*up[0]+(yy-lm[13,1])*up[1]
    regions = {'upper': mask*(local_y>=0), 'lower': mask*(local_y<0)}
    regions['m_lip'] = regions['upper']
    luma = source@np.array([.2126,.7152,.0722])
    full_ring = polygon_inside(xx.ravel(),yy.ravel(),lm[list(OUTER)]).reshape(shape)
    full_ring &= ~polygon_inside(xx.ravel(),yy.ravel(),lm[list(INNER)]).reshape(shape)
    for side, sign in (('left',1),('right',-1)):
        regions[f'gummy:{side}'] = regions['upper']*(local_x*sign>=0)
    facts = {}
    for key in (*S.SCALARS,'gummy:left','gummy:right'):
        region = regions.get(key, mask)
        count = int(np.count_nonzero(region>.01))
        reason = common
        area = full_ring.copy()
        if key in ('upper','m_lip') or key.startswith('gummy:'): area &= local_y>=0
        elif key == 'lower': area &= local_y<0
        if key.startswith('gummy:'): area &= local_x*(1 if key.endswith('left') else -1)>=0
        if excluded is not None and np.count_nonzero(area&(excluded<.2))<.9*np.count_nonzero(area):
            reason = reason or 'occluded_or_insufficient_support'
        if count and float(np.std(luma[region>.01]))<.004:
            reason = reason or 'no_reliable_lip_texture'
        if count < (8 if key.startswith('gummy:') else 14):
            reason = reason or 'occluded_or_insufficient_support'
        if key.startswith('gummy:'):
            if aperture < 2: reason = reason or 'closed_or_unobservable_aperture'
            if excluded is not None and aperture >= 2:
                # The actual aperture must be observable too, not merely predicted.
                cavity = polygon_inside(xx.ravel(),yy.ravel(),lm[list(INNER)]).reshape(shape)
                side_mask = cavity&(local_x*(1 if key.endswith('left') else -1)>=0)
                visible = side_mask&(excluded<.2)&(luma>.008)&(luma<.985)
                if visible.sum()<max(8,side_mask.sum()*.9):
                    reason = reason or 'closed_or_unobservable_aperture'
        facts[key] = {'control':key,'reason':reason,'support_px':count,
                      'method':base['visibility_method'],'limitation':base['limitation']}
    return facts,right,up,center,width,max(upper,.1),max(lower,.1),max(aperture,0.)


def build_controls(landmarks, shape, recipe, source, excluded, *, backend):
    r = S.check(recipe)
    if backend != 'mediapipe': raise ValueError('嘴形拒绝模板或占位人脸')
    lm = pixels(landmarks,shape)
    source = np.asarray(source)
    if source.shape != (*shape,3) or not np.isfinite(source).all() or np.any((source<0)|(source>1)):
        raise ValueError('嘴形需要同尺寸原始 RGB 浮点源图')
    if excluded is not None:
        excluded = np.asarray(excluded)
        if excluded.shape != shape or not np.isfinite(excluded).all() or np.any((excluded<0)|(excluded>1)):
            raise ValueError('嘴形遮挡排除场无效')
    facts,right,up,center,width,upper,lower,aperture = evidence(lm,shape,source,excluded,backend)
    for key,fact in facts.items():
        value = r['gummy'][key.split(':')[1]] if key.startswith('gummy:') else r[key]
        fact['requested'] = value != 0
        fact['applied'] = value != 0 and fact['reason'] is None
    safe = S.check(r)
    for key,fact in facts.items():
        if fact['reason']:
            if key.startswith('gummy:'): safe['gummy'][key.split(':')[1]] = 0.
            else: safe[key] = 0.
    points = lm[list(RING)]
    delta = np.zeros_like(points)
    windows = []
    if S.active(safe):
        roles = np.array([[float(i in LIP_CHAIN_UPPER[1:-1]),
                           float(i in LIP_CHAIN_LOWER[1:-1]),
                           float(i in INNER_UPPER[1:-1]),
                           float(i in (61,291,78,308))] for i in RING])
        delta = native_controls(points,roles,np.r_[right,up,center,width,upper,lower,aperture],S.vector(safe))
        target = points+delta
        if np.any(target<1) or np.any(target[:,0]>shape[1]-2) or np.any(target[:,1]>shape[0]-2):
            raise ValueError('嘴形目标超出画面')
        outer = target[[RING.index(i) for i in OUTER]]
        inner = target[[RING.index(i) for i in INNER]]
        if _crossed(outer) or _crossed(inner) or not np.all(polygon_inside(inner[:,0],inner[:,1],outer)):
            raise ValueError('嘴形使唇环交叉或内外唇越界，请减小强度')
        # Gummy must cover, never increase the observed central opening.
        if any(safe['gummy'][s] for s in S.SIDES):
            upper_target = target[RING.index(13)]
            lower_target = target[RING.index(14)]
            if float((upper_target-lower_target)@up)<max(.8,aperture*.35):
                raise ValueError('露龈调整后可见开口过小，未生成或翻转嘴部内部')
        protected = lm[list(ANCHORS)]
        if np.min(np.linalg.norm(target[:,None]-protected[None],axis=2))<max(1.,width*.025):
            raise ValueError('嘴形与鼻眼保护区域冲突')
        window_center = np.mean(np.concatenate((points,target)),axis=0)
        flat = float(np.linalg.norm(np.concatenate((points,target))-window_center,axis=1).max())+width*.08
        windows = [(window_center,flat,flat+width*.35)]
    from .ops.deform import BORDER_ANCHORS,dedupe_controls
    P = np.concatenate((points+delta,lm[list(ANCHORS)],np.asarray(BORDER_ANCHORS)*[shape[1],shape[0]]))
    D = np.concatenate((delta,np.zeros((len(ANCHORS)+len(BORDER_ANCHORS),2))))
    tolerance = max(.02,min(shape)*1e-5)
    for i in range(len(P)):
        near = np.linalg.norm(P[i+1:]-P[i],axis=1)<tolerance
        if np.any(np.linalg.norm(D[i+1:][near]-D[i],axis=1)>tolerance):
            raise ValueError('闭口或退化唇点无法支持此调整，未静默合并冲突')
    P,D,merged = dedupe_controls(P,D,tol=tolerance)
    return P,D,{'controls':facts,'merged':merged,'windows':windows,'landmarks':lm,
                'width':width,'protected':[lm[list(ids)] for ids in EYES.values()]}
