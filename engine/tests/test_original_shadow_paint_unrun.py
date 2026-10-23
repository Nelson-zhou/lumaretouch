"""AUTHORED / UNRUN: direct shadow vectors, ownership and reviewed reset.

No import, collection, execution, raster worker, numerical or photo acceptance
was performed while authoring these fixtures. Doubles only test routing intent.
"""
from copy import deepcopy
import pytest
from lumaretouch_engine import original_shadow_paint_vectors as V
from lumaretouch_engine import original_shadow_paint_source as P
from lumaretouch_engine import original_shadow_state as S
from lumaretouch_engine import original_shadow_review as REVIEW
from lumaretouch_engine import original_shadow_controller as CONTROL
from lumaretouch_engine import id_background_state as ID
from test_original_shadow_review_unrun import target, preview_request, apply_request

SOURCE = {'sha256': 'a' * 64, 'width': 80, 'height': 40}


def stroke(ident='lit-stroke', mode='restore', **changes):
    return {'id': ident, 'mode': mode, 'points': [[.2, .3], [.3, .4]],
            'radius': .1, 'opacity': .5, 'feather': 0., **changes}


def test_empty_role_starts_zero_without_automatic_full_coverage():
    raw = [stroke(), stroke('erase', 'erase')]
    prior = deepcopy(raw)
    result = V.append(None, SOURCE, raw, 'lit_floor')
    objects = result['mask']['recipe']['objects']
    assert [obj['kind'] for obj in objects] == ['brush', 'brush']
    assert [obj['operation'] for obj in objects] == ['add', 'subtract']
    assert objects[0]['axes'] == [[.05, 0.], [0., .1]]
    assert result['recipe_sha256'] == S.digest(result['mask'])
    assert raw == prior


def test_append_preserves_retained_objects_and_source():
    old = V.append(None, SOURCE, [stroke()], 'lit_floor')
    prior = deepcopy(old)
    new = V.append(old, SOURCE, [stroke('new')], 'lit_floor')
    assert new['mask']['recipe']['objects'][0] == old['mask']['recipe']['objects'][0]
    assert old == prior
    with pytest.raises(ValueError):
        V.append(old, {**SOURCE, 'sha256': 'b' * 64}, [stroke('new')], 'lit_floor')


@pytest.mark.parametrize('changes', [{'radius': 0}, {'radius': float('nan')},
    {'points': [[1.01, .5]]}, {'opacity': 2}, {'mode': 'replace'}, {'pixels': [255]}])
def test_invalid_vectors_and_client_rasters_refused(changes):
    with pytest.raises(ValueError):
        V.append(None, SOURCE, [stroke(**changes)], 'retention')


def test_duplicate_ids_and_budget_are_rejected():
    with pytest.raises(ValueError):
        V.append(None, SOURCE, [stroke(), stroke()], 'lit_floor')
    with pytest.raises(ValueError):
        V.append(None, SOURCE, [stroke(str(i)) for i in range(64)], 'lit_floor')
    with pytest.raises(ValueError):
        V.append(None, SOURCE, [stroke(str(i), points=[[.5, .5]] * 1024)
                                for i in range(9)], 'lit_floor')


def test_two_roles_cannot_reuse_object_ids():
    binding = V.append(None, SOURCE, [stroke()], 'lit_floor')
    with pytest.raises(ValueError):
        S.check({**S.neutral(), 'lit_floor': binding, 'retention': binding})


def test_source_owner_is_separate_and_empty_group_keeps_snapshot(monkeypatch):
    class Engine: pass
    engine = Engine()
    assert P.owner(engine) is P.owner(engine)
    assert not hasattr(engine, '_spill_removal_paint_source_owner')
    owner = P.owner(engine)
    saved = V.append(None, SOURCE, [stroke('old')], 'lit_floor')
    record = {'bindings': {'lit_floor': saved, 'retention': None}, 'source': SOURCE}
    monkeypatch.setattr(owner, '_verify', lambda request, token: record)
    result = owner.bindings({}, {'token': 'x', 'lit_strokes': [],
                                'retention_strokes': [stroke('retention')]})
    assert result['lit_floor'] == saved
    assert result['lit_floor'] is not saved
    assert record['bindings']['retention'] is None
    with pytest.raises(ValueError):
        owner.bindings({}, {'token': 'x', 'lit_strokes': [], 'retention_strokes': []})


def test_expired_or_changed_source_token_refused(monkeypatch):
    class Engine: pass
    owner = P.PaintSource(Engine())
    with pytest.raises(ValueError): owner._verify({}, 'missing')
    proof = dict(document_id='d', recipe_document_id='r', recipe_revision='1',
                 source=SOURCE, identity={'candidate': 'a'}, original_stamp=(1,))
    owner.record = {**proof, 'token': 'token', 'expires': float('inf')}
    monkeypatch.setattr(owner, '_proof', lambda request: {**proof, 'recipe_revision': '2'})
    with pytest.raises(ValueError): owner._verify({}, 'token')
    assert owner.record is None


