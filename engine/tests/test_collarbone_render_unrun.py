# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: manual-assisted partial collarbone render contracts.

LNX-REF-PC-32465-C-abf0a5c8c9 is NOT AI/3D or photographic acceptance.
No tests, collection, product imports, native execution, build, typecheck,
inference or downloads were run while authoring these fixtures. Synthetic
source/analysis data and native-only doubles establish routing intentions,
not successful execution, anatomical inference or native numerical quality.

Real ownership, support, graph, snapshot, source adapters and compositors stay
in the path. Only native prepare/compose/availability and the existing mask
worker are doubled. The conspicuously simple apply double is deliberately NOT
the Rust algorithm; it lets current-pixel/ROI/tile routing fail independently.
"""
import ast
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import collarbone_state as S, collarbone_native as N
from lumaretouch_engine import collarbone_composition as C
from lumaretouch_engine import people_effects as EFFECTS, people_pipeline as PIPE
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_project as PROJECT, people_export as EXPORT
from lumaretouch_engine import people_render_runtime as RENDER
from lumaretouch_engine import people_engine_runtime as ENGINE
from lumaretouch_engine import people_support_assets as ASSETS
from lumaretouch_engine import skin_colour_body_support as SUPPORT
from lumaretouch_engine import local_mask_recipe as MASK
from lumaretouch_engine import arm_shape_project as BODY_PROJECT
from test_body_skin_evenness_integration_unrun import (
    fixture as body_fixture, ManualWorkerDouble, frozen, set_recipe, BUDGET, DOCUMENT,
)

ROOT = Path(__file__).resolve().parents[2]
FAMILY = {'family': 'collarbone', 'operation_id': S.OP}
ACTIVE = {'version': 1, 'amount': .65}


def local_record(*, shape=(20, 24), origin=(5, 7), face='collarbone-test-face', amount=.65):
    field = np.full((*shape, 1), .04, np.float32)
    field[::3, :, 0] = -.03
    field[:, :2, 0] = 0
    field.setflags(write=False)
    return EFFECTS.LocalEffect({'asset_sha256': 'a'*64, 'face_instance_id': face, 'analysis_revision': 1},
        'collarbone', (*origin, *shape), log_gain=field, amounts={'amount': amount})


def apply_double(calls):
    def apply(current, field, amount, *, field_origin, source_shape, origin=(0, 0), cancelled=None):
        assert current.dtype == field.dtype == np.float32
        assert current.shape[:2] == field.shape and current.shape[2] == 3
        assert field_origin == origin
        assert 0 <= origin[0] and origin[0]+field.shape[1] <= source_shape[1]
        assert 0 <= origin[1] and origin[1]+field.shape[0] <= source_shape[0]
        assert field.size <= C.MAX_CHUNK_PIXELS
        calls.append({'pixels': current.copy(), 'field': field.copy(), 'amount': amount,
                      'origin': origin, 'source_shape': source_shape})
        # Routing seam only, NOT proposed product math or numeric parity proof.
        output = np.array(current, copy=True)
        output[field != 0] *= np.float32(1)+np.float32(amount)*field[field != 0, None]
        return output
    return apply


def prepare_double(calls):
    def prepare(reference_rgb, coverage, curves, *, cancelled=None):
        calls.append({'source': reference_rgb.copy(), 'coverage': coverage.copy(), 'curves': deepcopy(curves)})
        ys, xs = np.nonzero(coverage > 0)
        y, x = int(ys.min()), int(xs.min())
        end_y, end_x = int(ys.max())+1, int(xs.max())+1
        rgb = reference_rgb[y:end_y, x:end_x]
        admitted = coverage[y:end_y, x:end_x]
        field = ((rgb[..., 0]-rgb[..., 1])*.1*admitted).astype(np.float32)
        field[admitted == 0] = 0; field.setflags(write=False)
        return SimpleNamespace(field=field, origin=(x, y), source_shape=reference_rgb.shape[:2],
            report={'fixture_only': True, 'runtime_quality_accepted': False,
                    'supported_pixels': int(np.count_nonzero(field))})
    return prepare


def owned_fixture(*, recipe=ACTIVE, retained=True):
    value = body_fixture(recipe=None, retained=False)
    value.review['clavicle'] = {'version': 1, 'domain': 'source-normalized',
        'category': 'female', 'eligibility_confirmed': True, 'visible_anatomy_confirmed': True,
        'curves': [{'id': 'left', 'points': [[.36, .46], [.42, .445], [.48, .45]], 'width': .025},
                   {'id': 'right', 'points': [[.52, .45], [.58, .445], [.64, .46]], 'width': .025}]}
    if retained:
        value.state, value.assets = SUPPORT.retain(value.state, value.assets, value.ref,
            value.bank, value.analysis, value.review, **FAMILY)
    value.state = set_recipe(value.state, value.ref, recipe, operation=S.OP)
    return value


def test_stage_order_is_real_pipeline_order_not_only_a_registry_entry():
    order = ('body_face_match', 'body_skin_evenness', 'collarbone', 'skin_evenness', 'skin_colour')
    tree = ast.parse((ROOT/'engine/src/lumaretouch_engine/vram.py').read_text())
    stages = [(node.lineno, node.args[1].value) for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == 'PEOPLE_PIPE'
        and node.func.attr == 'source_effect' and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)]
    actual = [name for _, name in sorted(stages) if name in order]
    assert actual == list(order)
    assert [EFFECTS.STAGES.index(name) for name in order] == sorted(EFFECTS.STAGES.index(name) for name in order)
    assert S.OP in A.specifications() and A.defaults()[S.OP] == {'/amount': 0.}
    assert S.CONTROL_ID == 'LNX-REF-PC-32465-C-abf0a5c8c9'


def test_no_record_identity_never_calls_native_or_requests_source_analysis():
    pixels = np.full((30, 40, 3), .4, np.float32)
    with patch.object(N, 'compose_field', side_effect=AssertionError('Neutral entered native')) as apply, \
            patch.object(N, 'prepare', side_effect=AssertionError('Neutral re-solved source')) as prepare:
        out, facts = EFFECTS.apply('collarbone', pixels, ())
    assert out is pixels and facts['changed_pixels'] == 0
    apply.assert_not_called(); prepare.assert_not_called()


def test_current_pixels_not_source_delta_and_unowned_bytes_remain_exact():
    record = local_record(); current = np.full((40, 50, 3), [.31, .4, .58], np.float32)
    before = current.copy(); calls = []
    with patch.object(N, 'compose_field', side_effect=apply_double(calls)), \
            patch.object(N, 'prepare', side_effect=AssertionError('Composition re-solved source')):
        out, facts = EFFECTS.apply('collarbone', current, (record,))
    assert facts['changed_pixels'] > 0 and facts['overlap_pixels'] == 0
    np.testing.assert_array_equal(current, before)
    y, x, h, w = record.window
    np.testing.assert_array_equal(calls[0]['pixels'], current[y:y+h, x:x+w])
    assert calls[0]['origin'] == (x, y) and calls[0]['source_shape'] == current.shape[:2]
    np.testing.assert_array_equal(out[:y], current[:y])
    np.testing.assert_array_equal(out[y:y+h, x:x+2], current[y:y+h, x:x+2])
    assert record.delta is None and record.chroma_shift is None


def test_actual_tensor_pipeline_full_and_nonzero_origin_tiles_use_same_rust_boundary():
    import torch
    record = local_record(); source = np.full((40, 50, 3), [.31, .4, .58], np.float32)
    # Distinct upstream changes make sampling an old frozen source fail visibly.
    current = source*.87; current[9:22, 11:25] *= .91
    delta = np.zeros((1, 40, 50, 2), np.float32)
    prepared = SimpleNamespace(effects=(record,), recovery={}, geometry=SimpleNamespace(delta=delta))
    def pipe(origin, shape):
        return SimpleNamespace(people_prepared=prepared, people_origin=origin, h=shape[0], w=shape[1])
    full = torch.tensor(current.transpose(2, 0, 1)[None]); calls = []
    with patch.object(N, 'compose_field', side_effect=apply_double(calls)), \
            patch.object(N, 'prepare', side_effect=AssertionError('Tile re-solved field')):
        expected, _ = EFFECTS.apply('collarbone', current, prepared.effects)
        result = PIPE.source_effect(pipe((0, 0), (40, 50)), 'collarbone', full)
        oy, ox, h, w = 8, 10, 14, 19
        tile = full[:, :, oy:oy+h, ox:ox+w].clone()
        actual = PIPE.source_effect(pipe((oy, ox), (h, w)), 'collarbone', tile)
        outside = full[:, :, 30:35, 35:40].clone()
        count = len(calls)
        untouched = PIPE.source_effect(pipe((30, 35), (5, 5)), 'collarbone', outside)
    np.testing.assert_array_equal(result[0].permute(1, 2, 0).numpy(), expected)
    np.testing.assert_array_equal(actual[0].permute(1, 2, 0).numpy(), expected[oy:oy+h, ox:ox+w])
    assert untouched is outside and len(calls) == count
    np.testing.assert_array_equal(full[0].permute(1, 2, 0).numpy(), current)
    assert any(row['origin'] == (ox, oy) for row in calls)


def test_large_current_intersection_is_bounded_and_frozen_field_is_not_resolved_per_strip():
    record = local_record(shape=(600, 512), origin=(0, 0))
    current = np.full((600, 512, 3), .45, np.float32); calls = []
    with patch.object(N, 'compose_field', side_effect=apply_double(calls)), \
            patch.object(N, 'prepare', side_effect=AssertionError('Strip source solve')):
        out, _ = EFFECTS.apply('collarbone', current, (record,))
    assert out.shape == current.shape and len(calls) >= 3
    assert all(row['field'].size <= C.MAX_CHUNK_PIXELS for row in calls)
    assert sum(row['field'].size for row in calls) == 600*512
    assert not record.log_gain.flags.writeable


@pytest.mark.parametrize('fault', ['alpha', 'hdr', 'negative', 'nan', 'float64', 'writable-field',
                                  'field-bound', 'field-nan', 'rgb-delta', 'bool-amount', 'face-recovery'])
def test_invalid_active_inputs_refuse_before_native_publication(fault):
    record = local_record(); current = np.full((40, 50, 3), .4, np.float32); recovery = {}
    if fault == 'alpha': current = np.full((40, 50, 4), .4, np.float32)
    elif fault == 'hdr': current[0, 0, 0] = 1.01
    elif fault == 'negative': current[0, 0, 0] = -.01
    elif fault == 'nan': current[0, 0, 0] = np.nan
    elif fault == 'float64': current = current.astype(np.float64)
    elif fault in ('writable-field', 'field-bound', 'field-nan'):
        field = record.log_gain.copy()
        if fault == 'field-bound': field[0, 0, 0] = .5
        elif fault == 'field-nan': field[0, 0, 0] = np.nan
        if fault != 'writable-field': field.setflags(write=False)
        record = replace(record, log_gain=field)
    elif fault == 'rgb-delta': record = replace(record, delta=np.zeros((*record.window[2:], 3), np.float32))
    elif fault == 'bool-amount': record = replace(record, amounts={'amount': False})
    else: recovery[(record.face_ref['face_instance_id'], 'collarbone')] = {'weight': 'not admitted'}
    with patch.object(N, 'compose_field', side_effect=AssertionError('Invalid input entered native')) as apply:
        with pytest.raises(ValueError): EFFECTS.apply('collarbone', current, (record,), recovery=recovery)
    apply.assert_not_called()


def test_overlapping_owners_refuse_instead_of_silently_choosing_one_face():
    first = local_record(face='a-face'); second = local_record(face='b-face')
    current = np.full((40, 50, 3), .4, np.float32); before = current.copy()
    with patch.object(N, 'compose_field', side_effect=apply_double([])):
        with pytest.raises(ValueError, match='overlap'):
            EFFECTS.apply('collarbone', current, (second, first))
    np.testing.assert_array_equal(current, before)


@pytest.mark.parametrize('derived', [False, True])
def test_original16_and_derived_export_share_owned_support_and_actual_source_layer(derived):
    value = owned_fixture(); snap = frozen(value, derived=derived)
    source = value.original.astype(np.float32)/65535. if derived else value.original
    before = source.copy(); solves = []; applies = []
    with patch.object(MASK, '_Worker', ManualWorkerDouble), patch.object(N, 'available', return_value=True), \
            patch.object(N, 'prepare', side_effect=prepare_double(solves)), \
            patch.object(N, 'compose_field', side_effect=apply_double(applies)):
        prepared = ENGINE.prepare_export(snap, source, None, byte_budget=BUDGET, document_id=DOCUMENT,
            body_pose=BODY_PROJECT.snapshot(value.bank, value.frame))
        assert len(prepared.effects) == 1
        record = prepared.effects[0]
        assert record.stage == 'collarbone' and record.face_ref == value.ref
        assert record.facts['body_ref'] == value.review['body_ref']
        assert record.facts['runtime_quality_accepted'] is False
        assert record.log_gain.dtype == np.float32 and not record.log_gain.flags.writeable
        current = source.astype(np.float32)/(1 if derived else 65535.)*.9
        result, facts = prepared.apply_source_stage('collarbone', current)
    assert len(solves) == 1 and facts['changed_pixels'] > 0
    np.testing.assert_array_equal(solves[0]['source'], before.astype(np.float32)/(1 if derived else 65535.))
    np.testing.assert_array_equal(source, before)
    assert result.shape == current.shape and applies
    assert all(row['source_shape'] == source.shape[:2] for row in applies)
    assert RENDER.retained_bytes(prepared, include_geometry=False) >= record.log_gain.nbytes


def test_original_export_field_uses_effective_repaired_source_not_later_stage_pixels():
    value = owned_fixture(); solves = []
    repaired = (value.original.astype(np.float32)/65535.*.91).astype(np.float32)
    with patch.object(MASK, '_Worker', ManualWorkerDouble), patch.object(N, 'available', return_value=True), \
            patch.object(N, 'prepare', side_effect=prepare_double(solves)):
        ENGINE.prepare_export(frozen(value), value.original, repaired, byte_budget=BUDGET,
            document_id=DOCUMENT, body_pose=BODY_PROJECT.snapshot(value.bank, value.frame))
    assert len(solves) == 1
    np.testing.assert_array_equal(solves[0]['source'], repaired)


@pytest.mark.parametrize('strength', [0., .4])
def test_real_retouch_prefix_consumes_upstream_light_and_smoothing_pixels(strength):
    from lumaretouch_engine.vram import PreviewPipeline, LightOp
    value = owned_fixture(); source = value.original.astype(np.float32)/65535.
    solves = []; calls = []; pipes = []
    with patch.object(MASK, '_Worker', ManualWorkerDouble), patch.object(N, 'available', return_value=True), \
            patch.object(N, 'prepare', side_effect=prepare_double(solves)), \
            patch.object(N, 'compose_field', side_effect=apply_double(calls)):
        prepared = ENGINE.prepare_export(frozen(value), value.original, None, byte_budget=BUDGET,
            document_id=DOCUMENT, body_pose=BODY_PROJECT.snapshot(value.bank, value.frame))
        for _ in range(2):
            pipe = PreviewPipeline('cpu', 256, 256)
            pipe.load_rgb_f32(source.copy())
            pipe.set_light_params(.35, 4)
            pipe.set_light_ops([LightOp(1, np.full((256, 256), 180, np.uint8), sign=-1)])
            pipes.append(pipe)
        settings = {'radius': 6, 'texture_radius': 2, 'broad_gain': .55, 'mid_gain': .7, 'detail_gain': .85}
        baseline = pipes[0].retouch(strength, **settings)[0].permute(1, 2, 0).numpy()
        assert np.any(np.abs(baseline-source) > 1e-4)
        expected, facts = prepared.apply_source_stage('collarbone', baseline)
        PIPE.install(pipes[1], prepared)
        actual = pipes[1].retouch(strength, **settings)[0].permute(1, 2, 0).numpy()
    assert len(solves) == 1 and facts['changed_pixels'] > 0 and calls
    np.testing.assert_allclose(actual, expected, rtol=0, atol=3e-6)
    np.testing.assert_array_equal(pipes[1].src_f32[0].permute(1, 2, 0).numpy(), source)


def test_real_full_candidate_review_and_live_preview_share_stage_without_early_publication(tmp_path):
    from test_body_face_match_integration_unrun import file_backed_engine
    from lumaretouch_engine import skin_colour_body_host as HOST
    from lumaretouch_engine import optics_candidate_identity as IDENTITY
    engine, value, target, row = file_backed_engine(tmp_path)
    value.review['clavicle'] = owned_fixture(retained=False).review['clavicle']
    owner = engine._people_owner(); before = owner.snapshot()
    original = Path(row['path']).read_bytes()
    digest = IDENTITY.fingerprint(engine._capture_state())
    version = engine._document_versions().version(row)
    solves = []; calls = []
    with patch.object(MASK, '_Worker', ManualWorkerDouble), patch.object(N, 'available', return_value=True), \
            patch.object(N, 'prepare', side_effect=prepare_double(solves)), \
            patch.object(N, 'compose_field', side_effect=apply_double(calls)):
        reference = HOST.reference(engine, before, target, {}, **FAMILY)
        assert reference['attached'] is False
        shown = HOST.preview(engine, before, target,
            {'review': value.review, 'amount': ACTIVE['amount']}, **FAMILY)
        assert shown['before']['base64'] != shown['after']['base64']
        assert shown['runtime_quality_accepted'] is False
        assert shown['overlay']['mapping'] == 'normalized_full_frame'
        assert engine._collarbone_preview['after_proof']['source_size'] == [256, 256]
        assert owner.snapshot() == before and owner.fence == 0 and engine._people_support == {}
        assert engine._document_versions().version(row) == version
        assert IDENTITY.fingerprint(engine._capture_state()) == digest
        assert solves and calls  # Actual full candidate entered our real source stage.
        with pytest.raises(ValueError):
            HOST.confirm(engine, before, target, {'preview_id': 'wrong-review', 'reviewed': True}, **FAMILY)
        candidate, reply = HOST.confirm(engine, before, target,
            {'preview_id': shown['preview_id'], 'reviewed': True}, **FAMILY)
        assert reply == {'kind': 'confirmed', 'attached': True, **FAMILY}
        assert owner.snapshot() == before
        prepared = ENGINE.prepare_preview(engine._vram, candidate, value.binding['sha256'],
            {value.ref['face_instance_id']: value.analysis}, byte_budget=BUDGET, document_id=DOCUMENT,
            body_bank=value.bank, body_source=value.binding, collarbone_assets=engine._people_support)
        assert any(record.stage == 'collarbone' for record in prepared.effects)
        # Genuine RGB16 candidate solve is distinct from live RGB8 analysis proxy.
        assert not np.array_equal(solves[0]['source'], solves[-1]['source'])
        owner.commit(candidate, expected_fence=0)
        assert owner.fence == 1
    assert Path(row['path']).read_bytes() == original
    assert engine._collarbone_preview is None and engine._collarbone_reference is None


@pytest.mark.parametrize('retained', [False, True])
def test_neutral_dormant_review_needs_no_analysis_body_native_or_new_mask(retained):
    value = owned_fixture(recipe=S.neutral(), retained=retained)
    source = value.original.astype(np.float32)/65535.
    with patch.object(N, 'prepare', side_effect=AssertionError('Neutral source solve')) as prepare, \
            patch.object(N, 'available', side_effect=AssertionError('Neutral native load')) as available, \
            patch.object(MASK, '_Worker', side_effect=AssertionError('Neutral support raster')):
        prepared = RENDER.prepare(value.state, value.binding['sha256'], source, {},
            document_id=DOCUMENT, byte_budget=BUDGET, collarbone_assets=value.assets)
        out, facts = prepared.apply_source_stage('collarbone', source)
    assert not prepared.effects and out is source and facts['changed_pixels'] == 0
    assert not prepared.plan['entries'][0]['requires_analysis']
    prepare.assert_not_called(); available.assert_not_called()
    # Dedicated review assets never enter generic facial recovery rasterization.
    assert ASSETS.raster(value.state, value.assets, value.binding['sha256'], source.shape[:2]) == {}


@pytest.mark.parametrize('value', [False, True, '0', -1, 1.1])
def test_no_face_malformed_intent_blocks_passthrough_and_recursive_history(value):
    state = P.set_override(P.empty(), 'all_people', 'a'*64, S.OP, '/amount', value)
    snap = {'state': state, 'asset_sha256': 'a'*64}
    assert EXPORT.fastpath_blocker(snap)
    for project in ({'people_graph': state}, {'undo': [{'people_graph': state}]},
                    {'redo': [{'state': {'_people_state': state}}]}):
        with pytest.raises(ValueError): PROJECT.validate_records(project)


@pytest.mark.parametrize('value', [float('nan'), float('inf')])
def test_nonfinite_intent_is_rejected_even_before_feature_recipe_validation(value):
    with pytest.raises(ValueError):
        P.set_override(P.empty(), 'all_people', 'a'*64, S.OP, '/amount', value)


def test_active_review_is_not_face_recovery_and_unresolved_source_cannot_silently_export():
    value = owned_fixture(); saved = deepcopy(value.state)
    assert EXPORT.fastpath_blocker(frozen(value))
    assert ASSETS.raster(value.state, value.assets, value.binding['sha256'], value.original.shape[:2]) == {}
    with patch.object(N, 'prepare', side_effect=AssertionError('Missing ownership reached native')) as prepare:
        with pytest.raises(ValueError):
            RENDER.prepare(value.state, value.binding['sha256'], value.original.astype(np.float32)/65535.,
                {value.ref['face_instance_id']: value.analysis}, byte_budget=BUDGET,
                document_id=DOCUMENT, collarbone_assets=value.assets, body_bank=None)
    prepare.assert_not_called()
    assert value.state == saved
