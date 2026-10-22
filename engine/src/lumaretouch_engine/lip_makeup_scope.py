"""Portable parameters only; each destination owns its source/face/recovery."""
from . import lip_makeup_state as S
from .lip_makeup_runtime import identity, exclusion
OP = 'lnx.lip_makeup.v1'
FIELDS = ('_lip_makeup',)


def check_params(raw):
    if type(raw) is not dict or set(raw)!={'recipe'} or raw['recipe'] is None:
        raise ValueError('唇妆预设只接受三个控件的版本化配方')
    return {'recipe':S.check(raw['recipe'])}


def params_of(state):
    return {'recipe':S.preset(state.get('_lip_makeup'))}


def install(state,params):
    recipe=check_params(params)['recipe']
    if S.active(recipe):
        pc=state.get('_precompute')
        if pc is None or getattr(pc,'backend',None)!='mediapipe' or exclusion(pc) is None:
            raise ValueError('目标照片需完成真实人像分析，不能转移其他照片的人脸或蒙版')
        identity(pc.landmarks)
        if getattr(pc,'num_faces',1)!=1 and not state.get('_face_explicit'):
            raise ValueError('目标照片有多个人物，请明确选中人物后应用唇妆')
    state['_lip_makeup']=recipe
