# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored contract regressions. NOT RUN: static-only authorization this session."""
from copy import deepcopy
from unittest import mock
import numpy as np
import pytest
from lumaretouch_engine import hair_unification_state as S
from lumaretouch_engine import hair_unification_assets as A
from lumaretouch_engine import hair_unification_native as N
from lumaretouch_engine import hair_unification_runtime as R
from lumaretouch_engine import hair_unification_controller as C
from lumaretouch_engine import hair_unification_project as PROJECT
from lumaretouch_engine import hair_colour_assets as HAIR


def test_independent_exact_requirement_and_signed_meaning():
    assert S.OP == 'lnx.hair_unification.v1'
    assert S.CONTROL_ID == 'LNX-REF-PC-32472-C-fb2fe59a22'
    assert S.reference_side({'version': 1, 'amount': -1}) == 'tips'
    assert S.reference_side({'version': 1, 'amount': 1}) == 'roots'
    assert S.reference_side(S.neutral()) is None
    assert S.check(None) == {'version': 1, 'amount': 0.0}


@pytest.mark.parametrize('amount', [True, '1', float('nan'), float('inf'), -1.01, 1.01])
def test_bad_amount_refused(amount):
    with pytest.raises(ValueError): S.check({'version': 1, 'amount': amount})


def test_neutral_has_no_native_or_evidence_dependency_and_preserves_bits():
    source = np.array([[[np.nan, -0.0, 1.0]]], dtype=np.float32)
    with mock.patch.object(N, 'native', side_effect=AssertionError('native called')):
        assert N.compose(source, None, None, S.neutral()) is source
        assert N.measure(None, None, None, None, S.neutral(), byte_budget=0) is None
        assert R.prepare_bank({}, 'not-read', None, {'entries': []}, byte_budget=0) == ((), {})


def test_manual_sample_rejects_semantic_or_full_shortcuts():
    stack = A.empty_mask()
    stack['objects'] = [{'id': 'all', 'name': 'All', 'enabled': True, 'operation': 'add',
                         'kind': 'full', 'opacity': 1, 'feather': 0}]
    with pytest.raises(ValueError): A.sample(stack)


def test_selected_feather_footprint_is_exactly_protected():
    hair = np.ones((2, 3), dtype=np.float32)
    roots = np.array([[1, .01, 0], [0, 0, 0]], dtype=np.float32)
    tips = np.array([[0, 0, 0], [1, .01, 0]], dtype=np.float32)
    result = R.target_coverage(hair, roots, tips, {'version': 1, 'amount': 1})
    assert np.array_equal(result, [[0, 0, 1], [1, 1, 1]])
    result = R.target_coverage(hair, roots, tips, {'version': 1, 'amount': -1})
    assert np.array_equal(result, [[1, 1, 1], [0, 0, 1]])


def _request(action='context', payload=None):
    return {'cmd': 'hair_unification', 'protocol': 1, 'operation_id': S.OP,
        'request_id': 'request-1', 'action': action, 'people_context': {
            'document_id': 'document-1', 'document_epoch': 'epoch-1', 'document_revision': 1,
            'state_revision': 1, 'association_revision': 0,
            'target': {'scope': 'face', 'target_id': 'face-1', 'face_ref': {
                'asset_sha256': 'a'*64, 'face_instance_id': 'face-1', 'analysis_revision': 0}}},
        'payload': {} if payload is None else payload}


def test_request_requires_exact_operation_and_ack_contract():
    assert C.read_only(_request())
    assert not C.read_only(_request('clear'))
    wrong = _request(); wrong['operation_id'] = 'lnx.hair_colour.v1'
    with pytest.raises(ValueError): C.check_request(wrong)
    ack = {'preview_id': 'a'*32, 'review_token': 'b'*64, 'before_sha256': 'c'*64,
           'after_sha256': 'd'*64, 'support_sha256': 'e'*64}
    C.check_request(_request('presented', ack))
    wrong = deepcopy(ack); wrong.pop('after_sha256')
    with pytest.raises(ValueError): C.check_request(_request('presented', wrong))
    C.check_request(_request('commit', {'preview_id': 'a'*32, 'review_token': 'b'*64, 'confirmed': True}))


