# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN head-size transaction and routing contracts.

LNX-REF-PC-32473-C-dc1b0ba40a. Synthetic source fixtures are not detector output.
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
from lumaretouch_engine import head_size_state as S, head_size_project as P
from lumaretouch_engine import head_size_host as H
from lumaretouch_engine.body_pose_host import BodyPoseHostMixin
from lumaretouch_engine.body_pose_commands import BodyTransport
from lumaretouch_engine.history_controller import HistoryController, HistoryPorts
from test_head_size_support_unrun import fixture, geometry


@pytest.fixture(autouse=True)
def available_core_boundary(monkeypatch):
    """Availability-routing double only; never native numerical acceptance."""
    monkeypatch.setattr(H.N, 'available', lambda: True)


def host_fixture(*, amount=.5, enabled=True, prepare_error='synthetic native core unavailable'):
    bank, people, ref, _, source = fixture(amount=amount)
    if not enabled:
        bank = B.set_operation_enabled(bank, ref, S.OPERATION_ID, False)
    holder = {'bank': bank}; ledger = {}; published = []
    binding = {'document_id': 'synthetic-head-document', 'document_epoch': 'synthetic-head-epoch',
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
    adapter = H.HeadSizeHostAdapter(ports)
    request = {'request_id': 'head-size-request', 'gesture_id': 'head-size-gesture',
        **{key: binding[key] for key in ('document_id', 'document_epoch', 'document_revision')},
        'state_revision': bank['revision'], 'association_revision': bank['association_revision'],
        'people_association_revision': people['association_revision'],
        'body_graph_sha256': P.graph_digest(bank), 'people_graph_sha256': P.people_digest(people),
        'body_ref': ref, 'operation_id': S.OPERATION_ID,
        'action': 'recipe', 'payload': {'base': {'version': 1, 'amount': amount}, 'recipe': S.neutral()}}
    return adapter, request, holder, ledger, published, ports


def test_exact_family_routes_to_existing_canonical_body_owner():
    assert S.OPERATION_ID == 'lnx.head_size.v1'
    assert S.CONTROL_ID == 'LNX-REF-PC-32473-C-dc1b0ba40a'
    assert F.FAMILIES.count('head_size') == 1
    assert F.request_family({'operation_id': S.OPERATION_ID}) == 'head_size'
    assert F.presenter('head_size') is H
    assert BodyTransport('head_size').operation == 'head_size'
    for operation in ('lnx.head_size.v2', 'lnx.head.v1'):
        with pytest.raises(ValueError):
            F.request_family({'operation_id': operation})


def test_neutral_recovery_is_unapplied_and_exact_receipt_never_replays():
    adapter, request, holder, _, published, ports = host_fixture()
    first = adapter.execute(request)
    assert first['success'] is True and first['rendered'] is False
    assert first['outcome_unknown'] is False
    assert first['unapplied_reason'] == 'synthetic native core unavailable'
    assert adapter.execute(request) == first
    assert H.HeadSizeHostAdapter(ports).execute(request) == first
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
    request['payload']['recipe']['amount'] = .75
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
    for key in (*S.BOXES, 'pivot'):
        assert asset['data'][key] == draft[key]
    assert all(key in asset['data'] for key in S.FACE_BINDING_KEYS)


@pytest.mark.parametrize('key', ('head_box', 'transition_box', 'pivot'))
def test_missing_manual_region_never_falls_back_to_face_or_pose_box(key):
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
    adapter = H.HeadSizeHostAdapter(H.HostPorts(ports.binding, ports.read_bank,
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
                 {'operation': 'head_size', 'digest': 'f'*64}):
        engine._body_authoritative_requests[ident] = meta
        assert BodyPoseHostMixin._body_status(engine, ident, 'head_size') == pending
    engine._body_authoritative_requests[ident] = {'operation': 'head_size', 'digest': E.content_digest(request)}
    assert BodyPoseHostMixin._body_status(engine, ident, 'head_size') == actual
    assert adapter.execute(request) == actual and published == [ident]


def test_invalid_publication_is_not_promoted_by_an_unrelated_terminal_record():
    _, request, _, _, _, ports = host_fixture()
    def bad_publication(*args):
        result = ports.publish(*args)
        result['body_graph_sha256'] = 'f'*64
        return result
    adapter = H.HeadSizeHostAdapter(H.HostPorts(ports.binding, ports.read_bank,
        ports.read_people, ports.prepare, bad_publication, ports.receipt_get, ports.receipt_put))
    result = adapter.execute(request)
    assert result['phase'] == 'pending' and result['outcome_unknown'] is True
    assert result['publication_invalid'] is True
    with pytest.raises(ValueError):
        adapter.resolve_publication(request['request_id'], actual_result={
            'request_id': request['request_id'], 'phase': 'done', 'outcome_unknown': False})


def test_process_ledger_terminal_identity_cannot_change_or_expire_into_replay():
    owner = SimpleNamespace(_head_size_receipts={})
    put = lambda key, digest, result: BodyPoseHostMixin._head_size_receipt_put(owner, key, digest, result)
    terminal = {'phase': 'done', 'request_id': 'inner', 'success': True, 'outcome_unknown': False}
    put('inner', 'a'*64, {'phase': 'pending', 'request_id': 'inner', 'outcome_unknown': False})
    put('inner', 'a'*64, terminal); put('inner', 'a'*64, deepcopy(terminal))
    with pytest.raises(ValueError):
        put('inner', 'b'*64, terminal)
    with pytest.raises(ValueError):
        put('inner', 'a'*64, {**terminal, 'success': False})
    copy = BodyPoseHostMixin._head_size_receipt_get(owner, 'inner')
    copy['result']['success'] = False
    assert owner._head_size_receipts['inner']['result']['success'] is True


def test_existing_history_owner_coalesces_head_gesture_and_retains_sparse_body_patch():
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
    group = 'head_size:gesture:synthetic'
    controller.record(group, before, after=after_first)
    controller.record(group, after_first, after=after_second)
    assert len(controller.undo) == 1 and DOCUMENT_HISTORY.KEY in controller.undo[0]
    restored = DOCUMENT_HISTORY.restore(second, controller.undo[0])
    assert B.operation(restored, ref, S.OPERATION_ID)['recipe'] == S.neutral()


@pytest.mark.parametrize('amount', (-.01, 1.01, True, None, float('nan')))
def test_invalid_amount_is_rejected_before_preparation_or_publication(amount):
    adapter, request, holder, _, published, _ = host_fixture()
    before = deepcopy(holder['bank'])
    request['payload']['recipe']['amount'] = amount
    if amount != amount:  # Strict canonical serialization rejects NaN first.
        with pytest.raises(ValueError): adapter.execute(request)
    else:
        result = adapter.execute(request)
        assert result['success'] is False and result['outcome_unknown'] is False
    assert holder['bank'] == before and published == []


def test_retained_result_is_frozen_when_returned_view_is_later_mutated():
    _, request, _, _, _, ports = host_fixture()
    published_view = {}
    def publish(*args):
        published_view.update(ports.publish(*args))
        return published_view
    adapter = H.HeadSizeHostAdapter(H.HostPorts(ports.binding, ports.read_bank,
        ports.read_people, ports.prepare, publish, ports.receipt_get, ports.receipt_put))
    first = adapter.execute(request)
    assert first['success'] and not first['rendered']
    published_view['publication']['rendered'] = True
    first['view']['body_graph_sha256'] = 'f'*64
    retained = adapter.status(request['request_id'])
    assert retained['rendered'] is False and retained['view']['publication']['rendered'] is False
    assert retained['view']['body_graph_sha256'] != 'f'*64


@pytest.mark.parametrize('reason', (None, '', True, 'x'*8193))
def test_unapplied_publication_cannot_hide_its_actual_reason(reason):
    _, request, _, _, _, ports = host_fixture()
    def publish(*args):
        value = ports.publish(*args)
        value['publication']['unapplied_reason'] = reason
        return value
    adapter = H.HeadSizeHostAdapter(H.HostPorts(ports.binding, ports.read_bank,
        ports.read_people, ports.prepare, publish, ports.receipt_get, ports.receipt_put))
    result = adapter.execute(request)
    assert result['success'] is False and result['outcome_unknown'] is True
    assert result['publication_invalid'] is True


def test_view_exposes_only_current_factual_face_metadata_not_an_inferred_review():
    bank, people, ref, support, source = fixture(amount=0, review=False)
    binding = {'document_id': 'source-document', 'document_epoch': 'epoch',
               'document_revision': 1, 'asset_sha256': source['sha256']}
    shown = H.view(bank, binding, selected_body_ref=ref, people_state=people)
    body, = shown['bodies']
    assert body['associated_face'] == {key: support[key] for key in S.FACE_BINDING_KEYS}
    assert body['associated_face_error'] is None
    assert body['support'] is None and body['reviewed'] is False
    stale_people = deepcopy(people)
    stale_people['association_revision'] += 1
    stale = H.view(bank, binding, selected_body_ref=ref, people_state=stale_people)['bodies'][0]
    assert stale['associated_face'] is None and stale['associated_face_error']
    assert stale['support'] is None and stale['reviewed'] is False


def test_status_remains_query_only_when_current_source_is_missing():
    adapter, request, _, _, published, pending = uncertain_fixture()
    engine = SimpleNamespace(_body_status=lambda ident, operation: adapter.status(ident),
        _body_view=lambda operation: (_ for _ in ()).throw(OSError('source unavailable')))
    from lumaretouch_engine.body_pose_commands import apply
    result = apply(engine, {'cmd': 'head_size', 'action': 'status',
                           'request': {'request_id': request['request_id']}})
    assert result['receipt'] == pending and result['view_error'] == 'source unavailable'
    assert published == [request['request_id']]


@pytest.mark.parametrize('amount', (0., .5))
def test_review_without_native_is_explicitly_retained_unapplied_even_at_zero(monkeypatch, amount):
    adapter, request, holder, _, published, ports = host_fixture(amount=amount)
    monkeypatch.setattr(H.N, 'available', lambda: False)
    row = B.target(holder['bank'], request['body_ref'])
    request.update(action='support_review', payload={'data': geometry(),
        'points_sha256': row['record']['points_sha256'], 'visible_anchors': list(S.REQUIRED_ANCHORS),
        'ownership_confirmed': True})
    result = adapter.execute(request)
    assert result['success'] is True and result['rendered'] is False
    assert result['outcome_unknown'] is False and 'Rust core is unavailable' in result['unapplied_reason']
    assert result['view']['publication']['rendered'] is False
    assert B.operation(holder['bank'], request['body_ref'], S.OPERATION_ID)['review'] is not None
    assert published == [request['request_id']]


@pytest.mark.parametrize('enabled', (True, False))
def test_unavailable_native_refuses_nonzero_recipe_even_when_operation_is_dormant(monkeypatch, enabled):
    _, request, holder, _, published, ports = host_fixture(amount=0, enabled=enabled)
    monkeypatch.setattr(H.N, 'available', lambda: False)
    prepared = []
    def must_not_prepare(candidate):
        prepared.append(candidate)
        raise AssertionError('Missing ABI cannot prepare active head-size intent')
    adapter = H.HeadSizeHostAdapter(H.HostPorts(ports.binding, ports.read_bank,
        ports.read_people, must_not_prepare, ports.publish, ports.receipt_get, ports.receipt_put))
    before = deepcopy(holder['bank'])
    request['payload']['recipe']['amount'] = .4
    result = adapter.execute(request)
    assert result['success'] is False and result['outcome_unknown'] is False
    assert published == [] and prepared == [] and holder['bank'] == before


@pytest.mark.parametrize('action', ('reset', 'disable'))
def test_neutral_reset_or_disable_still_attempts_common_preparation_without_head_core(monkeypatch, action):
    _, request, _, _, _, ports = host_fixture()
    monkeypatch.setattr(H.N, 'available', lambda: False)
    attempts = []
    def prepare(candidate):
        attempts.append(candidate)
        raise ValueError('synthetic common-map refusal, not unavailable inactive head core')
    adapter = H.HeadSizeHostAdapter(H.HostPorts(ports.binding, ports.read_bank,
        ports.read_people, prepare, ports.publish, ports.receipt_get, ports.receipt_put))
    if action == 'disable': request.update(action='operation_status', payload={'enabled': False})
    result = adapter.execute(request)
    assert len(attempts) == 1 and result['success'] is True and result['rendered'] is False
    assert result['unapplied_reason'] == 'synthetic common-map refusal, not unavailable inactive head core'
