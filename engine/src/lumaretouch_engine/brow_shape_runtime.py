"""Selected-face lifecycle and geometry-only grid integration hooks for brow v1."""
import hashlib
import re
import numpy as np
from . import brow_shape_state as S
from .brow_shape_geometry import build_controls
from .brow_shape_field import BrowField,compose_delta


def identity(landmarks):
    lm=np.asarray(landmarks,dtype='<f4')
    if lm.shape!=(478,3) or not np.isfinite(lm).all() or np.any((lm[:,:2]<0)|(lm[:,:2]>1)):
        raise ValueError('眉形人物身份需要真实归一化 478×3 网格')
    return hashlib.sha256(np.ascontiguousarray(lm).tobytes()).hexdigest()


def exclusion(pc):
    if pc is None or getattr(pc,'backend',None)!='mediapipe': return None
    if not re.fullmatch('[0-9a-f]{64}',str(getattr(pc,'semantic_model_sha256',None))): return None
    fields=[]
    for key in ('hair','clothes','background'):
        v=(getattr(pc,'masks',None) or {}).get(key)
        if v is None: return None
        v=np.asarray(v,np.float32)
        if v.ndim!=2 or not np.isfinite(v).all() or np.any((v<0)|(v>1)):
            raise ValueError('眉形已知遮挡来源无效')
        if fields and v.shape!=fields[0].shape: raise ValueError('眉形遮挡场尺寸不一致')
        fields.append(v)
    return np.ascontiguousarray(np.maximum.reduce(fields))


def build(landmarks,recipe,source,excluded,*,backend):
    if not S.active(recipe): return None
    identity(landmarks)
    P,D,meta=build_controls(landmarks,source.shape[:2],recipe,source,excluded,backend=backend)
    return BrowField(P,D,meta,source.shape[:2])


def clear(pipe):
    pipe.brow_shape_field=None; pipe.brow_shape_signature=None; pipe.brow_shape_key=None; pipe.brow_shape_combined=False
    pipe.brow_shape_version=getattr(pipe,'brow_shape_version',0)+1
    pipe._deform_warp=None; pipe._deform_warp_key=None


def sync(engine,*,strict=False):
    pipe=engine._vram
    if pipe is None: return
    recipe=S.check(getattr(engine,'_brow_shape',None))
    if not S.active(recipe) and getattr(pipe,'brow_shape_field',None) is None:
        # Neutral must not invalidate the established automatic warp/cache.
        pipe.brow_shape=recipe; pipe.brow_shape_suspended=None
        pipe.brow_shape_signature=None; pipe.brow_shape_key=None
        return
    try:
        field=None; signature=None; key=None
        if S.active(recipe):
            pc=engine._precompute
            if pc is None or getattr(pc,'backend',None)!='mediapipe': raise ValueError('眉形需要真实人像分析')
            if getattr(pc,'num_faces',1)!=1 and not getattr(engine,'_face_explicit',False):
                raise ValueError('眉形需要明确选择一个人物')
            signature=identity(pc.landmarks)
            if getattr(engine,'_brow_shape_owner',None)!=signature:
                raise ValueError('眉形属于另一人物或人物身份已变化；请切回原人物或先重置')
            key=(signature,tuple((r,recipe[r]['linked'],recipe[r]['left'],recipe[r]['right']) for r in S.KEYS),
                 pipe.repair_version,id(pipe.src_f32),id(pc),getattr(pc,'semantic_model_sha256',None))
            if key==getattr(pipe,'brow_shape_key',None): return
            source=pipe.src_f32
            if source is None: raise ValueError('眉形缺少原始源图')
            import torch
            admit_working_set((pipe.h,pipe.w))
            rgb=source[0].permute(1,2,0).to('cpu',torch.float32).numpy()
            field=build(pc.landmarks,recipe,rgb,exclusion(pc),backend=pc.backend)
            refused={side:fact['reason'] for side,fact in field.facts.items() if fact['requested'] and not fact['applied']}
            if refused: raise ValueError(f'眉形可见性不足，未应用本次修改：{refused}')
        # Prepare completely before publishing: failed strict transactions retain
        # the previous field so the command owner can roll back atomically.
        clear(pipe); pipe.brow_shape_field=field; pipe.brow_shape_signature=signature
        pipe.brow_shape=recipe; pipe.brow_shape_suspended=None; pipe.brow_shape_key=key
    except Exception as error:
        if strict: raise
        clear(pipe); pipe.brow_shape=recipe; pipe.brow_shape_suspended=str(error)


