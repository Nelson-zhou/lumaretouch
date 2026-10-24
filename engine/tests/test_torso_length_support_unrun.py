# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN torso source ownership, support and host contracts.

No product imports, test collection/execution, builds, typechecks, inference,
downloads or native calls ran while authoring. Positive synthetic records carry
the expected manifest identifiers ONLY to exercise schema/ownership routing;
they are not detector outputs or evidence of anatomy or photographic quality.
Native-boundary doubles verify adapters, not the Rust numerical guarantees.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest

from lumaretouch_engine import body_pose_evidence as E, body_pose_manifest as M
from lumaretouch_engine import body_pose_state as B, people_state as PEOPLE
from lumaretouch_engine import torso_length_state as S, torso_length_native as N
from lumaretouch_engine import torso_length_runtime as R, torso_length_project as P
from lumaretouch_engine import torso_length_host as H, torso_length_adapter as A
from lumaretouch_engine.torso_length_field import TorsoLengthField

BUDGET = 16*1024*1024
SOURCE = {'sha256': 'a'*64, 'width': 1024, 'height': 1024, 'orientation': E.ORIENTATION}


def synthetic_record(*, source=None, observed=True):
    source = deepcopy(SOURCE if source is None else source)
    points = [dict(index=i, x=.5, y=.85, z=0., visibility=.99 if observed else 0.,
                   presence=.99 if observed else 0.) for i in range(33)]
    head = [(0.5, .32), (.49, .30), (.48, .30), (.47, .30), (.51, .30),
            (.52, .30), (.53, .30), (.46, .33), (.54, .33), (.49, .37), (.51, .37)]
    upper = {11: (.43, .46), 12: (.57, .46), 13: (.38, .55), 14: (.62, .55),
             15: (.35, .65), 16: (.65, .65), 17: (.34, .69), 18: (.66, .69),
             19: (.35, .70), 20: (.65, .70), 21: (.36, .68), 22: (.64, .68),
             23: (.44, .71), 24: (.56, .71)}
    for index, (x, y) in {**dict(enumerate(head)), **upper}.items():
        points[index].update(x=x, y=y)
    return E.create(source_frame=source, values=points,
        backend_version='synthetic-routing-fixture', backend_code_sha256='b'*64,
        model_id=M.MODEL_ID, model_sha256=M.MODEL_SHA256, input_rgb_sha256='c'*64,
        input_dimensions=(source['width'], source['height']))


def geometry():
    """Synthetic explicit contour choices, never proposed production anatomy."""
    return {'version': 1, 'method': S.METHOD,
            'outer_left': .03, 'inner_left': .28, 'inner_right': .72, 'outer_right': .97,
            'upper_zero': .03, 'upper_plateau': .23,
            'head_box': [.4, .25, .6, .4],
            'left_arm_box': [.3, .43, .49, .73],
            'right_arm_box': [.51, .43, .7, .73],
            'confirmations': {flag: True for flag in S.FLAGS}}


def fixture(*, amount=.5, review=True, source=None):
    record = synthetic_record(source=source)
    source = record['source']
    state = B.add_run(B.empty(), {'source': source, 'records': [record],
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False},
        initial_operations=(S.OPERATION_ID,), operation_policies=S.policies())
    ref = record['body_ref']
    evidence = {'backend': 'synthetic-routing-fixture', 'detector_model_sha256': 'd'*64,
                'semantic_model_sha256': None, 'landmark_digest': 'e'*64, 'status': 'verified',
                'source_width': source['width'], 'source_height': source['height'],
                'orientation': source['orientation']}
    face = PEOPLE.new_face(source['sha256'], [.44, .27, .56, .39], evidence)
    people = PEOPLE.empty()
    people['faces'][face['face_instance_id']] = face
    people['persons']['synthetic-person'] = {'anonymous': True}
    people['revision'] = people['association_revision'] = 1
    people['links'] = [{'face_instance_id': face['face_instance_id'], 'person_id': 'synthetic-person',
                       'state': 'confirmed', 'confirmation_revision': 1}]
    state = B.associate(state, ref, 'synthetic-person', people, user_confirmed=True)
    data = R.bind_support_review(geometry(), B.target(state, ref), people)
    if review:
        state = B.set_support(state, ref, S.OPERATION_ID, S.SUPPORT_KIND, data,
                              operation_policies=S.policies())
        state = B.review(state, ref, operation_id=S.OPERATION_ID,
            points_sha256=record['points_sha256'], visible_anchors=list(S.REQUIRED_ANCHORS),
            ownership_confirmed=True, support_sha256=B.operation(state, ref, S.OPERATION_ID)['support_sha256'],
            operation_policies=S.policies())
    state = B.set_recipe(state, ref, {'version': 1, 'amount': amount},
                         operation_id=S.OPERATION_ID, operation_policies=S.policies())
    return state, people, ref, data, source


