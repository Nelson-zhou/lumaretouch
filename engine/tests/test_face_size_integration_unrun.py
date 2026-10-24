"""AUTHORED / UNRUN: canonical whole-face-size integration contracts.

Every image, landmark and observation below is a synthetic fixture, not a real
detector measurement or photographic acceptance. The ONLY patched production
boundary is face_size_runtime.build. Its explicit field double proves routing,
not the native scale, anatomical admission, occlusion or photographic quality.
Full preview/export retains actual source checks, neutral existing geometry,
the size composition guard, common joint map, effects, repair proof and sampler.
Composition unit fixtures use the actual AutomaticField and existing TPS math;
the five-slot coexistence unit fixture explicitly labels its synthetic contour.

No product import, test collection/execution, native build, inference or type
check ran while authoring this file. Parsing its AST is not a test pass.
"""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from test_skin_colour_body_render_unrun import fixture as source_fixture
from lumaretouch_engine import face_size_state as S, face_size_runtime as CORE
from lumaretouch_engine import face_size_people as PORT, face_contour_state as C
from lumaretouch_engine import slim_face_state as SLIM
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_resolver as RESOLVE, people_project as PROJECT
from lumaretouch_engine import people_snapshot as SNAP, people_export as EXPORT
from lumaretouch_engine import people_render_runtime as RENDER
from lumaretouch_engine import people_engine_runtime as ENGINE
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY
from lumaretouch_engine.people_geometry import AutomaticField, FaceGeometry, CombinedGeometry
from lumaretouch_engine.ops import deform as D

ROOT = Path(__file__).resolve().parents[2]
BUDGET = 512 * 1024**2
DOCUMENT = 'synthetic-face-size-document'
ACTIVE = {'version': 1, 'amount': .4}
# Exact read-only e1ad9781 source hashes; preservation is not rendered parity.
PRIOR_GEOMETRY_SHA256 = {
    'engine/src/lumaretouch_engine/ops/deform.py': '5e0800bffa8f87f9f8e4f6cf8caa1ea782bee20d099a2232c869e0e9d53247fd',
    'engine/src/lumaretouch_engine/face_contour_geometry.py': 'f40ce390d517dc8159ba3e74b4b949555d2b79e40daa0848ab1f36170be65f2d',
    'engine/src/lumaretouch_engine/face_contour_field.py': 'e735091f5c4a07a93143fbfe066d917fbe2fa7f8d474accdd053db6ed378ded1',
    'core/face_contour/lib.rs': '517e6a791f65918f586194fc6d1090c35b8b32b22bfc2ff0089d432f68f19210',
    'engine/src/lumaretouch_engine/people_geometry.py': '554e4ea056f8c675be3b1fb859a2ca3101ca437dc1db52967e4151524955580b',
    'engine/src/lumaretouch_engine/brow_shape_geometry.py': '267cbf7c2484a34b2e238445d572372f9ebb60461e3e4cd668a74c346a8863b5',
    'engine/src/lumaretouch_engine/nose_shape_geometry.py': '1643f4d0ead92e59487708e90b2bb5b5910b961063bc81b7fcfaf58dc7a162ce',
    'engine/src/lumaretouch_engine/eye_shape_geometry.py': 'fbf65f20ba7cadaafa99a554f39791dd30f929e8cb169d7edec05a07bf7cd3b4',
    'engine/src/lumaretouch_engine/mouth_shape_geometry.py': 'ff866e32296384f898a0a21bf7af55e9690c56a69c467da68b6c4ea7786d0758',
}


def fixture(*, size=128, recipe=ACTIVE):
    state, _, ref, _, analysis, _, _ = source_fixture(retained=False)
    state['links'] = []
    state['persons'] = {}
    for evidence in (state['faces'][ref['face_instance_id']]['evidence'], analysis['evidence']):
        evidence['source_width'] = evidence['source_height'] = size
    for path, value in A.leaves(recipe).items():
        state = P.set_override(state, 'face', ref['face_instance_id'], S.OP, path, value)
    binding = {'sha256': ref['asset_sha256'], 'width': size, 'height': size}
    return state, ref, analysis, binding


