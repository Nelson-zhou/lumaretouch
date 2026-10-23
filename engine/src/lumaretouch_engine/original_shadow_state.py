"""Reviewed photographed-shadow intent, not a learned matte or source RGB layer.

Only an explicitly confirmed uniform diffuse floor is supported. The two
geometric source-owned selections are independent of the reviewed subject alpha.
Existing local-mask coverage is 8-bit; source RGB is never quantized to that grid.
"""
from copy import deepcopy
from hashlib import sha256
import json
from . import local_mask_state as M, local_mask_recipe as R
from .local_mask_recipe import number

VERSION = 1
ALGORITHM = 'lrt-original-shadow-uniform-floor-v1'
KINDS = frozenset(('brush', 'linear', 'radial'))
BLENDS = ('normal', 'multiply', 'softlight')


def neutral():
    return {'version': VERSION, 'algorithm': ALGORITHM, 'enabled': False,
            'strength': 100., 'blend': 'normal', 'uniform_floor_confirmed': False,
            'lit_floor': None, 'retention': None}


def digest(mask):
    return sha256(json.dumps(M.check(mask), sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode('utf-8')).hexdigest()


def check_binding(raw):
    if (type(raw) is not dict or set(raw) != {'version', 'reviewed', 'mask', 'recipe_sha256'}
            or type(raw['version']) is not int or raw['version'] != VERSION
            or raw['reviewed'] is not True):
        raise ValueError('原阴影样本与保留范围必须分别经过源图审核')
    mask = M.check(raw['mask'])
    if (mask['source'] is None or mask['semantic_owner'] is not None
            or not mask['recipe']['objects']
            or any(obj['kind'] not in KINDS for obj in mask['recipe']['objects'])):
        raise ValueError('原阴影只接受源图手工画笔、线性和径向范围，不使用自动或提示蒙版')
    if raw['recipe_sha256'] != digest(mask):
        raise ValueError('原阴影源图范围审核摘要不匹配')
    source = mask['source']
    R.validate_budget(mask['recipe'], (source['height'], source['width']))
    return deepcopy({**raw, 'mask': mask})


def check(raw):
    if (type(raw) is not dict or set(raw) != set(neutral())
            or type(raw['version']) is not int or raw['version'] != VERSION
            or raw['algorithm'] != ALGORITHM or type(raw['enabled']) is not bool
            or type(raw['uniform_floor_confirmed']) is not bool or raw['blend'] not in BLENDS):
        raise ValueError('原阴影提取的版本、算法、混合模式或适用性确认无效')
    out = {**raw, 'strength': number(raw['strength'], 0, 100),
           **{key: None if raw[key] is None else check_binding(raw[key])
              for key in ('lit_floor', 'retention')}}
    if (out['lit_floor'] is not None and out['retention'] is not None
            and out['lit_floor']['mask']['source'] != out['retention']['mask']['source']):
        raise ValueError('明亮地面样本与阴影保留范围必须属于同一有效源图')
    if (out['lit_floor'] is not None and out['retention'] is not None
            and {obj['id'] for obj in out['lit_floor']['mask']['recipe']['objects']}
            & {obj['id'] for obj in out['retention']['mask']['recipe']['objects']}):
        raise ValueError('明亮地面样本与阴影保留范围必须分别选择独立手工对象')
    if out['enabled'] and (not out['uniform_floor_confirmed']
                           or out['lit_floor'] is None or out['retention'] is None):
        raise ValueError('请分别审核明亮地面与原阴影范围，并确认同材质均匀漫反射地面')
    return deepcopy(out)


def active(raw):
    value = check(raw)
    return value['enabled'] and value['strength'] > 0


def review(engine, ids, reviewed):
    """Capture selected local vectors in retained composition order, unchanged."""
    if (reviewed is not True or type(ids) is not list or not ids
            or any(type(ident) is not str for ident in ids) or len(set(ids)) != len(ids)):
        raise ValueError('请在源图中审核并明确确认原阴影所选手工范围')
    from . import creative_derived_source as D
    source = D.binding(engine)
    local = M.check(engine._local_masks)
    if local['source'] != source:
        raise ValueError('原阴影所选范围不属于当前有效源图')
    objects = [obj for obj in local['recipe']['objects'] if obj['id'] in ids]
    if len(objects) != len(ids):
        raise ValueError('原阴影所选范围已变化，请重新审核')
    mask = M.check({'source': source, 'semantic_owner': None,
                    'recipe': {**local['recipe'], 'objects': objects}})
    value = check_binding({'version': VERSION, 'reviewed': True, 'mask': mask,
                           'recipe_sha256': digest(mask)})
    D.verify(source, engine)
    current = M.check(engine._local_masks)
    if (current['source'] != source
            or [obj for obj in current['recipe']['objects'] if obj['id'] in ids] != objects):
        raise ValueError('原阴影手工范围在审核期间变化，请重新审核')
    return value


def raster(raw, shape, *, source, full_source=False, cancelled=lambda: False):
    """Replay user vectors on this source grid only; no image/model inputs."""
    import numpy as np
    value = check_binding(raw)
    expected = M.check({'source': source, 'semantic_owner': None,
                        'recipe': M.empty()['recipe']})['source']
    if expected is None or value['mask']['source'] != expected:
        raise ValueError('原阴影手工范围属于另一张有效源图')
    if type(full_source) is not bool:
        raise ValueError('原阴影源图重放模式无效')
    h, w = R._shape(shape)
    if (h > expected['height'] or w > expected['width']
            or full_source and (h, w) != (expected['height'], expected['width'])):
        raise ValueError('原阴影不能将代理范围放大为完整源图')
    if cancelled():
        raise InterruptedError('原阴影范围准备已取消')
    result = R.raster(value['mask']['recipe'], (h, w))
    if cancelled():
        raise InterruptedError('原阴影范围准备已取消')
    return result.astype(np.float32) / 255.


def portable(raw):
    """No cross-target review exists. Only exact neutral intent may travel."""
    value = check(raw)
    if value != neutral():
        raise ValueError('原阴影提取不能跨照片移植；请在目标源图独立审核')
    return neutral()


def check_portable(raw):
    return portable(raw)