def native_prepare_double(points, values, support, shape):
    """Only copies the Rust ABI state layout; not its admission proof or solve."""
    h, w = shape
    shoulder = max(points[11, 1], points[12, 1])*(h-1)
    hip = min(points[23, 1], points[24, 1])*(h-1)
    state = np.array([*(np.asarray(support[:4])*(w-1)),
        *(np.asarray(support[4:6])*(h-1)), shoulder, hip,
        -.08*values[0]*(hip-shoulder), w, h], np.float64)
    state.setflags(write=False)
    return state


def native_facts_double(state):
    return {'support_box': [state[0], state[4], state[3], state[7]],
            'plateau_box': [state[1], state[5], state[2], state[6]],
            'max_displacement': abs(float(state[8])),
            'forward_jacobian_bounds': [.55, 1.45],
            'shoulder_level': state[6], 'hip_level': state[7],
            'head_translation_y': state[8]}


def prepare(data, *, shape=(512, 512), native=None, **kwargs):
    bank, people, _, _, source = data
    with patch.object(N, 'prepare', side_effect=native or native_prepare_double), \
            patch.object(N, 'facts', side_effect=native_facts_double):
        return R.prepare_fields(bank, source['sha256'], shape, people_state=people,
                                 byte_budget=BUDGET, source_frame=source, **kwargs)


def test_exact_upper_body_length_control_and_independent_anchors():
    assert S.OPERATION_ID == 'lnx.torso_length.v1'
    assert S.IDS == {'amount': 'LNX-REF-PC-32473-C-f1662d2dec'}
    assert S.REQUIRED_ANCHORS == tuple(range(25))
    assert S.SUPPORT_KIND == 'torso-length-visible-upper-body-review-v1'
    assert len(S.support_vector(fixture()[3])) == 18


@pytest.mark.parametrize('amount', [-1., -.5, 0., .5, 1.])
def test_bidirectional_amount_is_the_only_portable_value(amount):
    value = {'version': 1, 'amount': amount}
    assert S.vector(S.portable(value)) == [amount]
    assert S.adjust(S.neutral(), 'amount', amount) == value
    for forbidden in ('body_ref', 'associated_face_ref', 'support', 'waist_length', 'width'):
        with pytest.raises(ValueError):
            S.portable({**value, forbidden: None})


@pytest.mark.parametrize('amount', [True, None, -1.001, 1.001, float('nan'), float('inf'), 10**1000])
def test_invalid_amount_never_clamps_or_changes_direction(amount):
    with pytest.raises(ValueError):
        S.check({'version': 1, 'amount': amount})


def test_neutral_field_has_no_native_or_support_dependency():
    bank, _, ref, _, _ = fixture(amount=0, review=False)
    with patch.object(N, 'prepare', side_effect=AssertionError('neutral native prepare')), \
            patch.object(N, 'evaluate', side_effect=AssertionError('neutral native evaluate')):
        field = TorsoLengthField(B.target(bank, ref), None, (512, 512))
        points = np.array([[12.125, 45.75], [200.3, 300.6]])
        np.testing.assert_array_equal(field.evaluate(points), np.zeros_like(points))
        assert not field.contains(points).any() and field.supports == ()
        assert field.max_displacement == 0 and field.resident_bytes() == field.render_scale.nbytes
        assert field.facts['hidden_anatomy_inferred'] is False
        assert field.facts['runtime_quality_accepted'] is False


