# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded scalar-only torso transfer into independently reviewed target owners.

Only version/amount travel. One enabled body is required, and every retained
body, support and analysis run must belong to one effective source. This is an
explicitly bounded route, not positional/nearest-person matching. Actual people
and full-source render admission belongs to torso_length_transfer_review.
AUTHORED / UNRUN: no runtime or photographic acceptance is claimed.
"""
from copy import deepcopy
from . import body_pose_state as B, body_pose_evidence as E
from . import body_pose_project as D, torso_length_project as P, torso_length_state as S

OP = S.OPERATION_ID
FIELDS = (D.KEY,)


def check_params(raw):
    """Do not wrap or widen the existing scalar-only portable schema."""
    return S.portable(raw)


def target(state):
    """Return a checked bank and its sole enabled, already reviewed torso row.

    Disabled other bodies remain in the bank and in full render protection.
    Multiple sources or enabled bodies are not a license to guess a target.
    Even amount zero cannot create/enable an unreviewed operation.
    """
    bank = P.check(D.bank(state))
    enabled = [row for row in bank['bodies'].values() if row['enabled']]
    if len(enabled) != 1:
        raise ValueError('上半身长短迁移仅支持目标已有唯一启用身体；多人归属必须明确处理，不能按顺序或最近人脸猜测')
    row = enabled[0]
    frame = row['record']['source']
    if (any(other['record']['source'] != frame for other in bank['bodies'].values())
            or any(asset['source'] != frame for asset in bank['support_assets'].values())
            or any(asset != frame['sha256'] for asset in bank['analysis_runs'])):
        raise ValueError('上半身长短迁移不接受混合来源身体库，保留的分析与支持必须属于同一目标原图或合成来源')
    ref = row['record']['body_ref']
    item = B.operation(bank, ref, OP)
    if not item['enabled'] or item['review'] is None or row['association'] is None:
        raise ValueError('目标必须已有启用的上半身长短操作、独立可见关节审核和明确人物归属；不会替目标启用或补造审核')
    support = B.support(bank, ref, OP)
    if support is None:
        raise ValueError('目标缺少自己审核的完整头发、双臂双手和背景过渡范围；不能复制来源照片的支持')
    S.policy_check_support(support['data'], row['record'])
    return bank, row, item, support


def params_of(state):
    _, _, item, _ = target(state)
    return check_params(item['recipe'])


def install(state, params):
    clean = check_params(params)
    bank, row, item, _ = target(state)
    if check_params(item['recipe']) == clean:
        return  # No-op cannot rewrite packing, source identity or revisions.
    changed = B.set_recipe(bank, row['record']['body_ref'], clean,
                           operation_id=OP, operation_policies=S.policies())
    state[D.KEY] = P.pack(changed)


def validate_target(state, path, shape):
    """Check original/derived full-source ownership without live installation.

    The actual graph is intentionally not guessed from state. Review preparation,
    verification and history_identity validate the exact current associated face.
    """
    bank, row, _, _ = target(state)
    from . import creative_derived_source as SOURCE
    if SOURCE.record(state) is not None:
        from .creative_derived_body import validate
        effective = SOURCE.binding(state)
        validate(bank, effective)
    else:
        if (type(shape) not in (tuple, list) or len(shape) != 2
                or any(type(n) is not int or n < 2 for n in shape)):
            raise ValueError('上半身长短迁移需要目标完整原始来源尺寸')
        effective = SOURCE.binding(state, path, (shape[1], shape[0]))
    expected = E.source({**effective, 'orientation': E.ORIENTATION})
    if row['record']['source'] != expected:
        raise ValueError('上半身长短支持的来源、完整尺寸或方向与目标当前有效来源不一致')


def bank_sha256(state):
    """Exact complete bank digest, including monotonic revision, for proofs."""
    bank, _, _, _ = target(state)
    return E.content_digest(bank)


def undo_key(state):
    """Fence every target-owned dependency, not just its amount.

    Only the monotonic overall bank revision is omitted: scoped undo/redo must
    advance it without authorizing new support, analysis, association or intent.
    Exact review identities still include the unmodified complete bank revision.
    """
    bank, _, _, _ = target(state)
    bank.pop('revision')
    from .creative_derived_source import record, binding
    source = binding(state) if record(state) is not None else None
    return E.content_digest({'body_bank': bank, 'creative_source': source})


def restore(state, previous):
    """Restore only a prior scalar for the exact same reviewed target body.

    The caller matches undo_key against its frozen expectation first. Even a
    direct call cannot copy a foreign body, support, review or face association.
    Unrelated current operations/support assets remain untouched; history never
    rolls the monotonic body-bank revision backwards.
    """
    current, row, item, support = target(state)
    _, prior, old_item, old_support = target(previous)
    if (row['record'] != prior['record'] or row['association'] != prior['association']
            or item['review'] != old_item['review'] or support != old_support):
        raise ValueError('上半身长短历史只能恢复同一身体、来源、支持审核及人物归属，不能移植历史范围')
    recipe = check_params(old_item['recipe'])
    if check_params(item['recipe']) == recipe:
        return
    restored = B.set_recipe(current, row['record']['body_ref'], deepcopy(recipe),
                            operation_id=OP, operation_policies=S.policies())
    state[D.KEY] = P.pack(restored)
