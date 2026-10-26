"""Independent retained grade groups; no raster, inference or editor ownership.

The legacy scalar grade stays untouched on append. A reviewed type-selective
replacement may clear its object-scoped adjustment. A group is atomic:
its ordered max/subtract/min operands are never flattened into another group.
"""
from copy import deepcopy
import hashlib
import json
import re
from . import local_mask_state as M
from .ops.grade import check_params as check_grade

VERSION = 1
MAX_LAYERS = 8
MAX_OBJECTS = 128
MAX_MASK_PIXELS = 128_000_000
OP = 'lnx.local_grade.v1'
TYPES = ('subject', 'background', 'custom')
FIELDS = ('_local_grade_layers', '_grade', '_grade_scope', '_grade_mask', '_local_masks', '_lut_preset')
NEUTRAL = (0.0, 0.0, 0.0, 1.0)


def empty():
    return {'version': VERSION, 'layers': []}


def grade(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 4
            or any(type(v) not in (float, int) for v in value)):
        raise ValueError('独立局部调色需要四个有限数值')
    return list(check_grade(*value[:3], amount=value[3]))


def check_layer(raw):
    if type(raw) is not dict or set(raw) != {'id', 'name', 'enabled', 'grade', 'mask'}:
        raise ValueError('独立局部调色组字段无效')
    if type(raw['id']) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', raw['id']):
        raise ValueError('独立局部调色组 ID 无效')
    if (type(raw['name']) is not str or not raw['name'].strip() or len(raw['name']) > 80
            or any(ord(c) < 32 for c in raw['name'])):
        raise ValueError('局部调色组名称需要 1–80 个可显示字符')
    if type(raw['enabled']) is not bool:
        raise ValueError('独立局部调色组启用状态必须为布尔值')
    return {'id': raw['id'], 'name': raw['name'], 'enabled': raw['enabled'],
            'grade': grade(raw['grade']), 'mask': M.check(raw['mask'])}


def check(raw):
    if raw is None: return empty()
    if (type(raw) is not dict or set(raw) != {'version', 'layers'} or type(raw['version']) is not int
            or raw['version'] != VERSION or type(raw['layers']) is not list or len(raw['layers']) > MAX_LAYERS):
        raise ValueError('独立局部调色组版本无效或超过 8 组预算')
    layers = [check_layer(layer) for layer in raw['layers']]
    if len({layer['id'] for layer in layers}) != len(layers):
        raise ValueError('独立局部调色组 ID 重复')
    if sum(len(layer['mask']['recipe']['objects']) for layer in layers) > MAX_OBJECTS:
        raise ValueError('独立局部调色组超过 128 个对象预算')
    return {'version': VERSION, 'layers': layers}


def active(layer):
    return layer['enabled'] and layer['grade'][3] != 0 and any(layer['grade'][:3])


def check_source(raw):
    """A source can include the unchanged legacy slot plus eight new groups."""
    if type(raw) is not dict or set(raw) != {'version','layers'} or type(raw.get('version')) is not int or raw.get('version') != VERSION or type(raw.get('layers')) is not list or len(raw['layers']) > MAX_LAYERS+1:
        raise ValueError('源图局部调色组结构无效')
    layers = [check_layer(layer) for layer in raw['layers']]
    if len({layer['id'] for layer in layers}) != len(layers): raise ValueError('源图局部组 ID 重复')
    if sum(len(layer['mask']['recipe']['objects']) for layer in layers) > MAX_OBJECTS+M.R.MAX_OBJECTS:
        raise ValueError('源图局部组对象预算超限')
    return {'version':VERSION,'layers':layers}


def types(layer):
    # Disabled operands remain retained intent, not a licence to silently drop them.
    result = set()
    for obj in layer['mask']['recipe']['objects']:
        result.add(('background' if obj['channel'] == 'background' else 'subject')
                   if obj['kind'] == 'semantic' else 'custom')
    return result or {'custom'}


def from_state(state):
    layers = check(state.get('_local_grade_layers'))['layers']
    if state.get('_grade_scope') == 'objects':
        ident = 'current-local-grade'
        while any(layer['id'] == ident for layer in layers): ident += '_'
        layers.insert(0, {'id': ident, 'name': '当前编辑器局部调色', 'enabled': True,
                          'grade': grade(state.get('_grade', NEUTRAL)),
                          'mask': M.check(state.get('_local_masks'))})
    return check_source({'version': VERSION, 'layers': layers})


