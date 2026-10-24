# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN integration contracts for LNX-REF-PC-32473-C-dc1b0ba40a.

No product import, collection, test, build, inference or download was performed
while authoring. Synthetic observations and pixels below are contract inputs,
not detector results, a photographed subject, performance or quality evidence.
Installed-native tests intentionally do not replace the Rust numerical calls.
An unavailable ABI is an explicit acceptance blocker, never a passing mock.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import head_size_state as S, head_size_native as N
from lumaretouch_engine import head_size_runtime as R, head_size_project as P
from lumaretouch_engine import body_pose_state as B, body_pose_evidence as E
from lumaretouch_engine import body_pose_operations as O, body_pose_geometry as ORDER
from lumaretouch_engine import body_pose_families as F, body_pose_render as BODY_RENDER
from lumaretouch_engine import body_pose_project as DOCUMENT_BODY
from lumaretouch_engine import body_pose_manifest as MODEL
from lumaretouch_engine import body_pose_document_history as HISTORY
from lumaretouch_engine import people_state as PEOPLE, people_associations as LINKS
from lumaretouch_engine import people_cross_owner as CROSS, people_snapshot as SNAP
from lumaretouch_engine import people_engine_runtime as ENGINE
from lumaretouch_engine import creative_derived_body as DERIVED

DOCUMENT = 'synthetic-head-size-document'
REQUIREMENT = 'LNX-REF-PC-32473-C-dc1b0ba40a'
BUDGET = 512 * 1024**2


def manual_support():
    return {'version': 1, 'method': S.METHOD,
        'head_box': [.40, .22, .60, .38],
        'transition_box': [.10, .03, .90, .57], 'pivot': [.50, .30],
        'confirmations': {key: True for key in S.FLAGS}}


def fixture(*, amount=.5, asset='a'*64, reviewed=True, derived=False):
    """Real structural constructors with explicitly synthetic measured inputs."""
    size = 512
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
        remote = PEOPLE.new_face('9'*64, face['box'], evidence)
        members = [{'document_id': DOCUMENT, 'scope_id': DOCUMENT,
                    'original_sha256': asset, 'ref': face_ref},
                   {'document_id': 'synthetic-peer-document', 'scope_id': 'synthetic-peer-document',
                    'original_sha256': '9'*64, 'ref': PEOPLE.face_ref(remote)}]
        person = 'synthetic-reviewed-head-person'
        descriptor = CROSS.descriptor(person, DOCUMENT, members,
            [{'op': 'lnx.skin_colour.v1', 'path': '/temperature', 'value': 0.}])
        people = CROSS.create(people, person, descriptor)
    else:
        people, person = LINKS.create_person(people)
        people = LINKS.set_link(people, face['face_instance_id'], person, 'confirmed', user_confirmed=True)
    points = [{'index': index, 'x': .5, 'y': .8, 'z': 0.,
               'visibility': 0., 'presence': 0.} for index in range(33)]
    for index in range(11):
        points[index].update(x=.45+.01*(index % 6), y=.27+.01*(index % 4), visibility=.95, presence=.95)
    for index, x in ((11, .35), (12, .65)):
        points[index].update(x=x, y=.70, visibility=.95, presence=.95)
    measured = E.create(source_frame=frame, values=points, backend_version='synthetic-contract-only',
        backend_code_sha256='d'*64, model_id=MODEL.MODEL_ID, model_sha256=MODEL.MODEL_SHA256,
        input_rgb_sha256='e'*64, input_dimensions=(256, 256))
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
    pixels = np.stack((1000+xx*79, 2000+yy*83, 3000+(xx+yy)*37), axis=2).astype(np.uint16)
    pixels.setflags(write=False)
    return SimpleNamespace(bank=bank, people=people, frame=frame, binding=binding,
                           ref=ref, face_ref=face_ref, pixels=pixels, derived=derived)


def frozen(value):
    snapshot = SNAP.capture(value.people, value.frame['sha256'], {})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    if value.derived:
        snapshot['creative_source'] = deepcopy(value.binding)
    return snapshot


def full_export(value, *, pixels=None, body=None):
    if pixels is None:
        pixels = value.pixels.astype(np.float32)/65535. if value.derived else value.pixels
    return ENGINE.prepare_export(frozen(value), pixels, None, byte_budget=BUDGET,
        document_id=DOCUMENT, body_pose=P.snapshot(value.bank, value.frame) if body is None else body)


