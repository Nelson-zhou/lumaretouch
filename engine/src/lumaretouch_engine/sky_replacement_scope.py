"""Sky preset/batch scope: asset and parameters, each target's own regions."""
from copy import deepcopy
from . import sky_replacement_state as S

OP = 'lnx.sky_replacement.v1'
FIELDS = ('_sky_replacement',)


def check_params(raw):
    if type(raw) is not dict or set(raw) != {'recipe'}:
        raise ValueError('换天空预设只接受素材与参数配方')
    recipe = raw['recipe']
    if (type(recipe) is not dict or set(recipe) != {'version','enabled','asset','parameters'}
            or type(recipe['version']) is not int or recipe['version'] != 1 or type(recipe['enabled']) is not bool):
        raise ValueError('换天空预设字段或版本无效')
    asset = S.asset(recipe['asset'])
    if recipe['enabled'] and asset is None:
        raise ValueError('已启用天空预设缺少素材')
    return {'recipe':{'version':1,'enabled':recipe['enabled'],'asset':asset,'parameters':S.parameters(recipe['parameters'])}}


def params_of(state):
    value = S.check(state.get('_sky_replacement'))
    return check_params({'recipe':{'version':1,'enabled':value['enabled'],'asset':value['asset'],'parameters':value['parameters']}})


def install(state,params):
    recipe = check_params(params)['recipe']
    target = S.check(state.get('_sky_replacement'))
    value = S.check({**target,'enabled':recipe['enabled'],'asset':deepcopy(recipe['asset']),'parameters':deepcopy(recipe['parameters'])})
    if value['enabled']:
        if (state.get('_bg') or {}).get('active'):
            raise ValueError('此照片已启用完整换背景，不能同时换天空')
        S.ready(value)
        if target['source'] is None:
            raise ValueError('目标照片没有自己的天空标记；不会复制其他照片区域')
    state['_sky_replacement'] = value


def validate_target(value,path,shape):
    """Preflight/commit must call on each frozen target before writing any state."""
    from . import sky_replacement_runtime as R
    value = S.check(value)
    if not value['enabled']:
        return
    R.verify_snapshot({'sky_replacement':value},path,shape)
    # Rasterize against an admitted bounded validation grid. Final export still
    # validates/replays the ORIGINAL grid, not this disposable readiness proof.
    from .decode import proxy_size
    w,h = proxy_size(shape[1],shape[0],budget=1_000_000)
    prepared = R.prepare(value,(h,w))
    # Sampling bounds can be checked without copying RGB or pixels to a device.
    from .ops.sky_replacement import sample
    import numpy as np
    window = (0,0,h,w)
    _,valid = sample(prepared['asset'],value['parameters'],(h,w),window,prepared['cover'])
    fields = prepared['fields']
    selected = fields['sky']*(1-fields['person'])*(1-fields['recovery'])
    if value['parameters']['opacity']>0 and np.any((selected>0) & ~valid):
        raise ValueError('目标照片的天空标记超出新素材覆盖，请逐图调整')
    if value['parameters']['reflection']>0:
        _,valid = sample(prepared['reflection'],value['parameters'],(h,w),window,prepared['cover'],horizon=value['horizon'])
        water = fields['water']*(1-fields['person'])*(1-fields['recovery'])*(1-fields['sky']*value['parameters']['opacity']/100.)
        if value['parameters']['opacity']>0 and np.any((water>0) & ~valid):
            raise ValueError('目标照片的水面反射超出素材覆盖，请逐图调整')
