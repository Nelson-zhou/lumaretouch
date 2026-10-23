from . import photo_grain_state as S
OP='lnx.photo_grain.v1'
FIELDS=(S.KEY,)
def check_params(params):
    if type(params) is not dict or set(params)!={'recipe'}:raise ValueError('颗粒仅接受完整全图配方')
    return {'recipe':S.check(params['recipe'])}
def params_of(state):return {'recipe':S.from_state(state)}
def install(state,params):state[S.KEY]=check_params(params)['recipe']
