# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned scalar scope primitives shared by torso, waist and head. AUTHORED / UNRUN.

Portable data never contains body/support/face identity. Each explicitly selected
family validates its own immutable support policy before any scalar can change.
"""
from copy import deepcopy
from . import body_pose_state as B, body_pose_evidence as E, body_pose_project as D


class BodyScalarScope:
    def __init__(self, *, project, state, api, label, support_requirement,
                 review_requirement):
        self.project, self.state, self.api, self.label = project, state, api, label
        self.support_requirement, self.review_requirement = support_requirement, review_requirement

    def check_params(self, raw):
        """Do not wrap or widen the existing scalar-only portable schema."""
        return self.state.portable(raw)


    def target(self, state):
        """Return the sole enabled body with this family's own reviewed support.

        Disabled other bodies remain in the bank and in full render protection.
        Multiple sources or enabled bodies are not a license to guess a target.
        Even amount zero cannot create/enable an unreviewed operation.
        """
        bank = self.project.check(D.bank(state))
        enabled = [row for row in bank['bodies'].values() if row['enabled']]
        if len(enabled) != 1:
            raise ValueError('上半身长短迁移仅支持目标已有唯一启用身体；多人归属必须明确处理，不能按顺序或最近人脸猜测'.replace('上半身长短', self.label))
        row = enabled[0]
        frame = row['record']['source']
        if (any(other['record']['source'] != frame for other in bank['bodies'].values())
                or any(asset['source'] != frame for asset in bank['support_assets'].values())
                or any(asset != frame['sha256'] for asset in bank['analysis_runs'])):
            raise ValueError('上半身长短迁移不接受混合来源身体库，保留的分析与支持必须属于同一目标原图或合成来源'.replace('上半身长短', self.label))
        ref = row['record']['body_ref']
        item = B.operation(bank, ref, self.api.OP)
        if not item['enabled'] or item['review'] is None or row['association'] is None:
            raise ValueError(f'目标必须已有启用的{self.label}操作、{self.review_requirement}和明确人物归属；不会替目标启用或补造审核')
        support = B.support(bank, ref, self.api.OP)
        if support is None:
            raise ValueError(f'目标缺少自己审核的{self.support_requirement}；不能复制来源照片的支持')
        self.state.policy_check_support(support['data'], row['record'])
        return bank, row, item, support


    def params_of(self, state):
        _, _, item, _ = self.api.target(state)
        return self.api.check_params(item['recipe'])


    def install(self, state, params):
        clean = self.api.check_params(params)
        bank, row, item, _ = self.api.target(state)
        if self.api.check_params(item['recipe']) == clean:
            return  # No-op cannot rewrite packing, source identity or revisions.
        changed = B.set_recipe(bank, row['record']['body_ref'], clean,
                               operation_id=self.api.OP, operation_policies=self.state.policies())
        state[D.KEY] = self.project.pack(changed)


    def validate_target(self, state, path, shape):
        """Check original/derived full-source ownership without live installation.

        The actual graph is intentionally not guessed from state. Review preparation,
        verification and history_identity validate the exact current associated face.
        """
        bank, row, _, _ = self.api.target(state)
        from . import creative_derived_source as SOURCE
        if SOURCE.record(state) is not None:
            from .creative_derived_body import validate
            effective = SOURCE.binding(state)
            validate(bank, effective)
        else:
            if (type(shape) not in (tuple, list) or len(shape) != 2
                    or any(type(n) is not int or n < 2 for n in shape)):
                raise ValueError('上半身长短迁移需要目标完整原始来源尺寸'.replace('上半身长短', self.label))
            effective = SOURCE.binding(state, path, (shape[1], shape[0]))
        expected = E.source({**effective, 'orientation': E.ORIENTATION})
        if row['record']['source'] != expected:
            raise ValueError('上半身长短支持的来源、完整尺寸或方向与目标当前有效来源不一致'.replace('上半身长短', self.label))


    def bank_sha256(self, state):
        """Exact complete bank digest, including monotonic revision, for proofs."""
        bank, _, _, _ = self.api.target(state)
        return E.content_digest(bank)


    def undo_key(self, state):
        """Fence every target-owned dependency, not just its amount.

        Only the monotonic overall bank revision is omitted: scoped undo/redo must
        advance it without authorizing new support, analysis, association or intent.
        Exact review identities still include the unmodified complete bank revision.
        """
        bank, _, _, _ = self.api.target(state)
        bank.pop('revision')
        from .creative_derived_source import record, binding
        source = binding(state) if record(state) is not None else None
        return E.content_digest({'body_bank': bank, 'creative_source': source})


    def restore(self, state, previous):
        """Restore only a prior scalar for the exact same reviewed target body.

        The caller matches undo_key against its frozen expectation first. Even a
        direct call cannot copy a foreign body, support, review or face association.
        Unrelated current operations/support assets remain untouched; history never
        rolls the monotonic body-bank revision backwards.
        """
        current, row, item, support = self.api.target(state)
        _, prior, old_item, old_support = self.api.target(previous)
        if (row['record'] != prior['record'] or row['association'] != prior['association']
                or item['review'] != old_item['review'] or support != old_support):
            raise ValueError('上半身长短历史只能恢复同一身体、来源、支持审核及人物归属，不能移植历史范围'.replace('上半身长短', self.label))
        recipe = self.api.check_params(old_item['recipe'])
        if self.api.check_params(item['recipe']) == recipe:
            return
        restored = B.set_recipe(current, row['record']['body_ref'], deepcopy(recipe),
                                operation_id=self.api.OP, operation_policies=self.state.policies())
        state[D.KEY] = self.project.pack(restored)
