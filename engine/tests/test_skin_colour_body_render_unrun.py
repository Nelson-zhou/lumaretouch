"""AUTHORED / UNRUN: target-owned body/face colour render integration.

Meshes, pose records, image arrays and digests are synthetic contract fixtures,
not measurements or photographic acceptance. Positive coverage cases use the
real support resolver and anatomical selector; only manual-mask/native colour
boundaries are stubbed. Explicit corruption/routing tests name their doubles.
No product import, test collection, native execution or build ran in authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest

from lumaretouch_engine import people_state as P, people_associations as LINKS
from lumaretouch_engine import people_binding as BIND, people_snapshot as SNAP
from lumaretouch_engine import body_pose_state as BODY, body_pose_evidence as EVIDENCE
from lumaretouch_engine import arm_shape_project as BODY_PROJECT, body_pose_render as BODY_RENDER
from lumaretouch_engine import face_scope as FACE, skin_colour_support as FACE_SUPPORT
from lumaretouch_engine import body_skin_semantics as BODY_SUPPORT
from lumaretouch_engine import skin_colour_body_support as REVIEW
from lumaretouch_engine import skin_colour_people as COLOUR, skin_colour_state as RECIPE
from lumaretouch_engine import skin_colour_native as NATIVE, people_engine_runtime as RUNTIME
from lumaretouch_engine.ops import enhance as ENHANCE

BUDGET = 512 * 1024 * 1024
ACTIVE = {'version': 1, 'temperature': -.35, 'tint': .2}


def fixture(*, retained=True):
    h = w = 128
    source = {'sha256': 'a'*64, 'width': w, 'height': h, 'orientation': EVIDENCE.ORIENTATION}
    landmarks = np.full((478, 3), .5, np.float32)
    def ellipse(indices, cx, cy, rx, ry):
        for i, index in enumerate(indices):
            angle = 2*np.pi*i/len(indices)
            landmarks[index, :2] = [cx+rx*np.cos(angle), cy+ry*np.sin(angle)]
    ellipse(FACE.FACE_OVAL, .5, .25, .3, .2)
    ellipse(ENHANCE.EYE_RING_LEFT, .39, .21, .04, .02)
    ellipse(ENHANCE.EYE_RING_RIGHT, .61, .21, .04, .02)
    ellipse(FACE.BROW_LEFT, .61, .15, .05, .015)
    ellipse(FACE.BROW_RIGHT, .39, .15, .05, .015)
    ellipse(FACE.LIPS, .5, .34, .06, .025)
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': BIND.landmark_digest(landmarks),
        'status': 'verified', 'source_width': w, 'source_height': h, 'orientation': EVIDENCE.ORIENTATION}
    state = P.empty()
    # This deliberately narrow synthetic retained box permits a small overlap
    # with the synthetic oval, so max-union can be distinguished from addition.
    face = P.new_face(source['sha256'], [.4, .1, .6, .3], evidence)
    state['faces'][face['face_instance_id']] = face
    state, person = LINKS.create_person(state)
    state = LINKS.set_link(state, face['face_instance_id'], person, 'confirmed', user_confirmed=True)
    points = [{'index': i, 'x': .5, 'y': .5, 'z': 0., 'visibility': 0., 'presence': 0.} for i in range(33)]
    measured = EVIDENCE.create(source_frame=source, values=points, backend_version='fixture-only',
        backend_code_sha256='d'*64, model_id='synthetic-unit-fixture', model_sha256='e'*64,
        input_rgb_sha256='f'*64, input_dimensions=(w, h))
    bank = BODY.add_run(BODY.empty(), {'source': source, 'records': [measured],
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
    bank = BODY.associate(bank, measured['body_ref'], person, state, user_confirmed=True)
    ref = P.face_ref(face)
    analysis = {'face_ref': ref, 'evidence': deepcopy(evidence), 'landmarks': landmarks,
        'excluded': np.zeros((h,w), np.float32), 'skin': np.ones((h,w), np.float32),
        'face_skin': np.full((h,w), .7, np.float32), 'body_skin': np.full((h,w), .8, np.float32),
        'face_skin_observation': {'contract': FACE_SUPPORT.CONTRACT, 'source_sha256': source['sha256'],
            'semantic_model_sha256': 'c'*64, 'producer_width': w, 'producer_height': h},
        'body_skin_observation': {'contract': BODY_SUPPORT.CONTRACT, 'source_sha256': source['sha256'],
            'semantic_model_sha256': 'c'*64, 'detector_model_sha256': 'b'*64,
            'producer_width': w, 'producer_height': h}}
    review = {'body_ref': measured['body_ref'], 'points_sha256': measured['points_sha256'],
        'visible': True, 'unoccluded': True, 'ownership_confirmed': True,
        'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{
            'id': 'manual-body', 'name': 'Synthetic renderer fixture', 'kind': 'brush',
            'enabled': True, 'operation': 'add', 'opacity': 1., 'feather': 0.,
            'points': [[.5, .5], [.5, .8]], 'axes': [[.1, 0.], [0., .1]]}]}}
    assets = {}
    if retained: state, assets = REVIEW.retain(state, assets, ref, bank, analysis, review)
    pixels = np.full((h,w,3), .4, np.float32)
    return state, assets, ref, bank, analysis, review, pixels


def native_fixture(calls):
    def apply(pixels, coverage, temperature, tint):
        calls.append((pixels.copy(), coverage.copy(), temperature, tint))
        return pixels + coverage[..., None] * np.float32(.01)
    return apply


def prepare(values, *, recipe=ACTIVE, budget=BUDGET):
    state, assets, ref, bank, analysis, _, pixels = values
    return COLOUR.prepare(ref, analysis, [], pixels, recipe, byte_budget=budget,
        people_state=state, body_assets=assets, body_bank=bank)


def test_absent_descriptor_is_numerically_identical_to_legacy_face_only():
    values = fixture(retained=False); state, _, ref, _, analysis, _, pixels = values
    calls = []
    with patch.object(NATIVE, 'apply', side_effect=native_fixture(calls)), patch.object(REVIEW.M, 'raster') as manual:
        legacy = COLOUR.prepare(ref, analysis, [], pixels, ACTIVE, byte_budget=BUDGET)
        # Absence must not consult even a deliberately unusable body bank.
        current = COLOUR.prepare(ref, analysis, [], pixels, ACTIVE, byte_budget=BUDGET,
            people_state=state, body_assets={}, body_bank={'stale': True})
    assert len(calls) == 2 and len(legacy) == len(current) == 1
    assert legacy[0].window == current[0].window and legacy[0].facts == current[0].facts
    np.testing.assert_array_equal(legacy[0].delta, current[0].delta)
    manual.assert_not_called()


def test_neutral_never_resolves_stale_body_support_or_calls_native():
    values = fixture(); state, assets, ref, bank, analysis, review, pixels = values
    stale = BODY.unlink(bank, review['body_ref'])
    with patch.object(REVIEW, 'raster') as raster, patch.object(NATIVE, 'apply') as native:
        assert COLOUR.prepare(ref, analysis, [], pixels, RECIPE.neutral(), byte_budget=0,
            people_state=state, body_assets=assets, body_bank=stale) == []
    raster.assert_not_called(); native.assert_not_called()


def test_active_stale_link_refuses_before_manual_or_colour_native():
    values = list(fixture()); values[3] = BODY.unlink(values[3], values[5]['body_ref'])
    with patch.object(REVIEW.M, 'raster') as manual, patch.object(NATIVE, 'apply') as native:
        with pytest.raises(ValueError, match='association'): prepare(values)
    manual.assert_not_called(); native.assert_not_called()


def test_face_body_union_uses_max_and_one_native_colour_call_without_mutation():
    values = fixture(); state, assets, ref, bank, analysis, _, pixels = values
    before = pixels.copy(); face_before = analysis['face_skin'].copy(); body_before = analysis['body_skin'].copy()
    calls = []; manual = np.full(pixels.shape[:2], 128, np.uint8)
    with patch.object(REVIEW.M, 'raster', return_value=manual):
        body, _ = REVIEW.raster(state, assets, ref, bank, analysis, pixels.shape[:2], byte_budget=BUDGET)
        face = FACE.selected_face_skin(analysis['face_skin'], analysis['landmarks'])
        assert np.any((face > .5) & (body > .2))
        expected = np.maximum(face, body)
        with patch.object(NATIVE, 'apply', side_effect=native_fixture(calls)):
            records = prepare(values)
    assert len(records) == len(calls) == 1
    record = records[0]; y,x,h,w = record.window
    np.testing.assert_array_equal(calls[0][1], expected[y:y+h,x:x+w])
    assert calls[0][2:] == (ACTIVE['temperature'], ACTIVE['tint'])
    assert record.stage == 'skin_colour' and record.facts['body_extension']['enabled'] is True
    assert record.facts['scope'] == 'face-and-explicitly-reviewed-body-skin'
    assert not record.delta.flags.writeable
    np.testing.assert_array_equal(pixels, before)
    np.testing.assert_array_equal(analysis['face_skin'], face_before)
    np.testing.assert_array_equal(analysis['body_skin'], body_before)


def test_corrupt_returned_coverage_dtype_refuses_before_colour_native():
    values = fixture(); shape = values[-1].shape[:2]
    # Deliberate inter-module corruption, not a source or ownership substitute.
    with patch.object(REVIEW, 'raster', return_value=(np.ones(shape, np.float64), {'enabled': True})), \
            patch.object(NATIVE, 'apply') as native:
        with pytest.raises(ValueError, match='source-domain float32'): prepare(values)
    native.assert_not_called()


def test_budget_failures_never_invoke_native_or_publish_partial_effect():
    values = fixture()
    with patch.object(REVIEW.M, 'raster') as manual, patch.object(NATIVE, 'apply') as native:
        with pytest.raises(ValueError, match='memory budget'): prepare(values, budget=0)
    manual.assert_not_called(); native.assert_not_called()
    with patch.object(REVIEW.M, 'validate_budget', return_value={'work': REVIEW.M.MAX_WORK + 1}), \
            patch.object(REVIEW.M, 'raster') as manual, patch.object(NATIVE, 'apply') as native:
        with pytest.raises(ValueError, match='aggregate work budget'): prepare(values)
    manual.assert_not_called(); native.assert_not_called()


def test_source_colour_stage_does_not_warp_its_body_or_face_delta_again():
    torch = pytest.importorskip('torch')
    from lumaretouch_engine import people_pipeline as PIPE
    values = fixture(); pixels = values[-1]; calls = []
    with patch.object(REVIEW.M, 'raster', return_value=np.full(pixels.shape[:2], 128, np.uint8)), \
            patch.object(NATIVE, 'apply', side_effect=native_fixture(calls)):
        records = prepare(values)
    h,w = pixels.shape[:2]
    pipe = SimpleNamespace(h=h,w=w,device='cpu',people_origin=(0,0),
        people_prepared=SimpleNamespace(effects=tuple(records),recovery={}))
    tensor = torch.from_numpy(pixels.copy()).permute(2,0,1)[None]
    with patch.object(PIPE, 'warp', side_effect=AssertionError('Unexpected second source-effect warp')) as warp:
        output = PIPE.source_effect(pipe, 'skin_colour', tensor)
    warp.assert_not_called(); assert len(calls) == 1
    expected = pixels.copy(); y,x,rh,rw = records[0].window
    expected[y:y+rh,x:x+rw] += records[0].delta
    np.testing.assert_allclose(output[0].permute(1,2,0).numpy(), expected, rtol=0, atol=1e-7)


def test_export_passes_frozen_target_bank_before_one_common_body_prepare():
    values = fixture(); state, assets, ref, target_bank, analysis, _, pixels = values
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id='target-document', support_assets=deepcopy(assets))
    frame = next(iter(target_bank['bodies'].values()))['record']['source']
    body_snapshot = BODY_PROJECT.snapshot(target_bank, frame)
    # A different live bank cannot influence this snapshot-only export API.
    live_bank = deepcopy(target_bank); live_bank['association_revision'] += 1
    prepared = SimpleNamespace(effects=(),recovery={},geometry=SimpleNamespace(delta=np.zeros((1,128,128,2),np.float32)))
    order = []; observed = []
    def prepare_people(graph, asset, source, analyses, **kwargs):
        order.append('source-colour')
        assert graph == state and asset == ref['asset_sha256']
        assert kwargs['body_bank'] == target_bank and kwargs['body_bank'] != live_bank
        assert kwargs['skin_colour_body_assets'] is snapshot['support_assets']
        assert analyses[ref['face_instance_id']]['body_skin_observation'] == analysis['body_skin_observation']
        assert source.dtype == np.float32 and source.shape == pixels.shape
        observed.append(kwargs['body_bank'])
        return prepared
    def prepare_body(actual, bank, graph, source_frame, **kwargs):
        order.append('one-common-map')
        assert actual is prepared and bank is observed[0] and graph == state and source_frame == frame
        return prepared
    with patch.object(RUNTIME, 'prepare', side_effect=prepare_people), \
            patch.object(BODY_RENDER, 'prepare', side_effect=prepare_body) as common:
        result = RUNTIME.prepare_export(snapshot, np.full(pixels.shape, 102, np.uint8), None,
            byte_budget=BUDGET, document_id='target-document', body_pose=body_snapshot,
            body_source_path='target-owned-original.jpg')
    assert result is prepared and order == ['source-colour', 'one-common-map']
    assert common.call_count == 1 and target_bank != live_bank


def test_export_cannot_borrow_missing_body_snapshot_for_active_review():
    values = fixture(); state, assets, ref, _, analysis, _, pixels = values
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id='target-document', support_assets=deepcopy(assets))
    def prepare_people(graph, asset, source, analyses, **kwargs):
        assert kwargs['body_bank'] is None
        return COLOUR.prepare(ref, analyses[ref['face_instance_id']], [], source, ACTIVE,
            byte_budget=kwargs['byte_budget'], people_state=graph,
            body_assets=kwargs['skin_colour_body_assets'], body_bank=kwargs['body_bank'])
    with patch.object(RUNTIME, 'prepare', side_effect=prepare_people), patch.object(NATIVE, 'apply') as native:
        with pytest.raises(ValueError, match='body bank'):
            RUNTIME.prepare_export(snapshot, np.full(pixels.shape, 102, np.uint8), None,
                byte_budget=BUDGET, document_id='target-document')
    native.assert_not_called()