def original_pixels(size):
    """RGB16 gradient containing genuine below-RGB8-step integer values."""
    yy, xx = np.indices((size, size), dtype=np.uint32)
    return np.stack(((xx * 113 + yy * 17) % 65536,
                     (xx * 37 + yy * 101) % 65536,
                     (xx * 53 + yy * 61 + 12345) % 65536), axis=-1).astype(np.uint16)


class SyntheticSizeField:
    """Explicit build double, not the native radial solver or photo evidence.

    Positive pipeline cases use a tiny compact smooth map. Guard unit cases
    may supply a constant delta, intentionally unsafe, to exercise refusal.
    """
    def __init__(self, shape, recipe, *, constant_delta=None):
        self.shape = tuple(shape)
        self.state = {'synthetic_integration_double': True}
        self.scale = 1. - .06 * recipe['amount']
        self.facts = {'face_size': {
            'requested': recipe['amount'] != 0., 'applied': recipe['amount'] != 0.,
            'reason': None, 'operation_id': S.OP, 'version': 1,
            'amount': recipe['amount'], 'scale': self.scale,
            'evidence': 'synthetic_build_double_not_native_or_photo_acceptance'}}
        self.constant_delta = constant_delta
        self.evaluated_points = 0

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        self.evaluated_points += len(points)
        if self.constant_delta is not None:
            return np.tile(self.constant_delta, (len(points), 1)).astype(np.float64)
        h, w = self.shape
        offset = points - [(w-1)*.5, (h-1)*.5]
        radius = np.linalg.norm(offset / [w-1, h-1], axis=1)
        t = np.clip((radius-.10)/.12, 0., 1.)
        weight = 1. - t*t*(3.-2.*t)
        return offset * ((1.-1./self.scale)*weight)[:, None]

    def resident_bytes(self):
        return 64


def size_builder(received, expected_shape):
    def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes):
        assert recipe == ACTIVE
        assert backend == 'mediapipe' and protected_boxes == ()
        assert landmarks is analysis['landmarks']
        assert source.shape == (*expected_shape, 3) and source.dtype == np.float32
        assert excluded is analysis['excluded'] and excluded.shape == expected_shape
        assert analysis['face_skin'].shape == expected_shape
        assert not source.flags.writeable
        field = SyntheticSizeField(expected_shape, recipe)
        received.append({'source': source.copy(), 'field': field,
                         'face_ref': deepcopy(analysis['face_ref']),
                         'observation': deepcopy(analysis['face_skin_observation'])})
        return field
    return build


def assert_canonical_result(prepared, ref, received, shape):
    key = ref['face_instance_id']
    assert type(prepared.geometry) is CombinedGeometry
    assert prepared.geometry.delta.shape == (1, *shape, 2)
    assert prepared.geometry.owner.shape == shape
    assert prepared.geometry.face_ids == (key,)
    assert not prepared.geometry.delta.flags.writeable
    assert not prepared.geometry.owner.flags.writeable
    assert prepared.geometry.peak > 0 and np.any(prepared.geometry.owner == 0)
    assert len(prepared.face_fields) == 1 and prepared.effects == ()
    face = prepared.face_fields[0]
    assert type(face) is PORT.SizedFace
    assert type(face.automatic) is AutomaticField and not face.automatic.units
    assert face.fields[:4] == (None,)*4 and face.fields[3] is None
    assert len(face.fields) == 5 and face.fields[4] is received['field']
    assert type(face.prefix) is FaceGeometry and face.prefix.fields == (None,)*4
    assert received['field'].evaluated_points == shape[0]*shape[1]
    assert received['face_ref'] == ref
    assert received['observation']['source_sha256'] == ref['asset_sha256']
    assert set(prepared.facts[key]) == {'face_size'}
    assert prepared.facts[key]['face_size'] is received['field'].facts
    assert prepared.plan['sample_policy'] == 'one_original_source_sample_after_composed_field'