def test_neutral_runtime_does_not_reresolve_removed_face_or_body_association():
    bank, people, ref, support, source = fixture(amount=0)
    bank = B.unlink(bank, ref)
    people['faces'].clear(); people['links'].clear(); people['association_revision'] += 1
    with patch.object(R, 'associated_face', side_effect=AssertionError('neutral associated face')), \
            patch.object(N, 'prepare', side_effect=AssertionError('neutral native')):
        assert R.prepare_fields(bank, source['sha256'], (512, 512), people_state=people,
                                 byte_budget=BUDGET, source_frame=source) == ()


@pytest.mark.parametrize('flag', S.FLAGS)
def test_each_explicit_contour_and_background_confirmation_is_required(flag):
    bank, _, ref, support, _ = fixture()
    support['confirmations'][flag] = False
    with pytest.raises(ValueError):
        S.check_support(support, B.target(bank, ref)['record'])


@pytest.mark.parametrize('index', S.REQUIRED_ANCHORS)
def test_review_never_promotes_hidden_head_arm_hand_shoulder_or_hip(index):
    bank, _, ref, support, _ = fixture()
    record = deepcopy(B.target(bank, ref)['record'])
    record['points'][index]['visibility'] = .79
    record['points_sha256'] = E.content_digest(record['points'])
    with pytest.raises(ValueError):
        S.check_support(support, record)


@pytest.mark.parametrize('key', [*S.COLUMNS, *S.BOXES, *R.FACE_BINDING_KEYS])
def test_no_missing_support_geometry_or_reviewed_face_binding(key):
    support = fixture()[3]
    del support[key]
    with pytest.raises(ValueError):
        S.check_support(support)


def test_review_cannot_reuse_head_or_arm_box_as_anatomical_length_measurement():
    bank, _, ref, support, _ = fixture()
    record = B.target(bank, ref)['record']
    for key, box in (('head_box', [.4, .25, .6, .47]),
                     ('left_arm_box', [.4, .43, .49, .73]),
                     ('right_arm_box', [.51, .43, .6, .73])):
        altered = deepcopy(support); altered[key] = box
        with pytest.raises(ValueError):
            S.check_support(altered, record)


def test_active_without_independent_review_refuses_before_native():
    data = fixture(review=False)
    with pytest.raises(R.TorsoLengthRefused, match='independently reviewed'):
        prepare(data, native=lambda *a: pytest.fail('unreviewed native call'))


def test_field_prepares_original_source_coordinates_and_conjugates_decoder_scales():
    data = fixture(source={**SOURCE, 'width': 1200, 'height': 1600})
    seen = []
    def admission(points, values, support, shape):
        seen.append(shape)
        return native_prepare_double(points, values, support, shape)
    field, = prepare(data, shape=(800, 600), native=admission)
    assert seen == [(1600, 1200)]
    points = np.array([[31.25, 72.125], [300., 210.]])
    def evaluate(state, source_points):
        np.testing.assert_allclose(source_points, points/field.render_scale)
        return np.tile([0., -7.], (len(source_points), 1))
    with patch.object(N, 'evaluate', side_effect=evaluate):
        np.testing.assert_allclose(field.evaluate(points), np.tile([0., -7.], (2, 1))*field.render_scale)
    assert field.facts['fixed_joint_indices'] == [23, 24]
    assert field.facts['whole_arms_rigidly_translated'] is False


