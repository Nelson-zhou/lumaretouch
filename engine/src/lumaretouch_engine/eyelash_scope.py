"""Preset transport view only. Canonical people graph owns every applied leaf."""
from . import eyelash_state as S
OP=S.OPERATION
FIELDS=('_eyelash_preset',)
def check_params(raw):
    if type(raw) is not dict or set(raw)!={'recipe'} or raw['recipe'] is None:raise ValueError('睫毛预设只接受版本化素材参数')
    return {'recipe':S.check(raw['recipe'])}
def params_of(state):return {'recipe':S.preset(state.get('_eyelash_preset'))}
def install(state,params):
    recipe=check_params(params)['recipe']
    if not state.get('_eyelash_preset_target'):raise ValueError('睫毛预设需要当前明确人物；批量请使用已确认人物参数映射')
    if S.active(recipe) and not state.get('_eyelash_reviewed'):raise ValueError('目标人物需要自己的可见眼睑审核，预设不携带源图蒙版')
    state['_eyelash_preset']=recipe

def capture(engine,base=None):
    """Ephemeral parameter DTO for preset ports; never DOC_FIELDS or render state."""
    out=engine._capture_state() if base is None else base;recipe=S.neutral();ref=None;reviewed=False
    if engine._people_managed():
        from . import people_state as P,people_algorithms as A,people_resolver as R
        from .eyelash_support import resolve
        state=engine._people_owner().snapshot();source=engine._people_source()
        face=state['faces'].get(engine._people_cursors.get(source['sha256']))
        if face and face['asset_sha256']==source['sha256']:
            ref=P.face_ref(face);recipe=A.recipes(R.resolve(state,ref['face_instance_id'],A.defaults()))[OP]
            try:resolve(state,engine._people_support,ref);reviewed=True
            except ValueError:pass
    return {**out,'_eyelash_preset':recipe,'_eyelash_preset_target':ref,'_eyelash_reviewed':reviewed}