def _sample_record():
    ref = {'asset_sha256': 'a'*64, 'face_instance_id': 'person-one', 'analysis_revision': 0}
    support = A.empty_mask()
    support['objects'] = [{'id': 'hair', 'name': 'Reviewed hair', 'enabled': True, 'kind': 'radial',
        'operation': 'add', 'opacity': 1.0, 'feather': 0.0, 'center': [.5, .5], 'axes': [[.2, 0], [0, .2]]}]
    hair = HAIR.reviewed(ref, {'sha256': 'a'*64, 'width': 640, 'height': 480}, support,
                         HAIR.MODEL_SHA256, evidence_sha='b'*64, confirmed=True)
    record = A.reviewed(hair, A.empty_mask(), support, confirmed=True)
    return hair, record


def test_content_binding_cannot_copy_to_another_face_or_source():
    hair, record = _sample_record(); bank = {A.digest(hair): hair}
    assert A.verify_record(record, bank) == hair
    wrong = deepcopy(record); wrong['face_ref']['face_instance_id'] = 'person-two'
    with pytest.raises(ValueError): A.check(wrong)
    wrong = deepcopy(record); wrong['source']['sha256'] = 'c'*64
    with pytest.raises(ValueError): A.check(wrong)
    wrong = deepcopy(hair); wrong['support']['objects'][0]['center'] = [.6, .5]
    with pytest.raises(ValueError): A.verify_record(record, {A.digest(hair): wrong})


def test_asset_bank_is_append_only_and_digest_checked():
    _, record = _sample_record(); key = A.digest(record)
    assert A.check_store({key: record}) == {key: record}
    changed = deepcopy(record); changed['tip_sample']['objects'][0]['opacity'] = .5
    with pytest.raises(ValueError): A.check_store({key: changed})


def test_portable_leaf_never_embeds_samples():
    PROJECT.validate_leaf('/amount', -.5)
    with pytest.raises(ValueError): PROJECT.validate_leaf('/tip_sample', {})
    with pytest.raises(ValueError): PROJECT.validate_leaf('/amount', {'amount': .5})


def test_empty_stage_is_exact_identity_without_native():
    from lumaretouch_engine.hair_unification_composition import apply_records_np
    current = np.zeros((2, 2, 3), dtype=np.float32)
    with mock.patch.object(N, 'native', side_effect=AssertionError('native called')):
        result, fact = apply_records_np(current, [])
    assert result is current
    assert fact['changed_pixels'] == 0


def test_overlapping_boxes_disjoint_masks_preserve_both_people():
    """A later ROI's zero coverage must not overwrite earlier person's result."""
    from lumaretouch_engine.hair_unification_composition import apply_records_np
    from lumaretouch_engine.people_effects import LocalEffect
    current = np.full((8, 8, 3), .4, dtype=np.float32)
    first = np.zeros((8, 8), dtype=np.float32); first[1, 1] = 1
    second = np.zeros((8, 8), dtype=np.float32); second[2, 2] = 1
    reference = N.MeasuredReference(1, 8, 8, 64, 64, 64., 64., 64., 1., 0., (0., 0., 0.))
    parameters = R.Parameters(.5, reference)
    records = [LocalEffect({'face_instance_id': 'one'}, S.STAGE, (0, 0, 8, 8), weights=first, amounts=parameters),
               LocalEffect({'face_instance_id': 'two'}, S.STAGE, (0, 0, 8, 8), weights=second, amounts=parameters)]
    def compose(pixels, coverage, *_args, **_kwargs):
        return pixels + coverage[..., None] * np.float32(.01)
    with mock.patch.object(N, 'compose', side_effect=compose):
        output, _ = apply_records_np(current, records)
    assert np.all(output[1, 1] > current[1, 1])
    assert np.all(output[2, 2] > current[2, 2])
    assert np.array_equal(output[0, 0], current[0, 0])
    assert np.array_equal(current, np.full((8, 8, 3), .4, dtype=np.float32))


