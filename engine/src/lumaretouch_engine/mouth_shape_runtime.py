"""Selected-face lifecycle and geometry-only grid integration hooks for mouth v1."""
import numpy as np
from . import mouth_shape_state as S
from .mouth_shape_geometry import build_controls
from .mouth_shape_field import MouthField,compose_delta


# Identity and semantic veto are one shared selected-face contract.
from .nose_shape_runtime import identity,exclusion


class MouthRefusal(ValueError):
    def __init__(self,facts):
        self.facts={k:{**v, 'applied':False,
            'reason':v['reason'] or ('atomic_request_refused' if v['requested'] else None)}
            for k,v in facts.items()}
        refused={key:fact['reason'] for key,fact in facts.items() if fact['requested'] and not fact['applied']}
        super().__init__(f'嘴形局部可见性不足，整次修改未应用：{refused}')


def build(landmarks,recipe,source,excluded,*,backend):
    if not S.active(recipe): return None
    identity(landmarks)
    P,D,meta=build_controls(landmarks,source.shape[:2],recipe,source,excluded,backend=backend)
    if any(f['requested'] and not f['applied'] for f in meta['controls'].values()):
        raise MouthRefusal(meta['controls'])
    return MouthField(P,D,meta,source.shape[:2])


def clear(pipe):
    pipe.mouth_shape_teeth_support=None
    pipe.mouth_shape_field=None; pipe.mouth_shape_signature=None; pipe.mouth_shape_key=None; pipe.mouth_shape_combined=False
    pipe.mouth_shape_version=getattr(pipe,'mouth_shape_version',0)+1
    pipe._deform_warp=None; pipe._deform_warp_key=None


def sync(engine,*,strict=False):
    pipe=engine._vram
    if pipe is None: return
    recipe=S.check(getattr(engine,'_mouth_shape',None))
    if not S.active(recipe) and getattr(pipe,'mouth_shape_field',None) is None:
        # Neutral must not invalidate the established automatic warp/cache.
        pipe.mouth_shape=recipe; pipe.mouth_shape_suspended=None
        pipe.mouth_shape_signature=None; pipe.mouth_shape_key=None
        engine._mouth_shape_refusal=None
        return
    try:
        check_legacy(recipe,engine._effective_deform_amounts())
        field=None; signature=None; key=None
        if S.active(recipe):
            pc=engine._precompute
            if pc is None or getattr(pc,'backend',None)!='mediapipe': raise ValueError('嘴形需要真实人像分析')
            if getattr(pc,'num_faces',1)!=1 and not getattr(engine,'_face_explicit',False):
                raise ValueError('嘴形需要明确选择一个人物')
            signature=identity(pc.landmarks)
            if getattr(engine,'_mouth_shape_owner',None)!=signature:
                raise ValueError('嘴形属于另一人物或人物身份已变化；请切回原人物或先重置')
            key=(signature,tuple(S.vector(recipe)),recipe['gummy']['linked'],
                 pipe.repair_version,id(pipe.src_f32),id(pc),getattr(pc,'semantic_model_sha256',None))
            if key==getattr(pipe,'mouth_shape_key',None): return
            source=pipe.src_f32
            if source is None: raise ValueError('嘴形缺少原始源图')
            import torch
            admit_working_set((pipe.h,pipe.w))
            rgb=source[0].permute(1,2,0).to('cpu',torch.float32).numpy()
            field=build(pc.landmarks,recipe,rgb,exclusion(pc),backend=pc.backend)
            refused={side:fact['reason'] for side,fact in field.facts.items() if fact['requested'] and not fact['applied']}
            if refused: raise ValueError(f'嘴形可见性不足，未应用本次修改：{refused}')
        # Prepare completely before publishing: failed strict transactions retain
        # the previous field so the command owner can roll back atomically.
        clear(pipe); pipe.mouth_shape_field=field; pipe.mouth_shape_signature=signature
        pipe.mouth_shape=recipe; pipe.mouth_shape_suspended=None; pipe.mouth_shape_key=key
        engine._mouth_shape_refusal=None
    except Exception as error:
        if isinstance(error,MouthRefusal):
            engine._mouth_shape_refusal=(engine._load_id,identity(engine._precompute.landmarks),error.facts)
        if strict: raise
        clear(pipe); pipe.mouth_shape=recipe; pipe.mouth_shape_suspended=str(error)


def has_mouth(pipe):
    field=getattr(pipe,'mouth_shape_field',None)
    return field is not None and field.state is not None


def joint_delta(pipe,auto_delta):
    """M(E(N(B(A(x))))) evaluated at actual off-grid pullback coordinates."""
    from .mouth_shape_field import compose_delta
    delta,_=compose_delta(auto_delta,getattr(pipe,'brow_shape_field',None),
        getattr(pipe,'nose_shape_field',None),getattr(pipe,'eye_shape_field',None),
        getattr(pipe,'mouth_shape_field',None),(pipe.h,pipe.w))
    if delta is None: return None
    import torch
    return torch.as_tensor(delta,dtype=torch.float32,device=pipe.device)


