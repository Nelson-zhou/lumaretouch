"""PC-32476 retained intent. No guessed sky/water semantics or proxy RGB.

Regions are explicitly painted on a producer-owned, unwarped source locator.
They are rasterized by the existing bounded Rust LMR2 engine and aligned by the
actual automatic deformation at the sky consumer. Final manual liquify/crop
remain downstream. Numeric ranges not published by PixCake are our own scales.
"""
from copy import deepcopy
import os
import re
from . import local_mask_recipe as M, local_mask_state as B

VERSION = 1
DOMAIN = 'source-normalized'
REGIONS = ('sky', 'person', 'water')
LIMITS = {
    'vertical': (-100., 100., 0.), 'horizontal': (-100., 100., 0.),
    'angle': (-180., 180., 0.), 'scale': (25., 400., 125.),
    'edge': (-100., 100., 0.), 'gradient': (0., 100., 10.),
    'temperature': (-100., 100., 0.), 'tint': (-100., 100., 0.),
    'saturation': (-100., 100., 0.), 'brightness': (-100., 100., 0.),
    'blur': (0., 100., 0.), 'opacity': (0., 100., 100.),
    'scene': (-100., 100., 0.), 'person': (-100., 100., 0.),
    'reflection': (0., 100., 0.), 'reflection_blur': (0., 100., 0.),
}
MAX_POINTS = 8192
MAX_STROKES = 128
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_ASSET_PIXELS = 32_000_000


def mask():
    return {'version': 1, 'domain': DOMAIN, 'objects': []}


def defaults():
    return {**{key: value[2] for key, value in LIMITS.items()}, 'flip': False}


def empty():
    return {'version': VERSION, 'domain': DOMAIN, 'enabled': False, 'source': None,
            'asset': None, 'parameters': defaults(), 'regions': {key: mask() for key in REGIONS},
            'person_mode': 'unmarked', 'horizon': None, 'recovery': mask()}


def parameters(raw):
    if type(raw) is not dict or set(raw) != set(defaults()) or type(raw['flip']) is not bool:
        raise ValueError('天空参数字段或翻转状态无效')
    return {**{key: M.number(raw[key], low, high) for key, (low, high, _) in LIMITS.items()}, 'flip': raw['flip']}


