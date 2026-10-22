"""Selected-person preview/export lifecycle for independent lip recipe v1."""
import hashlib
import re
import numpy as np
from . import lip_makeup_state as S
from .lip_makeup_layer import LipMakeupLayer, attach_delta
from .ops.enhance import _landmark_pixels


def identity(landmarks):
    lm=np.asarray(landmarks,dtype='<f4')
    if lm.shape!=(478,3) or not np.isfinite(lm).all() or np.any((lm[:,:2]<-1)|(lm[:,:2]>2)):
        raise ValueError('唇妆人物身份需要真实归一化 478×3 关键点')
    return hashlib.sha256(np.ascontiguousarray(lm).tobytes()).hexdigest()


def bounds(landmarks,h,w):
    lm=_landmark_pixels(landmarks,h,w).astype(np.float32)
    pad=max(np.linalg.norm(lm[33]-lm[133]),np.linalg.norm(lm[263]-lm[362]))*2
    x,y=np.maximum(np.floor(lm.min(0)-pad),0).astype(int)
    x1,y1=np.minimum(np.ceil(lm.max(0)+pad)+1,[w,h]).astype(int)
    return (int(y),int(x),int(y1-y),int(x1-x)),lm


def exclusion(pc):
    if (pc is None or getattr(pc,'backend',None)!='mediapipe'
        or not re.fullmatch('[0-9a-f]{64}',str(getattr(pc,'semantic_model_sha256',None)))): return None
    fields=[]
    for key in ('hair','clothes','background'):
        v=(getattr(pc,'masks',None) or {}).get(key)
        if v is None: return None
        v=np.asarray(v,np.float32)
        if v.ndim!=2 or not v.size or not np.isfinite(v).all() or np.any((v<0)|(v>1)):
            raise ValueError('唇妆可见性来源无效')
        if fields and fields[0].shape!=v.shape: raise ValueError('唇妆排除场尺寸不一致')
        fields.append(v)
    return np.ascontiguousarray(np.maximum.reduce(fields),dtype=np.float32)


def clear_layer(pipe):
    pipe.lip_makeup_layer=None; pipe.lip_makeup_delta=None; pipe.lip_makeup_local=None
    pipe.lip_makeup_tile_key=None; pipe.lip_makeup_facts={}


def clear_face(pipe):
    clear_layer(pipe); pipe.lip_makeup_face=None


def install_face(pipe,pc):
    lm=np.array(pc.landmarks,dtype=np.float32,copy=True); signature=identity(lm)
    veto=exclusion(pc)
    if veto is not None and veto.shape!=(pipe.h,pipe.w): raise ValueError('唇妆排除场与源图未对齐')
    pipe.lip_makeup_face={'landmarks':lm,'signature':signature,'excluded':veto,'backend':pc.backend,'model':getattr(pc,'semantic_model_sha256',None)}
    clear_layer(pipe)


def solve_preview(pipe,recipe):
    r=S.check(recipe)
    if not S.active(r):
        clear_layer(pipe); pipe.lip_makeup_facts={'reason':'disabled','gated_px':0,'changed_px':0}
        return
    face=getattr(pipe,'lip_makeup_face',None)
    if face is None: raise ValueError('唇妆尚未绑定当前选中人物')
    layer=getattr(pipe,'lip_makeup_layer',None)
    if layer is None or layer.source_version!=pipe.repair_version or layer.identity!=face['signature']:
        import torch
        admit_working_set((pipe.h,pipe.w),face['landmarks'],additional_bytes=resident_bytes(pipe))
        window,lm=bounds(face['landmarks'],pipe.h,pipe.w); y,x,h,w=window
        source=pipe.repair_base if pipe.repair_base is not None else pipe.src_f32
        pixels=source[0,:,y:y+h,x:x+w].permute(1,2,0).to('cpu',torch.float32).numpy()
        veto=None if face['excluded'] is None else face['excluded'][y:y+h,x:x+w]
        layer=LipMakeupLayer(window,pixels,lm,veto,backend=face['backend'],identity=face['signature'])
        layer.source_version=pipe.repair_version
    delta=layer.solve(r)
    attach_delta(pipe,layer.window,delta)
    pipe.lip_makeup_layer=layer; pipe.lip_makeup_facts=layer.facts


def refresh_source(pipe):
    if getattr(pipe,'lip_makeup_tile_key',None) is not None: return
    if getattr(pipe,'lip_makeup_suspended',None): return
    if S.active(getattr(pipe,'lip_makeup',None)): solve_preview(pipe,pipe.lip_makeup)


def configure_export(spec,snap,h,w):
    spec.lip_makeup_face=None
    if not S.active(getattr(spec,'lip_makeup',None)): return
    pc=snap.get('precompute')
    if pc is None or getattr(pc,'backend',None)!='mediapipe': raise ValueError('唇妆导出需要真实选中人物')
    signature=identity(pc.landmarks)
    if signature!=identity(spec.landmarks): raise ValueError('唇妆导出人物身份不匹配')
    admit_working_set((h,w),spec.landmarks)
    veto=exclusion(pc)
    if veto is None: raise ValueError('唇妆导出缺少可信可见性来源')
    if veto.shape!=(h,w):
        import cv2
        veto=cv2.resize(veto,(w,h),interpolation=cv2.INTER_LINEAR)
    spec.lip_makeup_face={'signature':signature,'excluded':np.ascontiguousarray(veto),'backend':pc.backend}


