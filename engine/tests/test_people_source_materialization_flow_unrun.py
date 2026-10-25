# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: opt-in portrait source materialization flow contracts.

No product imports, collection, tests, native execution, build, typecheck,
inference or downloads were run while authoring. Synthetic pixels, landmarks
and model hashes are labelled routing fixtures, not photographic acceptance.
The small preparation capture double isolates source transport, not rendering.
Real source/document/derived-repair checks and semantic admission stay in that
path. The final active-effect fixture instead keeps real preparation and uses
the established, explicitly synthetic skin-evenness native-boundary doubles.

Exact comparisons below are authored byte-parity expectations for the legacy
NumPy expression, not a claim of executed numerical or memory acceptance.
"""
from copy import deepcopy
import ctypes
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import people_engine_runtime as ENGINE
from lumaretouch_engine import people_export as EXPORT
from lumaretouch_engine import people_snapshot as SNAPSHOT
from lumaretouch_engine import people_state as STATE
from lumaretouch_engine import people_source_materialization as MATERIALIZE
from lumaretouch_engine import people_render_runtime as RENDER
from lumaretouch_engine import cpu_memory_budget as BUDGET_SOURCE
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY
from lumaretouch_engine import creative_derived_repairs as REPAIRS


DOCUMENT = 'synthetic-source-materialization-document'
ASSET = 'a' * 64
BUDGET = 512 * 1024**2
SUPPORT_PORTS = (
    'eye_light_assets', 'blush_makeup_assets', 'face_decoration_assets',
    'facial_sculpt_assets', 'eye_makeup_enhance_assets', 'lipstick_assets',
    'eyeliner_assets', 'eyelash_assets', 'brow_makeup_assets', 'iris_makeup_assets',
    'skin_colour_body_assets', 'skin_finish_body_assets',
    'body_skin_evenness_assets', 'body_face_match_assets', 'collarbone_assets',
    'eye_bag_preserve_assets',
)


def pixels(kind, shape=(7, 11)):
    """Own exact SDR samples, including low bits absent from an RGB8 proxy."""
    if kind == 'rgb8':
        values = np.array([0, 1, 2, 17, 127, 128, 254, 255], np.uint8)
    elif kind == 'rgb16':
        values = np.array([0, 1, 255, 256, 257, 1023, 10001, 32767,
                           32768, 32769, 65533, 65534, 65535], np.uint16)
    else:
        assert kind == 'derived'
        values = np.array([-0., 0., np.nextafter(np.float32(0), np.float32(1)),
                           .000013, .04045, .500013, .777771,
                           np.nextafter(np.float32(1), np.float32(0)), 1.], np.float32)
    out = np.array(np.resize(values, (*shape, 3)), copy=True)
    out.setflags(write=False)
    return out


def divisor(kind):
    return {'rgb8': 255, 'rgb16': 65535, 'derived': 1}[kind]


def legacy_pixels(source, scale):
    # Keep the literal old expression, including both its cast and final copy.
    return np.array(source.astype(np.float32) / scale, dtype=np.float32, copy=True)


def snapshot(source, *, derived=False, semantics=True):
    """Fabricated evidence exercises real schema guards, never model quality."""
    height, width = source.shape[:2]
    value = {'state': STATE.empty(), 'asset_sha256': ASSET, 'document_id': DOCUMENT,
             'analyses': {}, 'support_assets': {}}
    if semantics:
        landmarks = np.zeros((478, 3), dtype='<f4')
        landmarks.setflags(write=False)
        evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b' * 64,
            'semantic_model_sha256': 'c' * 64,
            'landmark_digest': sha256(landmarks.tobytes()).hexdigest(),
            'status': 'verified', 'source_width': width, 'source_height': height,
            'orientation': 'exif_normalized_once'}
        face = STATE.new_face(ASSET, [.1, .1, .9, .9], evidence)
        value['state']['faces'][face['face_instance_id']] = face
        skin = np.full((height, width), .625, np.float32)
        excluded = np.zeros((height, width), np.float32)
        skin.setflags(write=False)
        excluded.setflags(write=False)
        value['analyses'][face['face_instance_id']] = {
            'face_ref': STATE.face_ref(face), 'evidence': deepcopy(evidence),
            'landmarks': landmarks, 'excluded': excluded, 'skin': skin}
    if derived:
        value['creative_source'] = {'sha256': ASSET, 'width': width, 'height': height}
    return value


class PreparationCaptureDouble:
    """Synthetic routing sink only, deliberately not a PreparedPeople solver."""

    def __init__(self):
        self.calls = []
        self.result = object()

    def __call__(self, state, asset, source, analyses, **kwargs):
        self.calls.append({'state': state, 'asset': asset, 'source': source,
                           'analyses': analyses, 'kwargs': kwargs})
        return self.result


def direct(value, source, repaired=None, **kwargs):
    return ENGINE.prepare_export(value, source, repaired, byte_budget=BUDGET,
                                 document_id=DOCUMENT, **kwargs)


def assert_exact_private_source(actual, expected, original):
    assert type(actual) is np.ndarray and actual.dtype == np.float32
    assert actual.shape == original.shape and not actual.flags.writeable
    assert not np.shares_memory(actual, original)
    # Bytes additionally pin signed zero, not just numerical equality.
    assert actual.tobytes(order='C') == expected.tobytes(order='C')


@pytest.mark.parametrize('kind', ['rgb8', 'rgb16', 'derived'])
def test_unversioned_direct_caller_keeps_exact_legacy_default(kind):
    source = pixels(kind)
    value = snapshot(source, derived=kind == 'derived')
    sink = PreparationCaptureDouble()
    forbidden = AssertionError('Legacy default entered opt-in materialization')
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(MATERIALIZE, 'can_materialize_export_source', side_effect=forbidden), \
            patch.object(MATERIALIZE, 'inspect_export_source', side_effect=forbidden), \
            patch.object(MATERIALIZE, 'materialize_export_source', side_effect=forbidden):
        assert direct(value, source) is sink.result
        assert direct(value, source, source_materialization_version=0) is sink.result
    assert len(sink.calls) == 2
    for call in sink.calls:
        assert_exact_private_source(call['source'], legacy_pixels(source, divisor(kind)), source)


@pytest.mark.parametrize('kind', ['rgb8', 'rgb16', 'derived'])
@pytest.mark.parametrize('layout', ['owning', 'reversed'])
def test_opted_adapter_matches_legacy_across_block_boundary_without_mutation(kind, layout):
    owned = pixels(kind, (257, 257))  # More than one 65,536-pixel block.
    source = owned if layout == 'owning' else owned[::-1, ::-1, :]
    value = snapshot(source, derived=kind == 'derived')
    before, state_before = source.tobytes(), deepcopy(value['state'])
    sink = PreparationCaptureDouble()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(MATERIALIZE, 'materialize_export_source',
                         wraps=MATERIALIZE.materialize_export_source) as materialize:
        assert direct(value, source, source_materialization_version=1) is sink.result
    materialize.assert_called_once()
    assert materialize.call_args.args[0] is source
    assert materialize.call_args.args[1] == divisor(kind)
    assert_exact_private_source(sink.calls[0]['source'], legacy_pixels(source, divisor(kind)), source)
    assert source.tobytes() == before and not source.flags.writeable
    assert value['state'] == state_before
    for key, original in value['analyses'].items():
        copied = sink.calls[0]['analyses'][key]
        assert copied['landmarks'] is original['landmarks']
        for name in ('skin', 'excluded'):
            assert not copied[name].flags.writeable
            assert not np.shares_memory(copied[name], original[name])
            np.testing.assert_array_equal(copied[name], original[name])


@pytest.mark.parametrize('kind', ['rgb8', 'rgb16', 'derived'])
def test_actual_public_prepare_opts_in_and_keeps_all_source_support_ports(kind):
    source = pixels(kind)
    value = snapshot(source, derived=kind == 'derived')
    spec = SimpleNamespace(people=value, people_document_id=DOCUMENT, body_pose=None)
    sink = PreparationCaptureDouble()
    with patch.object(BUDGET_SOURCE, 'available_estimate', return_value=BUDGET), \
            patch.object(ENGINE, 'prepare_export', wraps=ENGINE.prepare_export) as adapter, \
            patch.object(ENGINE, 'prepare', sink), \
            patch.object(MATERIALIZE, 'materialize_export_source',
                         wraps=MATERIALIZE.materialize_export_source) as materialize:
        assert EXPORT.prepare(spec, source, None) is sink.result
    adapter.assert_called_once()
    assert adapter.call_args.kwargs['source_materialization_version'] == 1
    materialize.assert_called_once()
    call = sink.calls[0]
    assert call['asset'] == ASSET and call['state'] == value['state']
    assert call['kwargs']['byte_budget'] == BUDGET
    assert call['kwargs']['document_id'] == DOCUMENT
    assert call['kwargs']['force_hair_prompted'] is True
    assert call['kwargs']['repaired'] is None and call['kwargs']['body_bank'] is None
    assert call['kwargs']['recovery_assets'] == {}
    for name in SUPPORT_PORTS:
        assert call['kwargs'][name] is value['support_assets']
    if kind == 'derived':
        assert call['kwargs']['creative_source'] is value['creative_source']
        assert call['kwargs']['creative_repair_evidence'] is None
        assert 'hair_source_path' not in call['kwargs']
    else:
        assert call['kwargs']['hair_source_path'] is None
        assert 'creative_source' not in call['kwargs']
    assert_exact_private_source(call['source'], legacy_pixels(source, divisor(kind)), source)
    assert spec.people is value


def test_public_route_without_people_does_not_prepare_or_materialize():
    with patch.object(ENGINE, 'prepare_export', side_effect=AssertionError('No portrait graph')), \
            patch.object(MATERIALIZE, 'materialize_export_source',
                         side_effect=AssertionError('No portrait source')):
        assert EXPORT.prepare(SimpleNamespace(people=None), None, None) is None


@pytest.mark.parametrize('kind', ['rgb8', 'rgb16', 'derived'])
def test_unknown_backing_alone_selects_legacy_before_optional_allocation(kind):
    original = pixels(kind)
    # Ctypes is an opaque buffer owner, not a recognized ndarray/bytes owner.
    # Its valid pixel representation remains admitted by the legacy adapter.
    storage = (ctypes.c_uint8 * original.nbytes).from_buffer_copy(original.tobytes())
    source = np.ndarray(original.shape, dtype=original.dtype, buffer=storage)
    source.setflags(write=False)
    value = snapshot(source, derived=kind == 'derived')
    assert MATERIALIZE.can_materialize_export_source(source, divisor(kind)) is False
    sink = PreparationCaptureDouble()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(MATERIALIZE, 'materialize_export_source',
                         side_effect=AssertionError('Opaque backing reached optional allocation')) as materialize:
        assert direct(value, source, source_materialization_version=1) is sink.result
    materialize.assert_not_called()
    assert_exact_private_source(sink.calls[0]['source'], legacy_pixels(source, divisor(kind)), source)
    assert source.tobytes() == original.tobytes()


@pytest.mark.parametrize('version', [None, False, True, -1, 2, 1., '1', np.int64(1)])
def test_invalid_version_refuses_before_even_source_or_snapshot_inspection(version):
    # Deliberately invalid later arguments prove strategy rejection runs first.
    forbidden = AssertionError('Invalid version reached downstream preparation')
    with patch.object(SNAPSHOT, 'at_dimensions', side_effect=forbidden) as dimensions, \
            patch.object(ENGINE, 'prepare', side_effect=forbidden) as prepare, \
            patch.object(MATERIALIZE, 'can_materialize_export_source', side_effect=forbidden) as probe:
        with pytest.raises(ValueError, match='materialization strategy'):
            ENGINE.prepare_export(None, object(), None, byte_budget=None,
                                  source_materialization_version=version)
    dimensions.assert_not_called()
    prepare.assert_not_called()
    probe.assert_not_called()


@pytest.mark.parametrize('kind', ['rgb8', 'rgb16', 'derived'])
@pytest.mark.parametrize('version', [0, 1])
def test_existing_repaired_buffer_identity_and_real_derived_proof_are_preserved(kind, version):
    source = pixels(kind)
    value = snapshot(source, derived=kind == 'derived')
    repaired = legacy_pixels(source, divisor(kind)) * np.float32(.91)
    repaired.setflags(write=False)
    source_before, repair_before = source.tobytes(), repaired.tobytes()
    proof = None
    if kind == 'derived':
        binding = value['creative_source']
        proof = REPLAY.make_evidence(binding, source, repaired, REPAIRS.digest_ops([], [], binding))
    sink = PreparationCaptureDouble()
    with patch.object(ENGINE, 'prepare', sink):
        assert direct(value, source, repaired, creative_repair_evidence=proof,
                      source_materialization_version=version) is sink.result
    assert sink.calls[0]['kwargs']['repaired'] is repaired
    if kind == 'derived':
        assert sink.calls[0]['kwargs']['creative_repair_evidence'] is proof
        REPLAY.verify_evidence(proof, value['creative_source'], sink.calls[0]['source'], repaired)
    assert source.tobytes() == source_before and repaired.tobytes() == repair_before
    assert not repaired.flags.writeable


@pytest.mark.parametrize('fault', ['missing', 'changed-input', 'changed-output', 'wrong-source'])
def test_opted_derived_repair_proof_failure_cannot_publish_or_materialize(fault):
    source = pixels('derived')
    value = snapshot(source, derived=True)
    repaired = legacy_pixels(source, 1) * np.float32(.91)
    binding = value['creative_source']
    proof = REPLAY.make_evidence(binding, source, repaired, REPAIRS.digest_ops([], [], binding))
    if fault == 'missing':
        proof = None
    elif fault == 'changed-input':
        source = source.copy()
        source[1, 1, 0] = np.float32(.312345)
    elif fault == 'changed-output':
        repaired[1, 1, 0] = np.float32(.312345)
    else:
        proof['source']['sha256'] = 'f' * 64
    sink = PreparationCaptureDouble()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(MATERIALIZE, 'materialize_export_source',
                         side_effect=AssertionError('Unproved repair materialized')) as materialize:
        with pytest.raises(ValueError, match='evidence'):
            direct(value, source, repaired, creative_repair_evidence=proof,
                   source_materialization_version=1)
    assert sink.calls == []
    materialize.assert_not_called()


@pytest.mark.parametrize('kind', ['rgb8', 'rgb16', 'derived'])
def test_opted_semantic_reservation_keeps_old_floor_and_full_backing_charge(kind):
    backing = pixels(kind, (70, 90))
    source = backing[2:9, 3:14, :]
    value = snapshot(source, derived=kind == 'derived')
    plan = MATERIALIZE.inspect_export_source(source, divisor(kind))
    count = source.shape[0] * source.shape[1]
    reserved = max(source.nbytes + count * 36, plan.peak_bytes)
    sink = PreparationCaptureDouble()
    with patch.object(SNAPSHOT, 'at_dimensions', wraps=SNAPSHOT.at_dimensions) as dimensions, \
            patch.object(ENGINE, 'prepare', sink):
        assert direct(value, source, source_materialization_version=1) is sink.result
    assert dimensions.call_args.kwargs['byte_budget'] == BUDGET - reserved
    # Source materialization admission never replaces the independent solver gate.
    assert sink.calls[0]['kwargs']['byte_budget'] == BUDGET


@pytest.mark.parametrize('version', [0, 1])
@pytest.mark.parametrize('with_repair', [False, True])
def test_semantic_budget_refusal_precedes_source_allocation_and_publication(version, with_repair):
    source = pixels('rgb16')
    value = snapshot(source)
    repaired = legacy_pixels(source, 65535) if with_repair else None
    count = source.shape[0] * source.shape[1]
    reserved = source.nbytes + count * 36
    if version:
        reserved = max(reserved, MATERIALIZE.inspect_export_source(source, 65535).peak_bytes)
    if repaired is not None:
        reserved += repaired.nbytes
    # Two same-grid f32 masks: 8N retained plus the existing 4N scratch bound.
    budget = reserved + count * 12 - 1
    sink = PreparationCaptureDouble()
    before = source.tobytes()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(MATERIALIZE, 'materialize_export_source',
                         side_effect=AssertionError('Refused semantics allocated source')) as materialize:
        with pytest.raises(ValueError, match='semantic copies exceed memory budget'):
            ENGINE.prepare_export(value, source, repaired, byte_budget=budget,
                document_id=DOCUMENT, source_materialization_version=version)
    assert sink.calls == [] and source.tobytes() == before
    materialize.assert_not_called()


@pytest.mark.parametrize('version', [0, 1])
def test_real_256n_solver_gate_stays_terminal_after_source_preparation(version):
    source = pixels('rgb16')
    value = snapshot(source, semantics=False)
    count = source.shape[0] * source.shape[1]
    budget = count * 256 + 128 * 1024**2 - 1
    result = object()
    original_result = result
    with patch.object(ENGINE, 'prepare', wraps=ENGINE.prepare) as prepare, \
            patch.object(RENDER, 'combine', side_effect=AssertionError('Refused solver made geometry')) as combine:
        with pytest.raises(ValueError, match='source analysis exceeds memory admission budget'):
            result = ENGINE.prepare_export(value, source, None, byte_budget=budget,
                document_id=DOCUMENT, source_materialization_version=version)
    assert result is original_result
    assert prepare.call_args.kwargs['byte_budget'] == budget
    combine.assert_not_called()


@pytest.mark.parametrize('budget', [-1, None, True, 1.5, np.int64(BUDGET)])
def test_invalid_budget_does_not_fallback_or_publish(budget):
    source = pixels('rgb16')
    value = snapshot(source)
    sink = PreparationCaptureDouble()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(MATERIALIZE, 'can_materialize_export_source',
                         side_effect=AssertionError('Invalid budget reached strategy probe')) as probe:
        with pytest.raises(ValueError, match='nonnegative byte budget'):
            ENGINE.prepare_export(value, source, None, byte_budget=budget,
                document_id=DOCUMENT, source_materialization_version=1)
    assert sink.calls == []
    probe.assert_not_called()


@pytest.mark.parametrize('public', [False, True])
def test_wrong_document_ownership_never_reaches_source_or_prepared_publication(public):
    source = pixels('rgb16')
    value = snapshot(source)
    value['document_id'] = 'same-source-different-document'
    sink = PreparationCaptureDouble()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(SNAPSHOT, 'at_dimensions', side_effect=AssertionError('Wrong owner resampled')) as dimensions, \
            patch.object(MATERIALIZE, 'can_materialize_export_source',
                         side_effect=AssertionError('Wrong owner materialized')) as probe:
        with pytest.raises(ValueError, match='document'):
            if public:
                EXPORT.prepare(SimpleNamespace(people=value, people_document_id=DOCUMENT), source, None)
            else:
                direct(value, source, source_materialization_version=1)
    assert sink.calls == []
    dimensions.assert_not_called()
    probe.assert_not_called()


def test_rewriting_outer_document_cannot_bypass_real_replica_owner():
    from test_people_document_owner_unrun import replica
    source = pixels('rgb16', (128, 128))
    value = snapshot(source, semantics=False)
    value['state'] = replica()  # Its real capsule remains owned by doc-a.
    sink = PreparationCaptureDouble()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(SNAPSHOT, 'at_dimensions', side_effect=AssertionError('Foreign replica resampled')) as dimensions, \
            patch.object(MATERIALIZE, 'can_materialize_export_source',
                         side_effect=AssertionError('Foreign replica materialized')) as probe:
        with pytest.raises(ValueError, match='another document owner'):
            direct(value, source, source_materialization_version=1)
    assert sink.calls == []
    dimensions.assert_not_called()
    probe.assert_not_called()


@pytest.mark.parametrize('fault', ['wrong-asset', 'wrong-size', 'integer', 'float64', 'nan', 'hdr', 'negative'])
def test_derived_source_proofs_and_sdr_gate_remain_terminal(fault):
    source = pixels('derived')
    value = snapshot(source, derived=True, semantics=False)
    if fault == 'wrong-asset':
        value['creative_source']['sha256'] = 'f' * 64
    elif fault == 'wrong-size':
        value['creative_source']['width'] += 1
    elif fault == 'integer':
        source = np.rint(source * 65535).astype(np.uint16)
    elif fault == 'float64':
        source = source.astype(np.float64)
    else:
        source = source.copy()
        source[1, 1, 0] = {'nan': np.nan, 'hdr': 1.01, 'negative': -.01}[fault]
    sink = PreparationCaptureDouble()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(MATERIALIZE, 'can_materialize_export_source',
                         side_effect=AssertionError('Invalid derived pixels reached materialization')) as probe:
        with pytest.raises(ValueError, match='verified creative float32 working source'):
            direct(value, source, source_materialization_version=1)
    assert sink.calls == []
    probe.assert_not_called()


@pytest.mark.parametrize('error', [ValueError('Synthetic materializer budget refusal'),
                                 MemoryError('Synthetic allocation failure'),
                                 InterruptedError('Synthetic materializer cancellation')])
def test_opted_materialization_failure_never_retries_legacy_or_publishes(error):
    source = pixels('rgb16')
    value = snapshot(source)
    sink = PreparationCaptureDouble()
    before = source.tobytes()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(MATERIALIZE, 'materialize_export_source', side_effect=error) as materialize:
        with pytest.raises(type(error), match='Synthetic'):
            direct(value, source, source_materialization_version=1)
    assert sink.calls == [] and source.tobytes() == before
    materialize.assert_called_once()


@pytest.mark.parametrize('kind', ['rgb8', 'rgb16', 'derived'])
def test_body_chain_still_receives_canonical_source_not_private_normalization(kind):
    from lumaretouch_engine import body_pose_state as BODY
    from lumaretouch_engine import arm_shape_project as BODY_PROJECT
    from lumaretouch_engine import body_pose_render as BODY_RENDER
    source = pixels(kind)
    value = snapshot(source, derived=kind == 'derived')
    height, width = source.shape[:2]
    frame = {'sha256': ASSET, 'width': width, 'height': height,
             'orientation': 'exif_normalized_once'}
    body = BODY_PROJECT.snapshot(BODY.empty(), frame)
    path = None if kind == 'derived' else 'synthetic-not-decoded-original.tif'
    sink = PreparationCaptureDouble()
    # The body routing double needs only the real body_budget contract fields.
    # Neither this placeholder nor the body return marker claims rendered data.
    sink.result = SimpleNamespace(effects=(), recovery={},
        geometry=SimpleNamespace(delta=np.zeros((1, height, width, 2), np.float32)))
    final = object()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(BODY_RENDER, 'prepare', return_value=final) as body_prepare:
        assert direct(value, source, body_pose=body, body_source_path=path,
                      source_materialization_version=1) is final
    body_prepare.assert_called_once()
    args, kwargs = body_prepare.call_args
    assert args[0] is sink.result and args[1] == BODY.empty()
    assert args[2] == value['state'] and args[3] is body['source']
    assert sink.calls[0]['kwargs']['body_bank'] == args[1]
    assert kwargs['byte_budget'] == BUDGET - height * width * 24
    assert kwargs['source_path'] == path
    assert kwargs['source_pixels'] is (source if kind == 'derived' else None)
    assert sink.calls[0]['source'] is not source


@pytest.mark.parametrize('fault', ['extent', 'source'])
def test_body_owner_mismatch_refuses_before_face_or_body_publication(fault):
    from lumaretouch_engine import body_pose_state as BODY
    from lumaretouch_engine import arm_shape_project as BODY_PROJECT
    from lumaretouch_engine import body_pose_render as BODY_RENDER
    source = pixels('rgb16')
    value = snapshot(source)
    frame = {'sha256': ASSET, 'width': source.shape[1], 'height': source.shape[0],
             'orientation': 'exif_normalized_once'}
    if fault == 'extent':
        frame['width'] += 1
    else:
        frame['sha256'] = 'f' * 64
    body = BODY_PROJECT.snapshot(BODY.empty(), frame)
    sink = PreparationCaptureDouble()
    with patch.object(ENGINE, 'prepare', sink), \
            patch.object(BODY_RENDER, 'prepare', side_effect=AssertionError('Foreign body published')) as body_prepare:
        with pytest.raises(ValueError, match='Body'):
            direct(value, source, body_pose=body, source_materialization_version=1)
    assert sink.calls == []
    body_prepare.assert_not_called()


@pytest.mark.parametrize('kind', ['rgb8', 'rgb16', 'derived'])
def test_real_active_skin_effect_preparation_and_composition_keep_legacy_pixels(kind):
    # Established synthetic source/semantic fixtures and native-only doubles.
    # No source, support, graph, solver admission, geometry or compositor guard
    # is replaced. This is routing parity, NOT native-solver image quality.
    from test_skin_evenness_integration_unrun import (
        fixture as skin_fixture, snapshot as skin_snapshot,
        native_prepare_double, native_apply_double, DOCUMENT as SKIN_DOCUMENT,
    )
    from lumaretouch_engine import skin_evenness_native as NATIVE
    state, ref, analysis, binding, original = skin_fixture(size=256)
    if kind == 'rgb8':
        source = np.rint(original.astype(np.float64) / 257).astype(np.uint8)
    elif kind == 'rgb16':
        source = original
    else:
        source = original.astype(np.float32) / 65535
    value = skin_snapshot(state, ref, analysis, binding, derived=kind == 'derived')
    before = source.tobytes()
    prepared, outputs, solves, applies = [], [], [], []
    current = legacy_pixels(source, divisor(kind)) * np.float32(.9)
    with patch.object(NATIVE, 'available', return_value=True), \
            patch.object(NATIVE, 'prepare', side_effect=native_prepare_double(solves)), \
            patch.object(NATIVE, 'apply', side_effect=native_apply_double(applies)):
        for version in (0, 1):
            result = ENGINE.prepare_export(value, source, None, byte_budget=BUDGET,
                document_id=SKIN_DOCUMENT, source_materialization_version=version)
            prepared.append(result)
            output, facts = result.apply_source_stage('skin_evenness', current)
            assert facts['changed_pixels'] > 0
            outputs.append(output)
    assert len(solves) == 2 and len(applies) >= 2
    assert solves[0]['source'].tobytes() == solves[1]['source'].tobytes()
    assert prepared[0].plan == prepared[1].plan
    np.testing.assert_array_equal(prepared[0].geometry.delta, prepared[1].geometry.delta)
    assert len(prepared[0].effects) == len(prepared[1].effects) == 1
    old, new = prepared[0].effects[0], prepared[1].effects[0]
    assert old.stage == new.stage == 'skin_evenness'
    assert old.face_ref == new.face_ref == ref and old.window == new.window
    y, x, height, width = new.window
    expected = legacy_pixels(source, divisor(kind))[y:y+height, x:x+width]
    assert solves[1]['source'].tobytes() == expected.tobytes()
    np.testing.assert_array_equal(old.chroma_shift, new.chroma_shift)
    assert outputs[0].tobytes() == outputs[1].tobytes()
    assert source.tobytes() == before
