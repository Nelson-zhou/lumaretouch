"""AUTHORED / UNRUN: ID v1/v2 state and ownership contracts, no quality claim.

Source-only authoring: these fixtures were not imported, collected or executed.
They do not invoke the numerical spill kernel, model inference or a raster worker.
"""
from copy import deepcopy
from hashlib import sha256
import json
import pytest
from lumaretouch_engine import id_background_state as I
from lumaretouch_engine import id_background_scope as SCOPE
from lumaretouch_engine import id_background_project as PROJECT
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import spill_removal_state as S
from lumaretouch_engine import spill_removal_coverage as C

SOURCE = {'sha256': 'a' * 64, 'width': 32, 'height': 24}
OTHER = {'sha256': 'b' * 64, 'width': 40, 'height': 30}


def vector(identity='manual', operation='add', x=.5):
    return {'id': identity, 'name': 'Manual spill coverage', 'enabled': True,
            'kind': 'brush', 'operation': operation, 'opacity': 1., 'feather': 0.,
            'points': [[x, .5]], 'axes': [[.1, 0.], [0., .1]]}


def coverage(source=SOURCE, objects=None):
    mask = M.empty()
    mask['source'] = deepcopy(source)
    mask['recipe']['objects'] = [vector()] if objects is None else deepcopy(objects)
    return {'version': 1, 'reviewed': True, 'mask': mask,
            'recipe_sha256': C.digest(mask)}


def recipe(source=SOURCE, *, covered=True, enabled=True):
    value = I.empty()
    value['source'] = deepcopy(source)
    spill = S.neutral()
    spill.update(enabled=enabled, coverage=coverage(source) if covered else None)
    return I.with_spill(value, spill)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def test_v1_validation_and_neutral_accessor_do_not_rewrite_old_context_hashes():
    old = I.empty()
    old['source'] = deepcopy(SOURCE)
    before = deepcopy(old)
    old_hash = digest(old)
    assert old['version'] == 1 and 'spill' not in old
    assert I.check(old) == before and digest(I.check(old)) == old_hash
    assert I.spill_of(old) == S.neutral()
    assert old == before and I.portable(old)['version'] == 1
    assert 'spill' not in I.portable(old)


def test_only_explicit_spill_edit_upgrades_id_recipe():
    old = I.empty()
    upgraded = I.with_spill(old, S.neutral())
    assert upgraded['version'] == 2 and upgraded['spill'] == S.neutral()
    assert old == I.empty() and 'spill' not in old
    assert I.check(upgraded) == upgraded


@pytest.mark.parametrize('change', [
    lambda value: value.update(spill=None),
    lambda value: value.pop('spill'),
    lambda value: value.update(version=True),
    lambda value: value.update(version=3),
    lambda value: value.update(unreviewed_coverage={}),
])
def test_id_v2_rejects_missing_null_unknown_or_unsupported_fields(change):
    value = recipe()
    change(value)
    with pytest.raises(ValueError):
        I.check(value)


def test_v1_cannot_smuggle_spill_under_legacy_version():
    value = I.empty()
    value['spill'] = S.neutral()
    with pytest.raises(ValueError):
        I.check(value)


@pytest.mark.parametrize('key,value', [
    ('version', True), ('version', 2), ('algorithm', 'another-estimator'),
    ('enabled', 1), ('strength', float('nan')), ('strength', float('inf')),
    ('strength', -1), ('strength', 101), ('strength', True),
])
def test_strict_versioned_spill_parameters(key, value):
    raw = S.neutral()
    raw[key] = value
    with pytest.raises(ValueError):
        S.check(raw)


def test_spill_active_has_exact_disabled_and_zero_endpoints():
    value = S.neutral()
    assert not S.active(value)
    value.update(enabled=True, strength=0.)
    assert not S.active(value)
    value['strength'] = .01
    assert S.active(value)
    # The ID parent's disabled state remains authoritative for rendering.
    assert not I.active(recipe())


def test_manual_coverage_is_separate_from_foreground_support():
    value = recipe()
    assert all(item is None for item in value['support'].values())
    assert value['spill']['coverage']['mask']['source'] == value['source']
    value['enabled'] = True
    with pytest.raises(ValueError):
        I.check(value)  # A spill brush cannot stand in for subject review.


def test_disabled_manual_coverage_retains_exact_source_ownership():
    value = recipe(enabled=False)
    value['source'] = deepcopy(OTHER)
    with pytest.raises(ValueError):
        I.check(value)
    value['source'] = None
    with pytest.raises(ValueError):
        I.check(value)


def test_manual_review_rejects_forgery_or_content_change():
    value = coverage()
    value['reviewed'] = False
    with pytest.raises(ValueError):
        C.check_binding(value)
    value = coverage()
    value['mask']['recipe']['objects'][0]['points'][0][0] = .6
    with pytest.raises(ValueError):
        C.check_binding(value)
    value = coverage()
    value['recipe_sha256'] = 'x' * 64
    with pytest.raises(ValueError):
        C.check_binding(value)


