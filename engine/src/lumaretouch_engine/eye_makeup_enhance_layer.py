# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen-source original eye makeup, target-owned review and measured protection.

478 points locate conservative periocular limits, NOT cosmetic segmentation.
Visible source pigment is user-reviewed; references are independent same-eye
bare-skin samples, not a claim to know the skin hidden under pigment. UNRUN.
"""
import hashlib
import math
import numpy as np
from . import eye_makeup_enhance_state as S, eye_makeup_enhance_support as V
from . import eye_makeup_enhance_native as N, people_state as P
from .face_scope import FACE_OVAL, LIPS, _polygon_field
from .ops.enhance import EYE_RING_LEFT, EYE_RING_RIGHT
from .brow_makeup_geometry import CHAINS
from .skin_colour_support import check_analysis_fields

# Explicit subject-relative sides. Existing EYE_RING names use image convention.
_EYES = {'left': (EYE_RING_RIGHT, (263,362)), 'right': (EYE_RING_LEFT, (33,133))}
_FOOTPRINT = math.sqrt(.5)


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('已有眼妆增强取消，未发布部分图层')


def _boxes(value):
    if type(value) not in (list,tuple) or len(value) > P.MAX_FACES:
        raise ValueError('眼妆邻近人物保护范围无效')
    for box in value:
        if (type(box) not in (list,tuple) or len(box)!=4
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in box)
                or not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1):
            raise ValueError('眼妆须使用所有其他已保留人物的真实源图归一化框')
    return value


def _geometry(landmarks, eyes, sides, shape, need_references):
    h,w = shape; points=landmarks[:,:2].astype(np.float64)*[w-1,h-1]
    widths={side:float(np.linalg.norm(points[ends[1]]-points[ends[0]])) for side,(_,ends) in _EYES.items()}
    if min(widths.values()) < 32 or min(widths.values()) < .55*max(widths.values()):
        raise ValueError('原有眼妆需要足够大且非严重侧转的双眼实测定位')
    geometry=[]
    for side in sides:
        if side not in eyes:
            raise ValueError('请独立审核人物'+('左' if side=='left' else '右')+'侧已有眼妆')
        eye=eyes[side]; ring,ends=_EYES[side]; width=widths[side]
        a,b=points[list(ends)]; centre=(a+b)*.5; axis=(b-a)/width
        up=np.array([-axis[1],axis[0]])
        if np.dot(up,points[10]-centre)<0: up=-up
        radius=max(1,int(round(width*.0125)))
        if radius>N.MAX_RADIUS: raise ValueError('眼妆实测结构半径超预算，不改变尺度伪装支持')
        vectors=[eye['makeup'],*eye['exclusions']]
        if side in need_references and eye['reference_a'] is not None: vectors.extend((eye['reference_a'],eye['reference_b']))
        coords=[np.asarray(v,np.float64)*[w-1,h-1] for v in vectors]
        # Restrict even independently reviewed points to the measured same-eye
        # neighbourhood; no forehead/cheek brightness masquerades as eye makeup.
        allpoints=np.concatenate(coords); relative=allpoints-centre
        if np.any(np.abs(relative@axis)>.95*width) or np.any(relative@up > .72*width) or np.any(relative@up < -.45*width):
            raise ValueError('审核轮廓超出此人物实测眼周范围，请勿包含另一眼或普通面部皮肤')
        pad=3*radius+3
        x,y=np.floor(allpoints.min(0)-pad).astype(int); x1,y1=np.ceil(allpoints.max(0)+pad+1).astype(int)
        if x<1 or y<1 or x1>w-1 or y1>h-1: raise ValueError('眼妆或皮肤参考被图像边界裁切')
        shape_roi=(int(y1-y),int(x1-x)); N.memory_estimate(shape_roi)
        geometry.append({'side':side,'width':width,'radius':radius,'centre':centre,'axis':axis,'up':up,
            'window':(int(y),int(x),*shape_roi),'points':points,'eye':eye,'need_reference':side in need_references})
    return geometry


def _field(xx,yy,polygon,feather):
    inside,distance=_polygon_field(xx,yy,polygon)
    return np.where(inside,np.clip((distance-_FOOTPRINT)/feather,0,1),0)


def _observe(source,skin,excluded,g,boxes,cancelled):
    _poll(cancelled); y,x,h,w=g['window']; H,W=source.shape[:2]
    xx=np.arange(x,x+w,dtype=np.float64)[None,:]; yy=np.arange(y,y+h,dtype=np.float64)[:,None]
    points=g['points']; width=g['width']; feather=max(1.,width*.018)
    safe=_field(xx,yy,points[list(FACE_OVAL)],feather)
    # Lash-line guard expands measured globe contours rather than pretending to
    # segment individual eyelashes. Explicit review exclusions remain mandatory.
    for ring,_ in _EYES.values():
        inside,distance=_polygon_field(xx,yy,points[list(ring)])
        safe*=np.where(inside,0,np.clip((distance-_FOOTPRINT-width*.075)/feather,0,1))
    for upper,lower in CHAINS.values():
        polygon=np.concatenate((points[list(upper)],points[list(lower)][::-1]))
        inside,distance=_polygon_field(xx,yy,polygon)
        safe*=np.where(inside,0,np.clip((distance-_FOOTPRINT-width*.045)/feather,0,1))
    inside,distance=_polygon_field(xx,yy,points[list(LIPS)])
    safe*=np.where(inside,0,np.clip((distance-_FOOTPRINT)/feather,0,1))
    # Mid-face/nose side hard fence: retain only measured side of bridge 168.
    other='right' if g['side']=='left' else 'left'
    other_centre=points[list(_EYES[other][1])].mean(0)
    between=other_centre-g['centre']; span=float(np.linalg.norm(between)); between/=span
    mid=(other_centre+g['centre'])*.5
    mid_distance=-((xx-mid[0])*between[0]+(yy-mid[1])*between[1])
    safe*=np.clip((mid_distance-width*.10)/feather,0,1)
    for box in boxes:
        _poll(cancelled)
        left,top,right,bottom=np.asarray(box)*[W,H,W,H]
        halo=max(1.,width*.04)+_FOOTPRINT
        if right+halo<x or left-halo>x+w or bottom+halo<y or top-halo>y+h: continue
        dx=np.maximum(np.maximum(left-xx,xx-right),0); dy=np.maximum(np.maximum(top-yy,yy-bottom),0)
        safe*=np.clip((np.hypot(dx,dy)-_FOOTPRINT)/max(1.,width*.04),0,1)
    eye=g['eye']; scale=np.array([W-1,H-1])
    for poly in eye['exclusions']:
        inside,distance=_polygon_field(xx,yy,np.asarray(poly)*scale)
        safe*=np.where(inside,0,np.clip((distance-_FOOTPRINT)/feather,0,1))
    safe*=((skin[y:y+h,x:x+w]>=.65)&(excluded[y:y+h,x:x+w]<=.10))
    target_poly=np.asarray(eye['makeup'])*scale
    target_raw=_field(xx,yy,target_poly,feather)
    target=np.ascontiguousarray(target_raw*safe,dtype=np.float32)
    # Remove ambiguous clipped/glint/shadow samples from both edits and kernels.
    rgb=source[y:y+h,x:x+w]
    photometric=np.all((rgb>.005)&(rgb<.985),axis=2)
    target*=photometric
    target_count=int(np.count_nonzero(target>.5)); raw_count=int(np.count_nonzero(target_raw>.5))
    if target_count<32 or target_count<.70*max(1,raw_count):
        raise ValueError(g['side']+' 眼妆受保护或不可靠区域过多；请缩小到真实可见妆区')
    references=[]
    for name in ('reference_a','reference_b'):
        if not g['need_reference'] or eye[name] is None:
            references.append(np.zeros((h,w),np.float32)); continue
        raw=_field(xx,yy,np.asarray(eye[name])*scale,feather)
        ref=np.ascontiguousarray(raw*safe*photometric,dtype=np.float32)
        if np.count_nonzero(ref>.5)<16 or np.count_nonzero(ref>.5)<.80*max(1,np.count_nonzero(raw>.5)):
            raise ValueError(g['side']+' 独立干净皮肤参考面积不足或被保护区遮挡')
        # Reference must not use any pixel of the reviewed makeup polygon even
        # if that target pixel was vetoed by an occluder or a low skin score.
        in_makeup,edge=_polygon_field(xx,yy,target_poly)
        if np.any((ref>0)&(in_makeup|(edge<feather+_FOOTPRINT))):
            raise ValueError('独立干净皮肤参考触及眼妆范围，不能估计减淡方向')
        references.append(ref)
    a,b=references
    if np.any((a>0)&(b>0)): raise ValueError('两块皮肤参考必须独立，不能互相重叠')
    for array in (target,a,b): array.setflags(write=False)
    return target,a,b,{'reviewed_makeup_pixels':raw_count,'permitted_makeup_pixels':target_count,
        'reference_pixels':[int(np.count_nonzero(a)),int(np.count_nonzero(b))],
        'measured_eye_width':width,'radius':g['radius']}


def prepare(face_ref,analysis,source,recipe,*,reviewed,byte_budget,protected_boxes=(),cancelled=None):
    """All active sides, one frozen source grid; return one immutable delta layer.

    Caller supplies EVERY other retained same-source face box, including disabled
    and unresolved faces, and validates opaque SDR source provenance beforehand.
    No tile solver, aliased source, proxy-mask enlargement or fallback effect.
    """
    recipe=S.check(recipe)
    if not S.active(recipe): return []
    if cancelled is not None and not callable(cancelled): raise TypeError('cancelled must be callable')
    _poll(cancelled); ref=P.check_ref(face_ref); record=V.check_record(reviewed)
    if record['face_ref']!=ref: raise ValueError('眼妆支撑属于另一人物或来源')
    if type(source) is not np.ndarray or source.dtype!=np.float32 or source.ndim!=3 or source.shape[-1]!=3:
        raise ValueError('眼妆需要原始有效源 float32 working-sRGB SDR RGB，不接受 alpha')
    h,w=source.shape[:2]
    if type(byte_budget) is not int or byte_budget<32*h*w+16*1024**2:
        raise MemoryError('眼妆源校验前内存预算不足')
    if type(analysis) is not dict or analysis.get('face_ref')!=ref:
        raise ValueError('眼妆需要当前人物自己持有的真实分析')
    evidence=P.check_evidence(analysis.get('evidence'))
    if evidence['status']!='verified' or evidence['backend']!='mediapipe':
        raise ValueError('眼妆需要真实保留的 478 点分析，不能凭空生成面部')
    if (record['source']['width'],record['source']['height'])!=(evidence['source_width'],evidence['source_height']):
        raise ValueError('眼妆支撑与人物来源尺寸不符')
    lm=np.asarray(analysis.get('landmarks'),dtype='<f4')
    if (lm.shape!=(478,3) or not np.isfinite(lm).all() or np.any((lm[:,:2]<0)|(lm[:,:2]>1))
            or hashlib.sha256(np.ascontiguousarray(lm).tobytes()).hexdigest()!=evidence['landmark_digest']
            or record['row']['landmark_digest']!=evidence['landmark_digest']):
        raise ValueError('眼妆真实关键点缺失、裁切或摘要不一致')
    sides=[side for side in S.SIDES if S.side_active(recipe,side)]
    geometry=_geometry(lm,record['row']['eyes'],sides,(h,w),{side for side in sides if recipe['amount'][side]!=0}); boxes=_boxes(protected_boxes)
    work=0
    for g in geometry:
        eye=g['eye']; gy,gx,gh,gw=g['window']
        edges=len(FACE_OVAL)+len(LIPS)+sum(len(ring) for ring,_ in _EYES.values())+20
        edges+=sum(len(poly) for poly in eye['exclusions'])+3*len(eye['makeup'])
        if g['need_reference']: edges+=sum(len(eye[key]) if eye[key] is not None else 0 for key in ('reference_a','reference_b'))
        work+=gh*gw*(edges+len(boxes))
    if work>180_000_000:
        raise MemoryError('眼妆轮廓、邻脸保护与原尺寸栅格工作量超预算，不简化轮廓或降采样')
    y=min(g['window'][0] for g in geometry); x=min(g['window'][1] for g in geometry)
    y1=max(g['window'][0]+g['window'][2] for g in geometry); x1=max(g['window'][1]+g['window'][3] for g in geometry)
    reserve=32*h*w+16*1024**2+24*(y1-y)*(x1-x)+sum(224*g['window'][2]*g['window'][3] for g in geometry)
    if reserve+max(N.memory_estimate(g['window'][2:]) for g in geometry)>byte_budget:
        raise MemoryError('眼妆完整支撑、结构与原尺寸求解超预算，不降采样')
    if not np.isfinite(source).all() or np.any((source<0)|(source>1)):
        raise ValueError('眼妆不接受非有限或 HDR 源像素，也不会裁切源图')
    observation=check_analysis_fields(analysis,(h,w)); skin=analysis.get('face_skin'); excluded=analysis.get('excluded')
    if observation is None: raise ValueError('眼妆缺少真实 face-skin 观察；不借用合并皮肤蒙版')
    for value in (skin,excluded):
        if type(value) is not np.ndarray or value.dtype!=np.float32 or value.shape!=(h,w) or not np.isfinite(value).all() or np.any((value<0)|(value>1)):
            raise ValueError('眼妆需要当前网格真实皮肤与已知遮挡证据')
    observed=[]
    for g in geometry:
        if recipe['amount'][g['side']]!=0 and g['eye']['reference_a'] is None:
            raise ValueError('原有妆效增强或减淡须有两块同眼邻近干净皮肤参考；不会猜测卸妆')
        observed.append((g,*_observe(source,skin,excluded,g,boxes,cancelled)))
    merged=np.zeros((y1-y,x1-x,3),np.float32); occupied=np.zeros(merged.shape[:2],bool); facts={}
    for g,target,a,b,observations in observed:
        _poll(cancelled); gy,gx,gh,gw=g['window']; controls=S.side_controls(recipe,g['side'])
        frozen=np.array(source[gy:gy+gh,gx:gx+gw],dtype=np.float32,order='C',copy=True); frozen.setflags(write=False)
        output=N.apply(frozen,target,controls,reference_a=a,reference_b=b,radius=g['radius'],cancelled=cancelled or (lambda:False))
        delta=np.ascontiguousarray(output-frozen,dtype=np.float32)
        if not np.isfinite(delta).all() or np.any(delta[target==0]!=0): raise ValueError('眼妆修改了保护区，已丢弃')
        changed=np.any(delta!=0,axis=2); used=occupied[gy-y:gy-y+gh,gx-x:gx-x+gw]
        if np.any(used & changed): raise ValueError('左右眼妆区域重叠，未重复叠加')
        merged[gy-y:gy-y+gh,gx-x:gx-x+gw][changed]=delta[changed]; used[changed]=True
        facts[g['side']]={**observations,'controls':controls,'changed_pixels':int(np.count_nonzero(changed)),
            'reason':None if np.any(changed) else 'no_measurable_change'}
    _poll(cancelled); merged.setflags(write=False)
    from .people_effects import LocalEffect
    return [LocalEffect(ref,'eye_makeup_enhance',(y,x,y1-y,x1-x),delta=merged,facts={
        'recipe':recipe,'review_sha256':V.content_digest(record),'face_ref':ref,'sides':facts,
        'landmark_digest':evidence['landmark_digest'],'face_skin_observation':observation,
        'changed_pixels':int(np.count_nonzero(occupied)),'native_solver':'rust-eye-makeup-enhance-v1',
        'source_dimensions':[record['source']['width'],record['source']['height']],'render_dimensions':[w,h],
        'protected_face_boxes':len(boxes),'limitations':['user-reviewed-visible-makeup-not-cosmetic-segmentation',
        'paired-nearby-skin-reference-not-known-underlying-skin','bounded-appearance-fading-not-makeup-removal',
        'no-pigment-pattern-generation-or-hidden-anatomy','authored-unrun-no-photo-quality-acceptance']})]