def test_rounded_proxy_edges_map_exactly_without_clipping_nearby_coordinates():
    data = fixture(source={**SOURCE, 'width': 1201, 'height': 1601})
    field, = prepare(data, shape=(800, 600))
    # ALIGN=8 proxy extents differ from the exact original-source ratio.
    points = np.array([[0., 0.], [599., 799.], [0., 799.], [599., 0.],
                       [598.875, 798.875],
                       [np.nextafter(599., 0.), np.nextafter(799., 0.)]])
    expected_interior = points[4:]/field.render_scale
    def evaluate(state, source_points):
        np.testing.assert_array_equal(source_points[:4],
            [[0., 0.], [1200., 1600.], [0., 1600.], [1200., 0.]])
        np.testing.assert_array_equal(source_points[4:], expected_interior)
        return np.zeros_like(source_points)
    with patch.object(N, 'evaluate', side_effect=evaluate) as native:
        np.testing.assert_array_equal(field.evaluate(points), np.zeros_like(points))
        assert native.call_count == 1
    with patch.object(N, 'evaluate', side_effect=AssertionError('outside coordinate reached native')):
        for outside in ([[np.nextafter(599., np.inf), 400.]],
                        [[300., np.nextafter(799., np.inf)]],
                        [[np.nextafter(0., -np.inf), 400.]],
                        [[300., np.nextafter(0., -np.inf)]]):
            with pytest.raises(ValueError, match='no clipping'):
                field.evaluate(outside)


def test_native_refusal_is_all_or_nothing_without_attenuation_or_fallback():
    calls = []
    def refuse(points, values, support, shape):
        calls.append(list(values))
        raise ValueError('synthetic native contraction refusal')
    with pytest.raises(R.TorsoLengthRefused, match='contraction') as error:
        prepare(fixture(amount=1), native=refuse)
    assert calls == [[1.]]
    assert all(row['applied'] is False for row in error.value.refusals)


@pytest.mark.parametrize('fault', ['missing', 'stale-link', 'unconfirmed', 'manual', 'unresolved',
                                 'face-analysis', 'face-box', 'face-evidence', 'face-source-size'])
def test_current_actual_associated_face_is_mandatory(fault):
    bank, people, ref, support, source = fixture()
    face = people['faces'][support['associated_face_ref']['face_instance_id']]
    if fault == 'missing': people = None
    elif fault == 'stale-link': people['association_revision'] += 1
    elif fault == 'unconfirmed': people['links'][0].update(state='candidate', confirmation_revision=None)
    elif fault == 'manual': face['manual'] = True
    elif fault == 'unresolved': face['evidence']['status'] = 'unresolved'
    elif fault == 'face-analysis': face['analysis_revision'] += 1
    elif fault == 'face-box': face['box'][0] += .01
    elif fault == 'face-evidence': face['evidence']['landmark_digest'] = 'f'*64
    else: face['evidence']['source_width'] += 1
    with pytest.raises(R.TorsoLengthRefused):
        prepare((bank, people, ref, support, source), native=lambda *a: pytest.fail('invalid face reached native'))


def test_reviewer_binding_fills_only_current_facts_and_refuses_partial_or_conflicting_metadata():
    bank, people, ref, support, _ = fixture()
    raw = geometry(); original = deepcopy(raw)
    assert R.bind_support_review(raw, B.target(bank, ref), people) == support
    assert raw == original
    assert R.bind_support_review(support, B.target(bank, ref), people) == support
    with pytest.raises(ValueError):
        R.bind_support_review({**raw, 'associated_face_box': support['associated_face_box']},
                              B.target(bank, ref), people)
    changed = deepcopy(support); changed['associated_face_evidence_sha256'] = 'f'*64
    with pytest.raises(ValueError):
        R.bind_support_review(changed, B.target(bank, ref), people)


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('status', ['verified', 'unresolved'])
def test_all_foreign_retained_faces_protect_their_pixels(enabled, status):
    data = fixture(); people = data[1]
    own = next(iter(people['faces'].values()))
    evidence = {**own['evidence'], 'status': status}
    other = PEOPLE.new_face(data[4]['sha256'], [.75, .4, .85, .5], evidence, manual=True)
    other['enabled'] = enabled
    people['faces'][other['face_instance_id']] = other
    with pytest.raises(R.TorsoLengthRefused, match='another retained face'):
        prepare(data)


