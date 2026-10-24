"""AUTHORED / UNRUN: canonical slim-face v2 integration contracts.

All images, landmarks and asserted observation records are synthetic fixtures,
not detector measurements or photographic acceptance. Positive rendering tests
replace ONLY face_contour_runtime.build with an explicit smooth field double.
They retain the actual source checks, neutral legacy builders, guarded contour
adapter, combined map, effects preparation, repair proof and common sampler.
Negative ordering tests additionally install a fail-if-called legacy-builder
tripwire; that is not a substitute successful geometry implementation.

No product import, test collection/execution, native build, inference or type
check ran while authoring this file. Static AST inspection is not a test pass.
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
from lumaretouch_engine import slim_face_state as S, face_contour_state as C
from lumaretouch_engine import face_contour_runtime as CORE
from lumaretouch_engine import face_contour_people as CONTOUR
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_resolver as RESOLVE, people_project as PROJECT
from lumaretouch_engine import people_snapshot as SNAP, people_export as EXPORT
from lumaretouch_engine import people_render_runtime as RENDER
from lumaretouch_engine import people_engine_runtime as ENGINE
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY
from lumaretouch_engine.people_geometry import AutomaticField, CombinedGeometry

ROOT = Path(__file__).resolve().parents[2]
BUDGET = 512 * 1024**2
DOCUMENT = 'synthetic-slim-document'
ACTIVE = {'version': 2, 'linked': False, 'left': .35, 'right': -.2}
LEGACY_SHA256 = '5e0800bffa8f87f9f8e4f6cf8caa1ea782bee20d099a2232c869e0e9d53247fd'


def fixture(*, size=128, recipe=ACTIVE):
    state, _, ref, _, analysis, _, _ = source_fixture(retained=False)
    # Derived-source graphs cannot borrow a person or group from another source.
    state['links'] = []
    state['persons'] = {}
    for evidence in (state['faces'][ref['face_instance_id']]['evidence'], analysis['evidence']):
        evidence['source_width'] = evidence['source_height'] = size
    for path, value in A.leaves(recipe).items():
        state = P.set_override(state, 'face', ref['face_instance_id'], S.OP, path, value)
    binding = {'sha256': ref['asset_sha256'], 'width': size, 'height': size}
    return state, ref, analysis, binding


def original_pixels(size):
    """Nonconstant RGB16, deliberately retaining information below RGB8 steps."""
    yy, xx = np.indices((size, size), dtype=np.uint32)
    return np.stack(((xx * 113 + yy * 17) % 65536,
                     (xx * 37 + yy * 101) % 65536,
                     (xx * 53 + yy * 61 + 12345) % 65536), axis=-1).astype(np.uint16)


class SyntheticContourField:
    """A compact, tiny smooth pullback; no anatomical/native validity asserted."""
    def __init__(self, shape, recipe):
        self.shape = tuple(shape)
        self.state = {'synthetic_integration_double': True}
        self.facts = {
            f'{key}/{side}': {'requested': recipe[key][side] != 0.,
                             'applied': recipe[key][side] != 0., 'reason': None}
            for key in C.KEYS for side in C.SIDES}
        self.evaluated_points = 0

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        self.evaluated_points += len(points)
        h, w = self.shape
        xy = points / [w - 1, h - 1] - [.5, .5]
        bump = np.maximum(0., 1. - np.sum(xy * xy, axis=1) / .18**2)**2
        return np.column_stack((.125 * bump, np.zeros(len(points))))

    def resident_bytes(self):
        return 64


def contour_builder(received, expected_shape):
    def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes):
        assert recipe == S.contour_recipe(ACTIVE)
        assert backend == 'mediapipe' and protected_boxes == ()
        assert landmarks is analysis['landmarks']
        assert source.shape == (*expected_shape, 3) and source.dtype == np.float32
        assert excluded is analysis['excluded'] and excluded.shape == expected_shape
        assert analysis['face_skin'].shape == expected_shape
        assert not source.flags.writeable
        field = SyntheticContourField(expected_shape, recipe)
        received.append({'source': source.copy(), 'field': field,
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
    assert prepared.geometry.peak > 0 and np.any(prepared.geometry.owner == 0)
    assert len(prepared.face_fields) == 1 and prepared.effects == ()
    face = prepared.face_fields[0]
    assert type(face) is CONTOUR.ContouredFace
    assert type(face.automatic) is AutomaticField and not face.automatic.units
    assert face.fields[:4] == (None,) * 4 and face.fields[3] is None
    assert face.fields[4] is received['field'] and len(face.fields) == 5
    assert face.prefix.fields == (None,) * 4
    assert received['field'].evaluated_points == shape[0] * shape[1]
    facts = prepared.facts[key]
    assert set(facts) == {'slim_face_v2'}  # Not a second standalone contour edit.
    report = facts['slim_face_v2']
    assert report['operation_id'] == S.OP and report['version'] == 2
    assert report['recipe'] == ACTIVE and report['contour_recipe'] == S.contour_recipe(ACTIVE)
    assert report['contour_facts'] is received['field'].facts
    assert report['profile']['legacy_numeric_or_appearance_equivalent'] is False
    assert prepared.plan['sample_policy'] == 'one_original_source_sample_after_composed_field'


def test_registry_defaults_and_derived_transport_keep_new_operation_separate():
    assert A.SLIM_FACE is S and S.OP == 'lnx.slim_face.v2'
    assert A.GEOMETRY == ('lnx.brow_shape.v1', 'lnx.nose_shape.v1',
                          'lnx.eye_shape.v1', 'lnx.mouth_shape.v1')
    assert S.OP not in A.GEOMETRY and S.OP != A.DEFORM
    assert A.defaults()[S.OP] == {'/linked': True, '/left': 0., '/right': 0.}
    assert '/version' not in A.defaults()[S.OP]
    assert A.defaults()[A.DEFORM]['/slim_face'] == 0.
    assert S.OP in DERIVED.OPERATIONS and C.OP in DERIVED.OPERATIONS
    entries = json.loads((ROOT / 'docs/p0/registry-extensions.json').read_text())['entries']
    matching = [entry for entry in entries if entry['operation_id'] == S.OP]
    assert len(matching) == 1
    assert matching[0]['neutral'] == S.neutral()
    assert matching[0]['requirement_ids'] == ['LNX-REF-PC-32466-C-da1d54e292']
    assert matching[0]['range']['version'] == [2, 2]
    assert matching[0]['range']['left_right'] == [-1, 1]


@pytest.mark.parametrize('path,value', [('/linked', False), ('/left', -.2), ('/right', 1)])
def test_derived_transport_accepts_only_the_portable_typed_leaves(path, value):
    DERIVED._leaf(S.OP, path, value)


@pytest.mark.parametrize('path,value', [('/linked', 1), ('/linked', 'false'),
    ('/left', True), ('/right', False), ('/left', '0.2'), ('/right', 1.1),
    ('/left', float('nan')), ('/right', float('inf')), ('/version', 2),
    ('/slim_face', .2), ('/mask', []), ('/source_sha256', 'a' * 64)])
def test_derived_transport_refuses_coercion_legacy_aliases_and_nonportable_data(path, value):
    with pytest.raises(ValueError):
        DERIVED._leaf(S.OP, path, value)


def test_json_saved_graph_and_history_preserve_v2_values_without_converting_legacy():
    neutral, ref, _, _ = fixture(recipe=S.neutral())
    key = ref['face_instance_id']
    old = P.set_override(neutral, 'face', key, A.DEFORM, '/slim_face', .6)
    # Use the same durable face identity in each history state.
    new = deepcopy(neutral)
    for path, value in A.leaves(ACTIVE).items():
        new = P.set_override(new, 'face', key, S.OP, path, value)
    payload = {'people_graph': new, 'undo': [{'_people_state': old}],
               'redo': [{'_people_state': neutral}]}
    wire = json.dumps(payload, sort_keys=True, allow_nan=False)
    restored = json.loads(wire)
    PROJECT.validate_records(restored)
    assert restored == payload
    for graph, expected_v2, expected_legacy in (
            (restored['people_graph'], ACTIVE, 0.),
            (restored['undo'][0]['_people_state'], S.neutral(), .6),
            (restored['redo'][0]['_people_state'], S.neutral(), 0.)):
        values = A.recipes(RESOLVE.resolve(P.check(graph), key, A.defaults()))
        assert values[S.OP] == expected_v2
        assert values[A.DEFORM]['slim_face'] == expected_legacy
        assert values[C.OP] == C.neutral()
    assert json.dumps(restored, sort_keys=True, allow_nan=False) == wire


def test_absent_v2_in_old_saved_intent_resolves_neutral_without_injecting_overrides():
    state, ref, _, _ = fixture(recipe=S.neutral())
    state['overrides'] = []
    state = P.set_override(state, 'face', ref['face_instance_id'], A.DEFORM, '/slim_face', -.45)
    before = deepcopy(state)
    values = A.recipes(RESOLVE.resolve(state, ref['face_instance_id'], A.defaults()))
    assert values[S.OP] == S.neutral() and values[A.DEFORM]['slim_face'] == -.45
    assert state == before and all(row['operation_id'] != S.OP for row in state['overrides'])
    assert hashlib.sha256((ROOT / 'engine/src/lumaretouch_engine/ops/deform.py').read_bytes()).hexdigest() == LEGACY_SHA256


def test_export_fastpath_blocks_active_v2_or_legacy_but_not_explicit_neutral():
    neutral, ref, _, _ = fixture(recipe=S.neutral())
    snapshot = {'state': neutral, 'asset_sha256': ref['asset_sha256']}
    assert not EXPORT.fastpath_blocker(snapshot)
    for operation, path, amount in ((S.OP, '/left', -.2), (S.OP, '/right', .3),
                                    (A.DEFORM, '/slim_face', .4)):
        changed = P.set_override(neutral, 'face', ref['face_instance_id'], operation, path, amount)
        assert EXPORT.fastpath_blocker({**snapshot, 'state': changed})


@pytest.mark.parametrize('linked', [True, False])
def test_neutral_export_needs_no_analysis_or_new_field_and_preserves_uint16(linked):
    state, ref, _, _ = fixture(recipe={**S.neutral(), 'linked': linked})
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    pixels = original_pixels(128)
    with patch.object(CORE, 'build', side_effect=AssertionError('neutral must bypass contour')) as build:
        prepared = ENGINE.prepare_export(snapshot, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert prepared.face_fields == () and prepared.effects == () and prepared.facts == {}
    assert not prepared.plan['entries'][0]['requires_analysis']
    assert A.recipes(prepared.plan['entries'][0]['resolved'])[S.OP]['linked'] is linked
    np.testing.assert_array_equal(prepared.geometry.warp_original(pixels), pixels)
    assert prepared.geometry.warp_original(pixels).dtype == np.uint16
    assert state == before


@pytest.mark.parametrize('path,value', [('/linked', 1), ('/linked', 0),
    ('/linked', 'false'), ('/left', .2), ('/right', -.2)])
def test_link_only_neutral_exception_still_refuses_malformed_or_active_without_analysis(path, value):
    state, ref, _, _ = fixture(recipe={**S.neutral(), 'linked': False})
    state = P.set_override(state, 'face', ref['face_instance_id'], S.OP, path, value)
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    with patch.object(CORE, 'build', side_effect=AssertionError('missing analysis reached contour')) as build:
        with pytest.raises(RENDER.PeoplePreparationRefused) as error:
            ENGINE.prepare_export(snapshot, original_pixels(128), None,
                                  byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert len(error.value.refusals) == 1
    assert error.value.refusals[0]['face_instance_id'] == ref['face_instance_id']
    # Python equates integer 1 with default True, so recipe validation must
    # still reject its type even when equality made the plan otherwise neutral.
    if path == '/linked' and value == 1:
        assert 'explicit boolean' in str(error.value)
    else:
        assert 'frozen_source_analysis_missing_or_stale' in str(error.value)
    assert state == before


@pytest.mark.parametrize('conflict', ['legacy', 'standalone_contour'])
def test_canonical_conflicts_refuse_before_legacy_builder_without_erasing_intent(conflict):
    state, ref, analysis, _ = fixture()
    op, path = (A.DEFORM, '/slim_face') if conflict == 'legacy' else (C.OP, '/jaw/left')
    state = P.set_override(state, 'face', ref['face_instance_id'], op, path, .25)
    before = deepcopy(state)
    pixels = original_pixels(128).astype(np.float32) / 65535.
    with patch.object(A, 'build_geometry', side_effect=AssertionError('conflict reached legacy builder')) as legacy, \
            patch.object(CORE, 'build', side_effect=AssertionError('conflict reached contour builder')) as contour:
        with pytest.raises(RENDER.PeoplePreparationRefused) as error:
            RENDER.prepare(state, ref['asset_sha256'], pixels, {ref['face_instance_id']: analysis},
                           byte_budget=BUDGET, document_id=DOCUMENT)
    legacy.assert_not_called()
    contour.assert_not_called()
    assert len(error.value.refusals) == 1
    assert error.value.refusals[0]['face_instance_id'] == ref['face_instance_id']
    assert ('neutral legacy' if conflict == 'legacy' else 'cannot coexist') in str(error.value)
    assert state == before


def test_canonical_source_orders_compatibility_before_legacy_and_keeps_mouth_slot_three():
    text = (ROOT / 'engine/src/lumaretouch_engine/people_render_runtime.py').read_text()
    tree = ast.parse(text)
    prepare = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'prepare')
    calls = [node for node in ast.walk(prepare) if isinstance(node, ast.Call)]
    def line(name):
        selected = [node.lineno for node in calls if
                    (isinstance(node.func, ast.Name) and node.func.id == name) or
                    (isinstance(node.func, ast.Attribute) and node.func.attr == name)]
        assert len(selected) == 1
        return selected[0]
    assert line('check_coexistence') < line('build_geometry') < line('append_slim') < line('append_contour')
    assert 'mouth = field.fields[3]' in text and 'mouth = field.fields[-1]' not in text
    assert "facts[key]['slim_face_v2'] = slim_facts" in text


def test_actual_uint16_and_derived_float_export_rebuild_full_grid_and_share_common_map():
    state, ref, analysis, binding = fixture(size=384)
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    derived = {**snapshot, 'creative_source': binding}
    pixels = original_pixels(384)
    original_before = pixels.copy()
    working = pixels.astype(np.float32) / 65535.
    working_before = working.copy()
    assert np.any(pixels % 257 != 0)  # This is not RGB8 multiplied into RGB16.
    received = []
    with patch.object(CORE, 'build', side_effect=contour_builder(received, (384, 384))) as build:
        old = ENGINE.prepare_export(snapshot, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT)
        new = ENGINE.prepare_export(derived, working, None, byte_budget=BUDGET, document_id=DOCUMENT)
    assert build.call_count == len(received) == 2
    for prepared, record in zip((old, new), received):
        assert_canonical_result(prepared, ref, record, (384, 384))
        np.testing.assert_array_equal(record['source'], working)
        assert record['observation']['producer_width'] == record['observation']['producer_height'] == 128
    assert received[0]['field'] is not received[1]['field']
    np.testing.assert_array_equal(old.geometry.delta, new.geometry.delta)
    np.testing.assert_array_equal(old.geometry.owner, new.geometry.owner)
    original_output = old.geometry.warp_original(pixels)
    derived_output = new.geometry.warp(working)
    assert original_output.dtype == np.uint16 and original_output.shape == pixels.shape
    assert np.any(original_output != pixels) and np.any(derived_output != working)
    # Only final original quantization may differ; neither path consumes RGB8.
    np.testing.assert_allclose(original_output.astype(np.float64) / 65535., derived_output,
                               rtol=0, atol=1.1 / 65535.)
    np.testing.assert_array_equal(pixels, original_before)
    np.testing.assert_array_equal(working, working_before)
    assert state == before and snapshot['state'] == before


def test_actual_original_and_derived_preview_keep_real_repair_proof_and_single_map():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding = fixture()
    proxy = (original_pixels(128) // 257).astype(np.uint8)
    working = proxy.astype(np.float32) / 255.
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working.copy()).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    proof = REPLAY.make_evidence(binding, working, None, REPAIRS.digest_ops([], [], binding))
    pipe._creative_repair_source = deepcopy(binding)
    pipe._creative_repair_input = deepcopy(proof['input'])
    pipe._creative_repair_evidence = proof
    received = []
    with patch.object(CORE, 'build', side_effect=contour_builder(received, (128, 128))) as build:
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
    assert REPLAY.verify_pipeline(pipe, binding) == proof
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)


@pytest.mark.parametrize('derived', [False, True])
def test_export_refuses_the_other_source_dtype_before_any_contour_field(derived):
    state, ref, analysis, binding = fixture()
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    pixels = original_pixels(128)
    if derived:
        snapshot['creative_source'] = binding
        wrong_source = pixels  # A creative source is not an original RGB16 decoder.
    else:
        wrong_source = pixels.astype(np.float32) / 65535.
    with patch.object(CORE, 'build', side_effect=AssertionError('invalid dtype reached contour')) as build:
        with pytest.raises(ValueError, match='creative float32' if derived else 'original RGB8/16'):
            ENGINE.prepare_export(snapshot, wrong_source, None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()


def test_derived_preview_missing_repair_proof_is_not_silently_bypassed():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding = fixture()
    proxy = (original_pixels(128) // 257).astype(np.uint8)
    working = proxy.astype(np.float32) / 255.
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    with patch.object(CORE, 'build', side_effect=AssertionError('unbound source reached contour')) as build:
        with pytest.raises(ValueError, match='bound to another immutable source'):
            ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                   byte_budget=BUDGET, document_id=DOCUMENT,
                                   creative_source=binding, creative_proxy=proxy)
    build.assert_not_called()
