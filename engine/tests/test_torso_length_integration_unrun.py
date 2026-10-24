# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN integration contracts for LNX-REF-PC-32473-C-f1662d2dec.

No product import, collection, test, native execution, build, typecheck, model
inference or download was performed while authoring. Synthetic pixels, pose,
face evidence and model-identity strings below are contract inputs, NOT actual
detector output, photographic acceptance, measured performance or AI parity.

Positive integration fixtures keep real body/person/face ownership, immutable
supports, snapshots, native-source fields, common-map admission, RGB16 sampler,
derived repair proof and history. Only torso_length_native prepare/facts/evaluate
are doubled. The double is explicitly a routing fixture, not native numerical
acceptance. The final endpoint test deliberately uses the REAL native boundary
and must be run in an authorized environment with the installed extension.
No fake prepared object, synthetic host publication or receipt is counted as
integration evidence. The later reviewed preset/batch route has separate UNRUN
fixtures; this file guards its distinction from the private transfer helper.
"""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import torso_length_state as S, torso_length_native as N
from lumaretouch_engine import torso_length_runtime as R, torso_length_project as P
from lumaretouch_engine import body_pose_evidence as E, body_pose_manifest as MODEL
from lumaretouch_engine import body_pose_state as B, body_pose_operations as O
from lumaretouch_engine import body_pose_geometry as ORDER, body_pose_render as BODY_RENDER
from lumaretouch_engine import body_pose_project as DOCUMENT_BODY
from lumaretouch_engine import body_pose_document_history as HISTORY
from lumaretouch_engine import people_state as PEOPLE, people_associations as LINKS
from lumaretouch_engine import people_cross_owner as CROSS, people_snapshot as SNAP
from lumaretouch_engine import people_engine_runtime as ENGINE, people_pipeline as PIPE
from lumaretouch_engine import creative_derived_body as DERIVED_BODY
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / 'engine/src/lumaretouch_engine'
DOCUMENT = 'synthetic-torso-document'
BUDGET = 512 * 1024**2
REQUIREMENT = 'LNX-REF-PC-32473-C-f1662d2dec'


def manual_support():
    return {'version': 1, 'method': S.METHOD,
        'outer_left': .05, 'inner_left': .25, 'inner_right': .75, 'outer_right': .95,
        'upper_zero': .025, 'upper_plateau': .20,
        'head_box': [.39, .22, .61, .39],
        'left_arm_box': [.28, .40, .41, .88],
        'right_arm_box': [.59, .40, .72, .88],
        'confirmations': {flag: True for flag in S.FLAGS}}


def fixture(*, amount=.6, asset='a'*64, size=512, reviewed=True, derived=False):
    """Synthetic observations through real structural/ownership constructors."""
    frame = {'sha256': asset, 'width': size, 'height': size, 'orientation': E.ORIENTATION}
    binding = {key: frame[key] for key in ('sha256', 'width', 'height')}
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': None, 'landmark_digest': 'c'*64, 'status': 'verified',
        'source_width': size, 'source_height': size, 'orientation': E.ORIENTATION}
    people = PEOPLE.empty()
    face = PEOPLE.new_face(asset, [.43, .25, .57, .35], evidence)
    face_ref = PEOPLE.face_ref(face)
    people['faces'][face['face_instance_id']] = face
    if derived:
        # Derived admission does not accept an ordinary shared-person link.
        # Use the actual reviewed-replica contract, not a require_graph mock.
        remote = PEOPLE.new_face('9'*64, face['box'], evidence)
        members = [{'document_id': DOCUMENT, 'scope_id': DOCUMENT,
                    'original_sha256': asset, 'ref': face_ref},
                   {'document_id': 'synthetic-peer-document', 'scope_id': 'synthetic-peer-document',
                    'original_sha256': '9'*64, 'ref': PEOPLE.face_ref(remote)}]
        capsule = CROSS.descriptor('synthetic-reviewed-person', DOCUMENT, members,
            [{'op': 'lnx.skin_colour.v1', 'path': '/temperature', 'value': 0.}])
        person = 'synthetic-reviewed-person'
        people = CROSS.create(people, person, capsule)
    else:
        people, person = LINKS.create_person(people)
        people = LINKS.set_link(people, face['face_instance_id'], person, 'confirmed', user_confirmed=True)
    points = [{'index': index, 'x': .5, 'y': .5, 'z': 0.,
               'visibility': 0., 'presence': 0.} for index in range(33)]
    for index in range(11):
        points[index].update(x=.45+.01*(index % 6), y=.27+.01*(index % 4), visibility=.95, presence=.95)
    observed = {11: (.38, .42), 12: (.62, .42), 13: (.34, .59), 14: (.66, .59),
        15: (.32, .78), 16: (.68, .78), 17: (.31, .81), 18: (.69, .81),
        19: (.32, .82), 20: (.68, .82), 21: (.33, .80), 22: (.67, .80),
        23: (.40, .72), 24: (.60, .72)}
    for index, (x, y) in observed.items():
        points[index].update(x=x, y=y, visibility=.95, presence=.95)
    measured = E.create(source_frame=frame, values=points, backend_version='synthetic-contract-only',
        backend_code_sha256='d'*64, model_id=MODEL.MODEL_ID, model_sha256=MODEL.MODEL_SHA256,
        input_rgb_sha256='e'*64, input_dimensions=(size//2, size//2))
    ref = measured['body_ref']
    bank = B.add_run(B.empty(), {'source': frame, 'records': [measured],
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
    bank = B.associate(bank, ref, person, people, user_confirmed=True)
    if reviewed:
        data = R.bind_support_review(manual_support(), B.target(bank, ref), people)
        bank = B.set_support(bank, ref, S.OP, S.SUPPORT_KIND, data)
        bank = B.review(bank, ref, operation_id=S.OP,
            points_sha256=measured['points_sha256'], visible_anchors=list(S.REQUIRED_ANCHORS),
            ownership_confirmed=True, support_sha256=B.operation(bank, ref, S.OP)['support_sha256'])
    bank = B.set_recipe(bank, ref, {'version': 1, 'amount': amount}, operation_id=S.OP)
    yy, xx = np.mgrid[:size, :size]
    original = np.stack((1000+xx*79, 2000+yy*83, 3000+(xx+yy)*37), axis=2).astype(np.uint16)
    original.setflags(write=False)
    return SimpleNamespace(bank=bank, people=people, ref=ref, face_ref=face_ref, person=person,
                           frame=frame, binding=binding, original=original, derived=derived)


def frozen(value):
    snap = SNAP.capture(value.people, value.frame['sha256'], {})
    snap.update(document_id=DOCUMENT, support_assets={})
    if value.derived:
        snap['creative_source'] = deepcopy(value.binding)
    return snap


def export(value, *, budget=BUDGET, source=None, snapshot=None, body=None):
    if source is None:
        source = value.original.astype(np.float32)/65535. if value.derived else value.original
    return ENGINE.prepare_export(frozen(value) if snapshot is None else snapshot, source, None,
        byte_budget=budget, document_id=DOCUMENT,
        body_pose=P.snapshot(value.bank, value.frame) if body is None else body)


class NativeRoutingDouble:
    """The real three native calls only; no bypass of Python admission gates.

    A compact smooth vertical map makes sampled-image assertions meaningful.
    Its construction is not an independent certification of the Rust inverse.
    Native facts copied here are routing facts, explicitly not quality evidence.
    """
    def __init__(self):
        self.prepared = []
        self.evaluated = []

    def prepare(self, points, amounts, support, shape):
        points = np.asarray(points)
        assert points.shape == (33, 5) and tuple(shape) == (512, 512)
        assert len(amounts) == 1 and len(support) == 18
        h, w = shape
        top = max(points[11, 1], points[12, 1])*(h-1)
        hip = min(points[23, 1], points[24, 1])*(h-1)
        state = np.array([*[support[i]*(w-1) for i in range(4)],
            support[4]*(h-1), support[5]*(h-1), top, hip,
            -float(amounts[0])*.08*(hip-top), w, h], np.float64)
        state.setflags(write=False)
        self.prepared.append((points.copy(), list(amounts), list(support), tuple(shape), state))
        return state

    def facts(self, state):
        return {'support_box': [state[0], state[4], state[3], state[7]],
                'plateau_box': [state[1], state[5], state[2], state[6]],
                'max_displacement': abs(float(state[8]))}

    @staticmethod
    def smooth(value):
        value = np.clip(value, 0., 1.)
        return value**3*(10.+value*(-15.+6.*value))

    def evaluate(self, state, points):
        points = np.asarray(points, np.float64)
        assert points.ndim == 2 and points.shape[1] == 2
        assert np.isfinite(points).all()
        assert np.all(points >= 0) and np.all(points <= state[9:11]-1)
        self.evaluated.append((points.shape[0], tuple(np.max(points, axis=0))))
        x, target = points.T
        horizontal = self.smooth((x-state[0])/(state[1]-state[0]))
        horizontal *= self.smooth((state[3]-x)/(state[3]-state[2]))
        source = target.copy()
        for _ in range(64):
            vertical = self.smooth((source-state[4])/(state[5]-state[4]))
            vertical *= self.smooth((state[7]-source)/(state[7]-state[6]))
            source = target-state[8]*horizontal*vertical
        result = np.zeros_like(points)
        result[:, 1] = target-source
        return result


@pytest.fixture
def native_boundary():
    double = NativeRoutingDouble()
    with patch.object(N, 'prepare', side_effect=double.prepare), \
            patch.object(N, 'facts', side_effect=double.facts), \
            patch.object(N, 'evaluate', side_effect=double.evaluate):
        yield double


def assert_common(prepared, value):
    assert len(prepared.body_fields) == 1 and not prepared.effects
    field = prepared.body_fields[0]
    assert field.operation_id == S.OP and field.body_ref == value.ref
    assert field.associated_face_id == value.face_ref['face_instance_id']
    assert prepared.geometry.delta.shape == (1, 512, 512, 2)
    assert not prepared.geometry.delta.flags.writeable
    assert np.any(prepared.geometry.delta) and np.all(prepared.geometry.delta[..., 0] == 0)
    assert prepared.body_operation_order == ORDER.TORSO_LENGTH_BODY_ORDER.record()
    assert prepared.geometry.composition_order == 'body-then-face-inverse-v1'
    assert field.facts['requirement_id'] == REQUIREMENT
    assert field.facts['runtime_quality_accepted'] is False
    assert field.facts['hidden_anatomy_inferred'] is False
    ORDER.require_prepared(value.bank, value.frame['sha256'], prepared.body_fields, people_state=value.people)
    return field


def test_exact_signed_requirement_is_separate_from_adjacent_waist_length():
    assert S.OP == 'lnx.torso_length.v1' and S.CONTROL_ID == REQUIREMENT
    assert S.neutral() == {'version': 1, 'amount': 0.}
    assert S.OP in O.policies() and 'torso_length' in DERIVED_BODY.COMMANDS
    for amount in (-1., -.125, 0., .125, 1.):
        assert S.portable({'version': 1, 'amount': amount}) == {'version': 1, 'amount': amount}
    for amount in (True, '1', -1.0001, 1.0001, float('nan'), float('inf')):
        with pytest.raises(ValueError):
            S.check({'version': 1, 'amount': amount})
    for key in ('waist_length', 'width', 'body_ref', 'support', 'head_box', 'field'):
        with pytest.raises(ValueError):
            S.portable({**S.neutral(), key: 0})


@pytest.mark.parametrize('amount', [-1., -.25, .25, 1.])
@pytest.mark.parametrize('derived', [False, True])
def test_original_rgb16_and_derived_float_use_real_common_map(native_boundary, amount, derived):
    value = fixture(amount=amount, derived=derived)
    before = deepcopy(value.bank)
    prepared = export(value)
    field = assert_common(prepared, value)
    assert len(native_boundary.prepared) == 1
    assert native_boundary.prepared[0][3] == (512, 512)
    assert native_boundary.prepared[0][1] == [amount]
    source = value.original.astype(np.float32)/65535. if derived else value.original
    actual = prepared.geometry.warp(source) if derived else prepared.geometry.warp_original(source)
    assert actual.shape == source.shape and actual.dtype == source.dtype
    assert np.any(actual != source) and value.bank == before
    np.testing.assert_array_equal(actual[[0, -1]], source[[0, -1]])
    np.testing.assert_array_equal(actual[:, [0, -1]], source[:, [0, -1]])
    assert field.state.flags.writeable is False
    # Export outcome belongs to actual buffer bytes, not file/save completion.
    outcome = BODY_RENDER.export_outcome(prepared, actual, (512, 512))
    assert outcome['encoded_file_published'] is False and outcome['geometry_original_resolution'] is True
    assert outcome['common_portrait_sampling_stages'] == 1
    assert outcome['fields'][0]['applied'] is True and outcome['runtime_quality_accepted'] is False


@pytest.mark.parametrize('derived', [False, True])
def test_proxy_preview_and_original_export_rebuild_from_original_coordinates(native_boundary, derived):
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline
    value = fixture(derived=derived)
    proxy = (value.original[::2, ::2]//257).astype(np.uint8)
    pipe = PreviewPipeline('cpu', 256, 256)
    pipe.load_rgb_u8(proxy)
    kwargs = {}
    if derived:
        source = proxy.astype(np.float32)/255.
        proof = REPLAY.make_evidence(value.binding, source, None, REPAIRS.digest_ops([], [], value.binding))
        pipe._creative_repair_source = deepcopy(value.binding)
        pipe._creative_repair_input = deepcopy(proof['input'])
        pipe._creative_repair_evidence = proof
        kwargs = {'creative_source': value.binding, 'creative_proxy': proxy}
    preview = ENGINE.prepare_preview(pipe, value.people, value.frame['sha256'], {},
        byte_budget=BUDGET, document_id=DOCUMENT, body_bank=value.bank, body_source=value.binding, **kwargs)
    full = export(value)
    assert len(native_boundary.prepared) == 2
    assert all(call[3] == (512, 512) for call in native_boundary.prepared)
    assert preview.geometry.delta.shape == (1, 256, 256, 2)
    assert full.geometry.delta.shape == (1, 512, 512, 2)
    assert not np.shares_memory(preview.geometry.delta, full.geometry.delta)
    scale = np.array([255/511, 255/511])
    points = np.array([[250.125, 240.75], [190.5, 300.125], [300.1, 130.75]])
    np.testing.assert_allclose(preview.body_fields[0].evaluate(points*scale)/scale,
                               full.body_fields[0].evaluate(points), rtol=0, atol=1e-10)
    PIPE.install(pipe, preview)
    actual = PIPE.warp(pipe, pipe.src_f32)[0].permute(1, 2, 0).numpy()
    expected = preview.geometry.warp(proxy.astype(np.float32)/255.)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=3e-6)
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), proxy.astype(np.float32)/255.)


@pytest.mark.parametrize('reviewed', [False, True])
def test_exact_neutral_keeps_old_order_and_rgb16_without_native(reviewed):
    value = fixture(amount=0, reviewed=reviewed)
    with patch.object(N, 'prepare', side_effect=AssertionError('Neutral prepared native')) as prepare, \
            patch.object(N, 'evaluate', side_effect=AssertionError('Neutral evaluated native')) as evaluate:
        prepared = export(value)
    prepare.assert_not_called()
    evaluate.assert_not_called()
    assert not prepared.body_fields and not np.any(prepared.geometry.delta)
    assert prepared.body_operation_order == ORDER.DEFAULT_BODY_ORDER.record()
    np.testing.assert_array_equal(prepared.geometry.warp_original(value.original), value.original)


def test_missing_native_refuses_active_but_reset_and_disable_need_no_native():
    value = fixture()
    saved = deepcopy(value.bank)
    with patch.object(N, 'native', side_effect=RuntimeError('Synthetic missing installed torso ABI')) as load:
        with pytest.raises(R.TorsoLengthRefused): export(value)
        assert value.bank == saved
        assert load.call_count == 1
        load.reset_mock()
        value.bank = B.set_recipe(value.bank, value.ref, S.neutral(), operation_id=S.OP)
        reset = export(value)
        value.bank = B.set_operation_enabled(saved, value.ref, S.OP, False)
        disabled = export(value)
        load.assert_not_called()
    assert not reset.body_fields and not disabled.body_fields
    assert B.operation(value.bank, value.ref, S.OP)['recipe'] == B.operation(saved, value.ref, S.OP)['recipe']
    assert value.bank['support_assets'] == saved['support_assets']
    np.testing.assert_array_equal(reset.geometry.warp_original(value.original), value.original)
    np.testing.assert_array_equal(disabled.geometry.warp_original(value.original), value.original)


def test_transport_capability_is_not_confused_with_installed_native_readiness():
    tree = ast.parse((ENGINE_ROOT/'server.py').read_text())
    ready = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            entries = {key.value: value for key, value in zip(node.keys, node.values)
                       if isinstance(key, ast.Constant) and isinstance(key.value, str)}
            if 'torso_length_protocol' in entries: ready.append(entries)
    assert len(ready) == 1
    assert ast.literal_eval(ready[0]['torso_length_protocol']) == 1
    assert isinstance(ready[0]['torso_length_available'], ast.Name)
    assert ready[0]['torso_length_available'].id == 'torso_length_ready'
    assert 'torso_length_unavailable_reason' in ready[0]
    host = (ENGINE_ROOT/'torso_length_host.py').read_text()
    assert "if action=='recipe' and S.active(payload['recipe']): raise" in host
    assert 'prepared=UnappliedPreparation(str(error))' in host


def test_native_bridge_preserves_exact_support_schema_epochs_and_query_only_recovery():
    bridge = (ROOT/'ui/src-tauri/src/torso_length_api.rs').read_text()
    for key in (*S.COLUMNS, *S.BOXES, *S.FLAGS, *S.FACE_BINDING_KEYS):
        assert '"'+key+'"' in bridge
    assert '"lnx.torso_length.v1"' in bridge and '(-1.0..=1.0).contains(&n)' in bridge
    assert 'a.len()==25' in bridge and 'allow_draft&&fields(v,&base)' in bridge
    assert 'r.epoch==epoch&&r.result.is_none()' in bridge
    assert 'signature_bytes' in bridge and 'MAX_SIGNATURE_BYTES' in bridge
    assert 'only_correlated_authoritative_status_settles_the_original_fence' in bridge
    assert 'explicit_support_draft_is_not_a_persisted_bound_support' in bridge
    dispatch = (ROOT/'ui/src-tauri/src/engine.rs').read_text()
    assert 'crate::torso_length_api::ready(inspection_epoch, v["torso_length_protocol"].as_u64() == Some(1))' in dispatch
    assert 'v["event"] != "torso_length_result"' in dispatch
    assert 'crate::torso_length_api::receive(inspection_epoch, &v)' in dispatch


def test_neutral_new_family_preserves_every_old_frozen_order():
    from lumaretouch_engine import shoulder_shape_state as SHOULDER, leg_shape_state as LEG
    from lumaretouch_engine import arm_shape_state as ARM, waist_shape_state as WAIST
    from lumaretouch_engine import leg_length_state as LENGTH, neck_shape_state as NECK
    cases = [(None, None, ORDER.DEFAULT_BODY_ORDER),
        (SHOULDER.OPERATION_ID, SHOULDER.adjust(SHOULDER.neutral(), 'width', 'left', .2), ORDER.DEFAULT_BODY_ORDER),
        (LEG.OPERATION_ID, {**LEG.neutral(), 'calf': .2}, ORDER.LEG_BODY_ORDER),
        (ARM.OPERATION_IDS['left_upper'], {**ARM.neutral(), 'amount': .2}, ORDER.PORTRAIT_BODY_ORDER),
        (WAIST.OPERATION_ID, {'version': 1, 'amount': .2}, ORDER.WAIST_BODY_ORDER),
        (LENGTH.OPERATION_ID, {'version': 1, 'thigh': .2, 'calf': 0.}, ORDER.LEG_LENGTH_BODY_ORDER),
        (NECK.OPERATION_ID, {**NECK.neutral(), 'length': .2}, ORDER.NECK_BODY_ORDER)]
    for operation, recipe, old_order in cases:
        value = fixture(amount=0, reviewed=False)
        if operation is not None:
            value.bank = B.set_recipe(value.bank, value.ref, recipe, operation_id=operation)
        assert ORDER.effective_order(value.bank) == old_order
        assert P.snapshot(value.bank, value.frame)['body_operation_order'] == old_order.record()
        active = B.set_recipe(value.bank, value.ref, {'version': 1, 'amount': .2}, operation_id=S.OP)
        assert ORDER.effective_order(active) == ORDER.TORSO_LENGTH_BODY_ORDER
    assert ORDER.TORSO_LENGTH_BODY_ORDER.operation_ids[:-1] == ORDER.NECK_BODY_ORDER.operation_ids


@pytest.mark.parametrize('fault', ['unreviewed', 'unlinked', 'association-revision', 'face-revision',
    'face-evidence', 'face-box', 'manual-face', 'foreign-frame', 'missing-support', 'points'])
def test_stale_or_unowned_inputs_refuse_before_native_prepare(fault):
    value = fixture(reviewed=fault != 'unreviewed')
    row = B.target(value.bank, value.ref)
    face = value.people['faces'][value.face_ref['face_instance_id']]
    if fault == 'unlinked': value.bank = B.unlink(value.bank, value.ref)
    elif fault == 'association-revision': value.people['association_revision'] += 1
    elif fault == 'face-revision': face['analysis_revision'] += 1
    elif fault == 'face-evidence': face['evidence']['detector_model_sha256'] = '8'*64
    elif fault == 'face-box': face['box'][0] += .001
    elif fault == 'manual-face': face['manual'] = True
    elif fault == 'foreign-frame': value.frame['width'] += 8
    elif fault == 'missing-support': value.bank['support_assets'].clear()
    elif fault == 'points': row['record']['points'][11]['x'] += .01
    with patch.object(N, 'prepare', side_effect=AssertionError('Unowned data reached native')) as native:
        with pytest.raises(ValueError):
            export(value)
    native.assert_not_called()


def test_body_ref_is_not_face_ref_and_another_body_support_cannot_be_rebound():
    value, donor = fixture(), fixture(asset='f'*64)
    with pytest.raises(ValueError): B.target(value.bank, value.face_ref)
    copied = B.support(donor.bank, donor.ref, S.OP)
    copied_key = E.content_digest(copied)
    invalid = deepcopy(value.bank)
    invalid['support_assets'][copied_key] = copied
    item = B.operation(invalid, value.ref, S.OP)
    item['support_sha256'] = copied_key
    item['review']['support_sha256'] = copied_key
    with patch.object(N, 'prepare', side_effect=AssertionError('Foreign support reached native')) as native:
        with pytest.raises(ValueError): B.check(invalid)
    native.assert_not_called()


@pytest.mark.parametrize('foreign', ['disabled-face', 'unresolved-body', 'observed-body'])
def test_every_retained_foreign_owner_protects_its_pixels(native_boundary, foreign):
    value = fixture()
    if foreign == 'disabled-face':
        own = value.people['faces'][value.face_ref['face_instance_id']]
        face = PEOPLE.new_face(value.frame['sha256'], [.16, .30, .23, .40], own['evidence'])
        face['enabled'] = False
        value.people['faces'][face['face_instance_id']] = face
    else:
        record = deepcopy(B.target(value.bank, value.ref)['record'])
        points = deepcopy(record['points'])
        if foreign == 'unresolved-body':
            for point in points: point.update(visibility=0., presence=0.)
        observed = E.create(source_frame=value.frame, values=points, backend_version='synthetic-only',
            backend_code_sha256='d'*64, model_id=MODEL.MODEL_ID, model_sha256=MODEL.MODEL_SHA256,
            input_rgb_sha256='e'*64, input_dimensions=(256, 256))
        value.bank = B.add_run(value.bank, {'source': value.frame, 'records': [observed],
            'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
    with pytest.raises(R.TorsoLengthRefused) as failure:
        export(value)
    assert all(item['applied'] is False and item['operation_id'] == S.OP for item in failure.value.refusals)


def test_memory_source_edges_and_review_flags_are_not_silently_clamped():
    value = fixture(amount=0, reviewed=False)
    row = B.target(value.bank, value.ref)
    for flag in S.FLAGS:
        data = manual_support()
        data['confirmations'][flag] = False
        with pytest.raises(ValueError): R.bind_support_review(data, row, value.people)
    edge = manual_support()
    edge['outer_left'] = .00001
    with pytest.raises(ValueError): R.bind_support_review(edge, row, value.people)
    with patch.object(N, 'prepare', side_effect=AssertionError('Budget refusal reached native')) as native:
        with pytest.raises(ValueError): export(fixture(), budget=1)
    native.assert_not_called()


@pytest.mark.parametrize('fault', ['dtype', 'alpha', 'proxy', 'document', 'source', 'frozen-order'])
@pytest.mark.parametrize('derived', [False, True])
def test_export_precision_source_and_snapshot_fences_precede_native(fault, derived):
    value = fixture(derived=derived)
    source = value.original.astype(np.float32)/65535. if derived else value.original
    snap = frozen(value)
    body = P.snapshot(value.bank, value.frame)
    if fault == 'dtype': source = value.original if derived else source.astype(np.float32)
    elif fault == 'alpha': source = np.concatenate((source, source[..., :1]), axis=2)
    elif fault == 'proxy': source = source[::2, ::2]
    elif fault == 'document': snap['document_id'] = 'wrong-owner'
    elif fault == 'source': body['source']['sha256'] = '8'*64
    else: body['body_operation_order']['version'] = 6
    with patch.object(N, 'prepare', side_effect=AssertionError('Bad export reached native')) as native:
        with pytest.raises(ValueError): export(value, source=source, snapshot=snap, body=body)
    native.assert_not_called()


def test_reset_history_and_project_preserve_support_and_unrelated_body_intent(native_boundary):
    value = fixture()
    before = deepcopy(value.bank)
    reset = B.set_recipe(before, value.ref, S.neutral(), operation_id=S.OP)
    assert reset['support_assets'] == before['support_assets']
    assert B.operation(reset, value.ref, S.OP)['review'] == B.operation(before, value.ref, S.OP)['review']
    assert B.operation(reset, value.ref) == B.operation(before, value.ref)
    patch_value = P.history_patch(before, reset, people_sha256=P.people_digest(value.people))
    undone = P.replay_patch(reset, patch_value, undo=True, people_state=value.people,
                           expected_bank_sha256=P.graph_digest(reset))
    assert B.operation(undone, value.ref, S.OP) == B.operation(before, value.ref, S.OP)
    redone = P.replay_patch(undone, patch_value, undo=False, people_state=value.people,
                           expected_bank_sha256=P.graph_digest(undone))
    assert B.operation(redone, value.ref, S.OP)['recipe'] == S.neutral()
    # Existing document history and persisted bank, not a second torso stack.
    old_doc = {DOCUMENT_BODY.KEY: P.pack(before)}
    reset_doc = {DOCUMENT_BODY.KEY: P.pack(reset)}
    restored = HISTORY.restore(reset, HISTORY.decorate(old_doc, reset_doc))
    assert B.operation(restored, value.ref, S.OP) == B.operation(before, value.ref, S.OP)
    assert P.unpack(P.pack(restored)) == restored
    value.bank = restored
    assert_common(export(value), value)
    value.bank = redone
    assert not export(value).body_fields
    stale = deepcopy(value.people)
    stale['association_revision'] += 1
    with pytest.raises(ValueError):
        P.replay_patch(reset, patch_value, undo=True, people_state=stale,
                       expected_bank_sha256=P.graph_digest(reset))


def test_prepared_field_cannot_survive_recipe_or_face_association_change(native_boundary):
    value = fixture()
    prepared = export(value)
    changed = B.set_recipe(value.bank, value.ref, {'version': 1, 'amount': -.4}, operation_id=S.OP)
    with pytest.raises(ValueError):
        ORDER.require_prepared(changed, value.frame['sha256'], prepared.body_fields, people_state=value.people)
    people = deepcopy(value.people)
    people['association_revision'] += 1
    with pytest.raises(ValueError):
        ORDER.require_prepared(value.bank, value.frame['sha256'], prepared.body_fields, people_state=people)
    with pytest.raises(ValueError):
        ORDER.require_prepared(value.bank, value.frame['sha256'], (), people_state=value.people)
    with pytest.raises(ValueError):
        ORDER.require_prepared(value.bank, value.frame['sha256'], prepared.body_fields*2, people_state=value.people)


def test_private_parameter_transfer_keeps_target_support_and_rebuilds_its_own_source(native_boundary):
    source, target = fixture(amount=-.7), fixture(amount=.1, asset='f'*64)
    people = deepcopy(source.people)
    target_face = deepcopy(target.people['faces'][target.face_ref['face_instance_id']])
    people['faces'][target_face['face_instance_id']] = target_face
    people = LINKS.set_link(people, target_face['face_instance_id'], source.person, 'confirmed', user_confirmed=True)
    source.people = target.people = people
    source.bank = B.associate(source.bank, source.ref, source.person, people, user_confirmed=True)
    target.bank = B.associate(target.bank, target.ref, source.person, people, user_confirmed=True)
    target_before = deepcopy(target.bank)
    result = P.transfer_recipe(source.bank, source.ref, target.bank, target.ref, people_state=people,
        expected_people_sha256=P.people_digest(people), expected_source_bank_sha256=P.graph_digest(source.bank),
        expected_target_bank_sha256=P.graph_digest(target.bank), confirmed_person_id=source.person, user_confirmed=True)
    assert B.operation(result, target.ref, S.OP)['recipe'] == {'version': 1, 'amount': -.7}
    assert result['support_assets'] == target_before['support_assets']
    assert B.support(result, target.ref, S.OP) == B.support(target_before, target.ref, S.OP)
    assert B.support(result, target.ref, S.OP) != B.support(source.bank, source.ref, S.OP)
    target.bank = result
    field = assert_common(export(target), target)
    assert field.record['source'] == target.frame
    assert target.bank['bodies'][target.ref['body_instance_id']]['record'] == target_before['bodies'][target.ref['body_instance_id']]['record']


@pytest.mark.parametrize('derived', [False, True])
def test_public_scalar_scope_rebuilds_real_target_common_geometry_and_scoped_restore(native_boundary, derived):
    """UNRUN: real ownership/common sampler; only native numerical boundary doubled."""
    from lumaretouch_engine import torso_length_scope as T
    source = fixture(amount=-.7)
    target = fixture(amount=.1, asset='f'*64, derived=derived)
    original_bank = deepcopy(target.bank)
    before = {DOCUMENT_BODY.KEY: P.pack(target.bank)}
    state = deepcopy(before)
    portable = T.params_of({DOCUMENT_BODY.KEY: P.pack(source.bank)})
    assert set(portable) == {'version', 'amount'}
    T.install(state, portable)
    target.bank = DOCUMENT_BODY.bank(state)
    assert target.bank['support_assets'] == original_bank['support_assets']
    assert B.support(target.bank, target.ref, S.OP) == B.support(original_bank, target.ref, S.OP)
    field = assert_common(export(target), target)
    assert field.record['source'] == target.frame
    assert native_boundary.prepared[-1][1] == [-.7]
    # Distinct private people owners are not merged or relinked by scalar transfer.
    assert target.people != source.people
    restored = deepcopy(state)
    T.restore(restored, before)
    target.bank = DOCUMENT_BODY.bank(restored)
    assert B.operation(target.bank, target.ref, S.OP)['recipe'] == {'version': 1, 'amount': .1}
    assert target.bank['revision'] > original_bank['revision']
    assert_common(export(target), target)
    assert native_boundary.prepared[-1][1] == [.1]


def test_reviewed_torso_scope_is_distinct_from_private_same_graph_helper():
    from lumaretouch_engine import scope
    assert scope.MODULES[S.OP]["transferable"] is True
    assert scope.check_scope([S.OP]) == [S.OP]
    assert scope.check_params(S.OP, {"version": 1, "amount": .4}) == {"version": 1, "amount": .4}
    with pytest.raises(scope.ScopeError): scope.check_scope([S.OP, scope.OP_EXPOSURE])
    with pytest.raises(scope.ScopeError): scope.check_params(S.OP, {"version": 1, "amount": .4, "body_ref": {}})
    # Source audit: a helper definition is not a reachable reviewed UI flow.
    for path in ENGINE_ROOT.glob('*.py'):
        if path.name == 'torso_length_project.py': continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'torso_length_project':
                assert all(alias.name != 'transfer_recipe' for alias in node.names)


def test_actual_native_endpoint_length_is_not_a_fixed_endpoint_interior_warp():
    """UNRUN real ABI acceptance, intentionally NO NativeRoutingDouble.

    Keep this visibly separate from Python routing coverage. Missing installed
    extension is a reported acceptance blocker, not a passing substitute map.
    """
    if not N.available():
        pytest.skip('UNRUN real torso native endpoint acceptance: installed extension unavailable')
    for amount in (-1., -.25, .25, 1.):
        value = fixture(amount=amount)
        fields = R.prepare_fields(value.bank, value.frame['sha256'], (512, 512),
            people_state=value.people, byte_budget=BUDGET, source_frame=value.frame)
        field = fields[0]
        shoulder, hip = .42*511, .72*511
        displacement = -amount*S.LENGTH_GAIN*(hip-shoulder)
        # Inverse at the expected moved shoulder/head must recover actual source
        # positions. Hip inverse stays fixed; their distance changes in both signs.
        output = np.array([[.5*511, shoulder+displacement], [.5*511, hip],
                           [.5*511, .30*511+displacement]], np.float64)
        recovered = output-field.evaluate(output)
        np.testing.assert_allclose(recovered[:, 1], [shoulder, hip, .30*511], rtol=0, atol=1e-7)
        assert np.isclose(output[1, 1]-output[0, 1], (hip-shoulder)*(1+amount*S.LENGTH_GAIN))
        assert not np.isclose(output[1, 1]-output[0, 1], hip-shoulder)
        edges = np.array([[0., 0.], [511., 511.], [0., 250.25], [511., 250.25]])
        np.testing.assert_array_equal(field.evaluate(edges), np.zeros_like(edges))