def prefix_fixture(*, translation=None):
    """Real geometry classes; optional synthetic controls use real TPS math."""
    state, ref, analysis, _ = fixture()
    source = original_pixels(128).astype(np.float32)/65535.
    automatic = AutomaticField(analysis['landmarks'], {}, source.shape[:2])
    if translation is not None:
        points = np.array([[0., 0.], [127., 0.], [0., 127.], [127., 127.],
                           [40., 45.], [85., 80.]])
        values = (np.tile(translation, (len(points), 1)) if translation != 'curved'
                  else np.array([[0., 0.], [.4, 0.], [0., .3], [.2, -.2], [.7, -.3], [-.2, .5]]))
        tps_state = D.tps_solve(points, values, scale=128.)
        # The evaluator/solver are real; these are authored control fixtures,
        # not a patched legacy geometry builder or authentic anatomy claim.
        automatic.units.append((tps_state, 1., np.array([63.5, 63.5]), 100., 150.))
        automatic.windows.append((np.array([63.5, 63.5]), 100., 150.))
    prefix = FaceGeometry(ref['face_instance_id'], source.shape[:2], automatic, (None,)*4)
    return state, ref, analysis, source, prefix


def test_registry_defaults_and_derived_transport_keep_whole_size_distinct():
    assert A.FACE_SIZE is S and S.OP == 'lnx.face_size.v1'
    assert A.GEOMETRY == ('lnx.brow_shape.v1', 'lnx.nose_shape.v1',
                          'lnx.eye_shape.v1', 'lnx.mouth_shape.v1')
    assert S.OP not in A.GEOMETRY and S.OP not in (A.DEFORM, C.OP, SLIM.OP)
    assert A.defaults()[S.OP] == {'/amount': 0.}
    assert '/version' not in A.defaults()[S.OP]
    assert S.OP in DERIVED.OPERATIONS
    entries = json.loads((ROOT/'docs/p0/registry-extensions.json').read_text())['entries']
    matching = [entry for entry in entries if entry['operation_id'] == S.OP]
    assert len(matching) == 1
    assert matching[0]['neutral'] == S.neutral()
    assert matching[0]['requirement_ids'] == ['LNX-REF-PC-32466-C-728fc62cdd']
    assert matching[0]['range']['version'] == [1, 1]
    assert matching[0]['range']['amount'] == [-1, 1]


@pytest.mark.parametrize('amount', [-1, -.25, 0, .25, 1])
def test_scalar_portable_intent_has_declared_local_sign_and_scale(amount):
    DERIVED._leaf(S.OP, '/amount', amount)
    assert S.check({'version': 1, 'amount': amount}) == {'version': 1, 'amount': float(amount)}
    assert S.scale_for_amount(amount) == 1.-.06*amount
    assert S.active({'version': 1, 'amount': amount}) is (amount != 0)


@pytest.mark.parametrize('path,value', [('/amount', True), ('/amount', False),
    ('/amount', '0.2'), ('/amount', 1.1), ('/amount', -1.1),
    ('/amount', float('nan')), ('/amount', float('inf')), ('/version', 1),
    ('/linked', True), ('/left', .2), ('/slim_face', .2), ('/mask', []),
    ('/source_sha256', 'a'*64)])
def test_derived_transport_rejects_coercion_aliases_and_source_payloads(path, value):
    with pytest.raises(ValueError):
        DERIVED._leaf(S.OP, path, value)


@pytest.mark.parametrize('recipe', [True, [], {'amount': .2},
    {'version': True, 'amount': 0.}, {'version': 2, 'amount': .2},
    {'version': 1, 'amount': False}, {'version': 1, 'amount': '0'},
    {'version': 1, 'amount': 0., 'landmarks': []}])
