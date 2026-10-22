"""Per-operator recovery intent. Persist vectors, never a preview raster or RGB.

The matrix is deliberately smaller than PixCake's: only implemented operators
with an independently removable contribution are admitted. This is not repair,
clone, a whole-photo original blend, or a claim of proprietary algorithm parity.
"""
from copy import deepcopy
from . import local_mask_recipe as R, local_mask_state as M
from . import facial_wrinkle_recovery as FACE

VERSION = 1
TARGETS = ('skin_smoothing', 'fabric_fine', 'facial_wrinkles', 'lip_makeup', 'background_replace')
LABELS = {'skin_smoothing': '磨皮与肌理', 'fabric_fine': '衣物细褶',
          'background_replace': '换底边缘', 'facial_wrinkles': '面部祛纹八部位', 'lip_makeup': '唇妆增强'}
STAGES = {'skin_smoothing': 'pre-deform-smoothing', 'fabric_fine': 'pre-deform-fabric',
          'background_replace': 'post-grade-background', 'facial_wrinkles': 'pre-deform-facial-wrinkles',
          'lip_makeup': 'pre-deform-lip-makeup'}
MAX_STROKES = 128
MAX_MASK_PIXELS = 128_000_000


def empty():
    return {'version': VERSION, 'source': None, 'targets': []}


def target(value):
    if type(value) is not str or value not in TARGETS:
        raise ValueError('此效果没有已实现的专属恢复算子')
    return value


def check(raw):
    if raw is None:
        return empty()
    if (type(raw) is not dict or set(raw) != {'version', 'source', 'targets'}
            or type(raw['version']) is not int or raw['version'] != VERSION
            or type(raw['targets']) is not list or len(raw['targets']) > len(TARGETS)):
        raise ValueError('效果恢复配方版本或字段无效')
    rows, seen, strokes, points = [], set(), 0, 0
    for row in raw['targets']:
        if type(row) is not dict or set(row) not in ({'target', 'enabled', 'recipe'}, {'target', 'enabled', 'recipe', 'owner'}):
            raise ValueError('效果恢复目标字段无效')
        name = target(row['target'])
        if name in seen or type(row['enabled']) is not bool:
            raise ValueError('效果恢复目标重复或启用状态无效')
        seen.add(name)
        recipe = R.check_stack(row['recipe'])
        if not recipe['objects']:
            raise ValueError('空效果恢复目标应移除，不保留无意义图层')
        for obj in recipe['objects']:
            if obj['kind'] != 'brush' or obj['operation'] not in ('add', 'subtract'):
                raise ValueError('效果恢复只接受加/减画笔，不能借用其他蒙版类型')
            strokes += 1
            points += len(obj['points'])
        clean = {'target': name, 'enabled': row['enabled'], 'recipe': recipe}
        if 'owner' in row: clean['owner'] = deepcopy(row['owner'])
        rows.append(clean)
    if strokes > MAX_STROKES or points > R.MAX_TOTAL_POINTS:
        raise ValueError('效果恢复超过 128 笔或 8192 个路径点预算')
    # Reuse the strict source identity validator, without semantic/model fields.
    binding = M.check({'source': raw['source'], 'semantic_owner': None,
                      'recipe': rows[0]['recipe'] if rows else M.empty()['recipe']})['source']
    for row in rows: FACE.check_row(row, binding)
    if not rows and binding is not None:
        raise ValueError('空效果恢复配方不能保留源图绑定')
    return deepcopy({'version': VERSION, 'source': binding, 'targets': rows})


def enabled(value):
    return [row for row in check(value)['targets'] if row['enabled']]


def check_saved_record(value):
    """A missing legacy field is empty; an explicitly saved null is corruption."""
    if type(value) is not dict:
        raise ValueError('已保存的效果恢复配方必须是对象，不能以 null 丢弃笔迹')
    return check(value)


def migrate_legacy_states(value, *, root=False):
    """Add empty intent to owned legacy snapshots, without touching grade groups."""
    if isinstance(value, dict):
        for child in list(value.values()):
            migrate_legacy_states(child)
        if root or any(key in value for key in ('_grade', '_local_masks', '_local_grade_layers')):
            value.setdefault('_effect_recovery', empty())
    elif isinstance(value, list):
        for child in value:
            migrate_legacy_states(child)