def installed_native():
    if not N.available():
        pytest.skip('UNRUN head size integration: installed Rust ABI unavailable; no numerical substitute')


def test_registered_family_protocol_and_exclusive_target_reviewed_scalar_scope():
    from lumaretouch_engine import scope
    assert S.OP == 'lnx.head_size.v1' and S.CONTROL_ID == REQUIREMENT
    assert S.OP in O.policies() and F.FAMILIES[-1] == 'head_size'
    assert F.request_family({'operation_id': S.OP}) == 'head_size'
    assert F.presenter('head_size').S.OP == S.OP
    assert 'head_size' in DERIVED.COMMANDS
    assert S.OP in scope.MODULES and S.OP in scope.transferable_ops()
    assert scope.MODULES[S.OP]['params'] == ('version', 'amount')
    assert scope.check_scope([S.OP]) == [S.OP]
    assert scope.check_params(S.OP, S.neutral()) == S.neutral()
    for other in ('lnx.torso_length.v1', 'lnx.waist_length.v1', scope.OP_CROP):
        with pytest.raises(scope.ScopeError): scope.check_scope([S.OP, other])
    with pytest.raises(ValueError):
        scope.apply_modules({}, {S.OP: S.neutral()})  # Zero never fabricates target support.


@pytest.mark.parametrize('operation,version', [
    ('lnx.shoulder_shape.v1', 1), ('lnx.leg_shape.v1', 2),
    ('lnx.arm_shape.left_upper.v1', 3), ('lnx.waist_shape.v1', 4),
    ('lnx.leg_length.v1', 5), ('lnx.neck_shape.v1', 6),
    ('lnx.torso_length.v1', 7), ('lnx.waist_length.v1', 8)])
def test_neutral_head_keeps_every_prior_chain_identity(operation, version):
    recipe = O.require_policy(operation).neutral()
    if 'amount' in recipe:
        recipe['amount'] = .2
    elif 'thigh' in recipe:
        recipe['thigh'] = .2
    elif 'length' in recipe:
        recipe['length'] = .2
    else:
        recipe['square']['left'] = .2
    row = {'enabled': True, 'operations': {
        operation: {'enabled': True, 'recipe': recipe},
        S.OP: {'enabled': True, 'recipe': S.neutral()}}}
    state = {'bodies': {'synthetic-order-only': row}}
    before = ORDER.effective_order(state).record()
    assert before['version'] == version and S.OP not in before['operation_ids']
    row['operations'][S.OP]['recipe']['amount'] = .5
    assert ORDER.effective_order(state) == ORDER.HEAD_SIZE_BODY_ORDER
    assert ORDER.HEAD_SIZE_BODY_ORDER.record()['version'] == 9
    assert ORDER.HEAD_SIZE_BODY_ORDER.operation_ids[:-1] == ORDER.WAIST_LENGTH_BODY_ORDER.operation_ids
    row['operations'][S.OP]['enabled'] = False
    assert ORDER.effective_order(state).record() == before


def test_same_body_bank_support_and_document_history_round_trip():
    value = fixture(amount=0.)
    before = DOCUMENT_BODY.fields({DOCUMENT_BODY.KEY: P.pack(value.bank)})
    active = B.set_recipe(value.bank, value.ref, {'version': 1, 'amount': .5}, operation_id=S.OP)
    after = DOCUMENT_BODY.fields({DOCUMENT_BODY.KEY: P.pack(active)})
    transition = HISTORY.decorate(before, after)
    restored = HISTORY.restore(active, transition)
    assert B.operation(restored, value.ref, S.OP)['recipe'] == S.neutral()
    assert restored['support_assets'] == active['support_assets']
    assert B.target(restored, value.ref)['record'] == B.target(active, value.ref)['record']
    assert P.unpack(P.pack(active)) == active
    assert P.check_snapshot(P.snapshot(active, value.frame), value.frame) == active
    assert set(after) == {DOCUMENT_BODY.KEY}


