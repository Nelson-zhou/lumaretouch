"""Scalar-only photographed-shadow transfer; all evidence stays target-owned.

This is not the whole-ID portable recipe. It never transfers floor samples,
retention vectors, subject alpha, applicability confirmation, assets or AI claims.
The caller must obtain a real full-render review for each target before commit.
"""
from copy import deepcopy
from . import id_background_state as I, id_background_scope as ID
from . import original_shadow_state as S
from .local_mask_recipe import number

OP = 'lnx.original_shadow.v1'
FIELDS = ('_id_background',)


def check_params(raw):
    if (type(raw) is not dict or set(raw) != {'enabled', 'strength', 'blend'}
            or type(raw['enabled']) is not bool or raw['blend'] not in S.BLENDS):
        raise ValueError('原图阴影迁移只接受启用、程度与混合方式，不接受任何样本或蒙版')
    return {'enabled': raw['enabled'], 'strength': number(raw['strength'], 0, 100),
            'blend': raw['blend']}


def params_of(state):
    value = I.original_shadow_of(state.get('_id_background'))
    return check_params({key: value[key] for key in ('enabled', 'strength', 'blend')})


def install(state, params):
    clean = check_params(params)
    value = I.check(state.get('_id_background'))
    prior = I.original_shadow_of(value)
    if clean['enabled']:
        subject = value['support']['subject']
        if (not I.active(value) or not prior['uniform_floor_confirmed']
                or prior['lit_floor'] is None or prior['retention'] is None
                or value['selected_support'] != 'subject' or subject is None
                or any(obj['kind'] not in S.KINDS for obj in subject['mask']['recipe']['objects'])):
            raise ValueError('目标必须已有启用的背景、独立审核的手工主体及同源明亮地面和保留范围；不会复制样本或替目标确认地面')
    if params_of(state) == clean:
        return  # Neutral transfer must not upgrade a legacy recipe/hash.
    state['_id_background'] = I.with_original_shadow(value, S.check({**prior, **clean}))


def validate_target(state, path, shape):
    # Do not repeat install's enable admission here: undo may restore a valid
    # dormant enabled intent beneath an inactive parent, with its exact samples.
    ID.validate_target(state, path, shape)


def undo_key(state):
    return ID.undo_key(state)  # Freeze samples, support, asset and spill sibling.


def restore(state, previous):
    """Restore prior target shadow only; never overwrite unrelated ID intent."""
    current = I.check(state.get('_id_background'))
    prior = I.check(previous.get('_id_background'))
    if current['source'] != prior['source']:
        raise ValueError('原图阴影历史只能恢复同一目标来源的样本，不能复制另一来源')
    if prior['version'] != I.ORIGINAL_SHADOW_VERSION:
        spill = I.spill_of(current)
        current.pop('original_shadow', None)
        current['version'] = I.SPILL_VERSION
        current['spill'] = spill
        # A v1 predecessor had no spill field. Only remove the neutral field
        # introduced by our own v3 upgrade; never discard later spill edits.
        from . import spill_removal_state as SP
        if prior['version'] == I.VERSION and spill == SP.neutral():
            current.pop('spill', None)
            current['version'] = I.VERSION
        restored = I.check(current)
    else:
        restored = I.with_original_shadow(current, deepcopy(I.original_shadow_of(prior)))
    state['_id_background'] = restored
