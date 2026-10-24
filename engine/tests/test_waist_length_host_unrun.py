# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN waist-length transaction and routing contracts.

LNX-REF-PC-32473-C-5d33f285bb. Synthetic source fixtures are not detector output.
The isolated host publication double below verifies request semantics only. It
does not stand in for real PreparedPeople, pixel publication, UI, native kernel,
end-to-end history/export acceptance or measured quality/performance. No product
import, collection, tests, native execution, build or typecheck ran in authoring.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from lumaretouch_engine import body_pose_evidence as E, body_pose_state as B
from lumaretouch_engine import body_pose_families as F, body_pose_project as D
from lumaretouch_engine import shoulder_shape_project as COMMON_PROJECT
from lumaretouch_engine import body_pose_document_history as DOCUMENT_HISTORY
from lumaretouch_engine import waist_length_state as S, waist_length_project as P
from lumaretouch_engine import waist_length_host as H
from lumaretouch_engine.body_pose_host import BodyPoseHostMixin
from lumaretouch_engine.body_pose_commands import BodyTransport
from lumaretouch_engine.history_controller import HistoryController, HistoryPorts
from test_waist_length_support_unrun import fixture, geometry


def host_fixture(*, amount=.5, enabled=True, prepare_error='synthetic native core unavailable'):
    bank, people, ref, _, source = fixture(amount=amount)
    if not enabled:
        bank = B.set_operation_enabled(bank, ref, S.OPERATION_ID, False)
    holder = {'bank': bank}; ledger = {}; published = []
    binding = {'document_id': 'synthetic-waist-document', 'document_epoch': 'synthetic-waist-epoch',
               'document_revision': 7, 'asset_sha256': source['sha256']}

    def prepare_candidate(candidate):
        raise ValueError(prepare_error)

    def publish(before, candidate, prepared, delta, request):
        assert isinstance(prepared, H.UnappliedPreparation)
        holder['bank'] = deepcopy(candidate)
        published.append(request['request_id'])
        return {'state_revision': candidate['revision'], 'body_graph_sha256': P.graph_digest(candidate),
                'publication': {'request_id': request['request_id'], 'rendered': False,
                                'unapplied_reason': prepared.reason}}

    def put(key, digest, result):
        if key in ledger:
            assert ledger[key]['digest'] == digest
        ledger[key] = {'digest': digest, 'result': deepcopy(result)}

    ports = H.HostPorts(lambda: binding, lambda: holder['bank'], lambda: people,
        prepare_candidate, publish, lambda key: deepcopy(ledger.get(key)), put)
    adapter = H.WaistLengthHostAdapter(ports)
    request = {'request_id': 'waist-length-request', 'gesture_id': 'waist-length-gesture',
        **{key: binding[key] for key in ('document_id', 'document_epoch', 'document_revision')},
        'state_revision': bank['revision'], 'association_revision': bank['association_revision'],
        'people_association_revision': people['association_revision'],
        'body_graph_sha256': P.graph_digest(bank), 'people_graph_sha256': P.people_digest(people),
        'body_ref': ref, 'operation_id': S.OPERATION_ID,
        'action': 'recipe', 'payload': {'base': {'version': 1, 'amount': amount}, 'recipe': S.neutral()}}
    return adapter, request, holder, ledger, published, ports


def test_exact_family_routes_to_existing_canonical_body_owner():
    assert S.OPERATION_ID == 'lnx.waist_length.v1'
    assert S.CONTROL_ID == 'LNX-REF-PC-32473-C-5d33f285bb'
    assert F.FAMILIES.count('waist_length') == 1
    assert F.request_family({'operation_id': S.OPERATION_ID}) == 'waist_length'
    assert F.presenter('waist_length') is H
    assert BodyTransport('waist_length').operation == 'waist_length'
    for operation in ('lnx.waist_length.v2', 'lnx.waist.v1'):
        with pytest.raises(ValueError):
            F.request_family({'operation_id': operation})


def test_neutral_recovery_is_unapplied_and_exact_receipt_never_replays():
    adapter, request, holder, _, published, ports = host_fixture()
    first = adapter.execute(request)
    assert first['success'] is True and first['rendered'] is False
    assert first['outcome_unknown'] is False
    assert first['unapplied_reason'] == 'synthetic native core unavailable'
    assert adapter.execute(request) == first
    assert H.WaistLengthHostAdapter(ports).execute(request) == first
    assert published == [request['request_id']]
    assert B.operation(holder['bank'], request['body_ref'], S.OPERATION_ID)['recipe'] == S.neutral()
    changed = deepcopy(request); changed['payload']['recipe']['amount'] = .2
    with pytest.raises(ValueError):
        adapter.execute(changed)


