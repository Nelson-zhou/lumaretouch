# SPDX-License-Identifier: GPL-3.0-or-later
"""Ephemeral portable preset DTO; canonical people graph owns applied parameters."""
from . import lipstick_state as S
OP=S.OP
FIELDS=('_lipstick_preset',)
def check_params(raw):
    if type(raw) is not dict or set(raw)!={'recipe'} or raw['recipe'] is None:raise ValueError('口红预设只接受版本化图案、程度和颜色')
    return {'recipe':S.check(raw['recipe'])}
def params_of(state):return {'recipe':S.preset(state.get('_lipstick_preset'))}
def install(state,params):
    recipe=check_params(params)['recipe']
    if not state.get('_lipstick_preset_target'):raise ValueError('口红预设需要当前明确人物；批量请使用确认的人物参数映射')
    if S.active(recipe) and not state.get('_lipstick_supported'):raise ValueError('目标人物缺少自己的真实唇部审核与遮挡分析')
    state['_lipstick_preset']=recipe

def capture(engine,base=None):
    from . import people_state as P,people_algorithms as A,people_resolver as R
    out=engine._capture_state() if base is None else base
    recipe=S.neutral();ref=None;supported=False
    if engine._people_managed():
        state=engine._people_owner().snapshot();source=engine._people_source()
        face=state['faces'].get(engine._people_cursors.get(source['sha256']))
        if face and face['asset_sha256']==source['sha256']:
            ref=P.face_ref(face);recipe=A.recipes(R.resolve(state,ref['face_instance_id'],A.defaults()))[OP]
            analysis=engine._people_analyses.get(source['sha256'],{}).get(ref['face_instance_id'])
            from .lipstick_support import resolve as resolve_support
            try:resolve_support(state,engine._people_support,ref);reviewed=True
            except ValueError:reviewed=False
            supported=bool(reviewed and analysis and analysis['face_ref']==ref and face['evidence']['status']=='verified'
                           and analysis.get('excluded') is not None)
    return {**out,'_lipstick_preset':recipe,'_lipstick_preset_target':ref,'_lipstick_supported':supported}