@pytest.mark.parametrize('derived', [False, True])
def test_unreviewed_or_foreign_source_never_reaches_native(derived):
    value = fixture(reviewed=False, derived=derived)
    with patch.object(N, 'prepare', side_effect=AssertionError('Unreviewed support reached native')) as native:
        with pytest.raises(ValueError):
            R.prepare_fields(value.bank, value.frame['sha256'], (512, 512),
                people_state=value.people, byte_budget=BUDGET, source_frame=value.frame)
        foreign = {**value.frame, 'sha256': '8'*64}
        with pytest.raises(ValueError):
            R.prepare_fields(value.bank, value.frame['sha256'], (512, 512),
                people_state=value.people, byte_budget=BUDGET, source_frame=foreign)
        with pytest.raises(ValueError):
            DERIVED.validate(value.bank, {**value.binding, 'width': 1024})
    native.assert_not_called()


@pytest.mark.parametrize('action', ['reset', 'disable'])
def test_missing_core_neutral_correction_uses_real_common_pixels_and_factual_receipt(action):
    """Real common map, sampler, outcome and adapter, not a fake PreparedPeople.

    The test's publish port records an actual rendered buffer but simulates the
    frame delivery boundary. It is not shared-memory/native-UI acceptance.
    """
    from lumaretouch_engine import head_size_host as H
    from lumaretouch_engine import shoulder_shape_runtime as COMMON
    from lumaretouch_engine.body_pose_host import BodyPoseHostMixin
    value = fixture()
    holder = {'bank': value.bank}
    binding = {'document_id': DOCUMENT, 'document_epoch': 'synthetic-head-epoch',
               'document_revision': 7, 'asset_sha256': value.frame['sha256']}
    ledger = BodyPoseHostMixin()
    ledger._body_init()
    rendered = []

    def prepare(candidate):
        return full_export(value, body=P.snapshot(candidate, value.frame))

    def publish(before, candidate, prepared, delta, request):
        assert before == holder['bank']
        assert prepared.body_fields == ()
        assert prepared.body_operation_order == ORDER.DEFAULT_BODY_ORDER.record()
        actual = prepared.geometry.warp_original(value.pixels)
        np.testing.assert_array_equal(actual, value.pixels)
        outcome = COMMON.outcome(prepared.body_fields, prepared.geometry,
            request_id=request['request_id'], render_revision=binding['document_revision'],
            original_dimensions=(512, 512), rendered_pixels=actual,
            published_frame_id='synthetic-buffer-boundary:neutral-head', sampling_passes=1)
        holder['bank'] = deepcopy(candidate)
        rendered.append((actual, outcome))
        view = H.view(candidate, binding, selected_body_ref=value.ref, people_state=value.people)
        view.update(last_outcome=outcome, publication={'request_id': request['request_id'],
            'rendered': True, 'unapplied_reason': None})
        return view

    ports = H.HostPorts(lambda: binding, lambda: holder['bank'], lambda: value.people,
        prepare, publish, ledger._head_size_receipt_get, ledger._head_size_receipt_put)
    adapter = H.HeadSizeHostAdapter(ports)
    request = {'request_id': 'synthetic-neutral-head-edit', 'gesture_id': 'synthetic-neutral-head-gesture',
        **{key: binding[key] for key in ('document_id', 'document_epoch', 'document_revision')},
        'state_revision': value.bank['revision'], 'association_revision': value.bank['association_revision'],
        'people_association_revision': value.people['association_revision'],
        'body_graph_sha256': P.graph_digest(value.bank), 'people_graph_sha256': P.people_digest(value.people),
        'body_ref': value.ref, 'operation_id': S.OP,
        'action': 'recipe' if action == 'reset' else 'operation_status',
        'payload': {'base': {'version': 1, 'amount': .5}, 'recipe': S.neutral()}
                   if action == 'reset' else {'enabled': False}}
    with patch.object(N, 'available', return_value=False), \
            patch.object(N, 'prepare', side_effect=AssertionError('Inactive head loaded Rust')) as native:
        result = adapter.execute(request)
        assert result['success'] is True and result['rendered'] is True
        assert result['outcome_unknown'] is False and result['unapplied_reason'] is None
        assert adapter.execute(request) == result
    native.assert_not_called()
    assert len(rendered) == 1 and rendered[0][1]['runtime_quality_accepted'] is False
    assert result['view']['last_outcome']['output_pixel_sha256'] == rendered[0][1]['output_pixel_sha256']