def test_clear_is_neutral_and_still_requires_actual_review_transaction(target):
    engine, control, events, renders = target
    old = REVIEW._proposal(engine, preview_request(engine))
    engine._id_background = old
    request = {**preview_request(engine, 'clear-preview'),
               'parameters': {'enabled': False, 'strength': 100, 'blend': 'normal'},
               'lit_ids': None, 'retention_ids': None, 'samples_reviewed': False,
               'uniform_floor_confirmed': False, 'clear_samples': True}
    control.handle(request)
    assert events[-1]['success'] and len(renders) == 2
    assert engine._id_background == old
    review = events[-1]['shadow_review']
    control.handle(apply_request(request, review, 'clear-apply'))
    assert events[-1]['success']
    assert ID.original_shadow_of(engine._id_background) == S.neutral()


def test_clear_preserves_unrelated_spill_recipe(target):
    engine, _, _, _ = target
    from lumaretouch_engine import spill_removal_state as SPILL
    spill = {**SPILL.neutral(), 'strength': 37.}
    engine._id_background = ID.with_spill(REVIEW._proposal(engine, preview_request(engine)), spill)
    request = {**preview_request(engine), 'parameters': {'enabled': False, 'strength': 100, 'blend': 'normal'},
               'lit_ids': None, 'retention_ids': None, 'samples_reviewed': False,
               'uniform_floor_confirmed': False, 'clear_samples': True}
    proposed = REVIEW._proposal(engine, request)
    assert ID.spill_of(proposed) == spill
    assert ID.original_shadow_of(proposed) == S.neutral()


def test_clear_before_render_failure_cannot_change_recipe_or_history(target, monkeypatch):
    engine, control, events, _ = target
    engine._id_background = REVIEW._proposal(engine, preview_request(engine))
    before = deepcopy(engine._id_background)
    request = {**preview_request(engine), 'parameters': {'enabled': False, 'strength': 100, 'blend': 'normal'},
               'lit_ids': None, 'retention_ids': None, 'samples_reviewed': False,
               'uniform_floor_confirmed': False, 'clear_samples': True}
    def fail(*args): raise ValueError('before source unavailable')
    monkeypatch.setattr(REVIEW, '_view', fail)
    control.handle(request)
    assert events[-1]['success'] is False and events[-1]['outcome_unknown'] is False
    assert engine._id_background == before
    assert REVIEW.owner(engine).review is None


def test_source_combined_receipt_budget_invalidates_token(target, monkeypatch):
    engine, control, events, _ = target
    owner = P.owner(engine)
    def prepare(request):
        owner.record = {'token': 'must-expire'}
        return {'oversized': 'x' * CONTROL.MAX_RESULT_BYTES}
    monkeypatch.setattr(owner, 'prepare', prepare)
    request = {key: value for key, value in preview_request(engine).items() if key in CONTROL.BASE}
    request['action'] = P.ACTION
    control.handle(request)
    assert not events[-1]['success']
    assert 'shadow_paint_source' not in events[-1]
    assert owner.record is None


@pytest.mark.parametrize('patch', [
    {'parameters': {'enabled': True, 'strength': 100, 'blend': 'normal'}},
    {'parameters': {'enabled': False, 'strength': 25, 'blend': 'normal'}},
    {'uniform_floor_confirmed': True}, {'samples_reviewed': True},
    {'lit_ids': ['lit']}, {'paint': None},
])
def test_clear_does_not_silently_discard_other_intents(target, patch):
    engine, _, _, _ = target
    request = {**preview_request(engine), 'parameters': {'enabled': False, 'strength': 100, 'blend': 'normal'},
               'lit_ids': None, 'retention_ids': None, 'samples_reviewed': False,
               'uniform_floor_confirmed': False, 'clear_samples': True, **patch}
    with pytest.raises(ValueError): REVIEW._proposal(engine, request)


def test_exact_source_envelope_and_optional_preview_fields(target):
    engine, _, _, _ = target
    request = {key: value for key, value in preview_request(engine).items() if key in CONTROL.BASE}
    request['action'] = P.ACTION
    CONTROL.envelope(request)
    with pytest.raises(ValueError): CONTROL.envelope({**request, 'image': {}})
    with pytest.raises(ValueError):
        CONTROL.envelope({**preview_request(engine), 'clear_samples': False})
    with pytest.raises(ValueError):
        REVIEW._proposal(engine, {**preview_request(engine), 'clear_samples': False})
