from . import primary_calibration_state as S
from .primary_calibration_native import admit
OP='lnx.primary_calibration.v1'
FIELDS=(S.KEY,)
def check_params(params):
    if type(params) is not dict or set(params)!={'recipe'}:raise ValueError('RGB 原色校准仅接受完整全图配方')
    return {'recipe':admit(params['recipe'])}
def params_of(state):return {'recipe':S.from_state(state)}
def install(state,params):state[S.KEY]=check_params(params)['recipe']
