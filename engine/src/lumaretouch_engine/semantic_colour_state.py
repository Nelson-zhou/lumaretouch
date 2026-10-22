# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict AI-owned late-colour recipe. No legacy manual fields are overwritten."""
from copy import deepcopy
import math
import re

KEY = '_semantic_colour'
OP = 'lnx.semantic_colour.v1'
ALGORITHM = 'semantic-oklab-log-ot-pchip-hsv8-v1'
DOMAIN = 'rendered-canvas-normalized-semantic-colour-v1'
STAGE = 'working-srgb-float-after-geometry-and-reference-colour-v1'
CLASSES = ('background', 'hair', 'body_skin', 'face_skin', 'clothes', 'others')
LABELS = ('人像背景', '头发', '身体皮肤', '面部皮肤', '衣物', '其它（非背景）')
MAX_PIXELS = 32_000_000
PARAMS = 50
KNOTS = (0., .25, .5, .75, 1.)


def fail(message): raise ValueError(message)
def digest(v):
    if type(v) is not str or not re.fullmatch('[0-9a-f]{64}', v): fail('AI 追色摘要无效')
    return v

def number(v, low, high):
    if type(v) not in (float, int) or not math.isfinite(v) or not low <= v <= high:
        fail('AI 追色数值超出有限范围')
    return float(v)

def identifier(v):
    if type(v) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', v): fail('AI 追色对象身份无效')
    return v

def neutral(): return [0.] * 6 + list(KNOTS) * 4 + [0.] * 24

def parameters(v):
    if type(v) is not list or len(v) != PARAMS: fail('AI 追色参数必须包含完整的 50 个可编辑值')
    return [number(x, 0 if 6 <= i < 26 else -(2 if i < 4 else 60 if i >= 26 and (i-26) % 3 == 0 else 100),
                   1 if 6 <= i < 26 else 2 if i < 4 else 60 if i >= 26 and (i-26) % 3 == 0 else 100)
            for i, x in enumerate(v)]

def binding(v):
    expected = {'source', 'render_sha256', 'geometry_sha256', 'state_key', 'document_id', 'revision', 'width', 'height', 'stage'}
    if type(v) is not dict or set(v) != expected or v['stage'] != STAGE: fail('AI 追色需要完整的冻结渲染画布身份')
    from .reference_color_state import binding as source_binding
    source_binding(v['source'])
    for k in ('render_sha256', 'geometry_sha256', 'state_key'): digest(v[k])
    if type(v['document_id']) is not str or not 1 <= len(v['document_id']) <= 128: fail('AI 追色文档身份无效')
    if type(v['revision']) is not str or not v['revision'].isdecimal(): fail('AI 追色版本无效')
    if any(type(v[k]) is not int or not 1 <= v[k] <= 100000 for k in ('width', 'height')) or v['width'] * v['height'] > MAX_PIXELS:
        fail('AI 追色完整画布超过 3200 万像素预算，不会降采样最终输出')
    return deepcopy(v)

def empty():
    return {'version': 1, 'algorithm': ALGORITHM, 'domain': DOMAIN, 'enabled': False,
            'mode': 'harmonious', 'local_only': False, 'strengths': [100., 100., 100.],
            'target': None, 'reference': None, 'groups': [], 'masks': [], 'analysis': None, 'last_review': None}

def check(v):
    if v is None: return empty()
    if type(v) is not dict or set(v) != set(empty()) or type(v['version']) is not int or v['version'] != 1 or v['algorithm'] != ALGORITHM or v['domain'] != DOMAIN:
        fail('AI 追色配方版本或字段无效')
    if type(v['enabled']) is not bool or type(v['local_only']) is not bool or v['mode'] not in ('extreme', 'harmonious'): fail('AI 追色模式无效')
    out = deepcopy(v)
    if type(v['strengths']) is not list or len(v['strengths']) != 3: fail('需要整体、影调、色彩三个独立程度')
    out['strengths'] = [number(x, 0, 200) for x in v['strengths']]
    if v['target'] is not None: out['target'] = binding(v['target'])
    if v['reference'] is not None:
        from .reference_color_scope import check_params
        check_params({'version': 1, 'strength': 1., 'reference': v['reference']})
    if type(v['groups']) is not list or len(v['groups']) > 7 or type(v['masks']) is not list or len(v['masks']) > 8: fail('AI 追色分组或蒙版预算超限')
    from .semantic_colour_masks import check as check_mask
    out['masks'] = [check_mask(x) for x in v['masks']]
    mids = {m['id'] for m in out['masks']}
    if len(mids) != len(out['masks']): fail('AI 追色蒙版身份重复')
    if any(m['binding'] != out['target'] for m in out['masks']): fail('AI 追色蒙版不属于该目标冻结画布')
    ids = set()
    for g in out['groups']:
        if type(g) is not dict or set(g) != {'id', 'name', 'enabled', 'mask_id', 'baseline', 'parameters'}: fail('AI 追色可编辑组字段无效')
        identifier(g['id'])
        if g['id'] in ids: fail('AI 追色分组身份重复')
        ids.add(g['id'])
        if type(g['name']) is not str or not 1 <= len(g['name']) <= 80 or type(g['enabled']) is not bool: fail('AI 追色组名称/开关无效')
        if g['mask_id'] is not None and g['mask_id'] not in mids: fail('AI 追色组缺少对应蒙版')
        if g['id'] == 'global' and g['mask_id'] is not None: fail('整体组不能假装有语义蒙版')
        if g['id'] != 'global' and g['mask_id'] is None: fail('局部组不能丢失蒙版')
        g['parameters'] = parameters(g['parameters']); g['baseline'] = parameters(g['baseline'])
    if v['enabled'] and (not v['groups'] or v['target'] is None or v['reference'] is None or v['analysis'] is None): fail('活动 AI 追色缺少冻结身份或参数')
    if v['local_only'] and 'global' in ids: fail('局部追色不能包含全图调整')
    if v['analysis'] is not None:
        from .semantic_colour_analysis import check_receipt
        out['analysis'] = check_receipt(v['analysis'])
    if v['last_review'] is not None:
        from .semantic_colour_review import check_saved_review
        out['last_review']=check_saved_review(v['last_review'])
    return out

def active(v):
    p = check(v)
    return p['enabled'] and p['strengths'][0] != 0 and any(p['strengths'][1:]) and any(g['enabled'] and g['parameters'] != neutral() for g in p['groups'])

def install(state, recipe): return {**state, KEY: check(recipe)}

def portable(v):
    p = check(v)
    if p['local_only']: fail('局部双图追色不参加批量或预设同步，请使用整图模式')
    # A later per-target prepare owns inference and fitted values. User precise
    # offsets are explicit; source absolute gains/masks are NEVER portable.
    return {'version': 1, 'reference': deepcopy(p['reference']), 'mode': p['mode'],
            'strengths': p['strengths'], 'offset_policy': 'recompute-then-user-offset-v1',
            'offsets': {g['id']: [a-b for a,b in zip(g['parameters'],g['baseline'])] for g in p['groups']},
            'disabled_groups': [g['id'] for g in p['groups'] if not g['enabled']]}
