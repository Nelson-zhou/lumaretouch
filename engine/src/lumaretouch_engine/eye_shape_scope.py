"""Parameter-only transport. Destination recomputes its own anatomy and field."""
from . import eye_shape_state as S
from .eye_shape_runtime import identity,exclusion
OP='lnx.eye_shape.v1'
FIELDS=('_eye_shape','_eye_shape_owner')


def check_params(raw):
    if type(raw) is not dict or set(raw)!={'recipe'} or raw['recipe'] is None:
        raise ValueError('眼形预设只接受版本化十项二维参数')
    return {'recipe':S.check(raw['recipe'])}


def params_of(state): return {'recipe':S.preset(state.get('_eye_shape'))}


def install(state,params):
    recipe=check_params(params)['recipe']; owner=None
    from .eye_shape_runtime import check_legacy
    check_legacy(recipe,(state.get('_deform') or {}).get('amounts',{}))
    if S.active(recipe):
        pc=state.get('_precompute')
        if pc is None or getattr(pc,'backend',None)!='mediapipe' or exclusion(pc) is None:
            raise ValueError('目标照片需要自己的真实人像分析和遮挡来源')
        if getattr(pc,'num_faces',1)!=1 and not state.get('_face_explicit'):
            raise ValueError('目标照片有多个人物，请先明确选中人物')
        owner=identity(pc.landmarks)
    state['_eye_shape']=recipe; state['_eye_shape_owner']=owner


def validate_target(state,row):
    """Check target ORIGINAL pixels before any parked-target state is committed.

    Recomputed again on commit and export. This is admission, not a photograph
    acceptance test. It never runs inference or installs a source face/template.
    """
    recipe=S.check(state.get('_eye_shape'))
    if not S.active(recipe): return
    from types import SimpleNamespace
    from .decode import load_full
    from .full_source_working import working_rgb
    from .cpu_memory_budget import available_estimate
    from .local_mask_state import file_stamp
    from .eye_shape_runtime import export_field
    pc=state.get('_precompute')
    if pc is None or state.get('_eye_shape_owner')!=identity(pc.landmarks):
        raise ValueError('目标眼形人物归属不匹配')
    h,w=int(row['src_h']),int(row['src_w'])
    if h<=0 or w<=0 or h*w>64_000_000 or available_estimate()<40*h*w+128*1024*1024:
        raise ValueError('目标眼形原图验证超出内存预算；未降采样或提交')
    stamp=file_stamp(row['path'])
    decoded=load_full(row['path'],max_px=h*w,device='cpu',want_bits=16)
    if (decoded.h,decoded.w)!=(h,w) or file_stamp(row['path'])!=stamp:
        raise ValueError('目标原图在眼形验证期间变化')
    spec=SimpleNamespace(eye_shape=recipe,eye_shape_face=pc,deform_amounts=(state.get('_deform') or {}).get('amounts',{}))
    spec.landmarks=pc.landmarks
    source=working_rgb(decoded)
    export_field(spec,source,divisor=65535 if source.dtype.itemsize==2 else 255)
    if file_stamp(row['path'])!=stamp:
        raise ValueError('目标原图在眼形验证期间变化，未提交目标参数')
