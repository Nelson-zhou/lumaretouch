"""AUTHORED / UNRUN: retained state, scoped history and project contracts.

No product import, test execution, native build, inference, download or visual
acceptance was performed while authoring these fixtures. They require the
project's normal test environment before any passing claim can be made.
"""
from copy import deepcopy
import pytest

from lumaretouch_engine import fringe_repair_state as S
from lumaretouch_engine import fringe_repair_scope as F
from lumaretouch_engine import fringe_repair_project as P


def stroke(identity='one'):
    return {'id': identity, 'mode': 'subtract', 'points': [[0.4, 0.5], [0.6, 0.5]],
            'axes': [[0.03, 0.0], [0.0, 0.02]], 'opacity': 0.75, 'feather': 0.25}


def manual():
    value = S.neutral()
    value.update(enabled=True, source={'sha256': 'a' * 64, 'width': 800, 'height': 600})
    value['coverage']['strokes'] = [stroke()]
    return value


def test_old_documents_are_disabled_not_strength_fifty_autoapplied():
    assert S.from_state({}) == S.neutral()
    assert S.neutral()['strength'] == 50.0
    assert not S.active(S.neutral())
    active = S.neutral(); active['enabled'] = True
    assert S.active(active)
    active['strength'] = 0
    assert not S.active(active)
    with pytest.raises(ValueError):
        S.from_state({S.KEY: None})


@pytest.mark.parametrize('change', [
    {'enabled': 1}, {'strength': True}, {'strength': float('nan')},
    {'strength': float('inf')}, {'strength': -1}, {'strength': 101},
    {'version': True}, {'version': 2}, {'algorithm': 'another-algorithm'},
    {'raster': [[1.0]]}, {'cache': 'not-retained'},
])
def test_invalid_recipes_never_silently_become_neutral(change):
    value = S.neutral(); value.update(change)
    with pytest.raises(ValueError): S.check(value)


def test_source_is_mandatory_exactly_for_manual_coverage():
    value = manual(); value['source'] = None
    with pytest.raises(ValueError): S.check(value)
    value = manual(); value['coverage']['strokes'] = []
    with pytest.raises(ValueError): S.check(value)
    value = manual(); value['source']['sha256'] = 'A' * 64
    with pytest.raises(ValueError): S.check(value)
    value = manual(); value['source']['width'] = True
    with pytest.raises(ValueError): S.check(value)


@pytest.mark.parametrize('axes', [
    [[0.0, 0.0], [0.0, 0.1]], [[0.1, 0.0], [0.2, 0.0]],
    [[0.1, float('nan')], [0.0, 0.1]], [[3.0, 0.0], [0.0, 0.1]],
])
def test_singular_nonfinite_and_unbounded_ellipses_reject(axes):
    value = stroke(); value['axes'] = axes
    with pytest.raises(ValueError): S.check_stroke(value)


def test_recipe_owns_independent_copies_of_all_manual_vectors():
    original = manual(); result = S.check(original)
    result['source']['width'] = 123
    result['coverage']['strokes'][0]['points'][0][0] = 0.1
    result['coverage']['strokes'][0]['axes'][0][0] = 0.1
    assert original == manual()


def test_both_per_stroke_and_aggregate_budgets_are_enforced():
    value = manual()
    value['coverage']['strokes'][0]['points'] = [[0.5, 0.5]] * (S.MAX_STROKE_POINTS + 1)
    with pytest.raises(ValueError): S.check(value)
    value = manual()
    value['coverage']['strokes'] = [stroke(str(index)) for index in range(S.MAX_STROKES + 1)]
    with pytest.raises(ValueError): S.check(value)
    value = manual()
    value['coverage']['strokes'] = [stroke(str(index)) for index in range(9)]
    for item in value['coverage']['strokes']:
        item['points'] = [[0.5, 0.5]] * S.MAX_STROKE_POINTS
    with pytest.raises(ValueError): S.check(value)


def test_duplicate_ids_and_foreign_domain_reject():
    value = manual(); value['coverage']['strokes'].append(stroke())
    with pytest.raises(ValueError): S.check(value)
    value = manual(); value['coverage']['domain'] = 'display-proxy'
    with pytest.raises(ValueError): S.check(value)


def test_transfer_contains_only_parameters_and_resets_target_coverage():
    source = {S.KEY: manual()}
    params = F.params_of(source)
    assert params == {'enabled': True, 'strength': 50.0}
    target = {S.KEY: manual(), 'unrelated': object()}
    retained = target['unrelated']
    F.install(target, params)
    assert target[S.KEY]['source'] is None
    assert target[S.KEY]['coverage']['strokes'] == []
    assert target['unrelated'] is retained
    assert source[S.KEY] == manual()
    with pytest.raises(ValueError): F.check_params({**params, 'source': source[S.KEY]['source']})
    with pytest.raises(ValueError): F.check_params({'recipe': source[S.KEY]})


