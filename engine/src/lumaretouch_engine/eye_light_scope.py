"""Preset transport view only. Canonical people graph owns every applied leaf."""
from . import eye_light_state as S
OP=S.OPERATION
FIELDS=('_eye_light_preset',)
def check_params(raw):
    if type(raw) is not dict or set(raw)!={'recipe'} or raw['recipe'] is None:raise ValueError('眼神光预设只接受版本化素材参数')
    return {'recipe':S.check(raw['recipe'])}
def params_of(state):return {'recipe':S.preset(state.get('_eye_light_preset'))}
def install(state,params):
    recipe=check_params(params)['recipe']
    if not state.get('_eye_light_preset_target'):raise ValueError('眼神光预设需要当前明确人物；批量请使用已确认人物参数映射')
    if S.active(recipe) and not state.get('_eye_light_reviewed'):raise ValueError('目标人物需要自己的可见眼球审核，预设不携带源图蒙版')
    state['_eye_light_preset']=recipe

def capture(engine):
    """Ephemeral parameter DTO for preset ports; never DOC_FIELDS or render state."""
    out=engine._capture_state();recipe=S.neutral();ref=None;reviewed=False
    if engine._people_managed():
        from . import people_state as P,people_algorithms as A,people_resolver as R
        from .eye_light_support import resolve
        state=engine._people_owner().snapshot();source=engine._people_source()
        face=state['faces'].get(engine._people_cursors.get(source['sha256']))
        if face and face['asset_sha256']==source['sha256']:
            ref=P.face_ref(face);recipe=A.recipes(R.resolve(state,ref['face_instance_id'],A.defaults()))[OP]
            try:resolve(state,engine._people_support,ref);reviewed=True
            except ValueError:pass
    return {**out,'_eye_light_preset':recipe,'_eye_light_preset_target':ref,'_eye_light_reviewed':reviewed}