def params_of(state):
    return {'groups': from_state(state)}


def check_params(params):
    if type(params) is not dict or set(params) != {'groups'}:
        raise ValueError('局部调色范围必须完整包含独立组及其调色参数')
    return {'groups': check_source(params['groups'])}


def install(state, params):
    """Install an already target-bound complete set, never a source transfer."""
    state['_local_grade_layers'] = check(check_params(params)['groups'])


def clear_legacy(state):
    """Only a frozen, explicit replace decision may clear the legacy object slot."""
    if state.get('_grade_scope') == 'objects':
        state.update(_grade=NEUTRAL, _grade_scope='all', _grade_mask=None, _local_masks=M.empty(), _lut_preset=None)


def restore(current, previous):
    # Raw field restoration is required for old brush rasters and old scalar
    # scopes. Reconstructing through portable parameters would lose that intent.
    for key in FIELDS:
        if key in previous: current[key] = deepcopy(previous[key])
        elif key == '_local_grade_layers': current[key] = empty()
    return current


def undo_key(state):
    """Fence legacy-slot/link edits too; do not erase a later global grade/LUT."""
    value = {key: state.get(key) for key in FIELDS if key != '_grade_mask'}
    mask = state.get('_grade_mask')
    value['_grade_mask'] = None if mask is None else [str(mask.dtype), list(mask.shape), hashlib.sha256(mask.tobytes()).hexdigest()]
    lut = state.get('_lut')
    value['lut_dependency'] = None if lut is None else [lut.kind, lut.size,
        list(lut.domain_min), list(lut.domain_max), hashlib.sha256(lut.grid.tobytes()).hexdigest(), state.get('_lut_amount')]
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def selected(groups, selected_types, *, where):
    chosen, omitted = [], []
    for layer in check_source(groups)['layers']:
        present = types(layer)
        if not present.intersection(selected_types):
            omitted.append(layer); continue
        if not present.issubset(selected_types):
            raise ValueError(f'{where}“{layer["name"]}”混合了已选与未选类型；必须选择整组，不能删除其中的减去/交集对象')
        chosen.append(layer)
    return chosen, omitted


def portable(groups):
    value = check_source(groups)
    for layer in value['layers']:
        for obj in layer['mask']['recipe']['objects']:
            if obj['kind'] == 'brush':
                raise ValueError(f'“{layer["name"]}”含画笔，手册不支持画笔批量/预设；整组被拒，未静默排除对象')
            if obj['kind'] in ('prompted', 'automatic_foreground'):
                raise ValueError(f'“{layer["name"]}”含绑定原照片的 AI 提示选区；请在目标图重新选区，不能跨照片复制提示或匹配身份')
        _, channels = M.R.dependencies(layer['mask']['recipe'])
        if channels and layer['mask']['semantic_owner'] is None:
            raise ValueError(f'“{layer["name"]}”缺少真实语义模型身份')
    return value


def options(raw):
    if (type(raw) is not dict or set(raw) not in ({'mode', 'types', 'rebase'}, {'mode','types','rebase','groups'})
            or raw['mode'] not in ('append', 'replace') or type(raw['rebase']) is not bool
            or type(raw['types']) is not list or not raw['types']
            or any(type(t) is not str or t not in TYPES for t in raw['types'])
            or len(set(raw['types'])) != len(raw['types'])):
        raise ValueError('请选择局部蒙版叠加/替换、完整类型及原图相对位置映射策略')
    groups = raw.get('groups')
    if groups is not None and (type(groups) is not list or len(groups)>MAX_LAYERS+1 or any(type(v) is not str for v in groups) or len(set(groups))!=len(groups)):
        raise ValueError('请选择明确的完整局部调色组')
    return {'mode': raw['mode'], 'types': [t for t in TYPES if t in raw['types']], 'rebase': raw['rebase'], 'groups': deepcopy(groups)}


