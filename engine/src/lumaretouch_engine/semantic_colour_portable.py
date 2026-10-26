# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable *intent*, never a source-fitted colour recipe or source mask.

The caller owns fresh per-target analysis, proposal proof, review and atomic
commit. This module neither infers nor installs state. Editable curves keep the
native PCHIP contract: finite [0, 1] ordinates, including deliberate reversals.
The fitter's increasing-master-knot constraint is not a manual-edit constraint.
"""
from copy import deepcopy

from . import semantic_colour_state as S

OFFSET_POLICY = 'recompute-then-user-offset-v1'
CLASS_POLICY = 'require-requested-support-v1'
GROUPS = ('global',) + S.CLASSES
FIELDS = {'version', 'algorithm', 'reference', 'mode', 'strengths', 'enabled',
          'offset_policy', 'class_policy', 'groups'}


def _number(value, low, high):
    # Bound Python integers before math.isfinite converts them to C doubles.
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError('AI 追色便携数值超出有限范围')
    return S.number(value, low, high)


def _offset_limit(index):
    # Difference of two legal native colour.rs parameters, not an independent
    # creative-strength cap. Actual target baseline + offset is checked later.
    if index < 4:
        return 4.
    if 6 <= index < 26:
        return 1.
    if index >= 26 and (index - 26) % 3 == 0:
        return 120.
    return 200.


def _offsets(value):
    if type(value) is not list or len(value) != S.PARAMS:
        raise ValueError('AI 追色便携偏移必须包含完整的 50 个值')
    return [_number(v, -_offset_limit(i), _offset_limit(i))
            for i, v in enumerate(value)]


def check(value):
    """Validate and return a detached intent in canonical seven-group order.

    Missing classes are deliberate omissions, not requests for automatic new
    groups. Disabled requested classes still require support on every target.
    """
    if type(value) is not dict or set(value) != FIELDS:
        raise ValueError('AI 追色便携意图字段无效；不能携带目标参数、基线或蒙版')
    if (type(value['version']) is not int or value['version'] != 1
            or value['algorithm'] != S.ALGORITHM
            or value['offset_policy'] != OFFSET_POLICY
            or value['class_policy'] != CLASS_POLICY):
        raise ValueError('AI 追色便携意图版本或重算策略无效')
    if type(value['enabled']) is not bool or value['mode'] not in ('extreme', 'harmonious'):
        raise ValueError('AI 追色便携模式或开关无效')
    from .reference_color_scope import check_params
    reference = check_params({'version': 1, 'strength': 1.,
                              'reference': value['reference']})['reference']
    strengths = value['strengths']
    if type(strengths) is not list or len(strengths) != 3:
        raise ValueError('AI 追色便携意图需要三个独立程度')
    strengths = [_number(v, 0, 200) for v in strengths]
    groups = value['groups']
    if type(groups) is not list or not 1 <= len(groups) <= len(GROUPS):
        raise ValueError('AI 追色便携分组预算无效')
    requested = {}
    for group in groups:
        if type(group) is not dict or set(group) != {'id', 'enabled', 'offsets'}:
            raise ValueError('AI 追色便携分组只能包含身份、开关及手动偏移')
        ident = group['id']
        if type(ident) is not str or ident not in GROUPS or ident in requested:
            raise ValueError('AI 追色便携分组身份未知或重复')
        if type(group['enabled']) is not bool:
            raise ValueError('AI 追色便携分组开关必须是布尔值')
        requested[ident] = {'id': ident, 'enabled': group['enabled'],
                            'offsets': _offsets(group['offsets'])}
    if 'global' not in requested:
        raise ValueError('AI 追色便携意图必须保留全图基础组；关闭不等于删除')
    return {'version': 1, 'algorithm': S.ALGORITHM, 'reference': reference,
            'mode': value['mode'], 'strengths': strengths, 'enabled': value['enabled'],
            'offset_policy': OFFSET_POLICY, 'class_policy': CLASS_POLICY,
            'groups': [requested[ident] for ident in GROUPS if ident in requested]}


def _full_image(recipe, *, reviewed):
    out = S.check(recipe)
    if out['local_only']:
        raise ValueError('局部双图追色不能作为便携全图意图；不会默默丢弃选区')
    if out['target'] is None or out['reference'] is None or out['analysis'] is None:
        raise ValueError('AI 追色便携意图需要完整冻结来源、样片及真实分析记录')
    by_id = {g['id']: g for g in out['groups']}
    if 'global' not in by_id or set(by_id) - set(GROUPS):
        raise ValueError('AI 追色便携配方必须是全图基础组及真实六类语义组')
    masks = {m['id']: m for m in out['masks']}
    expected_masks = set()
    for ident, group in by_id.items():
        if ident == 'global':
            continue
        mid = 'semantic_' + ident
        if group['mask_id'] != mid or mid not in masks:
            raise ValueError('AI 追色便携分组必须使用自己的重新生成语义蒙版：' + ident)
        expected_masks.add(mid)
    # Inspect ALL masks, including disabled groups and otherwise orphaned masks.
    # No enabled-bit shortcut may silently discard source-bound manual intent.
    for mask in out['masks']:
        if mask['objects']:
            raise ValueError('AI 追色便携意图不支持画笔、渐变等用户蒙版标记，包括已关闭的标记')
        if mask['base'] is None or mask['id'] not in expected_masks:
            raise ValueError('AI 追色便携意图含有非生成语义蒙版或游离蒙版')
    if set(masks) != expected_masks:
        raise ValueError('AI 追色便携分组与生成语义蒙版不匹配')
    review = out['last_review']
    if reviewed and (review is None or review.get('authorization') is not None):
        raise ValueError('只能从已明确审核并提交的 AI 追色配方提取便携意图')
    if review is not None:
        binding = review['reference_binding']
        if (binding['source'] != out['reference']['source']
                or binding['render_sha256'] != out['reference']['render_sha256']):
            raise ValueError('AI 追色保留审核与拥有的样片身份不一致')
        for ident in by_id:
            if review['diagnostics'][GROUPS.index(ident)][9] != 1.:
                raise ValueError('AI 追色请求分组缺少初始拟合的共同支持证据：' + ident)
    return out


def extract(recipe):
    """Extract only manual-minus-retained-baseline deltas from committed state.

    A retained saved-review record is required; this is not an independent
    signature verifier or a claim that the user accepted photographic quality.
    """
    source = _full_image(recipe, reviewed=True)
    return check({'version': 1, 'algorithm': S.ALGORITHM,
                  'reference': deepcopy(source['reference']), 'mode': source['mode'],
                  'strengths': source['strengths'], 'enabled': source['enabled'],
                  'offset_policy': OFFSET_POLICY, 'class_policy': CLASS_POLICY,
                  'groups': [{'id': g['id'], 'enabled': g['enabled'],
                              'offsets': [actual - baseline for actual, baseline
                                          in zip(g['parameters'], g['baseline'])]}
                             for g in source['groups']]})


def apply_offsets(fresh_recipe, intent):
    """Add intent deltas to THIS target's fitted baseline, atomically in memory.

    The owner must call this on a fresh untouched fit in the requested mode,
    before recomputing its proposal proof and collecting target-specific review.
    No source masks, diagnostics or review are copied. No impossible request is
    clamped, dropped, or downgraded to a global fallback, even if disabled.
    """
    request = check(intent)
    fresh = _full_image(fresh_recipe, reviewed=False)
    if fresh['reference'] != request['reference'] or fresh['mode'] != request['mode']:
        raise ValueError('目标必须针对同一拥有样片及请求模式重新拟合')
    if any(g['parameters'] != g['baseline'] for g in fresh['groups']):
        raise ValueError('AI 追色偏移只能应用到尚未手动修改的逐目标新拟合')
    available = {g['id']: g for g in fresh['groups']}
    missing = [g['id'] for g in request['groups'] if g['id'] not in available]
    if missing:
        raise ValueError('目标缺少请求类别的真实共同支持，未应用任何分组：' + '、'.join(missing))
    groups = []
    for wanted in request['groups']:
        group = available[wanted['id']]
        candidate = [base + delta for base, delta in zip(group['baseline'], wanted['offsets'])]
        try:
            # Native evaluator accepts intentional non-monotone ordinates. Its
            # own strength-time curve/HSV clipping is not offset-time clamping.
            group['parameters'] = S.parameters(candidate)
        except ValueError as error:
            raise ValueError('目标新基线加手动偏移超出参数边界，未裁剪或应用：' + group['id']) from error
        group['enabled'] = wanted['enabled']
        groups.append(group)
    keep_masks = {g['mask_id'] for g in groups if g['mask_id'] is not None}
    fresh.update(groups=groups, masks=[m for m in fresh['masks'] if m['id'] in keep_masks],
                 enabled=request['enabled'], mode=request['mode'], strengths=request['strengths'])
    return S.check(fresh)
