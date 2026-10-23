"""Source-owned original-shadow vectors; never accept client raster evidence.

Both roles start empty, unlike spill's automatic whole-image coverage. The
existing Rust mask engine replays subtract/maximum-union geometry at source size.
"""
from copy import deepcopy
from . import local_mask_recipe as R, local_mask_state as M
from . import original_shadow_state as S

MAX_STROKES = 63
FIELDS = frozenset(('id', 'mode', 'points', 'radius', 'opacity', 'feather'))


def append(binding, source, strokes, role):
    if role not in ('lit_floor', 'retention'):
        raise ValueError('原阴影画笔角色无效')
    if type(strokes) is not list or not 1 <= len(strokes) <= MAX_STROKES:
        raise ValueError('每组原阴影画笔需要 1–63 条笔画')
    source = M.check({'source': source, 'semantic_owner': None,
                      'recipe': M.empty()['recipe']})['source']
    if source is None:
        raise ValueError('原阴影画笔缺少不可变源图身份')
    mask = M.check({'source': source, 'semantic_owner': None,
                    'recipe': M.empty()['recipe']}) if binding is None else S.check_binding(binding)['mask']
    if mask['source'] != source:
        raise ValueError('原阴影画笔不能复用另一张照片的范围')
    objects = deepcopy(mask['recipe']['objects'])
    if len(objects) + len(strokes) > R.MAX_OBJECTS:
        raise ValueError('原阴影单组范围最多保留 64 个矢量对象')
    for stroke in strokes:
        if (type(stroke) is not dict or set(stroke) != FIELDS
                or stroke['mode'] not in ('erase', 'restore')
                or type(stroke['points']) is not list
                or any(type(point) is not list or len(point) != 2 for point in stroke['points'])):
            raise ValueError('原阴影只接受完整源图归一化擦除或恢复笔画')
        radius = R.number(stroke['radius'], .0001, .5) * min(source['width'], source['height'])
        objects.append(R.check_object({
            'id': stroke['id'], 'name': ('Lit floor ' if role == 'lit_floor' else 'Shadow retention ') + stroke['mode'],
            'enabled': True, 'operation': 'subtract' if stroke['mode'] == 'erase' else 'add',
            'kind': 'brush', 'opacity': stroke['opacity'], 'feather': stroke['feather'],
            'points': stroke['points'],
            'axes': [[radius / source['width'], 0.], [0., radius / source['height']]],
        }))
    mask['recipe'] = R.check_stack({**mask['recipe'], 'objects': objects})
    return S.check_binding({'version': 1, 'reviewed': True, 'mask': mask,
                            'recipe_sha256': S.digest(mask)})