def prepare_export(spec,source,repaired,divisor):
    recipe=getattr(spec,'lip_makeup',None)
    if not S.active(recipe): return None
    face=getattr(spec,'lip_makeup_face',None)
    if face is None: raise ValueError('唇妆导出未验证选中人物')
    h,w=source.shape[:2]
    if face['excluded'].shape!=(h,w): raise ValueError('唇妆导出可见性场必须为原始尺寸')
    if divisor not in (255,65535): raise ValueError('唇妆导出只接受原始 RGB8/RGB16')
    admit_working_set((h,w),spec.landmarks)
    window,lm=bounds(spec.landmarks,h,w); y,x,rh,rw=window
    pixels=(repaired[y:y+rh,x:x+rw] if repaired is not None else source[y:y+rh,x:x+rw].astype(np.float32)/divisor)
    layer=LipMakeupLayer(window,pixels,lm,face['excluded'][y:y+rh,x:x+rw],backend=face['backend'],identity=face['signature'])
    layer.solve(recipe)
    return layer


def resident_bytes(pipe):
    layer=getattr(pipe,'lip_makeup_layer',None); delta=getattr(pipe,'lip_makeup_delta',None)
    face=getattr(pipe,'lip_makeup_face',None)
    return ((layer.resident_bytes() if layer else 0)+(delta.numel()*delta.element_size() if delta is not None else 0)
        +(face['landmarks'].nbytes+(face['excluded'].nbytes if face['excluded'] is not None else 0) if face else 0))


def working_bytes(shape,landmarks=None):
    h,w=shape
    window=bounds(landmarks,h,w)[0] if landmarks is not None else (0,0,h,w)
    return window[2]*window[3]*256+int(h)*int(w)*4


def sync(engine,*,strict=False):
    """Restore/reload entry point; non-strict failures remain visibly suspended."""
    pipe=engine._vram
    if pipe is None: return
    recipe=S.check(getattr(engine,'_lip_makeup',None))
    pipe.lip_makeup=recipe
    try:
        pc=engine._precompute
        if S.active(recipe):
            if pc is None: raise ValueError('唇妆尚未完成人像分析')
            from . import effect_recovery_state as ERS, facial_wrinkle_recovery as FACE
            recovery=ERS.check(getattr(engine,'_effect_recovery',None))
            FACE.verify(recovery,recovery['source'],pc,target='lip_makeup')
            if getattr(pc,'num_faces',1)!=1 and not getattr(engine,'_face_explicit',False):
                raise ValueError('唇妆需要明确选择一个人物')
            face=getattr(pipe,'lip_makeup_face',None)
            if face is None or face['signature']!=identity(pc.landmarks) or face['model']!=getattr(pc,'semantic_model_sha256',None): install_face(pipe,pc)
        solve_preview(pipe,recipe)
        pipe.lip_makeup_suspended=None
    except Exception as error:
        clear_layer(pipe); pipe.lip_makeup_suspended=str(error)
        if strict: raise


def report(engine):
    pipe=engine._vram
    return {'version':1,'recipe':S.check(getattr(engine,'_lip_makeup',None)),
        'facts':getattr(pipe,'lip_makeup_facts',{}),'suspended':getattr(pipe,'lip_makeup_suspended',None),
        'bytes_fields':resident_bytes(pipe) if pipe else 0,
        'boundaries':['三个独立控件；本地数值范围并非官网标定',
                      '真实外唇环减去内口腔，已知遮挡和异常颜色只做保守排除，不声称完整唇部分割',
                      '立体度改变现有低中频唇部光影，不生成高光、不锐化、不改嘴形']}


def install_export_tile(pipe,layer,origin,recipe):
    r=S.check(recipe)
    clear_layer(pipe)
    pipe.lip_makeup=r
    if layer is None:
        if S.active(r): raise ValueError('唇妆分块缺少已请求的全尺寸修正')
        return
    key=tuple(r[k] for k in S.KEYS)
    if key!=layer.key: raise ValueError('唇妆分块配方与冻结全尺寸修正不一致')
    attach_delta(pipe,layer.window,layer.delta,origin)
    pipe.lip_makeup_tile_key=key
    pipe.lip_makeup_facts=layer.facts


def admit_working_set(shape,landmarks,*,additional_bytes=0):
    """Conservative full-ROI admission. Reject instead of proxy/downsampling.

    Remaining process/cgroup budget already reflects other resident operators.
    This is not a measured peak or an allocation guarantee.
    """
    from .cpu_memory_budget import available_estimate
    import resource
    need=working_bytes(shape,landmarks)+int(additional_bytes)+64*1024*1024
    available=available_estimate()
    soft,_=resource.getrlimit(resource.RLIMIT_AS)
    if soft!=resource.RLIM_INFINITY:
        import os
        with open('/proc/self/statm',encoding='ascii') as stream:
            virtual=int(stream.read().split()[0])*os.sysconf('SC_PAGE_SIZE')
        available=min(available,max(0,soft-virtual))
    if need>available:
        raise ValueError(f'唇妆全尺寸计算需要约 {need//(1024*1024)} MiB 可用内存；预算不足，未缩小分辨率或省略效果')
    return need
