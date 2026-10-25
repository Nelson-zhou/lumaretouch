# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic host contracts, not native/photo acceptance.

No tests, imports, image rendering, ML inference or native execution were run
while authoring this file under the static-source-only authorization.
"""
from collections import OrderedDict
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest import mock
import pytest
from lumaretouch_engine import hair_volume_controller as C
from lumaretouch_engine import hair_volume_review as REVIEW
from lumaretouch_engine import hair_volume_project as PROJECT
from lumaretouch_engine import hair_volume_state as S, hair_volume_support as A
from lumaretouch_engine import hair_colour_evidence as EVIDENCE
from lumaretouch_engine import people_state as P
from test_hair_volume_contract_unrun import fixture


def request(action='context', payload=None):
    return {'cmd': 'hair_volume', 'protocol': 1, 'operation_id': S.OPERATION_ID,
        'request_id': 'request-1', 'action': action, 'people_context': {
            'document_id': 'document-1', 'document_epoch': 'epoch-1', 'document_revision': 1,
            'state_revision': 1, 'association_revision': 0,
            'target': {'scope': 'face', 'target_id': 'owner', 'face_ref': {
                'asset_sha256': 'a'*64, 'face_instance_id': 'owner', 'analysis_revision': 0}}},
        'payload': {} if payload is None else payload}


def preview_payload():
    _, _, _, _, record = fixture()
    recipe = S.neutral(); recipe['crown']['amount'] = .4
    regions = deepcopy(record['row']['regions']); regions.update(left=None, right=None)
    return {'recipe': recipe, 'regions': regions, 'protection': record['row']['protection'],
            'confirmed': True, 'crown_confirmed': True, 'left_confirmed': False, 'right_confirmed': False}


def test_exact_independent_protocol_and_current_face_only():
    assert C.read_only(request())
    assert not C.read_only(request('clear'))
    payload = preview_payload(); assert C.read_only(request('preview', payload))
    for key in ('confirmed', 'crown_confirmed'):
        wrong = deepcopy(payload); wrong[key] = False
        with pytest.raises(ValueError): C.check_request(request('preview', wrong))
    wrong = deepcopy(payload); wrong['regions']['left'] = wrong['regions']['crown']
    with pytest.raises(ValueError): C.check_request(request('preview', wrong))
    wrong = deepcopy(payload); wrong['hair_colour_confirmed'] = True
    with pytest.raises(ValueError): C.check_request(request('preview', wrong))
    wrong = request(); wrong['people_context']['target']['scope'] = 'group'
    with pytest.raises(ValueError): C.check_request(wrong)
    wrong = request(); wrong['people_context']['target']['face_ref']['face_instance_id'] = 'another-owner'
    with pytest.raises(ValueError): C.check_request(wrong)
    wrong = request(); wrong['operation_id'] = 'lnx.head_size.v1'
    with pytest.raises(ValueError): C.check_request(wrong)


def test_ack_requires_three_exact_image_hashes_and_explicit_commit():
    ack = {'preview_id': 'a'*32, 'review_token': 'b'*64,
           'before_sha256': 'c'*64, 'after_sha256': 'd'*64, 'support_sha256': 'e'*64}
    C.check_request(request('presented', ack))
    wrong = deepcopy(ack); wrong.pop('support_sha256')
    with pytest.raises(ValueError): C.check_request(request('presented', wrong))
    wrong = deepcopy(ack); wrong['preview_id'] = 'z'*32
    with pytest.raises(ValueError): C.check_request(request('presented', wrong))
    C.check_request(request('commit', {'preview_id': 'a'*32, 'review_token': 'b'*64, 'confirmed': True}))
    with pytest.raises(ValueError):
        C.check_request(request('commit', {'preview_id': 'a'*32, 'review_token': 'b'*64, 'confirmed': 1}))


def test_only_independent_scalar_leaves_and_no_shared_inheritance():
    state, _, _, _, _ = fixture()
    value = S.neutral(); value['crown']['amount'] = -.2
    value['sides'].update(linked=False, left=-.5, right=.8)
    changed = PROJECT.set_recipe(state, 'owner', value)
    assert PROJECT.recipe(changed, 'owner') == value
    assert set(PROJECT.LEAVES) == {'/crown/amount', '/sides/linked', '/sides/left', '/sides/right'}
    for path, raw in (('/regions', {}), ('/confirmed', True), ('/sides/linked', 1), ('/crown/amount', True)):
        with pytest.raises(ValueError): PROJECT.validate_leaf(path, raw)
    shared = P.set_override(state, 'all_people', 'a'*64, S.OPERATION_ID, '/crown/amount', .2)
    with pytest.raises(ValueError): PROJECT.validate_graph(shared)


def test_active_or_archived_owned_graph_requires_exact_support_and_source_census():
    state, bank, _, evidence, record = fixture()
    value = S.neutral(); value['crown']['amount'] = .3
    active = PROJECT.set_recipe(state, 'owner', value)
    PROJECT.validate_owned_graph(active, bank, {EVIDENCE.identity(evidence): EVIDENCE.encode(evidence)})
    missing = A.detach(active, record['face_ref'])
    with pytest.raises(ValueError): PROJECT.validate_owned_graph(missing, bank)
    other = deepcopy(active['faces']['owner'])
    other.update(face_instance_id='retained-disabled', enabled=False, local_assets={})
    changed = deepcopy(active); changed['faces']['retained-disabled'] = other
    with pytest.raises(ValueError): PROJECT.require_unreviewed_transition(active, changed)
    with pytest.raises(ValueError): PROJECT.validate_owned_graph(changed, bank)
    with pytest.raises(ValueError): PROJECT.require_unreviewed_transition(state, active)


def test_source_face_digest_uses_effective_derived_asset_not_original_provenance():
    state, _, source, _, _ = fixture(); row = {'path': '/not-opened/source.png'}
    owner = SimpleNamespace(fence=5)
    target = request()['people_context']['target']
    engine = SimpleNamespace(_people_source=lambda: source, _people_targets={source['sha256']: target},
        _people_cursors={source['sha256']: 'owner'}, _people_preset_capture=lambda: {},
        _people_owner=lambda: owner, _document_versions=lambda: SimpleNamespace(workspace='workspace',
            version=lambda row: SimpleNamespace(document_id='document-1', revision=1)), _load_id='load-1')
    proof = {'asset_sha256': source['sha256'], 'original_sha256': 'b'*64, 'creative_source': source}
    with mock.patch('lumaretouch_engine.people_host_commands.checked', return_value=(state, {}, target)), \
            mock.patch('lumaretouch_engine.virtual_copy_people.current_row', return_value=row), \
            mock.patch.object(C.SOURCE, 'row_proof', return_value=proof), \
            mock.patch.object(C.SOURCE, 'record', return_value=None), \
            mock.patch.object(C.SOURCE, 'verify'):
        captured, _, _, _ = C._live(engine, request()['people_context'])
        assert captured['source']['sha256'] == captured['face_ref']['asset_sha256'] == 'a'*64
        assert captured['source_proof']['original_sha256'] == 'b'*64
        wrong = deepcopy(target); wrong['face_ref']['asset_sha256'] = 'b'*64
        engine._people_targets[source['sha256']] = wrong
        with mock.patch('lumaretouch_engine.people_host_commands.checked', return_value=(state, {}, wrong)):
            with pytest.raises(ValueError): C._live(engine, request()['people_context'])


def test_staged_bank_is_private_append_only_without_live_owner_mutation():
    state, bank, _, _, _ = fixture()
    live = {'people_graph': P.empty(), 'people_support_assets': {}}
    with mock.patch('lumaretouch_engine.full_candidate_render.people_context', return_value=deepcopy(live)):
        staged = REVIEW.staged_context(object(), object(), state, bank)
    assert live == {'people_graph': P.empty(), 'people_support_assets': {}}
    assert staged['people_graph'] == state and staged['people_support_assets'] == bank
    with mock.patch('lumaretouch_engine.full_candidate_render.people_context',
                    return_value={'people_graph': state, 'people_support_assets': bank}):
        with pytest.raises(ValueError): REVIEW.staged_context(object(), object(), state, {})


def test_exact_presented_ack_and_claim_before_canonical_publication():
    candidate = {'candidate': True}
    entry = {'review_token': 'b'*64, 'metadata': {'before_sha256': 'c'*64, 'after_sha256': 'd'*64,
        'support_sha256': 'e'*64, 'support_asset_sha256': 'f'*64}, 'presented': None,
        'claimed': False, 'before': {}, 'candidate': candidate, 'bank': {}, 'captured': {}, 'recipe': S.neutral()}
    engine = SimpleNamespace(_people_owner=lambda: SimpleNamespace(snapshot=lambda: candidate))
    ack = REVIEW.ack(entry, 'a'*32)
    with mock.patch.object(C, '_review', return_value=entry):
        wrong = deepcopy(ack); wrong['after_sha256'] = '0'*64
        with pytest.raises(ValueError): C.presented(engine, {}, wrong)
        with pytest.raises(ValueError): C.commit(engine, {}, {'preview_id': 'a'*32})
        C.presented(engine, {}, ack)
        def publish(*args, **kwargs):
            assert entry['claimed'] is True
            assert kwargs['review_token'] == entry['review_token']
            return {'event': 'frame'}
        with mock.patch.object(C, '_publish', side_effect=publish):
            result, frame = C.commit(engine, {}, {'preview_id': 'a'*32})
    assert result['asset_sha256'] == 'f'*64 and result['committed'] is True
    assert frame == {'event': 'frame'}


def test_clear_detaches_active_pointer_but_retains_history_bytes_without_native():
    state, bank, source, _, record = fixture()
    value = S.neutral(); value['crown']['amount'] = .3
    state = PROJECT.set_recipe(state, 'owner', value)
    engine = SimpleNamespace(_people_support=bank)
    captured = {'face_ref': record['face_ref'], 'source': source}
    with mock.patch.object(C, '_live', return_value=(captured, state, {}, {})), \
            mock.patch.object(PROJECT, 'require_scope'), \
            mock.patch.object(C.N, 'native', side_effect=AssertionError('native called')), \
            mock.patch.object(C, '_publish', return_value=None) as publish:
        result, frame = C.clear(engine, {})
    candidate = publish.call_args.args[2]
    assert PROJECT.recipe(candidate, 'owner') == S.neutral()
    assert S.SUPPORT_KIND not in candidate['faces']['owner']['local_assets']
    assert publish.call_args.args[3] == bank and A.digest(record) in bank
    assert result == {'kind': 'cleared', 'committed': True, 'recipe': S.neutral()} and frame is None


def test_receipt_idempotency_capacity_and_read_image_tombstones():
    original = request()
    saved = {'digest': A.digest(original), 'result': {'action': 'context', 'payload': {
        'source_png': 'data:image/png;base64,'+'a'*128}, 'request_payload': {}, 'people_context': original['people_context']}}
    write = {'digest': 'b'*64, 'result': {'action': 'commit', 'payload': {'committed': True}}}
    ack = {'digest': 'c'*64, 'result': {'action': 'presented', 'payload': {'presented': True}}}
    receipts = OrderedDict((('request-1', saved), ('write', write), ('ack', ack)))
    REVIEW.bound_read_images(receipts, 0)
    assert receipts['request-1']['digest'] == A.digest(original)
    assert receipts['request-1']['result']['payload_released'] is True
    assert receipts['request-1']['result']['request_payload'] == {}
    assert receipts['write'] is write and receipts['ack'] is ack
    engine = SimpleNamespace(_hair_volume_receipts=receipts)
    C.execute(engine, original, lambda value: None)  # No owner/native needed for an exact repeated read.
    wrong = {**original, 'action': 'clear'}
    with pytest.raises(ValueError): C.execute(engine, wrong, lambda value: None)
    with mock.patch.object(C, 'MAX_RECEIPTS', 3):
        with pytest.raises(ValueError): C.execute(engine, {**original, 'request_id': 'new'}, lambda value: None)


def test_uncertain_mutation_blocks_edits_until_authoritative_reopen():
    engine = SimpleNamespace(_hair_volume_uncertain={'request_id': 'original'})
    C.guard_other(engine, 'hair_volume', {'action': 'status'})
    C.guard_other(engine, 'project', {'action': 'open'})
    with pytest.raises(ValueError): C.guard_other(engine, 'hair_volume', {'action': 'commit'})
    with pytest.raises(ValueError): C.guard_other(engine, 'people', {'action': 'patch'})
    C.invalidate_after_reload(engine)
    C.guard_other(engine, 'people', {'action': 'patch'})


def test_append_only_bytes_remain_when_canonical_publication_outcome_is_uncertain():
    before, old, source, _, record = fixture(); candidate = deepcopy(before); candidate['revision'] += 1
    added = {**old, 'unreachable-test-only': {'not': 'a validated publication'}}
    owner = SimpleNamespace(fence=2, snapshot=lambda: before)
    engine = SimpleNamespace(_people_support=old, _vram=object(), _people_owner=lambda: owner,
        _history_capture=lambda: {}, _history_record=mock.Mock())
    def fail_after_fence(*args):
        owner.fence += 1
        raise RuntimeError('Uncertain publication')
    engine._people_prepare_graph = fail_after_fence
    captured = {'source': source, 'graph_fence': 2}
    with mock.patch.object(PROJECT, 'reviewed_transition', return_value=nullcontext()):
        with pytest.raises(RuntimeError): C._publish(engine, before, candidate, added, captured, review_token='d'*64)
    assert engine._people_support == added
    assert engine._people_staged is None
    engine._history_record.assert_called_once_with('hair_volume', {}, coalesce=False)


def test_complete_mixed_render_never_replaces_with_source_or_diagnostic():
    """Static route specification; rendering this contract is not acceptance."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / 'engine/src/lumaretouch_engine'
    text = (root / 'hair_volume_review.py').read_text()
    assert text.count('= render_image(engine, row, current,') == 2
    assert "staged_people_context=staged" in text
    assert "proof_before['source_size'] != [source['width'], source['height']]" in text
    assert 'source_proof' in text and 'source_image_sha256' in text
    assert 'N.evaluate' not in text and 'HairVolumeField' not in text