def validate_budget(value, shape):
    rows = enabled(value)
    if not rows:
        return {'targets': 0, 'work': 0}
    R._shape(shape)
    if len(rows) * shape[0] * shape[1] > MAX_MASK_PIXELS:
        raise ValueError('效果恢复蒙版超过 1.28 亿总像素预算')
    work = sum(R.validate_budget(row['recipe'], shape)['work'] for row in rows)
    if work > R.MAX_WORK:
        raise ValueError('效果恢复累计计算超过预算；请减少笔划或羽化')
    return {'targets': len(rows), 'work': work}


def prepare_mutation(engine, capture, mutation):
    if type(mutation) is not dict:
        raise ValueError('效果恢复修改必须是对象')
    action = mutation.get('action')
    fields = {'stroke': {'action', 'target', 'stroke'},
              'clear': {'action', 'target'}, 'enable': {'action', 'target', 'enabled'},
              'delete': {'action', 'target', 'id'}}
    if action not in fields or set(mutation) != fields[action]:
        raise ValueError('效果恢复修改字段无效')
    name = target(mutation['target'])
    from . import people_recovery as PEOPLE
    if PEOPLE.handles(engine, name):
        PEOPLE.context(engine)
        value = PEOPLE.value(engine)
    else:
        value = check(getattr(engine, '_effect_recovery', None))
    binding = M.bind_source(engine)
    if value['source'] is not None and value['source'] != binding:
        raise ValueError('源图身份改变，恢复笔迹不能重新绑定到另一张照片')
    rows = value['targets']
    row = next((r for r in rows if r['target'] == name), None)
    if name in FACE.FACE_TARGETS and row is not None and (action == 'stroke' or action == 'enable' and mutation.get('enabled') is True):
        if FACE.check_owner(row.get('owner')) != FACE.owner(binding, engine._precompute):
            raise ValueError('人物恢复笔迹不属于当前真实人物，请选回原人物或清除本目标笔迹')
    if action == 'stroke':
        from .effect_recovery_runtime import availability
        ready = availability(engine)[name]
        if not ready['active']:
            raise ValueError(ready['reason'] or '请先开启此效果，再局部擦回')
        from .local_mask_geometry import inverse_object
        stroke = R.check_object(mutation['stroke'])
        if stroke['kind'] != 'brush' or stroke['operation'] not in ('add', 'subtract'):
            raise ValueError('此操作需要专属加/减恢复画笔')
        if not stroke['enabled'] or stroke['opacity'] <= 0:
            raise ValueError('新恢复笔迹必须启用且有非零强度')
        stroke = inverse_object(capture['spec'], stroke, capture['valid'], capture['descriptor']['full_source'])
        if row is None:
            if stroke['operation'] == 'subtract':
                raise ValueError('此效果尚无恢复笔迹，不能擦除空蒙版')
            row = {'target': name, 'enabled': True, 'recipe': M.empty()['recipe']}
            if name in FACE.FACE_TARGETS: row['owner'] = FACE.owner(binding, engine._precompute)
            rows.append(row)
        if not row['enabled']:
            raise ValueError('请先启用此目标的恢复笔迹，再继续涂抹')
        if any(obj['id'] == stroke['id'] for obj in row['recipe']['objects']):
            raise ValueError('恢复笔迹 ID 已存在；不会覆盖另一笔')
        row['recipe']['objects'].append(stroke)
    elif row is None:
        raise ValueError('此目标没有恢复笔迹')
    elif action == 'clear':
        rows.remove(row)
    elif action == 'enable':
        if type(mutation['enabled']) is not bool:
            raise ValueError('恢复启用状态必须是布尔值')
        row['enabled'] = mutation['enabled']
    else:
        objects = row['recipe']['objects']
        found = next((obj for obj in objects if obj['id'] == mutation['id']), None)
        if found is None:
            raise ValueError('恢复笔迹不存在')
        objects.remove(found)
        if not objects:
            rows.remove(row)
    value['source'] = binding if rows else None
    value = check(value)
    validate_budget(value, tuple(reversed(capture['descriptor']['full_source'])))
    return value
