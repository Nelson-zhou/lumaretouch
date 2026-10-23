"""Parameter-only preset/batch module; each target retains its own mask intent."""
from . import studio_background_state as S
OP='lnx.studio_background.v1'
FIELDS=('_studio_background',)


def check_params(raw):
    if type(raw) is not dict or set(raw)!={'recipe'}:raise ValueError('背景预设仅接受参数配方')
    recipe=raw['recipe']
    if type(recipe) is not dict or set(recipe)!={'version','parameters'} or type(recipe['version']) is not int or recipe['version']!=1:
        raise ValueError('背景预设版本或字段无效')
    return {'recipe':{'version':1,'parameters':S.parameters(recipe['parameters'])}}


def params_of(state):return {'recipe':S.portable(state.get('_studio_background'))}


def install(state,params):
    params=check_params(params);target=S.apply_portable(state.get('_studio_background'),params['recipe'])
    if S.active(target):
        from .id_background_state import active as id_background_active
        if id_background_active(state.get('_id_background')):raise ValueError('此照片已启用证件照换背景，不能同时启用影棚背景调整')
        if (state.get('_bg') or {}).get('active'):raise ValueError('该目标已完整换底，会覆盖背景调整；先关闭换底')
        targets={s['target'] for s in target['strokes'] if s['operation']=='add' and s['opacity']>0 and s['flow']>0}
        if target['region_mode']=='manual' and not targets.intersection({'background','floor'}):
            raise ValueError('目标照片没有自己的背景范围；批量只复制参数，不复制其他照片笔迹')
        if target['parameters']['blemish_floor'] and 'floor' not in targets:
            raise ValueError('目标照片缺少显式地面标记，不能套用地面祛瑕参数')
    state['_studio_background']=target
