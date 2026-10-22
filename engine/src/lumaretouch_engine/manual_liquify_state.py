"""Retained source-bound, post-effects/pre-crop inverse-field gesture intent.

No sampled RGB, proxy bitmap, automatic facial control or cross-photo tracking.
Freeze/thaw and reconstruction are ordered operations on this manual layer only.
"""
from copy import deepcopy
import math
import re
from . import local_mask_state as M
from .local_mask_recipe import number, _basis, _shape

VERSION = 1
DOMAIN = 'post-effects-pre-crop-normalized'
MODES = ('push', 'reconstruct', 'smooth', 'rotate', 'pucker', 'bloat', 'left', 'freeze', 'thaw')
LABELS = ('向前变形', '重建', '平滑', '旋转', '褶皱', '膨胀', '左推', '冻结', '解冻')
MAX_STROKES = 128
MAX_POINTS = 8192
MAX_DABS = 32768
MAX_WORK = 16_000_000_000


def empty():
    return {'version': VERSION, 'domain': DOMAIN, 'source': None, 'strokes': []}


def stroke(raw):
    fields = {'id', 'mode', 'axes', 'points', 'density', 'pressure', 'rate', 'fixed_edges', 'direction'}
    if type(raw) is not dict or set(raw) != fields or raw['mode'] not in MODES:
        raise ValueError('液化笔迹字段或工具无效')
    if type(raw['id']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', raw['id']):
        raise ValueError('液化笔迹身份无效')
    if type(raw['fixed_edges']) is not bool:
        raise ValueError('固定边缘必须是布尔值')
    direction = number(raw['direction'], -1, 1)
    if direction not in (-1, 1):
        raise ValueError('液化旋转方向无效')
    if type(raw['points']) is not list or not 1 <= len(raw['points']) <= 2048:
        raise ValueError('每笔液化需要 1–2048 个路径点')
    points = []
    previous = 0
    for i, p in enumerate(raw['points']):
        if type(p) is not list or len(p) != 4:
            raise ValueError('液化路径点需要横纵坐标、压感和毫秒时间')
        x, y, pressure = [number(v, 0, 1) for v in p[:3]]
        time = number(p[3], 0, 60000)
        if (i == 0 and time != 0) or (i > 0 and (time < previous or time - previous > 1000)):
            raise ValueError('液化手势时间不连续，请重新开始')
        previous = time
        points.append([x, y, pressure, time])
    return {'id': raw['id'], 'mode': raw['mode'], 'axes': _basis(raw['axes']), 'points': points,
            'density': number(raw['density'], 0, 1), 'pressure': number(raw['pressure'], 0, 1),
            'rate': number(raw['rate'], 0, 1), 'fixed_edges': raw['fixed_edges'], 'direction': direction}


def check(value):
    if value is None:
        return empty()
    if (type(value) is not dict or set(value) != {'version', 'domain', 'source', 'strokes'}
            or type(value['version']) is not int or value['version'] != VERSION or value['domain'] != DOMAIN
            or type(value['strokes']) is not list or len(value['strokes']) > MAX_STROKES):
        raise ValueError('手动液化版本、坐标域或笔迹预算不兼容')
    strokes = [stroke(s) for s in value['strokes']]
    if len({s['id'] for s in strokes}) != len(strokes) or sum(len(s['points']) for s in strokes) > MAX_POINTS:
        raise ValueError('手动液化笔迹重复或超过 8192 个总路径点')
    binding = M.check({'source': value['source'], 'recipe': M.empty()['recipe'], 'semantic_owner': None})['source']
    if bool(strokes) != (binding is not None):
        raise ValueError('手动液化必须绑定原照片；空配方不能保留源图身份')
    return deepcopy({'version': VERSION, 'domain': DOMAIN, 'source': binding, 'strokes': strokes})


def validate_budget(value, shape):
    value = check(value)
    if not value['strokes']:
        return {'dabs': 0, 'work': 0, 'bytes': 0}
    h, w = _shape(shape)
    dabs, work, patch = 0, 0, 0
    for s in value['strokes']:
        (a, b), (c, d) = s['axes']
        det = a*d-b*c
        count = 1
        for p, q in zip(s['points'], s['points'][1:]):
            dx, dy = q[0]-p[0], q[1]-p[1]
            distance = math.hypot((d*dx-c*dy)/det, (-b*dx+a*dy)/det)
            count += max(1, math.ceil(distance/.10), math.ceil((q[3]-p[3])/16))
        size = min(w, math.ceil(2*math.hypot(a, c)*w)+2)*min(h, math.ceil(2*math.hypot(b, d)*h)+2)
        dabs += count
        work += count*size*24
        patch = max(patch, size*12)
    if dabs > MAX_DABS or work > MAX_WORK:
        raise ValueError('液化重放超过计算预算，请缩小笔刷或减少笔迹；不会改为代理出片')
    return {'dabs': dabs, 'work': work, 'bytes': h*w*24+patch+2*1024*1024}


def prepare_mutation(engine, capture, mutation, *, verified_binding=None):
    if type(mutation) is not dict:
        raise ValueError('液化修改必须是对象')
    action = mutation.get('action')
    fields = {'stroke': {'action', 'stroke'}, 'clear': {'action'}, 'delete': {'action', 'id'}}
    if action not in fields or set(mutation) != fields[action]:
        raise ValueError('液化修改字段无效')
    value = check(getattr(engine, '_manual_liquify', None))
    # Only the producer-owned, revision/stamp-checked preview session supplies
    # this binding; wire mutations cannot select or override source identity.
    binding = M.bind_source(engine) if verified_binding is None else deepcopy(verified_binding)
    if value['source'] is not None and value['source'] != binding:
        raise ValueError('液化属于另一张源照片，不能重新绑定')
    if action == 'stroke':
        from .manual_liquify_geometry import inverse_stroke
        candidate = inverse_stroke(capture, stroke(mutation['stroke']))
        if any(s['id'] == candidate['id'] for s in value['strokes']):
            raise ValueError('此液化笔迹身份已存在，不重复提交')
        value['strokes'].append(candidate)
    elif action == 'clear':
        value['strokes'] = []
    else:
        found = next((s for s in value['strokes'] if s['id'] == mutation['id']), None)
        if found is None:
            raise ValueError('液化笔迹不存在')
        value['strokes'].remove(found)
    value['source'] = binding if value['strokes'] else None
    value = check(value)
    validate_budget(value, (binding['height'], binding['width']))
    return value


def check_saved_record(value):
    if type(value) is not dict:
        raise ValueError('保存的液化记录必须是对象，不能用 null 擦除意图')
    return check(value)


def migrate_legacy_states(value, *, root=False):
    """Only old schemas call this. Never overwrite present/manual or other layers."""
    if isinstance(value, dict):
        for child in list(value.values()):
            migrate_legacy_states(child)
        if root or any(key in value for key in ('_strength', '_grade', '_grade_scope', '_local_masks', '_local_grade_layers', '_effect_recovery')):
            value.setdefault('_manual_liquify', empty())
    elif isinstance(value, list):
        for child in value:
            migrate_legacy_states(child)
