"""AUTHORED / UNRUN. Synthetic ownership/routing contracts, not photo evidence.

The explicit contour field double below exercises integration, not the native
deformation or visibility algorithm. No imports or tests ran during authoring.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json

import numpy as np
import pytest

from test_skin_colour_body_render_unrun import fixture
from lumaretouch_engine import face_contour_people as PORT, face_contour_state as C
from lumaretouch_engine import face_contour_runtime as CORE, people_algorithms as A
from lumaretouch_engine import people_state as P, people_export as EXPORT
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine.people_geometry import FaceGeometry

ROOT = Path(__file__).resolve().parents[2]


def active():
    recipe = C.neutral()
    recipe['temple']['left'] = .3
    return recipe


def setup():
    state, _, ref, _, analysis, _, source = fixture(retained=False)
    auto = SimpleNamespace(evaluate=lambda points: np.zeros_like(points), resident_bytes=lambda: 0)
    field = FaceGeometry(ref['face_instance_id'], source.shape[:2], auto, (None,)*4)
    contour = SimpleNamespace(state={'synthetic': True},
        facts={'temple/left': {'requested': True, 'applied': True, 'reason': None}},
        evaluate=lambda points: np.zeros_like(points), resident_bytes=lambda: 64)
    return state, ref, analysis, source, field, contour


def test_three_controls_registered_without_extending_legacy_geometry_tuple():
    assert A.GEOMETRY == ('lnx.brow_shape.v1', 'lnx.nose_shape.v1', 'lnx.eye_shape.v1', 'lnx.mouth_shape.v1')
    assert A.FACE_CONTOUR.OP == C.OP and C.OP not in A.GEOMETRY
    assert A.defaults()[C.OP] == {f'/{key}/{leaf}': value
        for key in ('temple', 'cheekbone', 'jaw')
        for leaf, value in (('linked', True), ('left', 0.), ('right', 0.))}
    assert C.OP in DERIVED.OPERATIONS


def test_neutral_does_not_acquire_or_mutate_a_geometry_owner():
    original = object()
    with patch.object(CORE, 'build', side_effect=AssertionError('neutral must bypass')):
        assert PORT.append(original, None, None, None, None, C.neutral()) == (original, None)


def test_active_appends_only_one_field_and_keeps_source_identity():
    state, ref, analysis, source, field, contour = setup()
    before = source.copy()
    with patch.object(CORE, 'build', return_value=contour) as build:
        result, facts = PORT.append(field, state, ref, analysis, source, active())
    assert result is not field and field.fields == (None,)*4
    assert result.fields[:4] == field.fields and result.fields[4] is contour
    assert result.automatic is field.automatic and result.face_instance_id == field.face_instance_id
    assert result.resident_bytes() == 64 + 256 and facts is contour.facts
    assert build.call_args.args[0] is analysis['landmarks']
    assert build.call_args.args[2] is source
    assert build.call_args.kwargs['analysis'] is analysis
    assert build.call_args.kwargs['protected_boxes'] == ()
    np.testing.assert_array_equal(source, before)


def test_retained_disabled_and_manual_neighbors_are_not_silently_unprotected():
    state, ref, analysis, source, field, contour = setup()
    own = state['faces'][ref['face_instance_id']]
    for index, enabled in enumerate((False, True)):
        other = deepcopy(own)
        other['face_instance_id'] = f'neighbor-{index}'
        other['enabled'] = enabled
        other['box'] = [.05 + index*.2, .1, .15 + index*.2, .4]
        state['faces'][other['face_instance_id']] = other
    foreign = deepcopy(own); foreign['face_instance_id'] = 'other-source'; foreign['asset_sha256'] = 'f'*64
    state['faces']['other-source'] = foreign
    with patch.object(CORE, 'build', return_value=contour) as build:
        PORT.append(field, state, ref, analysis, source, active())
    assert build.call_args.kwargs['protected_boxes'] == ((.05, .1, .15, .4), (.25, .1, .35, .4))


@pytest.mark.parametrize('change', ['identity', 'disabled', 'digest', 'repeat', 'grid'])
def test_stale_foreign_or_repeated_field_refuses_before_build(change):
    state, ref, analysis, source, field, contour = setup()
    if change == 'identity': ref = {**ref, 'analysis_revision': ref['analysis_revision']+1}
    elif change == 'disabled': state['faces'][ref['face_instance_id']]['enabled'] = False
    elif change == 'digest': analysis['landmarks'][0, 0] += .001
    elif change == 'repeat': field = FaceGeometry(field.face_instance_id, field.shape, field.automatic, (*field.fields, contour))
    else: field = FaceGeometry(field.face_instance_id, (64, 64), field.automatic, field.fields)
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        PORT.append(field, state, ref, analysis, source, active())
    build.assert_not_called()


@pytest.mark.parametrize('mode', ['missing', 'no_state', 'refused'])
def test_unsupported_requested_controls_do_not_publish_partial_geometry(mode):
    state, ref, analysis, source, field, contour = setup()
    if mode == 'missing': contour = None
    elif mode == 'no_state': contour.state = None
    else: contour.facts['temple/left'].update(applied=False, reason='occluded')
    with patch.object(CORE, 'build', return_value=contour), pytest.raises(ValueError):
        PORT.append(field, state, ref, analysis, source, active())
    assert field.fields == (None,)*4


def test_contour_composes_actual_off_grid_after_legacy_fields_not_delta_sum():
    points = np.array([[10., 20.], [30., 40.]])
    automatic = SimpleNamespace(evaluate=lambda q: q*.1, resident_bytes=lambda: 0)
    prior = SimpleNamespace(state=True, evaluate=lambda q: np.tile([2., 0.], (len(q), 1)), resident_bytes=lambda: 0)
    contour = SimpleNamespace(state=True, evaluate=lambda q: q*.2, resident_bytes=lambda: 0)
    field = FaceGeometry('synthetic', (64, 64), automatic, (prior, None, None, None, contour))
    first = points*.1 + [2., 0.]
    np.testing.assert_allclose(field.evaluate(points), first + (points-first)*.2)
    assert not np.allclose(field.evaluate(points), first + points*.2)


def test_active_contour_blocks_unedited_export_fastpath():
    state, ref, *_ = setup()
    state = P.set_override(state, 'face', ref['face_instance_id'], C.OP, '/jaw/right', -.2)
    assert EXPORT.fastpath_blocker({'state': state, 'asset_sha256': ref['asset_sha256']})


@pytest.mark.parametrize('stage', ['output', 'before', 'after'])
def test_actual_composed_foreign_face_footprints_refuse_incremental_contour(stage):
    point = np.array([[50. if stage == 'output' else 70., 50.]])
    shift = {'output': [30., 0.], 'before': [20., 0.], 'after': [25., 0.]}[stage]
    prefix = SimpleNamespace(evaluate=lambda q: np.tile(shift, (len(q), 1)), resident_bytes=lambda: 0)
    contour = SimpleNamespace(state=True, evaluate=lambda q: np.tile([-5., 0.], (len(q), 1)), resident_bytes=lambda: 0)
    field = PORT.ContouredFace('synthetic', (101, 101), prefix,
        (None, None, None, None, contour), prefix, ((.49, .49, .51, .51),))
    with pytest.raises(ValueError, match='another retained face'): field.evaluate(point)


def test_composed_contour_refuses_out_of_image_sampling_not_border_replication():
    prefix = SimpleNamespace(evaluate=lambda q: np.zeros_like(q), resident_bytes=lambda: 0)
    contour = SimpleNamespace(state=True, evaluate=lambda q: np.tile([3., 0.], (len(q), 1)), resident_bytes=lambda: 0)
    field = PORT.ContouredFace('synthetic', (101, 101), prefix,
        (None, None, None, None, contour), prefix, ())
    with pytest.raises(ValueError, match='outside the genuine source'): field.evaluate(np.array([[1., 50.]]))


def test_derived_leaf_transport_keeps_boolean_and_amount_types():
    DERIVED._leaf(C.OP, '/temple/linked', False)
    DERIVED._leaf(C.OP, '/cheekbone/left', -.2)
    for path, value in [('/jaw/linked', 1), ('/jaw/right', True), ('/jaw/right', 1.1), ('/mask', [])]:
        with pytest.raises(ValueError): DERIVED._leaf(C.OP, path, value)


def test_canonical_render_keeps_mouth_slot_and_records_contour_separately():
    text = (ROOT/'engine/src/lumaretouch_engine/people_render_runtime.py').read_text()
    assert 'mouth = field.fields[3]' in text
    assert 'mouth = field.fields[-1]' not in text
    assert "facts[key]['face_contour'] = contour_facts" in text
    assert 'append_contour(field, state' in text


def test_exact_mapping_capability_and_offline_staging_are_connected():
    entry = next(row for row in json.loads((ROOT/'docs/p0/registry-extensions.json').read_text())['entries']
                 if row['operation_id'] == C.OP)
    assert entry['requirement_ids'] == ['LNX-REF-PC-32466-C-94bf91612d',
        'LNX-REF-PC-32466-C-d24d97d234', 'LNX-REF-PC-32466-C-3bc7e245b7']
    assert entry['neutral'] == C.neutral()
    assert 'face_contour_capability()' in (ROOT/'engine/src/lumaretouch_engine/server.py').read_text()
    stage = (ROOT/'packaging/stage-engine.sh').read_text()
    assert 'build-face-contour.sh' in stage and 'liblrt_face_contour.so' in stage
    assert 'core/face_contour/face_contour.h' in stage and 'third_party/face_contour/' in stage


def test_original_uint16_and_derived_float_export_rebuild_on_authentic_full_grid():
    from lumaretouch_engine import people_snapshot as SNAP, people_render_runtime as RENDER
    from lumaretouch_engine import people_engine_runtime as ENGINE
    state, ref, analysis, _, _, contour = setup()
    state['links'] = []; state['persons'] = {}; key = ref['face_instance_id']
    for evidence in (state['faces'][key]['evidence'], analysis['evidence']):
        evidence['source_width'] = evidence['source_height'] = 384
    state = P.set_override(state, 'face', key, C.OP, '/jaw/right', -.2)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {key: analysis})
    snapshot.update(document_id='contour-document', support_assets={})
    derived = {**snapshot, 'creative_source': {'sha256': ref['asset_sha256'], 'width': 384, 'height': 384}}
    original = np.full((384, 384, 3), 12345, np.uint16)
    working = original.astype(np.float32)/65535
    auto = SimpleNamespace(evaluate=lambda q: np.zeros_like(q), resident_bytes=lambda: 0)
    def base(face_id, landmarks, values, source, excluded, **kwargs):
        return FaceGeometry(face_id, source.shape[:2], auto, (None,)*4)
    received = []
    def rebuild(landmarks, recipe, source, excluded, **kwargs):
        received.append((source.copy(), kwargs['analysis']['face_skin_observation'].copy()))
        assert source.shape == (384, 384, 3) and excluded.shape == (384, 384)
        assert kwargs['analysis']['face_skin'].shape == (384, 384)
        assert recipe['jaw']['right'] == -.2
        return contour
    def common(fields, shape, **kwargs):
        assert len(fields) == 1 and len(fields[0].fields) == 5
        return SimpleNamespace(delta=np.zeros((1, *shape, 2), np.float32), owner=np.zeros(shape, np.int32))
    with patch.object(CORE, 'build', side_effect=rebuild) as native_port, \
            patch.object(RENDER.A, 'build_geometry', side_effect=base), \
            patch.object(RENDER.E, 'prepare', return_value=[]), \
            patch.object(RENDER, 'combine', side_effect=common) as combined, \
            patch('lumaretouch_engine.eye_light_people.prepare', return_value=[]), \
            patch('lumaretouch_engine.hair_colour_runtime.prepare_bank', return_value=((), {})):
        old = ENGINE.prepare_export(snapshot, original, None, byte_budget=512*1024**2, document_id='contour-document')
        new = ENGINE.prepare_export(derived, working, None, byte_budget=512*1024**2, document_id='contour-document')
    assert native_port.call_count == combined.call_count == 2
    for source, observation in received:
        np.testing.assert_array_equal(source, working)
        assert observation['producer_width'] == observation['producer_height'] == 128
    assert old.facts[key]['face_contour'] == new.facts[key]['face_contour'] == contour.facts
    assert len(old.effects) == len(new.effects) == 0


def test_original_and_derived_preview_share_source_owned_contour_port():
    torch = pytest.importorskip('torch')
    from lumaretouch_engine import people_render_runtime as RENDER, people_engine_runtime as ENGINE
    state, ref, analysis, source, field, contour = setup()
    state['links'] = []; state['persons'] = {}; key = ref['face_instance_id']
    state = P.set_override(state, 'face', key, C.OP, '/temple/left', .3)
    proxy = np.full(source.shape, 102, np.uint8); working = proxy.astype(np.float32)/255
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working).permute(2, 0, 1)[None], repair_base=None)
    creative = {'sha256': ref['asset_sha256'], 'width': 128, 'height': 128}
    geometry = SimpleNamespace(delta=np.zeros((1, 128, 128, 2), np.float32), owner=np.zeros((128, 128), np.int32))
    with patch.object(CORE, 'build', return_value=contour) as rebuild, \
            patch.object(RENDER.A, 'build_geometry', return_value=field), \
            patch.object(RENDER.E, 'prepare', return_value=[]), \
            patch.object(RENDER, 'combine', return_value=geometry), \
            patch('lumaretouch_engine.creative_derived_repair_runtime.verify_pipeline', return_value=None), \
            patch('lumaretouch_engine.eye_light_people.prepare', return_value=[]), \
            patch('lumaretouch_engine.hair_colour_runtime.prepare_bank', return_value=((), {})):
        ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {key: analysis},
            byte_budget=512*1024**2, document_id='contour-document')
        ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {key: analysis},
            byte_budget=512*1024**2, document_id='contour-document', creative_source=creative, creative_proxy=proxy)
    assert rebuild.call_count == 2
    for call in rebuild.call_args_list: np.testing.assert_array_equal(call.args[2], working)
