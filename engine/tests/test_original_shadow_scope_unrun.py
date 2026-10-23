"""AUTHORED / UNRUN: target-only original-shadow scalar and history ownership.

Synthetic vectors are schema evidence only, never photographic acceptance.
No module imports, collection or execution occurred while authoring.
"""
from copy import deepcopy
import pytest
from lumaretouch_engine import original_shadow_scope as SH
from lumaretouch_engine import original_shadow_state as S
from lumaretouch_engine import id_background_state as I
from lumaretouch_engine import spill_removal_state as SP
from lumaretouch_engine import scope as SC
from lumaretouch_engine import optics_auto_scope as OA
from test_original_shadow_integration_unrun import binding, SOURCE
from test_spill_transfer_wiring_unrun import owned_id


def owned_shadow(source=SOURCE):
    value = owned_id(source)
    return I.with_original_shadow(value, {**S.neutral(), 'uniform_floor_confirmed': True,
        'lit_floor': binding('target-lit', source), 'retention': binding('target-shadow', source)})


def test_only_scalars_transfer_and_target_evidence_is_preserved():
    state = {'_id_background': owned_shadow(), '_id_background_bundle': None}
    before = deepcopy(state)
    SH.install(state, {'enabled': True, 'strength': 63, 'blend': 'softlight'})
    prior, after = I.original_shadow_of(before['_id_background']), I.original_shadow_of(state['_id_background'])
    assert {k: after[k] for k in ('lit_floor', 'retention', 'uniform_floor_confirmed')} == {k: prior[k] for k in ('lit_floor', 'retention', 'uniform_floor_confirmed')}
    assert I.spill_of(state['_id_background']) == I.spill_of(before['_id_background'])
    assert state['_id_background']['support'] == before['_id_background']['support']
    assert SH.params_of(state) == {'enabled': True, 'strength': 63., 'blend': 'softlight'}
    assert set(SH.params_of(state)) == {'enabled', 'strength', 'blend'}


@pytest.mark.parametrize('params', [
    {'enabled': True, 'strength': float('nan'), 'blend': 'normal'},
    {'enabled': 1, 'strength': 1, 'blend': 'normal'},
    {'enabled': False, 'strength': 100, 'blend': 'screen'},
    {'enabled': False, 'strength': 100, 'blend': 'normal', 'lit_floor': None},
])
def test_non_scalar_or_invalid_payload_rejected(params):
    with pytest.raises(ValueError): SH.check_params(params)


@pytest.mark.parametrize('fault', ['inactive', 'unconfirmed', 'missing-lit', 'missing-retention', 'other-support'])
def test_enabled_zero_cannot_park_unreviewed_target_intent(fault):
    value = owned_shadow()
    if fault == 'inactive': value['enabled'] = False
    elif fault == 'unconfirmed': value['original_shadow']['uniform_floor_confirmed'] = False
    elif fault == 'missing-lit': value['original_shadow']['lit_floor'] = None
    elif fault == 'missing-retention': value['original_shadow']['retention'] = None
    else: value['selected_support'] = 'all'
    state = {'_id_background': value}; before = deepcopy(state)
    with pytest.raises(ValueError): SH.install(state, {'enabled': True, 'strength': 0, 'blend': 'normal'})
    assert state == before


def test_disabling_retains_target_samples_and_neutral_legacy_is_not_upgraded():
    value = owned_shadow(); value['original_shadow']['enabled'] = True
    state = {'_id_background': I.check(value)}
    SH.install(state, {'enabled': False, 'strength': 40, 'blend': 'multiply'})
    assert state['_id_background']['original_shadow']['lit_floor'] == value['original_shadow']['lit_floor']
    legacy = {'_id_background': I.empty()}; saved = deepcopy(legacy)
    SH.install(legacy, {'enabled': False, 'strength': 100, 'blend': 'normal'})
    assert legacy == saved


@pytest.mark.parametrize('version', [1, 2])
def test_undo_restores_exact_preupgrade_shape(version):
    old = owned_id(SOURCE)
    if version == 2: old = I.with_spill(old, {**SP.neutral(), 'strength': 74.})
    current = {'_id_background': deepcopy(old)}
    SH.install(current, {'enabled': False, 'strength': 72, 'blend': 'softlight'})
    SH.restore(current, {'_id_background': old})
    assert current['_id_background'] == old


def test_restore_keeps_spill_sibling_and_dormant_shadow():
    old = owned_shadow(); old['enabled'] = False; old['original_shadow']['enabled'] = True
    current = I.with_spill(old, {**SP.neutral(), 'strength': 83.})
    current['original_shadow']['strength'] = 33.
    state = {'_id_background': current}
    SH.restore(state, {'_id_background': old})
    assert state['_id_background']['original_shadow'] == old['original_shadow']
    assert I.spill_of(state['_id_background'])['strength'] == 83.
    assert state['_id_background']['enabled'] is False


def test_full_dependency_key_and_conflicting_modules():
    state = {'_id_background': owned_shadow(), '_id_background_bundle': None}
    before = SH.undo_key(state)
    state['_id_background']['opacity'] = .7
    assert SH.undo_key(state) != before
    assert OA.before_params(state, [SH.OP]) == {SH.OP: {'target_recipe_key': SH.undo_key(state)}}
    for other in (SC.SPILL_REMOVAL.OP, SC.ID_BACKGROUND.OP):
        with pytest.raises(SC.ScopeError): SC.check_scope([SH.OP, other])
    assert SC.check_scope([SH.OP]) == [SH.OP]


def test_enabled_zero_requires_manual_subject_even_without_visible_shadow():
    from lumaretouch_engine import id_background_support as SUPPORT
    value = owned_shadow()
    subject = value['support']['subject']
    subject['mask']['recipe']['objects'] = [{'id': 'full', 'name': 'Not manual subject',
        'enabled': True, 'kind': 'full', 'operation': 'add', 'opacity': 1., 'feather': 0.}]
    subject['recipe_sha256'] = SUPPORT.digest(subject['mask'])
    with pytest.raises(ValueError):
        SH.install({'_id_background': value}, {'enabled': True, 'strength': 0, 'blend': 'normal'})


def test_restore_cannot_copy_another_sources_sample_snapshot():
    current = {'_id_background': owned_shadow()}
    prior = {'_id_background': owned_shadow({**SOURCE, 'sha256': 'b' * 64})}
    before = deepcopy(current)
    with pytest.raises(ValueError): SH.restore(current, prior)
    assert current == before


def test_noop_legacy_undo_does_not_require_an_artificial_spill_field():
    prior = {'_id_background': I.empty()}
    current = deepcopy(prior)
    SH.restore(current, prior)
    assert current == prior
