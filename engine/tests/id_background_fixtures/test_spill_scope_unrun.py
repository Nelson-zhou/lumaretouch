"""AUTHORED / UNRUN: scalar-only target ownership and scoped history.

These fixtures were not imported, collected or executed. No numerical kernel,
source decoding, model inference or raster worker is invoked by this file.
"""
from copy import deepcopy
import pytest
from lumaretouch_engine import id_background_state as I
from lumaretouch_engine import id_background_support as SUPPORT
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import spill_removal_state as S
from lumaretouch_engine import spill_removal_coverage as C
from lumaretouch_engine import spill_removal_scope as SCOPE

SOURCE = {'sha256': 'a' * 64, 'width': 32, 'height': 24}
OTHER = {'sha256': 'b' * 64, 'width': 40, 'height': 30}


def mask(source, x=.5):
    value = M.empty()
    value['source'] = deepcopy(source)
    value['recipe']['objects'] = [
        {'id': 'target-vector', 'name': 'Target-owned vector', 'enabled': True,
         'kind': 'brush', 'operation': 'add', 'opacity': 1., 'feather': 0.,
         'points': [[x, .5]], 'axes': [[.1, 0.], [0., .1]]}]
    return value


def target(source=SOURCE, *, spill=False, enabled=False, covered=True):
    value = I.empty()
    value.update(source=deepcopy(source), enabled=True)
    support = mask(source)
    value['support']['subject'] = {
        'version': 1, 'category': 'subject', 'reviewed': True, 'mask': support,
        'recipe_sha256': SUPPORT.digest(support)}
    if spill:
        recipe = S.neutral()
        recipe['enabled'] = enabled
        if covered:
            local = mask(source, .6)
            recipe['coverage'] = {'version': 1, 'reviewed': True, 'mask': local,
                                  'recipe_sha256': C.digest(local)}
        value = I.with_spill(value, recipe)
    return {'_id_background': value, '_id_background_bundle': None,
            '_unrelated': {'preserve': True}}


def nonspill(value):
    result = deepcopy(value)
    result.pop('spill', None)
    result.pop('version')
    return result


def test_scope_exports_only_two_scalars_not_full_id_or_source_coverage():
    state = target(spill=True, enabled=True)
    assert SCOPE.OP == 'lnx.spill_removal.v1'
    assert SCOPE.FIELDS == ('_id_background',)
    assert SCOPE.params_of(state) == {'enabled': True, 'strength': 50.}
    assert SCOPE.params_of(target()) == {'enabled': False, 'strength': 50.}


@pytest.mark.parametrize('extra', [
    {'coverage': None}, {'source': SOURCE}, {'recipe': {}},
    {'algorithm': S.ALGORITHM}, {'version': 1}, {'background': {}},
])
def test_scope_rejects_non_scalar_payloads(extra):
    with pytest.raises(ValueError):
        SCOPE.check_params({'enabled': False, 'strength': 50., **extra})


@pytest.mark.parametrize('params', [
    {}, {'enabled': False}, {'enabled': 1, 'strength': 50.},
    {'enabled': True, 'strength': True},
    {'enabled': False, 'strength': float('nan')},
    {'enabled': False, 'strength': -1.}, {'enabled': False, 'strength': 101.},
])
def test_scope_scalar_validation_is_strict(params):
    with pytest.raises(ValueError):
        SCOPE.check_params(params)


def test_neutral_disabled_transfer_does_not_rewrite_legacy_or_missing_state():
    state = target()
    original = state['_id_background']
    before = deepcopy(state)
    SCOPE.install(state, {'enabled': False, 'strength': 50.})
    assert state == before and state['_id_background'] is original
    assert state['_id_background']['version'] == 1
    absent = {}
    SCOPE.install(absent, {'enabled': False, 'strength': 50.})
    assert absent == {}


def test_disabled_non_neutral_intent_upgrades_without_enabling_parent():
    state = {'_id_background': I.empty()}
    before = deepcopy(state['_id_background'])
    SCOPE.install(state, {'enabled': False, 'strength': 72.})
    value = state['_id_background']
    assert value['version'] == 2 and not value['enabled']
    assert value['spill']['strength'] == 72. and not value['spill']['enabled']
    assert value['spill']['coverage'] is None
    assert nonspill(value) == nonspill(before)


@pytest.mark.parametrize('strength', [0., 50.])
@pytest.mark.parametrize('kind', ['no-review', 'disabled', 'zero-opacity'])
def test_enabled_transfer_requires_already_active_reviewed_target(kind, strength):
    state = target()
    if kind == 'no-review':
        state['_id_background'] = I.empty()
    elif kind == 'disabled':
        state['_id_background']['enabled'] = False
    else:
        state['_id_background']['opacity'] = 0.
    before = deepcopy(state)
    with pytest.raises(ValueError):
        SCOPE.install(state, {'enabled': True, 'strength': strength})
    assert state == before


def test_scalar_transfer_keeps_target_support_background_asset_and_coverage():
    origin = target(spill=True, enabled=True)
    origin['_id_background']['spill']['strength'] = 83.
    destination = target(OTHER, spill=True, enabled=False)
    destination['_id_background']['background']['color'] = [12, 34, 56]
    before = deepcopy(destination)
    bundle = destination['_id_background_bundle']
    SCOPE.install(destination, SCOPE.params_of(origin))
    value = destination['_id_background']
    assert nonspill(value) == nonspill(before['_id_background'])
    assert value['spill']['coverage'] == before['_id_background']['spill']['coverage']
    assert value['spill']['coverage'] != origin['_id_background']['spill']['coverage']
    assert value['spill']['enabled'] and value['spill']['strength'] == 83.
    assert destination['_id_background_bundle'] is bundle
    assert destination['_unrelated'] == before['_unrelated']
    assert origin['_id_background']['source'] == SOURCE


