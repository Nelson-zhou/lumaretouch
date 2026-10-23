"""Separately reviewed source-domain manual spill coverage, never a matte.

Only geometric local vectors are admitted. The result gates a separately
estimated correction; it cannot turn uncertain background colour into evidence.
Object order, visibility and add/subtract/intersect semantics are preserved.
"""
from copy import deepcopy
from hashlib import sha256
import json
from . import local_mask_state as M, local_mask_recipe as R

VERSION = 1
KINDS = frozenset(('brush', 'linear', 'radial'))


def digest(mask):
    return sha256(json.dumps(M.check(mask), sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode('utf-8')).hexdigest()


def check_binding(raw):
    fields = {'version', 'reviewed', 'mask', 'recipe_sha256'}
    if (type(raw) is not dict or set(raw) != fields or type(raw['version']) is not int
            or raw['version'] != VERSION or raw['reviewed'] is not True):
        raise ValueError('祛染色手工覆盖度必须经独立源图审核')
    mask = M.check(raw['mask'])
    if mask['source'] is None or mask['semantic_owner'] is not None or not mask['recipe']['objects']:
        raise ValueError('祛染色覆盖度需要自己的源图与非空手工矢量')
    if any(obj['kind'] not in KINDS for obj in mask['recipe']['objects']):
        raise ValueError('祛染色手工覆盖度仅接受画笔、线性和径向矢量，不借用语义或提示蒙版')
    if raw['recipe_sha256'] != digest(mask):
        raise ValueError('祛染色手工覆盖度审核摘要不匹配')
    source = mask['source']
    # Check dormant vectors too. Restoring a record cannot quietly widen its
    # coverage or turn a proxy-only intent into an unaffordable source replay.
    R.validate_budget(mask['recipe'], (source['height'], source['width']))
    return deepcopy({**raw, 'mask': mask})


def verify_source(raw, source):
    value = check_binding(raw)
    expected = M.check({'source': source, 'semantic_owner': None,
                        'recipe': M.empty()['recipe']})['source']
    if expected is None or value['mask']['source'] != expected:
        raise ValueError('祛染色手工覆盖度属于另一张有效源图')
    return value


def review(engine, ids, reviewed):
    """Snapshot selected, already source-edited vectors without mutating them.

    The ID transaction owns its document/revision fence. This function proves
    the current effective source and selected local-object order again before
    returning; it never manufactures an original-file substitute for a return.
    """
    if (reviewed is not True or type(ids) is not list or not ids
            or any(type(ident) is not str for ident in ids) or len(set(ids)) != len(ids)):
        raise ValueError('请在源图中审核并明确确认祛染色手工覆盖度')
    from . import creative_derived_source as D
    source = D.binding(engine)
    local = M.check(engine._local_masks)
    if local['source'] != source:
        raise ValueError('祛染色所选手工矢量不属于当前有效源图')
    objects = [obj for obj in local['recipe']['objects'] if obj['id'] in ids]
    if len(objects) != len(ids):
        raise ValueError('祛染色所选手工矢量已改变，请重新审核')
    mask = M.check({'source': source, 'semantic_owner': None,
                    'recipe': {**local['recipe'], 'objects': objects}})
    value = check_binding({'version': VERSION, 'reviewed': True, 'mask': mask,
                           'recipe_sha256': digest(mask)})
    D.verify(source, engine)
    current = M.check(engine._local_masks)
    if (current['source'] != source
            or [obj for obj in current['recipe']['objects'] if obj['id'] in ids] != objects):
        raise ValueError('祛染色覆盖度在审核期间改变，请重新审核')
    return value


def raster(raw, shape, *, source, full_source=False, cancelled=lambda: False):
    """Return float32 coverage on the requested source grid, not aligned RGB.

    The caller authenticates actual original/derived pixels. No RGB or model
    input is needed by this geometric-only raster. Full export must use exact
    source dimensions; later the ID stage transports fields through its warp.
    """
    import numpy as np
    value = verify_source(raw, source)
    if type(full_source) is not bool:
        raise ValueError('祛染色覆盖度重放模式无效')
    h, w = R._shape(shape)
    expected = value['mask']['source']
    if (h > expected['height'] or w > expected['width']
            or full_source and (h, w) != (expected['height'], expected['width'])):
        raise ValueError('祛染色覆盖度不能把代理放大为完整源图')
    if cancelled():
        raise InterruptedError('祛染色覆盖度准备已取消')
    result = R.raster(value['mask']['recipe'], (h, w))
    if cancelled():
        raise InterruptedError('祛染色覆盖度准备已取消')
    return result.astype(np.float32) / 255.