def test_strict_recipe_validation_does_not_treat_malformed_as_neutral(recipe):
    with pytest.raises(ValueError):
        S.check(recipe)


def test_saved_graph_history_and_snapshot_keep_one_canonical_size_intent():
    neutral, ref, analysis, _ = fixture(recipe=S.neutral())
    key = ref['face_instance_id']
    old = P.set_override(neutral, 'face', key, A.DEFORM, '/slim_face', .6)
    current = P.set_override(neutral, 'face', key, S.OP, '/amount', ACTIVE['amount'])
    payload = {'people_graph': current, 'undo': [{'_people_state': old}],
               'redo': [{'_people_state': neutral}]}
    restored = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False))
    PROJECT.validate_records(restored)
    assert restored == payload
    for graph, expected_size, expected_legacy in (
            (restored['people_graph'], ACTIVE, 0.),
            (restored['undo'][0]['_people_state'], S.neutral(), .6),
            (restored['redo'][0]['_people_state'], S.neutral(), 0.)):
        values = A.recipes(RESOLVE.resolve(P.check(graph), key, A.defaults()))
        assert values[S.OP] == expected_size
        assert values[A.DEFORM]['slim_face'] == expected_legacy
        assert values[C.OP] == C.neutral() and values[SLIM.OP] == SLIM.neutral()
    snapshot = SNAP.capture(current, ref['asset_sha256'], {key: analysis})
    analysis['landmarks'][0, 0] += .001
    current['overrides'].clear()
    assert A.recipes(RESOLVE.resolve(snapshot['state'], key, A.defaults()))[S.OP] == ACTIVE
    assert snapshot['analyses'][key]['landmarks'][0, 0] != analysis['landmarks'][0, 0]
    assert not snapshot['analyses'][key]['landmarks'].flags.writeable


def test_old_saved_intent_does_not_inject_size_or_convert_existing_geometry():
    state, ref, _, _ = fixture(recipe=S.neutral())
    state['overrides'] = []
    state = P.set_override(state, 'face', ref['face_instance_id'], A.DEFORM, '/slim_face', -.45)
    before = deepcopy(state)
    values = A.recipes(RESOLVE.resolve(state, ref['face_instance_id'], A.defaults()))
    assert values[S.OP] == S.neutral() and values[A.DEFORM]['slim_face'] == -.45
    assert state == before and all(row['operation_id'] != S.OP for row in state['overrides'])


@pytest.mark.parametrize('path,expected', list(PRIOR_GEOMETRY_SHA256.items()))
def test_existing_geometry_source_bytes_are_not_rewritten(path, expected):
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected


def test_neutral_append_needs_no_owner_analysis_or_native_acquisition():
    original = object()
    with patch.object(CORE, 'build', side_effect=AssertionError('neutral reached size build')) as build:
        assert PORT.append(original, None, None, None, None, S.neutral()) == (original, None)
    build.assert_not_called()


def test_export_fastpath_blocks_both_size_directions_but_not_explicit_neutral():
    neutral, ref, _, _ = fixture(recipe=S.neutral())
    snapshot = {'state': neutral, 'asset_sha256': ref['asset_sha256']}
    assert not EXPORT.fastpath_blocker(snapshot)
    for amount in (-.4, .4):
        changed = P.set_override(neutral, 'face', ref['face_instance_id'], S.OP, '/amount', amount)
        assert EXPORT.fastpath_blocker({**snapshot, 'state': changed})