def test_closed_boundary_contact_is_not_foreign_face_clearance():
    a = (np.array([1., 2.]), np.array([5., 6.]))
    b = (np.array([5., 3.]), np.array([7., 4.]))
    assert R._overlap(a, b)


@pytest.mark.parametrize('observed', [True, False])
def test_disabled_foreign_bodies_still_block_ambiguous_transition(observed):
    data = list(fixture())
    other = synthetic_record(observed=observed)
    data[0] = B.add_run(data[0], {'source': data[4], 'records': [other], 'detector_limit': 4,
        'limit_reached': False, 'census_complete': False}, initial_operations=(S.OPERATION_ID,))
    data[0]['bodies'][other['body_ref']['body_instance_id']]['enabled'] = False
    with pytest.raises(R.TorsoLengthRefused, match='body'):
        prepare(data)


def test_source_dimensions_digest_and_whole_canvas_cannot_be_substituted():
    data = fixture(); bank, people, _, _, source = data
    for changed in ({**source, 'width': 1032}, {**source, 'sha256': 'f'*64}):
        with pytest.raises(ValueError):
            R.prepare_fields(bank, source['sha256'], (512, 512), people_state=people,
                             byte_budget=BUDGET, source_frame=changed)
    with pytest.raises(ValueError):
        R.prepare_fields(bank, source['sha256'], (512, 400), people_state=people,
                         byte_budget=BUDGET, source_frame=source)


def test_wrong_pose_model_refuses_before_native_even_with_valid_manual_review():
    bank, people, ref, support, source = fixture()
    B.target(bank, ref)['record']['model_sha256'] = 'f'*64
    with pytest.raises(R.TorsoLengthRefused, match='model identity'):
        prepare((bank, people, ref, support, source), native=lambda *a: pytest.fail('wrong model native'))


def test_shared_project_roundtrip_freezes_source_support_and_common_order():
    bank, _, ref, support, source = fixture()
    assert P.unpack(P.pack(bank)) == bank
    frozen = P.snapshot(bank, source)
    assert P.check_snapshot(frozen, source) == bank
    assert frozen['body_operation_order']['operation_ids'][-1] == S.OPERATION_ID
    changed = deepcopy(frozen); changed['body_operation_order']['operation_ids'].remove(S.OPERATION_ID)
    with pytest.raises(ValueError): P.check_snapshot(changed, source)
    assert B.support(bank, ref, S.OPERATION_ID)['data'] == support


def test_history_cannot_overwrite_associations_other_operations_or_later_values():
    bank, people, ref, _, _ = fixture()
    changed = B.set_recipe(bank, ref, {'version': 1, 'amount': -.5}, operation_id=S.OPERATION_ID)
    delta = P.history_patch(bank, changed, people_sha256=P.people_digest(people))
    restored = P.replay_patch(changed, delta, undo=True, people_state=people,
                              expected_bank_sha256=P.graph_digest(changed))
    assert B.operation(restored, ref, S.OPERATION_ID)['recipe']['amount'] == .5
    later = B.set_recipe(changed, ref, {'version': 1, 'amount': .25}, operation_id=S.OPERATION_ID)
    with pytest.raises(ValueError):
        P.replay_patch(later, delta, undo=True, people_state=people,
                       expected_bank_sha256=P.graph_digest(later))
    different = deepcopy(changed); B.target(different, ref)['association'] = None
    with pytest.raises(ValueError): P.history_patch(bank, different, people_sha256=P.people_digest(people))


def test_neutral_new_family_preserves_prior_chain_identity():
    from lumaretouch_engine.body_pose_geometry import effective_order
    neutral = fixture(amount=0)[0]
    assert effective_order(neutral).record()['version'] == 1
    active = fixture(amount=.5)[0]
    assert effective_order(active).record()['version'] == 7