def test_disabled_operation_keeps_recipe_and_support_when_native_unavailable():
    adapter, request, holder, _, published, _ = host_fixture(amount=.5)
    before = deepcopy(B.operation(holder['bank'], request['body_ref'], S.OPERATION_ID))
    request.update(action='operation_status', payload={'enabled': False})
    result = adapter.execute(request)
    item = B.operation(holder['bank'], request['body_ref'], S.OPERATION_ID)
    assert result['success'] is True and result['rendered'] is False
    assert item['enabled'] is False and item['recipe'] == before['recipe']
    assert item['support_sha256'] == before['support_sha256']
    assert published == [request['request_id']]


def test_nonzero_request_cannot_publish_after_preparation_refusal():
    adapter, request, holder, _, published, _ = host_fixture()
    before = deepcopy(holder['bank'])
    request['payload']['recipe']['amount'] = -.5
    result = adapter.execute(request)
    assert result['phase'] == 'done' and result['success'] is False
    assert result['outcome_unknown'] is False and published == []
    assert holder['bank'] == before


def test_nonzero_enable_cannot_publish_after_preparation_refusal():
    adapter, request, holder, _, published, _ = host_fixture(amount=.5, enabled=False)
    before = deepcopy(holder['bank'])
    request.update(action='operation_status', payload={'enabled': True})
    result = adapter.execute(request)
    assert result['success'] is False and result['outcome_unknown'] is False
    assert holder['bank'] == before and published == []


@pytest.mark.parametrize('amount', (0., .5))
def test_review_keeps_manual_markers_and_actual_face_binding_atomically(amount):
    adapter, request, holder, _, published, _ = host_fixture(amount=amount)
    row = B.target(holder['bank'], request['body_ref'])
    draft = geometry()
    request.update(action='support_review', payload={'data': draft,
        'points_sha256': row['record']['points_sha256'], 'visible_anchors': list(S.REQUIRED_ANCHORS),
        'ownership_confirmed': True})
    result = adapter.execute(request)
    assert result['success'] is True and published == [request['request_id']]
    assert result['rendered'] is False and result['outcome_unknown'] is False
    assert result['unapplied_reason'] == 'synthetic native core unavailable'
    item = B.operation(holder['bank'], request['body_ref'], S.OPERATION_ID)
    assert item['recipe'] == {'version': 1, 'amount': amount}
    asset = B.support(holder['bank'], request['body_ref'], S.OPERATION_ID)
    assert item['review']['support_sha256'] == item['support_sha256'] == E.content_digest(asset)
    for key in S.WAIST_MARKERS:
        assert asset['data'][key] == draft[key]
    assert all(key in asset['data'] for key in S.FACE_BINDING_KEYS)


@pytest.mark.parametrize('key', ('waist_upper_left', 'waist_upper_right', 'waist_lower_left', 'waist_lower_right'))
def test_missing_manual_waist_mark_never_falls_back_to_pose_hip(key):
    adapter, request, holder, _, published, _ = host_fixture(amount=0)
    row = B.target(holder['bank'], request['body_ref'])
    draft = geometry(); del draft[key]
    request.update(action='support_review', payload={'data': draft,
        'points_sha256': row['record']['points_sha256'], 'visible_anchors': list(S.REQUIRED_ANCHORS),
        'ownership_confirmed': True})
    result = adapter.execute(request)
    assert result['success'] is False and result['outcome_unknown'] is False
    assert published == []


@pytest.mark.parametrize('key,value', (
    ('document_epoch', 'other-epoch'), ('document_revision', 8),
    ('body_graph_sha256', 'f'*64), ('people_graph_sha256', 'f'*64),
    ('state_revision', True), ('operation_id', 'lnx.torso_length.v1'),
    ('operation_id', 'lnx.waist_shape.v1')))
def test_stale_identity_or_adjacent_operation_never_publishes(key, value):
    adapter, request, _, _, published, _ = host_fixture()
    request[key] = value
    result = adapter.execute(request)
    assert result['success'] is False and result['outcome_unknown'] is False and published == []


def uncertain_fixture():
    _, request, holder, ledger, published, ports = host_fixture()
    def lost_notification(*args):
        ports.publish(*args)
        raise RuntimeError('synthetic lost notification after publication')
    adapter = H.WaistLengthHostAdapter(H.HostPorts(ports.binding, ports.read_bank,
        ports.read_people, ports.prepare, lost_notification, ports.receipt_get, ports.receipt_put))
    result = adapter.execute(request)
    return adapter, request, holder, ledger, published, result


