"""Image-evidence perspective fitting, never guessed transforms or claimed ML.

OpenCV's mature LSD supplies line segments; robust, regularized least-squares
fits a small rectification homography. Guided fitting uses the same objective.
All coordinates are normalized pixel edges before centering to [-1,1].
"""
import math
import importlib
import numpy as np
from . import optics_state as S


def rotation(theta, aspect=1.):
    c,s = math.cos(theta),math.sin(theta)
    return np.array([[c,-s/aspect,0.],[s*aspect,c,0.],[0.,0.,1.]],np.float64)


def fit_matrix(params, aspect=1.):
    theta,px,py = params
    return rotation(theta,aspect) @ np.array([[1.,0.,0.],[0.,1.,0.],[px,py,1.]])


def validate_matrix(value):
    m = np.asarray(value,np.float64).reshape(3,3)
    if not np.isfinite(m).all() or abs(np.linalg.det(m)) < .05 or np.linalg.cond(m) > 100:
        raise ValueError('透视解算退化或过度拉伸，请重新绘制引导线')
    for matrix in (m,np.linalg.inv(m)):
        denominator = np.array([[-1.,-1.,1.],[1.,-1.,1.],[-1.,1.,1.],[1.,1.,1.]]) @ matrix[2]
        if np.min(denominator) <= .15: raise ValueError('透视消失线穿过画布，不能安全渲染')
    return m


def matrix(value, shape):
    p = S.check(value)['perspective']; a = 2.**(p['aspect']/100)
    # Aspect works in actual pixel units, not a normalized-square rotation.
    projective = np.array([[a,0.,0.],[0.,1./a,0.],[p['horizontal']*.004,p['vertical']*.004,1.]])
    manual = rotation(math.radians(p['rotation']),shape[1]/shape[0]) @ projective
    scale = p['scale']/100
    manual = np.diag([scale,scale,1.]) @ manual
    translate = np.array([[1.,0.,p['offset_x']/50],[0.,1.,p['offset_y']/50],[0.,0.,1.]])
    return validate_matrix(translate @ manual @ np.asarray(p['matrix']).reshape(3,3))


def _residual(params, lines, aspect=1.):
    m = fit_matrix(params,aspect)
    pts = lines[:,:4].reshape(-1,2,2)*2-1
    augmented = np.concatenate([pts,np.ones((*pts.shape[:-1],1))],axis=-1)
    mapped = augmented @ m.T
    if np.any(mapped[...,2] < .12): return np.full(len(lines),1e3)
    mapped = mapped[...,:2]/mapped[...,2:]
    delta = (mapped[:,1]-mapped[:,0])*np.array([aspect,1.])
    length = np.linalg.norm(delta,axis=1)
    axis = lines[:,4].astype(int)
    return delta[np.arange(len(lines)),axis]/np.maximum(length,1e-9)


def _fit(lines, mode, *, guided=False, aspect=1.):
    # x residual for vertical, y residual for horizontal. Single-axis modes
    # cannot alter the unrequested projective component.
    available = set(lines[:,4].astype(int))
    keys = [0]+([1] if 1 in available else [])+([2] if 0 in available else [])
    if len(lines) < 2: raise ValueError('有效直线不足，不能解算当前透视自由度')
    weights = lines[:,5]; params = np.zeros(3)
    regularization = .04 if mode == 'smart' and not guided else 1e-6
    for _ in range(32):
        residual = _residual(params,lines,aspect)
        robust = np.minimum(1.,.025/np.maximum(abs(residual),1e-9))*weights
        jac = np.column_stack([(_residual(params+np.eye(3)[key]*1e-5,lines,aspect)-residual)/1e-5 for key in keys])
        lhs = jac.T @ (robust[:,None]*jac)+np.eye(len(keys))*regularization
        rhs = jac.T @ (robust*residual)+params[keys]*regularization
        step = np.linalg.lstsq(lhs,rhs,rcond=1e-10)[0]
        old = float(np.sum(weights*np.minimum(residual**2,.05**2)))+regularization*float(params@params)
        accepted = False
        for rate in (1.,.5,.25,.125,.0625):
            candidate = params.copy(); candidate[keys] -= step*rate
            if abs(candidate[0]) > math.radians(25) or abs(candidate[1])+abs(candidate[2]) > .65: continue
            current = _residual(candidate,lines,aspect)
            cost = float(np.sum(weights*np.minimum(current**2,.05**2)))+regularization*float(candidate@candidate)
            if cost <= old:
                params = candidate; accepted = True; break
        if not accepted or np.linalg.norm(step) < 1e-7: break
    result = validate_matrix(fit_matrix(params,aspect))
    residual = abs(_residual(params,lines,aspect))
    return result,residual