def has_brow(pipe):
    field=getattr(pipe,'brow_shape_field',None)
    return field is not None and field.state is not None


def joint_delta(pipe,auto_delta):
    """Call inside apply_deform grid preparation only, before the ONE sampler."""
    field=getattr(pipe,'brow_shape_field',None)
    if field is None: return auto_delta
    delta,_=compose_delta(auto_delta,field,(pipe.h,pipe.w))
    if delta is None: return None
    import torch
    return torch.as_tensor(delta,dtype=torch.float32,device=pipe.device)


def report(engine):
    pipe=engine._vram; field=getattr(pipe,'brow_shape_field',None)
    pc=getattr(engine,'_precompute',None)
    try: selected=identity(pc.landmarks) if pc is not None else 'none'
    except ValueError: selected='none'
    recipe=S.check(getattr(engine,'_brow_shape',None))
    import json
    key=json.dumps((getattr(engine,'_load_id',None),selected,recipe),sort_keys=True)
    if key!=getattr(engine,'_brow_report_key',None):
        engine._brow_report_revision=getattr(engine,'_brow_report_revision',0)+1; engine._brow_report_key=key
    return {'version':1,'revision':engine._brow_report_revision,'selected_face_id':selected,'recipe':recipe,
        'sides':field.facts if field else {},'suspended':getattr(pipe,'brow_shape_suspended',None),
        'bytes_fields':field.resident_bytes() if field else 0,
        'order':'source_brow_then_automatic_one_sampler',
        'boundaries':['人物左/右，重新联动不覆盖不等值；下一次明确联动调整才同步',
                      '只搬运现有眉毛，不生发、不补眉、不换眉毛素材',
                      '低对比、遮挡或不可靠侧眉拒绝；非完整眉毛分割']}


def export_field(spec,source,*,divisor):
    recipe=S.check(getattr(spec,'brow_shape',None))
    if not S.active(recipe): return None
    if divisor not in (255,65535) or source.dtype not in (np.uint8,np.uint16):
        raise ValueError('眉形导出需要原始 RGB8/RGB16')
    pc=getattr(spec,'brow_shape_face',None)
    if pc is None or getattr(pc,'backend',None)!='mediapipe': raise ValueError('眉形导出缺少真实人物')
    if identity(pc.landmarks)!=identity(spec.landmarks): raise ValueError('眉形导出人物身份不匹配')
    veto=exclusion(pc)
    h,w=source.shape[:2]
    if veto is not None and veto.shape!=(h,w):
        import cv2
        veto=cv2.resize(veto,(w,h),interpolation=cv2.INTER_LINEAR)
    admit_working_set((h,w))
    field=build(spec.landmarks,recipe,source.astype(np.float32)/divisor,veto,backend=pc.backend)
    refused={side:fact['reason'] for side,fact in field.facts.items() if fact['requested'] and not fact['applied']}
    if refused: raise ValueError(f'眉形导出存在不可应用侧别，未静默省略：{refused}')
    return field


def configure_export(spec,snap):
    spec.brow_shape=S.check(snap.get('brow_shape'))
    spec.brow_shape_face=None
    if not S.active(spec.brow_shape): return
    pc=snap.get('precompute')
    if pc is None or getattr(pc,'backend',None)!='mediapipe': raise ValueError('眉形导出缺少真实选中人物')
    if snap.get('brow_shape_owner')!=identity(pc.landmarks): raise ValueError('眉形导出人物归属不匹配')
    spec.landmarks=np.array(pc.landmarks,dtype=np.float32,copy=True)
    spec.brow_shape_face=pc


def admit_working_set(shape):
    from .cpu_memory_budget import available_estimate
    h,w=shape
    # Original float RGB + joint field + semantic veto and finite-validation
    # temporaries, plus bounded float64 TPS pair matrices. Never proxy fallback.
    needed=int(h)*int(w)*32+96*1024*1024
    if needed>available_estimate():
        raise ValueError('眉形全尺寸几何内存预算不足；未缩图或省略效果')
    return needed