def test_lost_publication_notification_stays_query_only():
    adapter, request, holder, _, published, first = uncertain_fixture()
    assert first['phase'] == 'pending' and first['outcome_unknown'] is True
    assert B.operation(holder['bank'], request['body_ref'], S.OPERATION_ID)['recipe'] == S.neutral()
    assert adapter.execute(request) == first and adapter.status(request['request_id']) == first
    assert published == [request['request_id']]


def test_canonical_status_reconciles_only_matching_family_and_request_digest():
    adapter, request, _, _, published, pending = uncertain_fixture()
    ident = request['request_id']
    actual = {'phase': 'done', 'protocol': 1, 'request_id': ident,
              'success': True, 'outcome_unknown': False, 'rendered': False}
    engine = SimpleNamespace(_body_adapter=lambda operation: adapter,
        _body_authoritative={ident: actual}, _body_authoritative_requests={})
    for meta in ({'operation': 'torso_length', 'digest': E.content_digest(request)},
                 {'operation': 'waist_length', 'digest': 'f'*64}):
        engine._body_authoritative_requests[ident] = meta
        assert BodyPoseHostMixin._body_status(engine, ident, 'waist_length') == pending
    engine._body_authoritative_requests[ident] = {'operation': 'waist_length', 'digest': E.content_digest(request)}
    assert BodyPoseHostMixin._body_status(engine, ident, 'waist_length') == actual
    assert adapter.execute(request) == actual and published == [ident]


def test_invalid_publication_is_not_promoted_by_an_unrelated_terminal_record():
    _, request, _, _, _, ports = host_fixture()
    def bad_publication(*args):
        result = ports.publish(*args)
        result['body_graph_sha256'] = 'f'*64
        return result
    adapter = H.WaistLengthHostAdapter(H.HostPorts(ports.binding, ports.read_bank,
        ports.read_people, ports.prepare, bad_publication, ports.receipt_get, ports.receipt_put))
    result = adapter.execute(request)
    assert result['phase'] == 'pending' and result['outcome_unknown'] is True
    assert result['publication_invalid'] is True
    with pytest.raises(ValueError):
        adapter.resolve_publication(request['request_id'], actual_result={
            'request_id': request['request_id'], 'phase': 'done', 'outcome_unknown': False})


def test_process_ledger_terminal_identity_cannot_change_or_expire_into_replay():
    owner = SimpleNamespace(_waist_length_receipts={})
    put = lambda key, digest, result: BodyPoseHostMixin._waist_length_receipt_put(owner, key, digest, result)
    terminal = {'phase': 'done', 'request_id': 'inner', 'success': True, 'outcome_unknown': False}
    put('inner', 'a'*64, {'phase': 'pending', 'request_id': 'inner', 'outcome_unknown': False})
    put('inner', 'a'*64, terminal); put('inner', 'a'*64, deepcopy(terminal))
    with pytest.raises(ValueError):
        put('inner', 'b'*64, terminal)
    with pytest.raises(ValueError):
        put('inner', 'a'*64, {**terminal, 'success': False})
    copy = BodyPoseHostMixin._waist_length_receipt_get(owner, 'inner')
    copy['result']['success'] = False
    assert owner._waist_length_receipts['inner']['result']['success'] is True


def test_existing_history_owner_coalesces_waist_gesture_and_retains_sparse_body_patch():
    bank, _, ref, _, _ = fixture(amount=0)
    first = B.set_recipe(bank, ref, {'version': 1, 'amount': .2}, operation_id=S.OPERATION_ID)
    second = B.set_recipe(first, ref, {'version': 1, 'amount': .5}, operation_id=S.OPERATION_ID)
    before = {D.KEY: COMMON_PROJECT.pack(bank)}
    after_first = {D.KEY: COMMON_PROJECT.pack(first)}
    after_second = {D.KEY: COMMON_PROJECT.pack(second)}
    clock = iter((0, 10**12))
    controller = HistoryController(HistoryPorts(lambda: after_second, E.content_digest,
        lambda *args: None, lambda *args: None, lambda: None, lambda: {}, lambda: None),
        lambda value: None, lambda: next(clock), 64, 100)
    group = 'waist_length:gesture:synthetic'
    controller.record(group, before, after=after_first)
    controller.record(group, after_first, after=after_second)
    assert len(controller.undo) == 1 and DOCUMENT_HISTORY.KEY in controller.undo[0]
    restored = DOCUMENT_HISTORY.restore(second, controller.undo[0])
    assert B.operation(restored, ref, S.OPERATION_ID)['recipe'] == S.neutral()