def test_derived_export_rejects_original_file_replay_before_native():
    value = fixture(derived=True)
    source = value.pixels.astype(np.float32)/65535.
    with patch.object(N, 'prepare', side_effect=AssertionError('Original path reached head solver')) as native:
        with pytest.raises(ValueError, match='original-path body inputs'):
            ENGINE.prepare_export(frozen(value), source, None, byte_budget=BUDGET,
                document_id=DOCUMENT, body_pose=P.snapshot(value.bank, value.frame),
                body_source_path='/synthetic-original-is-not-derived-input.tiff')
    native.assert_not_called()


@pytest.mark.parametrize('derived', [False, True])
def test_installed_head_uses_actual_rgb16_or_derived_float_common_map(derived):
    installed_native()
    value = fixture(derived=derived)
    before = deepcopy(value.bank)
    source = value.pixels.astype(np.float32)/65535. if derived else value.pixels
    prepared = full_export(value, pixels=source)
    assert len(prepared.body_fields) == 1
    field = prepared.body_fields[0]
    assert field.operation_id == S.OP and field.body_ref == value.ref
    assert field.associated_face_id == value.face_ref['face_instance_id']
    assert field.record['source'] == value.frame
    assert prepared.body_operation_order == ORDER.HEAD_SIZE_BODY_ORDER.record()
    assert prepared.geometry.composition_order == 'body-then-face-inverse-v1'
    assert prepared.geometry.delta.shape == (1, 512, 512, 2)
    assert np.any(prepared.geometry.delta[..., 0]) and np.any(prepared.geometry.delta[..., 1])
    actual = prepared.geometry.warp(source) if derived else prepared.geometry.warp_original(source)
    assert actual.shape == source.shape and actual.dtype == source.dtype and np.any(actual != source)
    np.testing.assert_array_equal(actual[[0, -1]], source[[0, -1]])
    np.testing.assert_array_equal(actual[:, [0, -1]], source[:, [0, -1]])
    assert value.bank == before
    ORDER.require_prepared(value.bank, value.frame['sha256'], prepared.body_fields, people_state=value.people)
    outcome = BODY_RENDER.export_outcome(prepared, actual, (512, 512))
    assert outcome['encoded_file_published'] is False
    assert outcome['geometry_original_resolution'] is True
    assert outcome['common_portrait_sampling_stages'] == 1
    assert outcome['runtime_quality_accepted'] is False
    assert outcome['fields'][0]['operation_id'] == S.OP


def test_installed_proxy_field_recomputes_original_coordinates_not_a_resized_bitmap():
    installed_native()
    value = fixture()
    full, = R.prepare_fields(value.bank, value.frame['sha256'], (512, 512),
        people_state=value.people, byte_budget=BUDGET, source_frame=value.frame)
    preview, = R.prepare_fields(value.bank, value.frame['sha256'], (256, 256),
        people_state=value.people, byte_budget=BUDGET, source_frame=value.frame)
    points = np.array([[230.125, 150.75], [270.5, 155.125], [220.1, 170.75]], np.float64)
    scale = np.array([255/511, 255/511])
    np.testing.assert_allclose(preview.evaluate(points*scale)/scale, full.evaluate(points), rtol=0, atol=1e-8)
    assert full.shape == (512, 512) and preview.shape == (256, 256)
    with pytest.raises(ValueError):
        full_export(value, pixels=value.pixels[::2, ::2])


