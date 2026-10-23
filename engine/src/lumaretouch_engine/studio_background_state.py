"""PC-32474 retained source-bound studio-background intent, never proxy pixels.

A person/background classifier does not supply a floor class. Floor support is
always explicit. Portable parameters never carry source masks to another photo.
"""
from copy import deepcopy
import math
import re
from . import local_mask_state as M
from .local_mask_recipe import number, _basis, _shape

VERSION = 1
DOMAIN = 'source-normalized'
CONTROLS = ('intrusions', 'blemish_background', 'blemish_floor', 'uniformity', 'brightness', 'banding', 'enhancement')
TARGETS = ('background', 'floor', 'protect', 'intrusion', 'blemish', 'recover_intrusions',
           'recover_blemishes', 'recover_uniformity', 'recover_banding')
RECOVERY = ('intrusions', 'blemishes', 'uniformity', 'banding')
MAX_STROKES = 128
MAX_POINTS = 8192
MAX_DABS = 65536
MAX_WORK = 2_000_000_000


def parameters(raw=None):
    if raw is None: return {key: 0. for key in CONTROLS}
    if type(raw) is not dict or set(raw) != set(CONTROLS):
        raise ValueError('背景调整参数字段不完整')
    return {key: number(raw[key], -100 if key == 'brightness' else 0, 100 if key == 'brightness' else 1) for key in CONTROLS}


def empty():
    return {'version': VERSION, 'domain': DOMAIN, 'source': None, 'region_mode': 'manual',
            'semantic_owner': None, 'parameters': parameters(), 'strokes': []}


