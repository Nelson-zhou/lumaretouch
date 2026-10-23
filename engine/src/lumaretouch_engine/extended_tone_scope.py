from . import extended_tone_state as S
OP='lnx.extended_tone.v1'
FIELDS=(S.KEY,)
def check_params(params):
    if type(params) is not dict or set(params)!={'recipe'}:raise ValueError('Extended tone module requires recipe')
    return {'recipe':S.check(params['recipe'])}
def params_of(state):return {'recipe':S.check(state.get(S.KEY))}
def install(state,params):state[S.KEY]=check_params(params)['recipe']