def report(engine):
    pipe=engine._vram; field=getattr(pipe,'mouth_shape_field',None)
    pc=getattr(engine,'_precompute',None)
    try: selected=identity(pc.landmarks) if pc is not None else 'none'
    except ValueError: selected='none'
    recipe=S.check(getattr(engine,'_mouth_shape',None))
    import json
    key=json.dumps((getattr(engine,'_load_id',None),selected,recipe),sort_keys=True)
    if key!=getattr(engine,'_mouth_report_key',None):
        engine._mouth_report_revision=getattr(engine,'_mouth_report_revision',0)+1; engine._mouth_report_key=key
    refused=getattr(engine,'_mouth_shape_refusal',None)
    facts=field.facts if field else {}
    if refused and refused[:2]==(getattr(engine,'_load_id',None),selected): facts=refused[2]
    from .mouth_shape_native import native
    try:
        native(); available=True
    except (RuntimeError,OSError,AttributeError):
        available=False
    return {'version':1,'revision':engine._mouth_report_revision,'selected_face_id':selected,'recipe':recipe,
        'controls':facts,'native_available':available,'suspended':getattr(pipe,'mouth_shape_suspended',None),
        'bytes_fields':field.resident_bytes() if field else 0,
        'legacy_smile':float(engine._effective_deform_amounts().get('smile',0)),
        'order':'M(E(N(B(A(x)))))_one_sampler',
        'boundaries':['只搬运已有唇部纹理，不生成牙齿、牙龈或嘴部内部；闭口不支持露龈调整',
                      '侧脸、遮挡、低对比或退化几何保守拒绝；非完整嘴部或遮挡分割；旧版微笑保持原值，与 M 唇叠加']}



def export_field(spec,source,*,divisor):
    recipe=S.check(getattr(spec,'mouth_shape',None))
    check_legacy(recipe,getattr(spec,'deform_amounts',{}))
    if not S.active(recipe): return None
    if (source.dtype==np.uint8 and divisor!=255) or (source.dtype==np.uint16 and divisor!=65535) or source.dtype not in (np.uint8,np.uint16):
        raise ValueError('嘴形导出需要原始 RGB8/RGB16')
    pc=getattr(spec,'mouth_shape_face',None)
    if pc is None or getattr(pc,'backend',None)!='mediapipe': raise ValueError('嘴形导出缺少真实人物')
    if identity(pc.landmarks)!=identity(spec.landmarks): raise ValueError('嘴形导出人物身份不匹配')
    veto=exclusion(pc)
    h,w=source.shape[:2]
    if veto is not None and veto.shape!=(h,w):
        import cv2
        veto=cv2.resize(veto,(w,h),interpolation=cv2.INTER_LINEAR)
    admit_working_set((h,w))
    field=build(spec.landmarks,recipe,source.astype(np.float32)/divisor,veto,backend=pc.backend)
    refused={side:fact['reason'] for side,fact in field.facts.items() if fact['requested'] and not fact['applied']}
    if refused: raise ValueError(f'嘴形导出存在不可应用控件，未静默省略：{refused}')
    return field


def configure_export(spec,snap):
    spec.mouth_shape=S.check(snap.get('mouth_shape'))
    spec.mouth_shape_face=None
    if not S.active(spec.mouth_shape): return
    pc=snap.get('precompute')
    if pc is None or getattr(pc,'backend',None)!='mediapipe': raise ValueError('嘴形导出缺少真实选中人物')
    if snap.get('mouth_shape_owner')!=identity(pc.landmarks): raise ValueError('嘴形导出人物归属不匹配')
    spec.landmarks=np.array(pc.landmarks,dtype=np.float32,copy=True)
    spec.mouth_shape_face=pc


def admit_working_set(shape):
    from .cpu_memory_budget import available_estimate
    h,w=shape
    # Original float RGB + joint field + semantic veto and finite-validation
    # temporaries, plus bounded float64 TPS pair matrices. Never proxy fallback.
    needed=int(h)*int(w)*180+128*1024*1024
    if needed>available_estimate():
        raise ValueError('嘴形全尺寸几何内存预算不足；未缩图或省略效果')
    return needed


def has_source_geometry(pipe):
    from .eye_shape_runtime import has_source_geometry as previous
    return previous(pipe) or has_mouth(pipe) or getattr(pipe,'mouth_shape_combined',False)


def warp_key(pipe):
    from .eye_shape_runtime import warp_key as previous
    key=previous(pipe)
    if has_mouth(pipe): key+=(('mouth_shape',pipe.mouth_shape_version),)
    return key


def check_legacy(recipe,amounts):
    """Legacy smile is unchanged. Stacking is intentional and disclosed in UI."""
    S.check(recipe)