def choose(groups, policy):
    layers = check_source(groups)['layers']
    ids = {layer['id'] for layer in layers}
    requested = policy['groups']
    if requested is not None and set(requested)-ids: raise ValueError('所选局部调色组已变化，请重新选择源组')
    considered = layers if requested is None else [layer for layer in layers if layer['id'] in requested]
    chosen, _ = selected({'version':VERSION,'layers':considered}, policy['types'], where='源图')
    picked = {layer['id'] for layer in chosen}
    return chosen, [layer for layer in layers if layer['id'] not in picked]


def inventory(state):
    result=[]
    for layer in from_state(state)['layers']:
        reason=None
        try: portable({'version':VERSION,'layers':[layer]})
        except ValueError as error: reason=str(error)
        result.append({'id':layer['id'],'name':layer['name'],'types':sorted(types(layer)), 'portable':reason is None,'reason':reason})
    return result


def transfer(source, target_state, target_binding, raw_options):
    """Pure preparation. Runtime checks source bytes/model/raster before approval."""
    policy = options(raw_options)
    incoming, excluded = choose(check_params(source)['groups'], policy)
    if not incoming: raise ValueError('所选类型没有可同步的局部调色组')
    incoming = portable({'version': VERSION, 'layers': incoming})['layers']
    existing = check(target_state.get('_local_grade_layers'))['layers']
    legacy_removed = False
    removed = []
    if policy['mode'] == 'replace':
        removed, existing = selected({'version': VERSION, 'layers': existing}, policy['types'], where='目标图')
        if target_state.get('_grade_scope') == 'objects':
            legacy = from_state({**target_state, '_local_grade_layers': empty()})
            matched, _ = selected(legacy, policy['types'], where='目标旧调色槽')
            legacy_removed = bool(matched)
            removed += matched
    used = {layer['id'] for layer in existing}
    for index, layer in enumerate(incoming):
        old_binding = layer['mask']['source']
        if any(obj['kind'] in ('linear', 'radial') for obj in layer['mask']['recipe']['objects']):
            if old_binding != target_binding and not policy['rebase']:
                raise ValueError(f'“{layer["name"]}”需要明确同意按目标原图相对位置重映射；不会自动寻找相同人物或物体')
        material = json.dumps([layer, target_binding, index, sorted(used)], sort_keys=True, allow_nan=False).encode()
        layer['id'] = 'transfer_' + hashlib.sha256(material).hexdigest()[:32]
        if layer['id'] in used: raise ValueError('局部调色组标识冲突')
        used.add(layer['id'])
        layer['mask']['source'] = deepcopy(target_binding) if layer['mask']['recipe']['objects'] else None
    result = check({'version': VERSION, 'layers': existing + incoming})
    return {'groups': result}, {'policy': policy, 'added': [l['name'] for l in incoming],
        'removed': [l['name'] for l in removed], 'excluded': [l['name'] for l in excluded],
        'selected_group_ids': [layer['id'] for layer in choose(check_params(source)['groups'], policy)[0]],
        'legacy_removed': legacy_removed, 'legacy_preserved': target_state.get('_grade_scope') == 'objects' and not legacy_removed,
        'semantic_scope': 'whole-photo-category', 'target_source': deepcopy(target_binding)}


def validate_budget(groups, shape):
    layers = check(groups)['layers']
    enabled = [layer for layer in layers if layer['enabled']]
    if len(enabled) * shape[0] * shape[1] > MAX_MASK_PIXELS:
        raise ValueError('独立组全尺寸蒙版超过 1.28 亿总像素预算；请减少启用组数')
    work = sum(M.R.validate_budget(layer['mask']['recipe'], shape)['work'] for layer in enabled)
    if work > M.R.MAX_WORK:
        raise ValueError('独立组累计蒙版计算超过预算；请减少组/对象或羽化')
    return {'layers': len(layers), 'enabled': len(enabled), 'work': work}


def report(state, suspended=None):
    value = check(state.get('_local_grade_layers'))
    return {'version': VERSION, 'layers': [{**layer, 'types': sorted(types(layer))} for layer in value['layers']],
            'suspended': suspended, 'max_layers': MAX_LAYERS,
            'grade_limits': [.05, .60, .60], 'semantic_scope': 'whole-photo-category'}