def test_transfer_copies_only_amount_and_keeps_independent_target_owned_review():
    source_bank, people, source_ref, source_support, _ = fixture(amount=-.75)
    target_bank, target_people, target_ref, target_support, _ = fixture(
        amount=0, source={**SOURCE, 'sha256': 'f'*64})
    people['faces'].update(target_people['faces']); people['links'].extend(target_people['links'])
    changed = P.transfer_recipe(source_bank, source_ref, target_bank, target_ref,
        people_state=people, expected_people_sha256=P.people_digest(people),
        expected_source_bank_sha256=P.graph_digest(source_bank),
        expected_target_bank_sha256=P.graph_digest(target_bank),
        confirmed_person_id='synthetic-person', user_confirmed=True)
    assert B.operation(changed, target_ref, S.OPERATION_ID)['recipe'] == {'version': 1, 'amount': -.75}
    assert B.support(changed, target_ref, S.OPERATION_ID)['data'] == target_support != source_support
    face = people['faces'][target_support['associated_face_ref']['face_instance_id']]
    face['analysis_revision'] += 1
    with pytest.raises(ValueError, match='reviewed face analysis'):
        P.transfer_recipe(source_bank, source_ref, target_bank, target_ref,
            people_state=people, expected_people_sha256=P.people_digest(people),
            expected_source_bank_sha256=P.graph_digest(source_bank),
            expected_target_bank_sha256=P.graph_digest(target_bank),
            confirmed_person_id='synthetic-person', user_confirmed=True)


def test_export_rejects_proxy_or_nonfinite_source_before_common_preparation():
    data = fixture(); source = data[4]
    prepared = SimpleNamespace(geometry=SimpleNamespace(delta=np.zeros((1, 512, 512, 2), np.float32)))
    with patch.object(A, 'prepare_common', side_effect=AssertionError('invalid export common preparation')):
        with pytest.raises(ValueError):
            A.prepare_export(prepared, (), P.snapshot(data[0], source), data[1], source,
                np.zeros((512, 512, 3), np.uint16), people_geometry_identity='f'*64, byte_budget=BUDGET)
        pixels = np.zeros((1024, 1024, 3), np.float32); pixels[0, 0, 0] = np.nan
        with pytest.raises(ValueError):
            A.prepare_export(prepared, (), P.snapshot(data[0], source), data[1], source,
                pixels, people_geometry_identity='f'*64, byte_budget=BUDGET)


def host_fixture(*, amount=.5, prepare_error='synthetic unrelated family refusal'):
    bank, people, ref, support, source = fixture(amount=amount)
    holder = {'bank': bank}; ledger = {}; published = []
    binding = {'document_id': 'synthetic-document', 'document_epoch': 'synthetic-epoch',
               'document_revision': 7, 'asset_sha256': source['sha256']}
    def prepare_candidate(candidate):
        raise ValueError(prepare_error)
    def publish(before, candidate, prepared, delta, request):
        assert isinstance(prepared, H.UnappliedPreparation)
        holder['bank'] = deepcopy(candidate); published.append(request['request_id'])
        return {'state_revision': candidate['revision'], 'body_graph_sha256': P.graph_digest(candidate),
                'publication': {'request_id': request['request_id'], 'rendered': False,
                                'unapplied_reason': prepared.reason}}
    def put(key, digest, result):
        if key in ledger: assert ledger[key]['digest'] == digest
        ledger[key] = {'digest': digest, 'result': deepcopy(result)}
    ports = H.HostPorts(lambda: binding, lambda: holder['bank'], lambda: people,
        prepare_candidate, publish, lambda key: deepcopy(ledger.get(key)), put)
    adapter = H.TorsoLengthHostAdapter(ports)
    request = {'request_id': 'torso-request', 'gesture_id': 'torso-gesture',
        **{key: binding[key] for key in ('document_id', 'document_epoch', 'document_revision')},
        'state_revision': bank['revision'], 'association_revision': bank['association_revision'],
        'people_association_revision': people['association_revision'],
        'body_graph_sha256': P.graph_digest(bank), 'people_graph_sha256': P.people_digest(people),
        'body_ref': ref, 'operation_id': S.OPERATION_ID,
        'action': 'recipe', 'payload': {'base': {'version': 1, 'amount': amount}, 'recipe': S.neutral()}}
    return adapter, request, holder, ledger, published, ports