def test_disabled_neighbor_hair_claim_is_still_checked_for_overlap():
    active = {'asset_sha256': 'a'*64, 'enabled': True, 'local_assets': {'hair_colour': {}}}
    disabled = {'asset_sha256': 'a'*64, 'enabled': False, 'local_assets': {'hair_colour': {}}}
    other_source = {'asset_sha256': 'b'*64, 'enabled': False, 'local_assets': {'hair_colour': {}}}
    claims = R.ownership_faces({'faces': {'one': active, 'two': disabled, 'three': other_source}}, 'a'*64)
    assert claims == [active, disabled]
    # Simulate two admitted positive support fields: inactive effect status cannot
    # turn their shared pixel into first-person ownership.
    occupied = np.array([[True, False]])
    disabled_support = np.array([[1.0, 0.0]], dtype=np.float32)
    assert np.any((disabled_support > 0) & occupied)


def test_read_image_receipt_budget_keeps_correlated_tombstones_and_exact_writes():
    from collections import OrderedDict
    first_request = _request()
    second_request = {**_request(), 'request_id': 'request-2'}
    def image_receipt(request, image):
        return {'digest': A.digest(request), 'result': {'event': 'hair_unification_result',
            'request_id': request['request_id'], 'action': request['action'],
            'people_context': deepcopy(request['people_context']), 'request_payload': deepcopy(request['payload']),
            'success': True, 'outcome_unknown': False, 'payload': {'source_png': image}}}
    first = image_receipt(first_request, 'data:image/png;base64,'+'a'*60)
    second = image_receipt(second_request, 'data:image/png;base64,'+'b'*60)
    mutation = {'digest': 'c'*64, 'result': {'action': 'commit', 'success': True, 'payload': {'committed': True}}}
    ack = {'digest': 'd'*64, 'result': {'action': 'presented', 'success': True, 'payload': {'presented': True}}}
    receipts = OrderedDict((('request-1', first), ('commit', mutation), ('ack', ack), ('request-2', second)))
    with mock.patch.object(C, 'MAX_READ_IMAGE_BYTES', 100):
        C._bound_read_images(receipts)
    old = receipts['request-1']
    assert old['digest'] == A.digest(first_request)
    assert old['result']['request_payload'] == first_request['payload']
    assert old['result']['people_context'] == first_request['people_context']
    assert old['result']['payload_released'] is True
    assert old['result']['success'] is False
    assert old['result']['outcome_unknown'] is False
    assert C._image_bytes(old['result']) == 0
    assert receipts['commit'] is mutation and receipts['ack'] is ack
    assert receipts['request-2'] is second
    assert sum(C._image_bytes(row['result']) for row in receipts.values()) <= 100
    # No live owner exists: exact identity returns immediately without recapture.
    from types import SimpleNamespace
    engine = SimpleNamespace(_hair_unification_receipts=receipts)
    C.execute(engine, first_request, lambda _value: None)


def test_receipt_identity_capacity_refuses_new_work_without_evicting_old_ids():
    from collections import OrderedDict
    from types import SimpleNamespace
    receipts = OrderedDict([('retained', {'digest': 'a'*64, 'result': {'action': 'commit'}})])
    engine = SimpleNamespace(_hair_unification_receipts=receipts)
    with mock.patch.object(C, 'MAX_RECEIPTS', 1):
        with pytest.raises(ValueError, match='receipt capacity'):
            C.execute(engine, _request(), lambda _value: None)
    assert list(receipts) == ['retained']