def test_neutral_export_without_analysis_preserves_original_rgb16():
    state, ref, _, _ = fixture(recipe=S.neutral())
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    pixels = original_pixels(128)
    with patch.object(CORE, 'build', side_effect=AssertionError('neutral reached size build')) as build:
        prepared = ENGINE.prepare_export(snapshot, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert prepared.face_fields == () and prepared.effects == () and prepared.facts == {}
    assert not prepared.plan['entries'][0]['requires_analysis']
    np.testing.assert_array_equal(prepared.geometry.warp_original(pixels), pixels)
    assert prepared.geometry.warp_original(pixels).dtype == np.uint16 and state == before


def test_active_missing_analysis_refuses_before_size_build_without_mutating_intent():
    state, ref, _, _ = fixture()
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    with patch.object(CORE, 'build', side_effect=AssertionError('missing evidence reached size')) as build:
        with pytest.raises(RENDER.PeoplePreparationRefused) as error:
            ENGINE.prepare_export(snapshot, original_pixels(128), None,
                                  byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert len(error.value.refusals) == 1
    assert error.value.refusals[0]['face_instance_id'] == ref['face_instance_id']
    assert 'frozen_source_analysis_missing_or_stale' in str(error.value)
    assert state == before


def test_append_preserves_owner_slots_and_returns_separate_size_facts():
    state, ref, analysis, source, prefix = prefix_fixture()
    size = SyntheticSizeField(source.shape[:2], ACTIVE)
    before = source.copy()
    with patch.object(CORE, 'build', return_value=size) as build:
        result, facts = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert type(result) is PORT.SizedFace and result.prefix is prefix
    assert result.automatic is prefix.automatic and result.face_instance_id == ref['face_instance_id']
    assert prefix.fields == (None,)*4 and result.fields == (*prefix.fields, size)
    assert facts is size.facts and result.resident_bytes() >= size.resident_bytes()
    assert build.call_args.args[0] is analysis['landmarks']
    assert build.call_args.args[2] is source and build.call_args.kwargs['analysis'] is analysis
    assert build.call_args.kwargs['protected_boxes'] == ()
    np.testing.assert_array_equal(source, before)


def test_size_is_outermost_pullback_not_appended_after_prefix_or_summed():
    state, ref, analysis, source, prefix = prefix_fixture(translation='curved')
    size = SyntheticSizeField(source.shape[:2], ACTIVE)
    with patch.object(CORE, 'build', return_value=size):
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    points = np.array([[58., 53.], [68., 61.], [75., 70.]])
    size_delta = size.evaluate(points)
    baseline = prefix.evaluate(points)
    expected = size_delta + prefix.evaluate(points-size_delta)
    np.testing.assert_allclose(result.evaluate(points), expected, rtol=0, atol=1e-12)
    assert not np.allclose(expected, baseline+size_delta, rtol=0, atol=1e-9)
    assert not np.allclose(expected, baseline+size.evaluate(points-baseline), rtol=0, atol=1e-9)


def test_five_slot_contour_or_slim_prefix_keeps_mouth_slot_and_outer_size_composition():
    """UNRUN unit fixture: real wrapper/TPS prefix, explicit contour-only double.

    Corrected slim and standalone contour share the real ContouredFace wrapper.
    This synthetic contour evaluator is only a five-slot composition fixture;
    it is not native contour/size evidence or a second patched runtime builder.
    Full canonical preview/export tests above/below retain their sole build patch.
    """
    from lumaretouch_engine.face_contour_people import ContouredFace
    state, ref, analysis, source, base = prefix_fixture(translation='curved')
    contour = SimpleNamespace(
        state={'synthetic_existing_contour_composition_fixture': True},
        evaluate=lambda q: (np.asarray(q, dtype=np.float64)-[63.5, 63.5])*.003,
        resident_bytes=lambda: 64)
    prefix = ContouredFace(base.face_instance_id, base.shape, base.automatic,
                           (*base.fields, contour), base, ())
    size = SyntheticSizeField(source.shape[:2], ACTIVE)
    with patch.object(CORE, 'build', return_value=size) as build:
        result, facts = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert build.call_count == 1 and type(result) is PORT.SizedFace
    assert result.prefix is prefix and type(result.prefix) is ContouredFace
    assert prefix.prefix is base and result.automatic is base.automatic
    assert base.fields == (None,)*4 and prefix.fields == (*base.fields, contour)
    assert len(result.fields) == 6 and result.fields[:4] == base.fields
    assert result.fields[3] is base.fields[3]  # The existing mouth slot, never last.
    assert result.fields[4] is contour and result.fields[5] is size
    assert facts is size.facts
    points = np.array([[58., 53.], [68., 61.], [75., 70.]])
    original_points = points.copy()
    size_delta = size.evaluate(points)
    baseline = prefix.evaluate(points)
    expected = size_delta+prefix.evaluate(points-size_delta)
    np.testing.assert_allclose(result.evaluate(points), expected, rtol=0, atol=1e-12)
    assert not np.allclose(expected, baseline+size_delta, rtol=0, atol=1e-9)
    assert not np.allclose(expected, baseline+size.evaluate(points-baseline), rtol=0, atol=1e-9)
    np.testing.assert_array_equal(points, original_points)


def test_all_retained_same_source_neighbors_reach_size_builder():
    state, ref, analysis, source, prefix = prefix_fixture()
    own = state['faces'][ref['face_instance_id']]
    for index, enabled in enumerate((False, True)):
        other = deepcopy(own)
        other['face_instance_id'] = f'neighbor-{index}'
        other['enabled'] = enabled
        other['box'] = [.05+index*.2, .1, .15+index*.2, .4]
        state['faces'][other['face_instance_id']] = other
    foreign = deepcopy(own)
    foreign.update(face_instance_id='other-source', asset_sha256='f'*64)
    state['faces']['other-source'] = foreign
    with patch.object(CORE, 'build', return_value=SyntheticSizeField(source.shape[:2], ACTIVE)) as build:
        PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert build.call_args.kwargs['protected_boxes'] == ((.05, .1, .15, .4), (.25, .1, .35, .4))


@pytest.mark.parametrize('change', ['identity', 'disabled', 'digest', 'grid'])
def test_stale_or_foreign_source_field_refuses_before_size_build(change):
    state, ref, analysis, source, prefix = prefix_fixture()
    if change == 'identity': ref = {**ref, 'analysis_revision': ref['analysis_revision']+1}
    elif change == 'disabled': state['faces'][ref['face_instance_id']]['enabled'] = False
    elif change == 'digest': analysis['landmarks'][0, 0] += .001
    else: prefix = FaceGeometry(prefix.face_instance_id, (64, 64), prefix.automatic, prefix.fields)
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    build.assert_not_called()


def test_repeated_size_cannot_acquire_a_second_geometry_owner():
    state, ref, analysis, source, prefix = prefix_fixture()
    with patch.object(CORE, 'build', return_value=SyntheticSizeField(source.shape[:2], ACTIVE)) as build:
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
        with pytest.raises(ValueError):
            PORT.append(result, state, ref, analysis, source, ACTIVE)
    assert build.call_count == 1 and prefix.fields == (None,)*4


@pytest.mark.parametrize('mode', ['missing', 'no_state', 'refused'])
def test_requested_missing_or_refused_size_never_publishes_partial_geometry(mode):
    state, ref, analysis, source, prefix = prefix_fixture()
    size = SyntheticSizeField(source.shape[:2], ACTIVE)
    if mode == 'missing': size = None
    elif mode == 'no_state': size.state = None
    else: size.facts['face_size'].update(applied=False, reason='synthetic_occlusion_refusal')
    with patch.object(CORE, 'build', return_value=size), pytest.raises(ValueError):
        PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert prefix.fields == (None,)*4


@pytest.mark.parametrize('stage', ['output', 'intermediate', 'final'])
def test_actual_composed_neighbor_footprints_are_protected(stage):
    translation = {'output': [-10., 0.], 'intermediate': [-30., 0.], 'final': [15., 0.]}[stage]
    point = np.array([[50. if stage == 'output' else 70., 50.]])
    delta = {'output': [-20., 0.], 'intermediate': [20., 0.], 'final': [5., 0.]}[stage]
    state, ref, analysis, source, prefix = prefix_fixture(translation=translation)
    neighbor = deepcopy(state['faces'][ref['face_instance_id']])
    neighbor.update(face_instance_id='protected-neighbor', enabled=False,
                    box=[49./127, 49./127, 51./127, 51./127])
    state['faces']['protected-neighbor'] = neighbor
    size = SyntheticSizeField(source.shape[:2], ACTIVE, constant_delta=delta)
    with patch.object(CORE, 'build', return_value=size):
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    with pytest.raises(ValueError, match='another retained face'):
        result.evaluate(point)


def test_composed_out_of_image_sampling_refuses_instead_of_border_fill():
    state, ref, analysis, source, prefix = prefix_fixture()
    size = SyntheticSizeField(source.shape[:2], ACTIVE, constant_delta=[3., 0.])
    with patch.object(CORE, 'build', return_value=size):
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    with pytest.raises(ValueError, match='outside the genuine source'):
        result.evaluate(np.array([[1., 50.]]))


def test_full_original_rgb16_and_derived_float_export_share_real_canonical_map():
    state, ref, analysis, binding = fixture(size=384)
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    derived = {**snapshot, 'creative_source': binding}
    original = original_pixels(384)
    original_before = original.copy()
    working = original.astype(np.float32)/65535.
    working_before = working.copy()
    assert np.any(original % 257 != 0)
    received = []
    with patch.object(CORE, 'build', side_effect=size_builder(received, (384, 384))) as build:
        old = ENGINE.prepare_export(snapshot, original, None, byte_budget=BUDGET, document_id=DOCUMENT)
        new = ENGINE.prepare_export(derived, working, None, byte_budget=BUDGET, document_id=DOCUMENT)
    assert build.call_count == len(received) == 2
    for prepared, record in zip((old, new), received):
        assert_canonical_result(prepared, ref, record, (384, 384))
        np.testing.assert_array_equal(record['source'], working)
        assert record['observation']['producer_width'] == record['observation']['producer_height'] == 128
    assert received[0]['field'] is not received[1]['field']
    np.testing.assert_array_equal(old.geometry.delta, new.geometry.delta)
    np.testing.assert_array_equal(old.geometry.owner, new.geometry.owner)
    old_output = old.geometry.warp_original(original)
    new_output = new.geometry.warp(working)
    assert old_output.dtype == np.uint16 and old_output.shape == original.shape
    assert np.any(old_output != original) and np.any(new_output != working)
    np.testing.assert_allclose(old_output.astype(np.float64)/65535., new_output, rtol=0, atol=1.1/65535.)
    np.testing.assert_array_equal(original, original_before)
    np.testing.assert_array_equal(working, working_before)
    assert state == before and snapshot['state'] == before


def test_original_and_derived_preview_retain_real_repair_proof_and_common_sampler():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding = fixture()
    before = deepcopy(state)
    proxy = (original_pixels(128)//257).astype(np.uint8)
    working = proxy.astype(np.float32)/255.
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working.copy()).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    proof = REPLAY.make_evidence(binding, working, None, REPAIRS.digest_ops([], [], binding))
    pipe._creative_repair_source = deepcopy(binding)
    pipe._creative_repair_input = deepcopy(proof['input'])
    pipe._creative_repair_evidence = proof
    received = []
    with patch.object(CORE, 'build', side_effect=size_builder(received, (128, 128))) as build:
        old = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT)
        new = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT,
                                     creative_source=binding, creative_proxy=proxy)
    assert build.call_count == len(received) == 2
    for prepared, record in zip((old, new), received):
        assert_canonical_result(prepared, ref, record, (128, 128))
        np.testing.assert_array_equal(record['source'], working)
    np.testing.assert_array_equal(old.geometry.delta, new.geometry.delta)
    np.testing.assert_array_equal(old.geometry.warp(working), new.geometry.warp(working))
    assert REPLAY.verify_pipeline(pipe, binding) == proof and state == before
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)


