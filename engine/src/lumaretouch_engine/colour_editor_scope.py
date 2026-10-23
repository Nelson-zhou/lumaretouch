from . import colour_editor_state as S
OP='lnx.colour_editor.v1'
FIELDS=(S.KEY,)
def check_params(params):
    if type(params) is not dict or set(params)!={'recipe'}:raise ValueError('色彩编辑器仅接受完整全图配方')
    return {'recipe':S.check(params['recipe'])}
def params_of(state):return {'recipe':S.from_state(state)}
def install(state,params):state[S.KEY]=check_params(params)['recipe']