def test_neutral_recovery_retains_original_unapplied_and_exact_receipt_once():
    adapter, request, holder, ledger, published, ports = host_fixture()
    first = adapter.execute(request)
    assert first['success'] is True and first['rendered'] is False and first['outcome_unknown'] is False
    assert first == adapter.execute(request) and published == ['torso-request']
    assert H.TorsoLengthHostAdapter(ports).status('torso-request') == first
    assert B.operation(holder['bank'], request['body_ref'], S.OPERATION_ID)['recipe'] == S.neutral()
    changed = deepcopy(request); changed['payload']['recipe']['amount'] = .2
    with pytest.raises(ValueError): adapter.execute(changed)


def test_active_recipe_cannot_publish_after_prepare_refusal():
    adapter, request, _, _, published, _ = host_fixture()
    request['payload']['recipe']['amount'] = -.5
    result = adapter.execute(request)
    assert result['success'] is False and result['outcome_unknown'] is False and published == []


def test_support_review_binds_current_face_and_publishes_both_asset_and_review_atomically():
    adapter, request, holder, _, published, _ = host_fixture(amount=0)
    row = B.target(holder['bank'], request['body_ref'])
    request.update(action='support_review', payload={'data': geometry(),
        'points_sha256': row['record']['points_sha256'], 'visible_anchors': list(S.REQUIRED_ANCHORS),
        'ownership_confirmed': True})
    result = adapter.execute(request)
    assert result['success'] is True and published == ['torso-request']
    item = B.operation(holder['bank'], request['body_ref'], S.OPERATION_ID)
    asset = B.support(holder['bank'], request['body_ref'], S.OPERATION_ID)
    assert item['review']['support_sha256'] == item['support_sha256'] == E.content_digest(asset)
    assert all(key in asset['data'] for key in R.FACE_BINDING_KEYS)


def test_stale_document_or_graph_envelope_never_publishes():
    for key, changed in (('document_epoch', 'different-epoch'), ('document_revision', 8),
                         ('body_graph_sha256', 'f'*64), ('people_graph_sha256', 'f'*64),
                         ('state_revision', True)):
        adapter, request, _, _, published, _ = host_fixture()
        request[key] = changed
        result = adapter.execute(request)
        assert result['success'] is False and result['outcome_unknown'] is False and published == []


def test_lost_publication_notification_is_query_only_never_replayed():
    _, request, holder, _, published, ports = host_fixture()
    def lost_notification(*args):
        ports.publish(*args)
        raise RuntimeError('synthetic notification lost after publication')
    adapter = H.TorsoLengthHostAdapter(H.HostPorts(ports.binding, ports.read_bank,
        ports.read_people, ports.prepare, lost_notification, ports.receipt_get, ports.receipt_put))
    first = adapter.execute(request)
    assert first['phase'] == 'pending' and first['outcome_unknown'] is True
    assert B.operation(holder['bank'], request['body_ref'], S.OPERATION_ID)['recipe'] == S.neutral()
    assert adapter.execute(request) == first and adapter.status(request['request_id']) == first
    assert published == [request['request_id']]


def test_off_grid_queries_must_be_finite_two_column_coordinates():
    data = fixture(amount=0, review=False)
    field = TorsoLengthField(B.target(data[0], data[2]), None, (512, 512))
    for invalid in (np.zeros((2, 3)), np.zeros(2), [[float('nan'), 1.]], [[1., float('inf')]]):
        with pytest.raises(ValueError): field.evaluate(invalid)
        with pytest.raises(ValueError): field.contains(invalid)
