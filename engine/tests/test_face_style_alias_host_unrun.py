# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: source-identical face-style host routing and receipts.

These orchestration fixtures use synthetic graphs and publication doubles. They
do not establish rendering quality, native/model acceptance, or runtime success.
No product imports, collection, tests, builds, typechecks, inference or downloads
were executed while authoring this file.
"""
from collections import OrderedDict
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from lumaretouch_engine import people_state as S, people_host_commands as H
from lumaretouch_engine import face_style_review as R
from lumaretouch_engine import creative_derived_effects as D


TOKEN = '1' * 32
ASSET = 'a' * 64


def alias_ack():
    return {'review_sha256': 'b' * 64, 'members': [
        {'document_id': 'doc-source', 'revision': '4',
         'before_sha256': 'c' * 64, 'after_sha256': 'd' * 64},
        {'document_id': 'doc-alias', 'revision': '8',
         'before_sha256': 'e' * 64, 'after_sha256': 'f' * 64}]}


def fixture(action='face_style_confirm', payload=None):
    state = S.empty()
    evidence = {'backend': 'synthetic', 'detector_model_sha256': None,
        'semantic_model_sha256': None, 'landmark_digest': None,
        'status': 'synthetic', 'source_width': 128, 'source_height': 160,
        'orientation': 'exif_normalized_once'}
    face = S.new_face(ASSET, [.2, .1, .8, .9], evidence)
    state['faces'][face['face_instance_id']] = face
    target = {'scope': 'face', 'target_id': face['face_instance_id'],
              'face_ref': S.face_ref(face)}
    row = {'document_id': 'doc-source'}
    owner = SimpleNamespace(fence=9, snapshot=lambda: deepcopy(state))
    binding = {'document_id': 'doc-source', 'document_epoch': 'workspace-one',
               'document_revision': 4, 'asset_sha256': ASSET}
    engine = SimpleNamespace(_docs=[row], _doc_index=0, _people_scope_row=row,
        _people_active_context={'owner': owner}, _people_graph_owner=owner,
        _guard_editable=lambda _: None, _people_binding=lambda: dict(binding),
        _people_owner=lambda: owner, _people_targets={ASSET: deepcopy(target)},
        _people_cursors={ASSET: target['target_id']}, _vram=object(),
        _people_bind=Mock(side_effect=AssertionError('A style command must not bind or migrate')),
        _people_prepare_graph=Mock(side_effect=AssertionError('Alias route must not prepare a local publish')),
        _people_publish_graph=Mock(side_effect=AssertionError('Alias route must not publish locally')),
        doc_state=Mock(return_value={'document_id': 'doc-source'}),
        _people_receipts=OrderedDict())
    if payload is None:
        payload = {'token': TOKEN, 'ack': alias_ack()}
    raw = {'cmd': 'people', 'action': action, 'payload': payload,
        **{key: value for key, value in binding.items() if key != 'asset_sha256'},
        'state_revision': state['revision'], 'association_revision': state['association_revision'],
        'request_id': 'request-alias', 'target': target}
    proof = {'kind': 'face_style_confirm', 'token': TOKEN,
        'review_sha256': payload.get('ack', {}).get('review_sha256', 'b' * 64),
        'ack': deepcopy(payload.get('ack')), 'recipe': {'version': 1, 'style': 'classic', 'amount': .5},
        'patches_sha256': '7' * 64,
        'alias_members': [
            {'document_id': 'doc-source', 'expected_revision': '4', 'result_revision': '5'},
            {'document_id': 'doc-alias', 'expected_revision': '8', 'result_revision': '9'}]}
    return engine, state, raw, proof


def test_alias_image_read_is_exact_document_identified_read_only_route():
    payload = {'token': TOKEN, 'document_id': 'doc-alias', 'side': 'after', 'sha256': 'f' * 64}
    engine, _, raw, _ = fixture('face_style_image', payload)
    assert H.face_style_read_only(raw) and D.is_local_command('people', raw)
    assert not H.face_style_read_only({**raw, 'unexpected': True})
    assert not H.face_style_read_only({**raw, 'payload': {**payload, 'revision': '8'}})
    assert not H.face_style_read_only({**raw, 'payload': {**payload, 'document_id': ''}})
    assert not H.face_style_read_only({**raw, 'payload': {**payload, 'token': 'not-a-token'}})
    assert not H.face_style_read_only({**raw, 'action': 'face_style_confirm'})
    engine._people_bind.assert_not_called()


def test_alias_image_echo_and_exact_retry_do_not_republish_or_capture_doc_state():
    payload = {'token': TOKEN, 'document_id': 'doc-alias', 'side': 'before', 'sha256': 'e' * 64}
    engine, _, raw, _ = fixture('face_style_image', payload)
    body = {'kind': 'face_style_image', **payload, 'review_sha256': 'b' * 64,
            'image': {'sha256': 'e' * 64, 'base64': 'RkFLRQ=='}}
    events = []
    with patch.object(R, 'image', return_value=body) as read, \
         patch.object(H, 'publish', side_effect=AssertionError('A read cannot publish')):
        H.apply(engine, raw, events.append); H.finish(engine, raw, None, events.append)
        H.apply(engine, raw, events.append); H.finish(engine, raw, None, events.append)
    assert read.call_count == 1 and events[0] == events[1]
    assert events[0]['success'] and not events[0]['outcome_unknown']
    assert events[0]['payload']['document_id'] == 'doc-alias'
    assert events[0]['face_style_request']['payload'] == payload
    assert 'doc_state' not in events[0]
    engine.doc_state.assert_not_called(); engine._people_bind.assert_not_called()


def test_alias_confirmation_uses_scoped_publication_never_local_publish():
    engine, state, raw, proof = fixture(); events = []; order = []
    def scoped(*args, **kwargs):
        assert args == (engine, state, raw['target'], raw['payload'], state, proof)
        assert kwargs == {'request_id': raw['request_id']}
        order.append('scoped')
        engine._people_graph_owner.fence += 1
        return 'batch-reviewed-alias', {'event': 'image_ready'}
    with patch.object(R, 'confirm', side_effect=lambda *args: (order.append('confirm') or state, proof)), \
         patch.object(R, 'publish_alias', side_effect=scoped) as publish_alias, \
         patch.object(R, 'verify_before_publish', side_effect=AssertionError('Alias publisher owns the final claim')), \
         patch.object(R, 'verify_after_publish', side_effect=lambda *args: order.append('after')), \
         patch.object(H, 'publish', side_effect=AssertionError('No fallback local publication')) as local:
        H.apply(engine, raw, events.append); H.finish(engine, raw, None, events.append)
    assert order == ['confirm', 'scoped', 'after']
    assert publish_alias.call_count == 1 and local.call_count == 0
    assert events[-1]['success'] and not events[-1]['outcome_unknown']
    assert events[-1]['batch_id'] == 'batch-reviewed-alias'
    assert events[-1]['payload']['alias_members'] == proof['alias_members']
    engine._people_prepare_graph.assert_not_called(); engine._people_publish_graph.assert_not_called()


def test_original_v1_confirmation_keeps_existing_local_verification_route():
    payload = {'token': TOKEN, 'ack': {'review_sha256': 'b' * 64,
        'before_sha256': 'c' * 64, 'after_sha256': 'd' * 64}}
    engine, state, raw, proof = fixture(payload=payload); proof.pop('alias_members')
    order = []
    def local(*args, **kwargs):
        assert kwargs['shared'] is False
        order.append('prepare'); kwargs['before_publish']()
        order.append('local-publish'); return None, None
    with patch.object(R, 'confirm', return_value=(state, proof)), \
         patch.object(R, 'publish_alias', side_effect=AssertionError('v1 may not turn into an alias batch')), \
         patch.object(R, 'verify_before_publish', side_effect=lambda *args: order.append('before')), \
         patch.object(R, 'verify_after_publish', side_effect=lambda *args: order.append('after')), \
         patch.object(H, 'publish', side_effect=local):
        H.apply(engine, raw, lambda _: None)
    assert order == ['prepare', 'before', 'local-publish', 'after']


@pytest.mark.parametrize('failure', ('before-publication', 'post-publication', 'rollback-fence'))
def test_alias_failure_preserves_known_vs_unknown_outcome_and_never_reapplies(failure):
    engine, state, raw, proof = fixture(); events = []
    def scoped(*args, **kwargs):
        if failure == 'before-publication': raise ValueError('Exact alias closure changed before claim')
        engine._people_graph_owner.fence += 2 if failure == 'rollback-fence' else 1
        return 'batch-reviewed-alias', None
    def after(*args):
        raise ValueError('Post-publication review boundary differs')
    with patch.object(R, 'confirm', return_value=(state, proof)) as confirm, \
         patch.object(R, 'publish_alias', side_effect=scoped) as publish_alias, \
         patch.object(R, 'verify_after_publish', side_effect=after), \
         patch.object(H, 'publish', side_effect=AssertionError('Do not hide an alias failure with a local edit')):
        with pytest.raises(ValueError): H.apply(engine, raw, events.append)
        H.finish(engine, raw, 'fixture publication refusal', events.append)
        H.apply(engine, raw, events.append); H.finish(engine, raw, None, events.append)
    assert confirm.call_count == 1 and publish_alias.call_count == 1
    assert len(events) == 2 and events[0] == events[1] and not events[0]['success']
    assert events[0]['outcome_unknown'] is (failure != 'before-publication')
    assert events[0]['face_style_request']['payload'] == raw['payload']


def test_alias_request_identity_cannot_be_reused_with_another_member_ack():
    engine, state, raw, proof = fixture(); events = []
    with patch.object(R, 'confirm', return_value=(state, proof)) as confirm, \
         patch.object(R, 'publish_alias', return_value=('batch-reviewed-alias', None)) as scoped, \
         patch.object(R, 'verify_after_publish'):
        H.apply(engine, raw, events.append); H.finish(engine, raw, None, events.append)
        changed = deepcopy(raw); changed['payload']['ack']['members'][1]['after_sha256'] = '0' * 64
        with pytest.raises(ValueError): H.apply(engine, changed, events.append)
        H.finish(engine, changed, 'identity reused', events.append)
    assert confirm.call_count == 1 and scoped.call_count == 1
    assert events[-1]['success'] is False and events[-1]['outcome_unknown'] is False
    assert events[-1]['face_style_request']['payload'] == changed['payload']