@pytest.mark.parametrize('obj', [
    {'id': 'full', 'name': 'Full', 'enabled': True, 'operation': 'add',
     'kind': 'full', 'opacity': 1., 'feather': 0.},
    {'id': 'semantic', 'name': 'Semantic', 'enabled': False, 'operation': 'add',
     'kind': 'semantic', 'channel': 'skin', 'opacity': 1., 'feather': 0.},
    {'id': 'color', 'name': 'Colour', 'enabled': True, 'operation': 'add',
     'kind': 'color_range', 'color': [.2, .3, .4], 'tolerance': .1,
     'invert': False, 'opacity': 1., 'feather': 0.},
    {'id': 'luminance', 'name': 'Luminance', 'enabled': True, 'operation': 'add',
     'kind': 'luminance_range', 'low': .2, 'high': .8, 'opacity': 1., 'feather': 0.},
])
def test_manual_coverage_rejects_non_geometric_operands_even_disabled(obj):
    with pytest.raises(ValueError):
        C.check_binding(coverage(objects=[obj]))


def test_manual_review_is_owned_deep_copy_and_preserves_operation_order():
    raw = coverage(objects=[vector('a'), vector('b', 'subtract', .6),
                            vector('c', 'intersect', .4)])
    checked = C.check_binding(raw)
    assert [obj['operation'] for obj in checked['mask']['recipe']['objects']] == ['add', 'subtract', 'intersect']
    raw['mask']['recipe']['objects'][0]['points'][0][0] = .9
    assert checked['mask']['recipe']['objects'][0]['points'][0][0] == .5


def test_manual_coverage_rejects_empty_and_oversized_source_grid():
    with pytest.raises(ValueError):
        C.check_binding(coverage(objects=[]))
    huge = {**SOURCE, 'width': 65537}
    with pytest.raises(ValueError):
        C.check_binding(coverage(huge))


def test_v2_portable_never_contains_coverage_source_or_algorithm_fields():
    value = recipe()
    portable = I.portable(value)
    assert portable['version'] == 2
    assert portable['spill'] == {'enabled': True, 'strength': 50.}
    assert 'source' not in portable and 'support' not in portable
    for key, extra in (('coverage', value['spill']['coverage']), ('source', SOURCE),
                       ('algorithm', S.ALGORITHM), ('version', 1)):
        forged = deepcopy(portable)
        forged['spill'][key] = extra
        with pytest.raises(ValueError):
            I.check_portable(forged)


def test_portable_parameters_keep_target_coverage_and_not_source_mask():
    origin = recipe()
    origin['spill']['strength'] = 77.
    target = recipe(OTHER, enabled=False)
    expected = deepcopy(target['spill']['coverage'])
    applied = I.apply_portable(target, I.portable(origin))
    assert applied['source'] == OTHER
    assert applied['spill']['coverage'] == expected
    assert applied['spill']['coverage'] != origin['spill']['coverage']
    assert applied['spill']['enabled'] and applied['spill']['strength'] == 77.
    assert target['spill']['enabled'] is False


def test_portable_to_uncovered_target_does_not_copy_source_coverage():
    target = I.empty()
    target['source'] = deepcopy(OTHER)
    applied = I.apply_portable(target, I.portable(recipe()))
    assert applied['version'] == 2 and applied['spill']['coverage'] is None
    assert applied['source'] == OTHER


def test_legacy_preset_disables_spill_without_erasing_target_vectors():
    target = recipe()
    applied = I.apply_portable(target, I.portable(I.empty()))
    assert applied['version'] == 2
    assert applied['spill']['enabled'] is False
    assert applied['spill']['coverage'] == target['spill']['coverage']
    assert I.apply_portable(I.empty(), I.portable(I.empty())) == I.empty()


def test_clear_background_preserves_disabled_spill_intent_and_source():
    target = recipe()
    cleared = I.clear_choice(target)
    assert not cleared['enabled'] and cleared['background']['kind'] == 'none'
    assert cleared['spill'] == target['spill'] and cleared['source'] == SOURCE


def test_scoped_history_identity_includes_manual_coverage_and_restores_exactly():
    original = {'_id_background': recipe(), '_id_background_bundle': None}
    edited = deepcopy(original)
    edited['_id_background']['spill']['coverage'] = coverage(objects=[vector(x=.6)])
    assert SCOPE.undo_key(original) != SCOPE.undo_key(edited)
    SCOPE.restore(edited, original)
    assert edited == original


def test_nested_project_history_checks_dormant_spill_ownership():
    old = {'_id_background': I.empty()}
    valid = {'history': [{'before': deepcopy(old), 'after': {'_id_background': recipe()}}]}
    PROJECT.validate_records(valid)
    assert valid['history'][0]['before'] == old
    bad = deepcopy(valid)
    dormant = bad['history'][0]['after']['_id_background']
    dormant['spill']['enabled'] = False
    dormant['spill']['coverage'] = coverage(OTHER)
    with pytest.raises(ValueError):
        PROJECT.validate_records(bad)
