"""Scalar-only spill transfer into each target's already reviewed ID effect.

This is intentionally not the ID-background portable recipe. It cannot select
a background, enable ID, import a source, choose support or replace coverage.
The caller owns frozen target/source proofs, strict replay and history fences.
Full-ID and spill modules must not coexist in one transfer: both own scalars.
"""
from . import id_background_state as I
from . import id_background_scope as ID
from . import spill_removal_state as S

OP = 'lnx.spill_removal.v1'
FIELDS = ('_id_background',)


def check_params(raw):
    return S.check_portable(raw)


def params_of(state):
    return S.portable(I.spill_of(state.get('_id_background')))


def install(state, params):
    """Replace only enabled/strength; retain all target-owned ID dependencies."""
    clean = check_params(params)
    value = I.check(state.get('_id_background'))
    if clean['enabled'] and not I.active(value):
        # Even enabled+zero must not park an unreviewed latent enable request.
        # I.check has already required the selected, source-bound ID review.
        raise ValueError('祛染色同步要求目标已启用并独立审核证件照背景；不会替目标启用背景或复制范围')
    prior = I.spill_of(value)
    if S.portable(prior) == clean:
        # In particular, a neutral transfer must not upgrade legacy v1 or
        # manufacture a missing ID record and change old derived recipe hashes.
        return
    state['_id_background'] = I.with_spill(value, S.apply_portable(prior, clean))


def validate_target(state, path, shape):
    """Validate actual original/derived ownership, assets and ID exclusions.

    Transfer enable eligibility is enforced by install. Do not impose it again
    here: exact undo may legitimately restore dormant enabled spill intent
    beneath a disabled ID parent, which remains a rendering no-op.
    """
    ID.validate_target(state, path, shape)


def undo_key(state):
    # Scalar equality alone cannot freeze the coverage/support used by the
    # target calculation. Later ID/background/source edits are conflicts, not
    # permission to apply a reviewed scalar against different dependencies.
    return ID.undo_key(state)


def restore(state, previous):
    """Restore only prior target-owned spill, never the parent's other edits.

    The caller must first match undo_key against its frozen expected target.
    A v3 original-shadow sibling must survive restoring legacy neutral spill.
    Only an otherwise v2 container can return to the exact v1 shape.
    """
    current = I.check(state.get('_id_background'))
    prior = I.check(previous.get('_id_background'))
    if current['source'] != prior['source']:
        raise ValueError('祛染色历史只能恢复同一目标来源；不能复制另一来源的覆盖范围')
    if prior['version'] == I.VERSION and current['version'] != I.ORIGINAL_SHADOW_VERSION:
        current.pop('spill', None)
        current['version'] = I.VERSION
        restored = I.check(current)
    else:
        restored = I.with_spill(current, I.spill_of(prior))
    state['_id_background'] = restored