def test_scoped_undo_restores_full_previous_coverage_not_transfer_parameters():
    from lumaretouch_engine import scope as SC
    before = {S.KEY: manual(), 'unrelated': 'earlier'}
    transferred = SC.apply_modules(before, {F.OP: {'enabled': True, 'strength': 80.0}})
    assert transferred[S.KEY]['source'] is None
    transferred['unrelated'] = 'later unrelated edit'
    restored = SC.restore_modules(transferred, before, [F.OP])
    assert restored[S.KEY] == before[S.KEY]
    assert restored['unrelated'] == 'later unrelated edit'
    assert restored[S.KEY] is not before[S.KEY]


def test_later_brush_changes_conflict_even_when_parameters_are_identical():
    from lumaretouch_engine import optics_auto_scope as OA
    before = {S.KEY: manual()}; later = deepcopy(before)
    later[S.KEY]['coverage']['strokes'][0]['opacity'] = 0.25
    assert F.params_of(before) == F.params_of(later)
    assert OA.before_params(before, [F.OP]) != OA.before_params(later, [F.OP])


def test_disabled_migration_preserves_all_nested_previous_coverage():
    old = {'state': {'_strength': 0.0},
           'undo': [{'_grade': [0.0, 0.0, 0.0, 1.0], S.KEY: manual()}],
           'redo': [{'_exposure': [0.0] * 7}]}
    P.migrate_states(old)
    assert old['state'][S.KEY] == S.neutral()
    assert old['redo'][0][S.KEY] == S.neutral()
    assert old['undo'][0][S.KEY] == manual()
    frozen = deepcopy(old); P.migrate_states(old)
    assert old == frozen


def test_invalid_nested_history_and_old_schema_payload_fail_closed():
    value = {'undo': [{'snapshot': {S.KEY: None}}]}
    with pytest.raises(ValueError): P.validate_records(value)
    with pytest.raises(ValueError): P.validate_records({S.KEY: manual()}, allowed=False)
    P.validate_records({'undo': [{S.KEY: manual()}]})


def test_source_verifier_uses_the_effective_immutable_binding(monkeypatch):
    from lumaretouch_engine import creative_derived_source as D
    recipe = manual(); owner = object(); observed = []
    def binding(value, path, size):
        observed.append((value, path, size))
        return dict(recipe['source'])
    monkeypatch.setattr(D, 'binding', binding)
    assert S.verify_source(recipe, owner, 'original.jpg', (800, 600)) == recipe['source']
    assert observed == [(owner, 'original.jpg', (800, 600))]
    monkeypatch.setattr(D, 'binding', lambda *args: {**recipe['source'], 'sha256': 'b' * 64})
    with pytest.raises(ValueError): S.verify_source(recipe, owner, 'original.jpg', (800, 600))


def test_project_codec_rejects_before_asset_or_dropped_list_mutation():
    from lumaretouch_engine import project
    assets = {}; dropped = []
    with pytest.raises(project.ProjectError):
        project.encode({'blob': b'not-published', 'undo': [{S.KEY: None}]}, assets, dropped, 'state')
    assert assets == {} and dropped == []
    with pytest.raises(project.ProjectError):
        project.decode({'redo': [{S.KEY: None}]}, {}, dropped, 'state')
    assert dropped == []


def test_v23_codec_roundtrip_retains_full_strokes_and_has_no_raster_assets():
    from lumaretouch_engine import project
    value = {'state': {S.KEY: manual()}, 'undo': [{S.KEY: S.neutral()}]}
    assets = {}; dropped = []
    encoded = project.encode(value, assets, dropped, 'document')
    assert project.decode(encoded, assets, dropped, 'document') == value
    assert assets == {} and dropped == []
    migrated = project._migrate({'schema_version': project.SCHEMA,
                                 'docs': [{'versions': [{'recipe': {}}]}]})
    assert migrated['schema_version'] == 'lrt.project.v23'
    assert migrated['docs'][0]['versions'][0]['recipe'][S.KEY] == S.neutral()


def test_derived_history_has_separate_exact_restoration_not_portable_coverage(monkeypatch):
    from lumaretouch_engine import creative_derived_transfer as T
    from lumaretouch_engine import scope as SC
    # Isolate the history comparison from native image-asset admission. Actual
    # source/pixel verification remains the batch owner's separate prerequisite.
    monkeypatch.setattr(T, '_context', lambda *args: (True, []))
    monkeypatch.setattr(T, '_photo_sources', lambda values: None)
    previous = {S.KEY: manual(), 'other': 'unchanged'}
    current = SC.apply_modules(previous, {F.OP: {'enabled': True, 'strength': 80}})
    restored = SC.restore_modules(current, previous, [F.OP])
    assert T.require_restoration(current, previous, restored, [F.OP], {}) == restored
    with pytest.raises(SC.ScopeError):
        T.require_candidate(current, restored, {F.OP: F.params_of(previous)})
    tampered = {**restored, 'other': 'changed without authorization'}
    with pytest.raises(SC.ScopeError): T.require_restoration(current, previous, tampered, [F.OP], {})
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({SC.OP_SKIN: {'enabled': False, 'strength': 0.0}})
    with pytest.raises(SC.ScopeError): T.require_restoration(current, previous, restored, [SC.OP_SKIN], {})