@pytest.mark.parametrize('derived', [False, True])
def test_export_rejects_other_source_dtype_before_size_build(derived):
    state, ref, analysis, binding = fixture()
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    original = original_pixels(128)
    if derived:
        snapshot['creative_source'] = binding
        wrong = original
    else:
        wrong = original.astype(np.float32)/65535.
    with patch.object(CORE, 'build', side_effect=AssertionError('wrong dtype reached size')) as build:
        with pytest.raises(ValueError, match='creative float32' if derived else 'original RGB8/16'):
            ENGINE.prepare_export(snapshot, wrong, None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()


def test_derived_preview_missing_repair_proof_is_not_bypassed():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding = fixture()
    proxy = (original_pixels(128)//257).astype(np.uint8)
    working = proxy.astype(np.float32)/255.
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    with patch.object(CORE, 'build', side_effect=AssertionError('unbound source reached size')) as build:
        with pytest.raises(ValueError, match='bound to another immutable source'):
            ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                   byte_budget=BUDGET, document_id=DOCUMENT,
                                   creative_source=binding, creative_proxy=proxy)
    build.assert_not_called()


@pytest.mark.parametrize('fault', ['document', 'derived_source', 'budget'])
def test_export_owner_or_memory_refusal_does_not_use_a_proxy_fallback(fault):
    state, ref, analysis, binding = fixture(size=384)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    source = original_pixels(384)
    budget = BUDGET
    if fault == 'document':
        snapshot['document_id'] = 'another-document'
    elif fault == 'derived_source':
        snapshot['creative_source'] = {**binding, 'sha256': 'f'*64}
        source = source.astype(np.float32)/65535.
    else:
        budget = 1
    with patch.object(CORE, 'build', side_effect=AssertionError('unowned/undersized source reached size')) as build:
        with pytest.raises(ValueError):
            ENGINE.prepare_export(snapshot, source, None, byte_budget=budget, document_id=DOCUMENT)
    build.assert_not_called()


def test_canonical_source_appends_size_after_contour_without_moving_mouth_slot():
    text = (ROOT/'engine/src/lumaretouch_engine/people_render_runtime.py').read_text()
    tree = ast.parse(text)
    prepare = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'prepare')
    calls = [node for node in ast.walk(prepare) if isinstance(node, ast.Call)]
    def line(name):
        selected = [node.lineno for node in calls if
                    (isinstance(node.func, ast.Name) and node.func.id == name) or
                    (isinstance(node.func, ast.Attribute) and node.func.attr == name)]
        assert len(selected) == 1
        return selected[0]
    assert line('build_geometry') < line('append_slim') < line('append_contour') < line('append_size')
    assert 'mouth = field.fields[3]' in text and 'mouth = field.fields[-1]' not in text
    assert "facts[key]['face_size'] = size_facts" in text


def test_new_capability_and_offline_staging_are_connected_without_building():
    server = (ROOT/'engine/src/lumaretouch_engine/server.py').read_text()
    assert 'from .face_size_state import capability as face_size_capability' in server
    assert 'face_size_capability()' in server
    stage = (ROOT/'packaging/stage-engine.sh').read_text()
    assert 'build-face-size.sh' in stage and 'liblrt_face_size.so' in stage
    assert 'core/face_size/face_size.h' in stage and 'third_party/face_size/' in stage
    build = (ROOT/'packaging/build-face-size.sh').read_text()
    # Dependency-free rustc is itself offline; it has no cargo --offline flag.
    assert 'rustc --edition=2021 --crate-type cdylib' in build
    assert 'core/face_size/lib.rs' in build
    assert not any(command in build for command in ('cargo build', 'curl ', 'wget ', 'pip install'))