def asset(raw):
    if raw is None:
        return None
    if (type(raw) is not dict or set(raw) != {'path', 'sha256', 'width', 'height', 'bits', 'working_color', 'icc_sha256'}
            or type(raw['path']) is not str or not os.path.isabs(raw['path']) or len(raw['path']) > 4096
            or '\x00' in raw['path'] or type(raw['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', raw['sha256'])
            or raw['working_color'] != 'encoded-srgb' or type(raw['bits']) is not int or raw['bits'] not in (8, 16)
            or any(type(raw[k]) is not int or raw[k] <= 0 for k in ('width', 'height'))
            or raw['width'] * raw['height'] > MAX_ASSET_PIXELS
            or (raw['icc_sha256'] is not None and (type(raw['icc_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', raw['icc_sha256'])))):
        raise ValueError('天空素材的文件、像素或工作色彩身份无效')
    return deepcopy(raw)


def selection(raw):
    value = M.check_stack(raw)
    if any(o['kind'] != 'brush' or o['operation'] not in ('add', 'subtract') for o in value['objects']):
        raise ValueError('天空、水面、人物与恢复区域只接受明确标记的加减画笔；不猜测背景语义')
    return value


def check(raw):
    if raw is None:
        return empty()
    if (type(raw) is not dict or set(raw) != set(empty()) or type(raw['version']) is not int
            or raw['version'] != VERSION or raw['domain'] != DOMAIN or type(raw['enabled']) is not bool
            or type(raw['regions']) is not dict or set(raw['regions']) != set(REGIONS)
            or raw['person_mode'] not in ('unmarked', 'none', 'marked')):
        raise ValueError('换天空配方版本、坐标域或字段无效')
    regions = {key: selection(raw['regions'][key]) for key in REGIONS}
    recovery = selection(raw['recovery'])
    objects = [obj for stack in [*regions.values(), recovery] for obj in stack['objects']]
    if len(objects) > MAX_STROKES or sum(len(o['points']) for o in objects) > MAX_POINTS:
        raise ValueError('换天空超过 128 笔或 8192 个路径点预算')
    if len({o['id'] for o in objects}) != len(objects):
        raise ValueError('换天空区域笔迹身份重复')
    source = B.check({'recipe': mask(), 'source': raw['source'], 'semantic_owner': None})['source']
    if (objects or raw['enabled']) and source is None:
        raise ValueError('换天空区域必须绑定其原照片')
    if raw['person_mode'] == 'none' and regions['person']['objects']:
        raise ValueError('标记有人物时不能声明没有人物')
    if raw['person_mode'] == 'marked' and not regions['person']['objects']:
        raise ValueError('人物模式缺少明确人物标记')
    horizon = None if raw['horizon'] is None else M.number(raw['horizon'], .01, .99)
    return {'version': VERSION, 'domain': DOMAIN, 'enabled': raw['enabled'], 'source': source,
            'asset': asset(raw['asset']), 'parameters': parameters(raw['parameters']), 'regions': regions,
            'person_mode': raw['person_mode'], 'horizon': horizon, 'recovery': recovery}


def check_saved_record(raw):
    if type(raw) is not dict:
        raise ValueError('已保存的换天空配方必须为对象；不能用 null 静默丢失效果')
    return check(raw)


def ready(value):
    """Fail closed only when enabled, so incomplete selection drafts can be saved."""
    value = check(value)
    if not value['enabled']:
        return
    if value['asset'] is None or not value['regions']['sky']['objects']:
        raise ValueError('请先选择自有天空素材并标记天空区域；没有自动天空检测')
    if value['person_mode'] == 'unmarked':
        raise ValueError('请标记人物，或明确选择照片中没有人物；不能把人物当景物处理')
    if value['parameters']['reflection'] > 0 and (value['horizon'] is None or not value['regions']['water']['objects']):
        raise ValueError('水面反射需要明确水面区域与地平线；不会自动覆盖下半幅')


def editable(value):
    value = check(value)
    return {key: deepcopy(value[key]) for key in ('enabled', 'parameters', 'regions', 'person_mode', 'horizon', 'recovery')} | {
        'asset_path': value['asset']['path'] if value['asset'] else None, 'asset_choice': None}


def from_editable(raw, binding, resolved_asset):
    if type(raw) is not dict or set(raw) != set(editable(empty())):
        raise ValueError('天空草稿字段无效')
    if raw['asset_path'] is not None and (type(raw['asset_path']) is not str or not os.path.isabs(raw['asset_path'])):
        raise ValueError('天空素材必须为通过文件选择器选择的本地绝对路径')
    if raw['asset_choice'] is not None and (type(raw['asset_choice']) is not str or not re.fullmatch('[0-9a-f]{32}',raw['asset_choice'])):
        raise ValueError('天空素材选择身份无效')
    if (resolved_asset['path'] if resolved_asset else None) != raw['asset_path']:
        raise ValueError('天空素材尚未验证或已变化')
    value = {**empty(), **{key: deepcopy(raw[key]) for key in raw if key not in ('asset_path','asset_choice')}, 'asset': resolved_asset}
    has_regions = any(v['objects'] for v in value['regions'].values()) or bool(value['recovery']['objects'])
    value['source'] = deepcopy(binding) if value['enabled'] or has_regions else None
    return check(value)


def validate_budget(value, shape):
    value = check(value)
    M._shape(shape)
    work = sum(M.validate_budget(v, shape)['work'] for v in [*value['regions'].values(), value['recovery']])
    if work > M.MAX_WORK:
        raise ValueError('换天空累计标记计算超过预算，请减少笔迹或羽化')
    return {'work': work, 'mask_bytes': shape[0] * shape[1] * 4}


def migrate_legacy_states(value, *, root=False):
    if isinstance(value, dict):
        for child in list(value.values()):
            migrate_legacy_states(child)
        if root or any(k in value for k in ('_grade', '_local_masks', '_local_grade_layers', '_manual_liquify', '_studio_background', '_optics')):
            value.setdefault('_sky_replacement', empty())
    elif isinstance(value, list):
        for child in value:
            migrate_legacy_states(child)