def test_installed_affine_head_maps_associated_face_at_off_grid_inverse_coordinates():
    """Real body solver/common composer; synthetic face evaluator is routing-only."""
    installed_native()
    from lumaretouch_engine.shoulder_shape_runtime import compose
    value = fixture()
    field, = R.prepare_fields(value.bank, value.frame['sha256'], (512, 512),
        people_state=value.people, byte_budget=BUDGET, source_frame=value.frame)

    class SyntheticFace:
        face_instance_id = value.face_ref['face_instance_id']
        shape = (512, 512)

        def resident_bytes(self):
            return 0

        def evaluate(self, points):
            # Compact differentiable displacement confined to this own face.
            points = np.asarray(points, np.float64)
            offset = (points-np.array([255.5, 153.3]))/np.array([25., 20.])
            radius = np.sum(offset**2, axis=1)
            weight = np.maximum(0., 1.-radius)**3
            return np.column_stack((.3*weight, -.2*weight))

    face = SyntheticFace()
    result = compose((face,), (field,), (512, 512), byte_budget=BUDGET,
                     body_operation_order=ORDER.HEAD_SIZE_BODY_ORDER)
    yy, xx = np.mgrid[:512, :512]
    points = np.column_stack((xx.ravel(), yy.ravel())).astype(np.float64)
    body_delta = field.evaluate(points)
    expected = body_delta+face.evaluate(points-body_delta)
    wrong_destination_face = body_delta+face.evaluate(points)
    np.testing.assert_allclose(result.delta[0].reshape(-1, 2), expected, rtol=0, atol=1e-6)
    assert not np.allclose(expected, wrong_destination_face, rtol=0, atol=1e-6)
    face.face_instance_id = 'synthetic-unassociated-face'
    with pytest.raises(ValueError, match='another face owner'):
        compose((face,), (field,), (512, 512), byte_budget=BUDGET,
                body_operation_order=ORDER.HEAD_SIZE_BODY_ORDER)


def test_transport_and_receipts_keep_exact_ids_and_do_not_replay_uncertain_edits():
    from lumaretouch_engine.body_pose_commands import BodyTransport
    from lumaretouch_engine.body_pose_host import BodyPoseHostMixin
    engine = BodyPoseHostMixin()
    engine._body_init()
    request = {'cmd': 'head_size', 'action': 'status', 'request_id': 'outer-head-status',
               'request': {'request_id': 'inner-head-edit'}}
    calls = []
    engine._body_status = lambda key, operation: calls.append((key, operation)) or {
        'protocol': 1, 'request_id': key, 'success': False, 'outcome_unknown': True}
    engine._body_view = lambda operation: {'operation_id': S.OP}
    results = []
    transport = BodyTransport('head_size')
    transport.handle(engine, request, results.append)
    transport.handle(engine, request, results.append)
    assert calls == [('inner-head-edit', 'head_size')]
    assert results[0] == results[1] and results[0]['outcome_unknown'] is True
    assert results[0]['event'] == 'head_size_result'
    changed = {**request, 'request': {'request_id': 'different-edit'}}
    transport.handle(engine, changed, results.append)
    assert results[-1]['success'] is False and len(calls) == 1
    receipt = {'phase': 'done', 'outcome_unknown': False, 'success': True}
    engine._head_size_receipt_put('inner-head-edit', 'a'*64, receipt)
    with pytest.raises(ValueError, match='immutable'):
        engine._head_size_receipt_put('inner-head-edit', 'a'*64, {**receipt, 'success': False})
    with pytest.raises(ValueError, match='identity changed'):
        engine._head_size_receipt_put('inner-head-edit', 'b'*64, receipt)
    assert engine._waist_receipts == {} and engine._waist_length_receipts == {}


def test_source_only_shared_registration_and_no_original_decoder_in_head_path():
    """UNRUN source assertions are wiring checks, not runtime acceptance."""
    root = Path(__file__).resolve().parents[2]
    engine = root/'engine/src/lumaretouch_engine'
    server = (engine/'server.py').read_text()
    assert len(server.splitlines()) <= 7065
    for token in ('head_size_protocol', 'head_size_available', 'head_size_unavailable_reason'):
        assert token in server
    commands = (engine/'body_pose_commands.py').read_text()
    assert 'analysis_rgb(engine)' in commands and "BodyTransport('head_size')" in (engine/'body_pose_host.py').read_text()
    render = (engine/'body_pose_render.py').read_text()
    assert "head_size.prepare_fields(bank,frame['sha256']" in render
    assert 'source_frame=frame' in render
    assert 'head_size' in (engine/'creative_document_host.py').read_text()
    assert 'head_size:gesture:' in (engine/'history_controller.py').read_text()
    assert 'head_size' in (engine/'project_recovery_runtime.py').read_text()
    native_source = (engine/'head_size_native.py').read_text()
    assert 'liblrt_head_size.so' in native_source and 'subprocess' not in native_source
    assert 'build-head-size.sh' in (root/'packaging/stage-engine.sh').read_text()