def solve_guides(guides, shape):
    guides = [S.guide(g) for g in guides]
    if len(guides) > 4: raise ValueError('最多 4 条引导线')
    if len(guides) < 2: return S.IDENTITY.copy(),None
    lines = np.array([[*g['start'],*g['end'],0 if g['axis']=='vertical' else 1,1.] for g in guides],np.float64)
    # Parallel duplicates do not provide a perspective constraint.
    for axis in (0,1):
        group = lines[lines[:,4]==axis]
        if len(group)>1:
            centers = (group[:,axis]+group[:,axis+2])/2
            if np.ptp(centers)<.04: raise ValueError('同向引导线过近，请选择相距更远的两条直边')
    m,residual = _fit(lines,'guided',guided=True,aspect=shape[1]/shape[0])
    degrees = float(np.degrees(np.arcsin(np.clip(np.max(residual),0,1))))
    if degrees > 1.5: raise ValueError('引导线互相矛盾或不足以稳定解算，请调整端点/方向')
    return m.ravel().tolist(),{'method':'guided-line-fit-v1','confidence':1.,'lines':len(lines),'residual_degrees':degrees,'message':'已根据实际引导线求解；可继续编辑或删除，最多 4 条'}


def automatic(rgb, mode):
    if mode not in ('smart','horizontal','vertical'): raise ValueError('自动透视模式无效')
    try: cv = importlib.import_module('cv2')
    except ImportError as error: raise RuntimeError('自动透视需要显式安装 OpenCV；手动和引导线仍可用，不会下载模型') from error
    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] != 3 or not np.isfinite(image).all(): raise ValueError('自动透视必须使用真实镜头校正后的 RGB')
    h,w = image.shape[:2]
    factor = min(1.,1400/max(h,w)); ow,oh = max(1,round(w*factor)),max(1,round(h*factor))
    if image.dtype != np.uint8: image = np.rint(np.clip(image,0,1)*255).astype(np.uint8)
    small = cv.resize(image,(ow,oh),interpolation=cv.INTER_AREA) if (ow,oh)!=(w,h) else image
    gray = cv.cvtColor(small,cv.COLOR_RGB2GRAY)
    detected = cv.createLineSegmentDetector(cv.LSD_REFINE_ADV).detect(gray)
    if detected[0] is None: raise ValueError('未找到可信直线；保留原参数，可改用引导线')
    candidates = []
    for raw in detected[0].reshape(-1,4):
        x0,y0,x1,y1 = (float(x) for x in raw)
        length = math.hypot(x1-x0,y1-y0)
        if length < max(24,min(ow,oh)*.08): continue
        angle = abs(math.degrees(math.atan2(y1-y0,x1-x0)))%180
        horizontal = min(angle,180-angle)<30; vertical = abs(angle-90)<30
        if mode=='horizontal' and not horizontal or mode=='vertical' and not vertical: continue
        if not horizontal and not vertical: continue
        axis = 1 if horizontal else 0
        candidates.append([(x0+.5)/ow,(y0+.5)/oh,(x1+.5)/ow,(y1+.5)/oh,axis,length/max(ow,oh)])
    candidates.sort(key=lambda x:x[5],reverse=True)
    # Suppress overlapping near-identical edges; texture cannot masquerade as
    # independent supporting architecture simply by producing many segments.
    unique = []
    for line in candidates:
        center = (np.array(line[:2])+line[2:4])/2
        if any(int(other[4])==int(line[4]) and np.linalg.norm(center-(np.array(other[:2])+other[2:4])/2)<.035 for other in unique): continue
        unique.append(line)
        if len(unique)==96: break
    lines = np.asarray(unique,np.float64)
    if len(lines)<4: raise ValueError('可信直线少于 4 条；未自动改图，请使用引导线')
    m,residual = _fit(lines,mode,aspect=w/h)
    inliers = residual < math.sin(math.radians(3))
    if np.count_nonzero(inliers)<4: raise ValueError('直线方向不一致，自动透视置信度不足；保留原参数')
    m,residual = _fit(lines[inliers],mode,aspect=w/h)
    good = lines[inliers]; support = float(good[:,5].sum()/lines[:,5].sum())
    spread = max(float(np.ptp((good[:,0]+good[:,2])/2)),float(np.ptp((good[:,1]+good[:,3])/2)))
    degrees = float(np.degrees(np.arcsin(np.clip(np.average(residual,weights=good[:,5]),0,1))))
    confidence = min(1.,len(good)/8)*min(1.,spread/.45)*support*math.exp(-degrees/3)
    if confidence < .45: raise ValueError(f'自动透视置信度不足（{confidence:.0%}）；保留原参数，请使用引导线')
    return m.ravel().tolist(),{'method':'opencv-lsd-robust-projective-v1','confidence':confidence,'lines':len(good),'residual_degrees':degrees,
                             'message':'基于真实线段的自动校正，不是 AI 模型；智能模式保守折中，避免强行拉直所有线条'}