def stroke(raw):
    fields = {'id', 'target', 'operation', 'axes', 'points', 'feather', 'flow', 'opacity'}
    if type(raw) is not dict or set(raw) != fields or raw['target'] not in TARGETS or raw['operation'] not in ('add', 'subtract'):
        raise ValueError('背景画笔目标、操作或字段无效')
    if type(raw['id']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', raw['id']):
        raise ValueError('背景画笔身份无效')
    if type(raw['points']) is not list or not 1 <= len(raw['points']) <= 2048:
        raise ValueError('背景画笔需要 1–2048 个路径点')
    points = []
    for point in raw['points']:
        if type(point) is not list or len(point) != 3:
            raise ValueError('背景路径点需要源图横纵坐标和压感')
        points.append([number(n, 0, 1) for n in point])
    return {'id': raw['id'], 'target': raw['target'], 'operation': raw['operation'],
            'axes': _basis(raw['axes']), 'points': points,
            **{k: number(raw[k], 0, 1) for k in ('feather', 'flow', 'opacity')}}


def check(raw):
    if raw is None: return empty()
    if (type(raw) is not dict or set(raw) != set(empty()) or type(raw['version']) is not int
            or raw['version'] != VERSION or raw['domain'] != DOMAIN
            or raw['region_mode'] not in ('manual', 'semantic_background')
            or type(raw['strokes']) is not list or len(raw['strokes']) > MAX_STROKES):
        raise ValueError('背景调整配方版本、坐标域或字段不兼容')
    strokes = [stroke(s) for s in raw['strokes']]
    if len({s['id'] for s in strokes}) != len(strokes) or sum(len(s['points']) for s in strokes) > MAX_POINTS:
        raise ValueError('背景笔迹身份重复或超过 8192 个路径点')
    binding = M.check({'source': raw['source'], 'semantic_owner': raw['semantic_owner'], 'recipe': M.empty()['recipe']})
    if raw['region_mode'] == 'semantic_background' and binding['semantic_owner'] is None:
        raise ValueError('自动背景范围必须有经过验证的人像分析来源；地面仍需手动标记')
    if raw['region_mode'] == 'manual' and binding['semantic_owner'] is not None:
        raise ValueError('手动背景范围不能保留语义身份')
    controls = parameters(raw['parameters'])
    has_intent = bool(strokes) or any(controls.values()) or raw['region_mode'] != 'manual'
    if has_intent and binding['source'] is None:
        raise ValueError('背景调整必须绑定当前原照片')
    return deepcopy({**raw, 'parameters': controls, 'strokes': strokes, **binding_without_recipe(binding)})


def binding_without_recipe(binding):
    return {k: binding[k] for k in ('source', 'semantic_owner')}


def active(value):
    p = check(value)['parameters']
    # Brightness is a child of light uniformity, not an independent exposure.
    return any(p[k] != 0 for k in CONTROLS if k != 'brightness')


def validate_budget(value, shape):
    value = check(value); h, w = _shape(shape)
    dabs = work = 0
    for s in value['strokes']:
        (a,b),(c,d) = s['axes']; determinant = a*d-b*c
        count = 1
        for p,q in zip(s['points'], s['points'][1:]):
            dx,dy = q[0]-p[0],q[1]-p[1]
            count += max(1, math.ceil(math.hypot((d*dx-c*dy)/determinant,(-b*dx+a*dy)/determinant)/.15))
        area = min(w, math.ceil(2*math.hypot(a,c)*w)+2)*min(h, math.ceil(2*math.hypot(b,d)*h)+2)
        dabs += count; work += count*area
    if dabs > MAX_DABS or work > MAX_WORK:
        raise ValueError('背景画笔超过完整重放预算，请减少笔划或笔刷范围；不会导出放大代理蒙版')
    return {'dabs': dabs, 'work': work, 'bytes': h*w*160+64*1024*1024}


def bind_proposal(engine, raw):
    """UI proposes controls/vectors only; source and semantic identity are producer-owned."""
    if type(raw) is not dict or set(raw) != {'parameters', 'region_mode', 'strokes'}:
        raise ValueError('背景修改只接受参数、范围来源和保留矢量笔迹')
    from . import creative_derived_source as D
    old = check(getattr(engine, '_studio_background', None))
    derived = D.record(engine) is not None
    binding = D.binding(engine) if derived else M.bind_source(engine)
    if old['source'] is not None and old['source'] != binding:
        raise ValueError('背景笔迹源图已变化，请重新打开；不会转绑旧笔迹')
    if derived and raw['region_mode'] == 'semantic_background':
        pc = getattr(engine, '_precompute', None)
        if pc is None:
            raise ValueError('合成图自动背景范围需要当前合成像素的真实分析')
        D.verify_precompute(engine, pc)
    owner = M.current_owner(engine) if raw['region_mode'] == 'semantic_background' else None
    value = check({**empty(), **raw, 'source': binding, 'semantic_owner': owner})
    if derived:
        # Validate the actual owned field too, not only a model-name label.
        from .creative_derived_studio import verify
        value = verify(engine, value)
    validate_budget(value, (binding['height'], binding['width']))
    return value


def check_saved_record(raw):
    if type(raw) is not dict: raise ValueError('保存的背景调整不能为空或 null')
    return check(raw)


def portable(value):
    return {'version': VERSION, 'parameters': parameters(check(value)['parameters'])}


def apply_portable(target, raw):
    if type(raw) is not dict or set(raw) != {'version', 'parameters'} or type(raw['version']) is not int or raw['version'] != VERSION:
        raise ValueError('背景预设参数格式不兼容')
    out = check(target); out['parameters'] = parameters(raw['parameters'])
    if any(out['parameters'][k] for k in CONTROLS if k != 'brightness') and out['source'] is None:
        raise ValueError('目标照片需先建立自己的背景范围；预设不会复制源照片笔迹或猜测地面')
    return check(out)


def migrate_legacy_states(value, *, root=False):
    if isinstance(value, dict):
        for child in list(value.values()): migrate_legacy_states(child)
        if root or any(k in value for k in ('_strength','_grade','_local_masks','_local_grade_layers','_manual_liquify')):
            value.setdefault('_studio_background', empty())
    elif isinstance(value,list):
        for child in value: migrate_legacy_states(child)
