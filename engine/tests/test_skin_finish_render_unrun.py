"""AUTHORED / UNRUN: ordered skin-finish source consumers and ownership ports.

These synthetic arrays/meshes and named native doubles test composition and
dispatch, not Rust execution, inference, portrait quality or real-user consent.
No imports, test collection, tests, inference or builds ran while authoring.
The existing skin-colour fixtures remain unchanged as regression contracts.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest

from test_skin_colour_body_render_unrun import fixture, BUDGET, ACTIVE as COLOUR_RECIPE
from lumaretouch_engine import skin_colour_people as COMPOSE
from lumaretouch_engine import skin_colour_state as COLOUR, skin_finish_state as FINISH
from lumaretouch_engine import skin_colour_native as COLOUR_NATIVE, skin_finish_native as FINISH_NATIVE
from lumaretouch_engine import skin_colour_body_support as REVIEW, face_scope as FACE
from lumaretouch_engine import people_state as PEOPLE, people_effects as EFFECTS
from lumaretouch_engine import people_snapshot as SNAPSHOT, people_render_runtime as RENDER
from lumaretouch_engine import people_engine_runtime as ENGINE, people_owned_inputs as INPUTS

FINISH_RECIPE = {'version': 1, 'whitening': .6, 'rosiness': .35}


def prepare(values, *, colour=COLOUR_RECIPE, finish=FINISH_RECIPE, **kwargs):
    state, assets, ref, bank, analysis, _, source = values
    return COMPOSE.prepare(ref, analysis, [], source, colour, finish_recipe=finish,
        byte_budget=BUDGET, people_state=state, body_assets=assets,
        finish_body_assets=assets, body_bank=bank, **kwargs)


def colour_double(rgb, coverage, *_controls, **_kwargs):
    """Bounded synthetic pointwise change, not the colour algorithm."""
    assert not rgb.flags.writeable and not coverage.flags.writeable
    return rgb + (np.float32(1)-rgb)*coverage[..., None]*np.float32(.25)


def finish_double(rgb, coverage, *_controls, **_kwargs):
    """Nonlinear double distinguishes sequencing from summed original deltas."""
    assert not rgb.flags.writeable and not coverage.flags.writeable
    return rgb + (np.float32(1)-rgb)**2*coverage[..., None]*np.float32(.4)


def render(record, source):
    result = source.copy(); y,x,h,w = record.window
    result[y:y+h,x:x+w] += record.delta
    return result


def test_both_neutral_need_no_source_support_or_native_core():
    with patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(FINISH_NATIVE, 'apply') as finish, \
            patch.object(REVIEW, 'raster') as raster:
        assert COMPOSE.prepare(None, None, None, None, COLOUR.neutral(),
            finish_recipe=FINISH.neutral(), byte_budget=0,
            people_state={'invalid': True}, body_assets={'stale': True},
            finish_body_assets={'stale': True}) == []
    colour.assert_not_called(); finish.assert_not_called(); raster.assert_not_called()


def test_colour_only_preserves_legacy_delta_window_facts_and_dormant_finish_bypass():
    values = fixture(retained=False)
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=AssertionError('Dormant finish core')) as finish:
        state, assets, ref, bank, analysis, _, source = values
        old_api = COMPOSE.prepare(ref, analysis, [], source, COLOUR_RECIPE,
            byte_budget=BUDGET, people_state=state, body_assets=assets, body_bank=bank)[0]
        new_api = COMPOSE.prepare(ref, analysis, [], source, COLOUR_RECIPE,
            byte_budget=BUDGET, people_state=state, body_assets=assets, body_bank=bank,
            finish_recipe=FINISH.neutral(), finish_body_assets={'stale': True})[0]
    assert old_api.window == new_api.window and old_api.facts == new_api.facts
    np.testing.assert_array_equal(old_api.delta, new_api.delta)
    finish.assert_not_called()


def test_finish_only_needs_no_colour_native_or_colour_support():
    values = fixture(retained=False); state, assets, ref, bank, analysis, _, source = values
    original_raster = REVIEW.raster; families = []
    def raster(*args, **kwargs):
        families.append(kwargs['family'])
        assert kwargs['family'] == 'skin_finish'
        return original_raster(*args, **kwargs)
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=RuntimeError('Missing colour ABI')) as colour, \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double) as finish, \
            patch.object(REVIEW, 'raster', side_effect=raster):
        records = COMPOSE.prepare(ref, analysis, [], source, COLOUR.neutral(),
            finish_recipe=FINISH_RECIPE, byte_budget=BUDGET, people_state=state,
            body_assets={'unusable dormant colour support': True},
            finish_body_assets=assets, body_bank=bank)
    colour.assert_not_called(); assert finish.call_count == 1 and families == ['skin_finish']
    assert len(records) == 1 and records[0].stage == 'skin_colour'
    assert records[0].facts['operation_order'] == [FINISH.OP]
    assert records[0].facts['skin_finish']['recipe'] == FINISH_RECIPE


def test_colour_then_finish_publishes_one_nonadditive_delta_and_immutable_inputs():
    values = fixture(retained=False); source = values[-1]; analysis = values[4]
    before = source.copy(); face_before = analysis['face_skin'].copy(); calls = []
    selected = FACE.selected_face_skin
    def colour(rgb, coverage, *controls):
        calls.append(('colour', rgb.copy(), coverage.copy(), controls))
        return colour_double(rgb, coverage, *controls)
    def finish(rgb, coverage, *controls):
        calls.append(('finish', rgb.copy(), coverage.copy(), controls))
        return finish_double(rgb, coverage, *controls)
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish), \
            patch.object(FACE, 'selected_face_skin', wraps=selected) as anatomy:
        records = prepare(values)
    assert len(records) == 1 and anatomy.call_count == 1
    assert [row[0] for row in calls] == ['colour', 'finish']
    original, coverage = calls[0][1:3]
    first = original + (1-original)*coverage[..., None]*np.float32(.25)
    expected = first + (1-first)**2*calls[1][2][..., None]*np.float32(.4)
    np.testing.assert_array_equal(calls[1][1], first)
    np.testing.assert_array_equal(records[0].delta, expected-original)
    incorrect_additive = first-original + (1-original)**2*calls[1][2][..., None]*np.float32(.4)
    assert np.any(np.abs(records[0].delta-incorrect_additive) > 1e-5)
    assert not records[0].delta.flags.writeable
    assert records[0].facts['operation_order'] == [COLOUR.OP, FINISH.OP]
    np.testing.assert_array_equal(source, before)
    np.testing.assert_array_equal(analysis['face_skin'], face_before)


def test_operation_specific_body_reviews_do_not_widen_each_other():
    values = list(fixture(retained=False)); state, assets, ref, bank, analysis, review, source = values
    review = deepcopy(review); review['recipe']['objects'][0]['id'] = 'colour-body'
    state, assets = REVIEW.retain(state, assets, ref, bank, analysis, review)
    finish_review = deepcopy(review); finish_review['recipe']['objects'][0]['id'] = 'finish-body'
    state, assets = REVIEW.retain(state, assets, ref, bank, analysis, finish_review, family='skin_finish')
    values[0:2] = [state, assets]
    def manual(recipe, shape):
        coverage = np.zeros(shape, np.uint8)
        if recipe['objects'][0]['id'] == 'colour-body': coverage[80:112, 20:48] = 255
        else: coverage[80:112, 80:108] = 255
        return coverage
    observed = []
    def colour(rgb, coverage, *controls):
        observed.append(coverage.copy()); return colour_double(rgb, coverage, *controls)
    def finish(rgb, coverage, *controls):
        observed.append(coverage.copy()); return finish_double(rgb, coverage, *controls)
    with patch.object(REVIEW.M, 'raster', side_effect=manual), \
            patch.object(COLOUR_NATIVE, 'apply', side_effect=colour), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish):
        records = prepare(values)
    assert len(records) == 1 and len(observed) == 2
    y,x,h,w = records[0].window
    full = [np.zeros(source.shape[:2], np.float32) for _ in observed]
    for coverage, roi in zip(full, observed): coverage[y:y+h,x:x+w] = roi
    assert full[0][96,32] > 0 and full[1][96,32] == 0
    assert full[1][96,96] > 0 and full[0][96,96] == 0
    assert records[0].facts['skin_colour']['body_extension']['enabled']
    assert records[0].facts['skin_finish']['body_extension']['enabled']


def test_stale_finish_review_refuses_before_either_native_solver():
    values = fixture(retained=False)
    original_raster = REVIEW.raster
    def raster(*args, **kwargs):
        if kwargs['family'] == 'skin_finish': raise ValueError('Synthetic stale finish review')
        return original_raster(*args, **kwargs)
    with patch.object(REVIEW, 'raster', side_effect=raster), \
            patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(FINISH_NATIVE, 'apply') as finish:
        with pytest.raises(ValueError, match='stale finish review'): prepare(values)
    colour.assert_not_called(); finish.assert_not_called()


@pytest.mark.parametrize('failure', [RuntimeError('Missing finish ABI'), InterruptedError('Cancelled')])
def test_second_solver_failure_never_publishes_a_partial_record(failure):
    values = fixture(retained=False); before = values[-1].copy()
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=failure):
        with pytest.raises(type(failure)): prepare(values)
    np.testing.assert_array_equal(values[-1], before)


def test_cancellation_after_colour_never_calls_finish_or_publishes():
    values = fixture(retained=False); cancelled = [False]
    def colour(rgb, coverage, *controls, **kwargs):
        result = colour_double(rgb, coverage, *controls); cancelled[0] = True
        return result
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour), \
            patch.object(FINISH_NATIVE, 'apply') as finish:
        with pytest.raises(InterruptedError): prepare(values, cancelled=lambda: cancelled[0])
    finish.assert_not_called()


@pytest.mark.parametrize('change', [
    lambda rgb: np.concatenate([rgb, np.ones((*rgb.shape[:2],1), np.float32)], axis=2),
    lambda rgb: rgb+np.float32(1),
    lambda rgb: np.full_like(rgb, np.nan),
])
def test_alpha_hdr_and_nonfinite_sources_are_refused_without_native_calls(change):
    values = list(fixture(retained=False)); values[-1] = change(values[-1])
    with patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(FINISH_NATIVE, 'apply') as finish:
        with pytest.raises(ValueError): prepare(values)
    colour.assert_not_called(); finish.assert_not_called()


def test_finish_extra_budget_is_admitted_before_anatomy_or_raster():
    state, assets, ref, bank, analysis, _, source = fixture(retained=False)
    h,w = source.shape[:2]
    with patch.object(FACE, 'selected_face_skin') as anatomy, patch.object(REVIEW, 'raster') as raster, \
            patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(FINISH_NATIVE, 'apply') as finish:
        with pytest.raises(ValueError, match='memory budget'):
            COMPOSE.prepare(ref, analysis, [], source, COLOUR_RECIPE, finish_recipe=FINISH_RECIPE,
                byte_budget=h*w*256+128*1024*1024, people_state=state,
                body_assets=assets, finish_body_assets=assets, body_bank=bank)
    anatomy.assert_not_called(); raster.assert_not_called(); colour.assert_not_called(); finish.assert_not_called()


def test_runtime_prepares_once_and_final_export_matches_owned_derived_pixels():
    state, assets, ref, _, analysis, _, source = fixture(retained=False)
    # Derived-local fixture has no person/group inheritance or body extension.
    state['links'] = []; state['persons'] = {}
    key = ref['face_instance_id']
    state = PEOPLE.set_override(state, 'face', key, COLOUR.OP, '/temperature', COLOUR_RECIPE['temperature'])
    state = PEOPLE.set_override(state, 'face', key, FINISH.OP, '/whitening', FINISH_RECIPE['whitening'])
    snapshot = SNAPSHOT.capture(state, ref['asset_sha256'], {key: analysis})
    snapshot.update(document_id='finish-document', support_assets=assets)
    # Full-bit-depth values deliberately not on the 8-bit display-proxy grid.
    original = np.full(source.shape, 12345, np.uint16)
    working = original.astype(np.float32)/65535
    derived = {**snapshot, 'creative_source': {'sha256': ref['asset_sha256'],
        'width': source.shape[1], 'height': source.shape[0]}}
    field = SimpleNamespace(fields=(None,None,None,None), resident_bytes=lambda:0)
    geometry = SimpleNamespace(delta=np.zeros((1,*source.shape[:2],2),np.float32),
                               owner=np.zeros(source.shape[:2],np.int32))
    compositor = COMPOSE.prepare; received = []
    def compose(*args, **kwargs):
        received.append(args[3].copy())
        assert kwargs['finish_recipe']['whitening'] == FINISH_RECIPE['whitening']
        assert kwargs['body_assets'] is assets and kwargs['finish_body_assets'] is assets
        return compositor(*args, **kwargs)
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(RENDER.A, 'build_geometry', return_value=field), \
            patch.object(RENDER.E, 'prepare', return_value=[]), \
            patch.object(RENDER, 'combine', return_value=geometry) as common, \
            patch.object(COMPOSE, 'prepare', side_effect=compose) as once, \
            patch('lumaretouch_engine.eye_light_people.prepare', return_value=[]), \
            patch('lumaretouch_engine.hair_colour_runtime.prepare_bank', return_value=((),{})):
        exported = ENGINE.prepare_export(snapshot, original, None, byte_budget=BUDGET,
                                         document_id='finish-document')
        derived_export = ENGINE.prepare_export(derived, working, None, byte_budget=BUDGET,
                                               document_id='finish-document')
    assert once.call_count == common.call_count == 2
    assert len(exported.effects) == len(derived_export.effects) == 1
    np.testing.assert_array_equal(received[0], working)
    np.testing.assert_array_equal(received[1], working)
    np.testing.assert_array_equal(exported.effects[0].delta, derived_export.effects[0].delta)


def test_existing_source_stage_has_no_second_warp_and_accepts_one_combined_delta():
    values = fixture(retained=False); source = values[-1]
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double):
        records = prepare(values)
    output, facts = EFFECTS.apply('skin_colour', source, records)
    np.testing.assert_array_equal(output, render(records[0], source))
    assert facts['overlap_pixels'] == 0 and len(records) == 1


def test_owned_original_preview_forwards_both_explicit_support_ports():
    state, assets, ref, bank, _, _, _ = fixture(retained=False)
    engine = SimpleNamespace(_creative_base=None, _people_support=assets,
        _people_owner=lambda:SimpleNamespace(snapshot=lambda:deepcopy(state)),
        _people_binding=lambda:{'document_id':'finish-document'},
        _people_source=lambda:{'sha256':ref['asset_sha256']}, _body_bank=lambda:bank,
        _doc_path='original-owned-source.tif')
    with patch('lumaretouch_engine.creative_derived_source.record', return_value=None), \
            patch('lumaretouch_engine.hair_colour_project.preview_kwargs', return_value={}):
        ports = INPUTS.preview(engine, state)
    assert ports['skin_colour_body_assets'] is assets and ports['skin_finish_body_assets'] is assets
    assert ports['body_bank'] is bank and ports['body_source_path'] == engine._doc_path