def test_uncovered_target_does_not_inherit_source_coverage():
    origin = target(spill=True, enabled=True)
    destination = target(OTHER)
    SCOPE.install(destination, SCOPE.params_of(origin))
    assert destination['_id_background']['spill']['coverage'] is None
    assert destination['_id_background']['source'] == OTHER


def test_validate_target_delegates_exact_original_or_derived_owner(monkeypatch):
    calls = []
    monkeypatch.setattr(SCOPE.ID, 'validate_target',
                        lambda state, path, shape: calls.append((state, path, shape)))
    state = target(spill=True, enabled=True)
    SCOPE.validate_target(state, '/target-original.png', (24, 32))
    assert calls == [(state, '/target-original.png', (24, 32))]


def test_undo_key_freezes_manual_coverage_and_all_id_dependencies():
    before = target(spill=True, enabled=True)
    expected = SCOPE.undo_key(before)
    unrelated = deepcopy(before)
    unrelated['_unrelated']['preserve'] = False
    assert SCOPE.undo_key(unrelated) == expected
    for field, changed in [('edge', 2.), ('opacity', .5), ('enabled', False)]:
        current = deepcopy(before)
        current['_id_background'][field] = changed
        assert SCOPE.undo_key(current) != expected
    current = deepcopy(before)
    local = mask(SOURCE, .7)
    current['_id_background']['spill']['coverage'] = {
        'version': 1, 'reviewed': True, 'mask': local,
        'recipe_sha256': C.digest(local)}
    assert SCOPE.undo_key(current) != expected


def test_restore_returns_exact_prior_nested_spill_without_overwriting_parent():
    before = target(spill=True, enabled=False)
    current = deepcopy(before)
    SCOPE.install(current, {'enabled': True, 'strength': 81.})
    # A caller's undo fence rejects such later parent edits. Even on its own,
    # the restore primitive must not overwrite an unowned parent field.
    current['_id_background']['edge'] = 2.
    current['_unrelated']['preserve'] = False
    parent = nonspill(current['_id_background'])
    SCOPE.restore(current, before)
    assert current['_id_background']['spill'] == before['_id_background']['spill']
    assert nonspill(current['_id_background']) == parent
    assert current['_unrelated']['preserve'] is False
    current['_id_background']['spill']['coverage']['mask']['recipe']['objects'][0]['points'][0][0] = .8
    assert before['_id_background']['spill']['coverage']['mask']['recipe']['objects'][0]['points'][0][0] == .6


def test_restore_legacy_shape_removes_only_nested_spill_and_version_upgrade():
    before = target()
    current = deepcopy(before)
    SCOPE.install(current, {'enabled': True, 'strength': 60.})
    SCOPE.restore(current, before)
    assert current == before
    assert current['_id_background']['version'] == 1
    assert 'spill' not in current['_id_background']


def test_restore_dormant_enabled_intent_is_not_a_fresh_transfer_enable():
    before = target(spill=True, enabled=True)
    before['_id_background']['enabled'] = False
    current = deepcopy(before)
    SCOPE.install(current, {'enabled': False, 'strength': 40.})
    SCOPE.restore(current, before)
    assert current == before and not I.active(current['_id_background'])


def test_history_cannot_copy_another_targets_spill_even_without_manual_vectors():
    current = target(SOURCE, spill=True, enabled=True, covered=False)
    before = deepcopy(current)
    with pytest.raises(ValueError):
        SCOPE.restore(current, target(OTHER, spill=True, covered=False))
    assert current == before


def test_shared_scope_admits_only_scalar_derived_path_not_full_id_transfer():
    from lumaretouch_engine import scope as SC
    assert SCOPE.OP in SC.DERIVED_PARAMETER_OPS
    assert SCOPE.ID.OP not in SC.DERIVED_PARAMETER_OPS
    modules = {SCOPE.OP: {'enabled': True, 'strength': 61.}}
    assert SC.check_derived_modules(modules) == modules
    with pytest.raises(SC.ScopeError):
        SC.check_derived_modules({SCOPE.ID.OP: SCOPE.ID.params_of(target())})


@pytest.mark.parametrize('reverse', [False, True])
def test_full_id_and_spill_scope_cannot_have_order_dependent_scalar_ownership(reverse):
    from lumaretouch_engine import scope as SC
    ops = [SCOPE.ID.OP, SCOPE.OP]
    if reverse:
        ops.reverse()
    with pytest.raises(SC.ScopeError):
        SC.check_scope(ops)


def test_shared_candidate_and_history_roundtrip_legacy_without_source_transfer():
    from lumaretouch_engine import scope as SC
    from lumaretouch_engine import optics_auto_scope as OA
    before = target(OTHER)
    modules = {SCOPE.OP: {'enabled': True, 'strength': 61.}}
    candidate = SC.apply_modules(before, modules)
    assert before['_id_background']['version'] == 1
    assert candidate['_id_background']['version'] == 2
    assert candidate['_id_background']['source'] == OTHER
    assert OA.before_params(candidate, [SCOPE.OP]) == {
        SCOPE.OP: {'target_recipe_key': SCOPE.undo_key(candidate)}}
    assert SC.restore_modules(candidate, before, [SCOPE.OP]) == before
