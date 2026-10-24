# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN direct shared-source ridge review contracts.

Synthetic retained graph, fake image bytes and mocked rendering/admission only.
No product imports, collection, tests, builds, inference or downloads ran while
writing these fixtures. They make no numerical or photographic-quality claim.
"""
from collections import OrderedDict
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_eye_bag_preserve_host_unrun import (
    host as single_host, ASSET, eye, display, payload, served_reference, raw)
from lumaretouch_engine import eye_bag_preserve_host as R, eye_bag_alias_review as ALIAS
from lumaretouch_engine import eye_bag_alias_history as HISTORY
from lumaretouch_engine import people_state as P, people_algorithms as A, eye_bag_preserve_state as S
from lumaretouch_engine import people_batch_ledger as LEDGER, people_host_commands as HOST

REAL_DEPENDENCIES = HISTORY._dependencies


@pytest.fixture
def host(single_host, monkeypatch):
    engine, owner, row, state, target = single_host
    row.update(copy_number=0, trashed=False)
    alias = {**deepcopy(row), 'document_id': 'doc-alias', 'document_revision': 8,
        'path': '/fixture/alias.png', 'state': {'source': ASSET, 'repair': 'alias-own-repair', 'crop': [91, 107]}}
    engine._docs.insert(0, alias); engine._doc_index = 1
    engine._people_project_context = engine._people_active_context
    versions = engine._document_versions()
    versions.check_advance = versions.version
    versions.find = lambda rows, identity: next(((index, item) for index, item in enumerate(rows)
                                                if item['document_id'] == identity), None)
    def advance(item): item['document_revision'] += 1
    versions.advance = advance
    def remember(): row['state'] = deepcopy(engine.current)
    batch = SimpleNamespace(documents=SimpleNamespace(rows=lambda: engine._docs, remember_current=remember),
        versions=versions, ledger={}, sequence=0, clock=lambda: 1., monotonic=lambda: 1,
        editor=SimpleNamespace(mark_dirty=Mock()))
    engine._batch_controller = lambda: batch
    monkeypatch.setattr(ALIAS, 'snapshot_key', R.snapshot_key)
    engine.render_calls = []
    def render(actual, item, captured, graph, document, revision, *, cancelled):
        assert not cancelled()
        actual.render_calls.append((document, deepcopy(captured), deepcopy(graph)))
        compact, image = display(document + R.digest(captured) + R.digest(graph))
        return compact, image, {'source_proof': R.SOURCE.row_proof({**item, 'state': captured}),
            'candidate_sha256': R.digest(captured), 'people_sha256': R.digest(graph),
            'source_size': [128, 192], 'output_size': captured['crop']}
    monkeypatch.setattr(ALIAS, 'render_image', render)
    def dependency(actual, item, graph):
        refs = graph['faces'][target['target_id']]['local_assets']
        return {'context_sha256': R.digest(refs), 'state_sha256': R.digest(item['state'])}
    monkeypatch.setattr(HISTORY, '_dependencies', dependency)
    result = SimpleNamespace(engine=engine, owner=owner, row=row, alias=alias, state=state,
        target=target, batch=batch, versions=versions)
    yield result
    if '_eye_bag_reviews' in engine.__dict__: engine._eye_bag_reviews['images'].directory.cleanup()


def reviewed(host, *, replacement=False, eyes=None):
    h = host; state = h.owner.snapshot()
    served_reference(h.engine, state, h.target)
    return R.preview(h.engine, state, h.target, payload(replace=replacement, eyes=eyes))['review']


def command(review):
    return {'token': review['token'], 'ack': ALIAS._ack(review)}


def entry(host, review):
    return host.engine._eye_bag_reviews['pending'][review['token']]


def serve(host, review):
    h = host
    for member in review['members']:
        visual = member['visual']
        for side in ('before', 'after'):
            result = R.image(h.engine, h.owner.snapshot(), h.target, {'token': review['token'],
                'document_id': visual['document_id'], 'side': side, 'sha256': visual[side]['sha256']})
            assert result['document_id'] == visual['document_id'] and result['review_sha256'] == review['review_sha256']
    R.image(h.engine, h.owner.snapshot(), h.target, {'token': review['token'],
        'document_id': review['visual']['document_id'], 'side': 'support', 'sha256': review['support_overlay']['sha256']})


def test_alias_review_uses_each_own_mixed_repair_crop_and_one_source_support(host):
    h = host; before = h.owner.snapshot(); saved_rows = deepcopy(h.engine._docs)
    review = reviewed(h)
    assert review['version'] == 2 and review['visual'] == review['members'][0]['visual']
    assert [member['visual']['document_id'] for member in review['members']] == ['doc-eye', 'doc-alias']
    assert [record[0] for record in h.engine.render_calls] == ['doc-eye', 'doc-eye', 'doc-alias', 'doc-alias']
    assert all(record[1] == h.engine.current for record in h.engine.render_calls[:2])
    assert all(record[1] == h.alias['state'] for record in h.engine.render_calls[2:])
    assert review['members'][0]['visual']['before_output_size'] == [64, 96]
    assert review['members'][1]['visual']['before_output_size'] == [91, 107]
    assert review['support_sha256'] in h.engine._people_support
    assert h.owner.snapshot() == before and h.owner.fence == 7 and h.engine._docs == saved_rows and not h.batch.ledger
    assert 'base64' not in review['support_overlay']


def test_all_pairs_and_support_must_be_delivered_before_exact_ack(host):
    h = host; review = reviewed(h)
    with pytest.raises(ValueError, match='Load every'):
        R.confirm(h.engine, h.state, h.target, command(review))
    serve(h, review)
    candidate, proof = R.confirm(h.engine, h.state, h.target, command(review))
    assert proof['ack'] == ALIAS._ack(review)
    assert proof['alias_members'] == [
        {'document_id': 'doc-eye', 'expected_revision': '4', 'result_revision': '5'},
        {'document_id': 'doc-alias', 'expected_revision': '8', 'result_revision': '9'}]
    assert candidate == entry(h, review)['candidate'] and not entry(h, review)['claimed']


@pytest.mark.parametrize('fault', ('missing', 'duplicate', 'reverse', 'revision', 'before', 'after', 'overlay', 'extra'))
def test_ack_refuses_wrong_or_partial_alias_identity(host, fault):
    h = host; review = reviewed(h); serve(h, review); request = command(review); ack = request['ack']
    if fault == 'missing': ack['members'].pop()
    elif fault == 'duplicate': ack['members'][1] = deepcopy(ack['members'][0])
    elif fault == 'reverse': ack['members'].reverse()
    elif fault == 'revision': ack['members'][1]['revision'] = '9'
    elif fault in ('before', 'after'): ack['members'][1][fault + '_sha256'] = '0' * 64
    elif fault == 'overlay': ack['support_overlay_sha256'] = '0' * 64
    else: ack['implicit'] = True
    with pytest.raises(ValueError): R.confirm(h.engine, h.state, h.target, request)
    assert not entry(h, review)['claimed'] and not h.batch.ledger


@pytest.mark.parametrize('fault', ('document', 'missing-document', 'wrong-side-owner', 'hash'))
def test_alias_image_coordinates_cannot_read_another_member_or_source_overlay(host, fault):
    h = host; review = reviewed(h)
    request = {'token': review['token'], 'document_id': 'doc-eye', 'side': 'support',
               'sha256': review['support_overlay']['sha256']}
    if fault == 'document': request['document_id'] = 'foreign'
    elif fault == 'missing-document': request.pop('document_id')
    elif fault == 'wrong-side-owner': request['document_id'] = 'doc-alias'
    else: request['sha256'] = '0' * 64
    with pytest.raises(ValueError): R.image(h.engine, h.state, h.target, request)


@pytest.mark.parametrize('fault', ('repair', 'crop', 'revision', 'trash', 'path', 'missing', 'new', 'graph', 'context', 'epoch'))
def test_complete_member_changes_invalidate_pending_alias_review(host, fault):
    h = host; review = reviewed(h); serve(h, review)
    if fault == 'repair': h.alias['state']['repair'] = 'changed'
    elif fault == 'crop': h.alias['state']['crop'] = [70, 80]
    elif fault == 'revision': h.alias['document_revision'] += 1
    elif fault == 'trash': h.alias['trashed'] = True
    elif fault == 'path': h.alias['path'] = '/fixture/replacement.png'
    elif fault == 'missing': h.engine._docs.pop(0); h.engine._doc_index = 0
    elif fault == 'new': h.engine._docs.append({**deepcopy(h.alias), 'document_id': 'doc-new'})
    elif fault == 'graph': h.owner.state['faces'][h.target['target_id']]['labels']['changed'] = True
    elif fault == 'context': h.engine._people_support['0' * 64] = {'unrelated': 'bank change'}
    else: h.versions.workspace = 'epoch-other'
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, command(review))
    assert not entry(h, review)['claimed'] and not h.batch.ledger


def test_legacy_replacement_and_removed_eye_are_one_narrow_candidate(host):
    h = host
    h.owner.state = P.set_override(h.state, 'face', h.target['target_id'], A.ENHANCE, '/eye_bags', .5)
    with pytest.raises(ValueError, match='Legacy'): reviewed(h)
    first = reviewed(h, replacement=True, eyes={'left': eye(), 'right': eye()})
    serve(h, first)
    second = R.preview(h.engine, h.owner.snapshot(), h.target, payload(replace=True, eyes={'right': eye()}))['review']
    serve(h, second)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, command(second))
    assert first['support_sha256'] != second['support_sha256']
    assert first['support_sha256'] in h.engine._people_support and second['support_sha256'] in h.engine._people_support
    assert set(h.engine._people_support[second['support_sha256']]['row']['eyes']) == {'right'}
    assert R._values(candidate, h.target)[1] == 0 and proof['replace_legacy'] is True
    assert R._values(h.owner.snapshot(), h.target)[1] == .5


def test_bounds_unavailable_owner_and_cancel_never_publish_partial_review(host, monkeypatch):
    h = host
    for index in range(15): h.engine._docs.append({**deepcopy(h.alias), 'document_id': 'extra-' + str(index)})
    with pytest.raises(ValueError): reviewed(h)
    assert not h.engine.render_calls and not h.batch.ledger
    del h.engine._docs[2:]
    calls = 0
    real = ALIAS.render_image
    def cancel_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3: raise InterruptedError('cancelled between alias renders')
        return real(*args, **kwargs)
    monkeypatch.setattr(ALIAS, 'render_image', cancel_second)
    with pytest.raises(InterruptedError): reviewed(h)
    assert h.owner.snapshot() == h.state and h.owner.fence == 7 and not h.batch.ledger
    assert h.engine._people_support  # Only append-only unused support may remain.
    assert not h.engine.__dict__.get('_eye_bag_reviews', {}).get('pending')


def test_different_original_lineage_same_effective_source_is_not_a_donor_transfer(host, monkeypatch):
    h = host; old = R.SOURCE.row_proof
    def source(item):
        proof = old(item)
        if item['document_id'] == 'doc-alias':
            proof = {'asset_sha256': ASSET, 'original_sha256': 'b' * 64,
                     'creative_source': {'sha256': ASSET, 'width': 128, 'height': 192}}
        return proof
    monkeypatch.setattr(R.SOURCE, 'row_proof', source)
    monkeypatch.setattr(R.SOURCE, 'row_asset', lambda item: source(item)['asset_sha256'])
    monkeypatch.setattr(R.SOURCE, 'verify_row', lambda item, proof: None if source(item) == proof else (_ for _ in ()).throw(ValueError('source changed')))
    review = reviewed(h)
    assert review['members'][0]['visual']['source_proof'] != review['members'][1]['visual']['source_proof']
    assert {member['visual']['source_proof']['asset_sha256'] for member in review['members']} == {ASSET}


@pytest.mark.parametrize('claimed', (False, True))
def test_preclaim_refusal_and_postclaim_unknown_replay_keep_original_request(host, monkeypatch, claimed):
    h = host; review = reviewed(h); serve(h, review)
    request = raw(h.engine, h.state, h.target, 'eye_bag_confirm', command(review), request='alias-boundary')
    monkeypatch.setattr(LEDGER, 'prepare_scoped', lambda *args: None)
    monkeypatch.setattr(LEDGER, '_verify', lambda *args: None)
    if claimed:
        failure = Mock(side_effect=ValueError('lost immediately after claim'))
        monkeypatch.setattr(LEDGER, 'commit_scoped', failure)
    else:
        failure = Mock(side_effect=ValueError('preparation refusal'))
        monkeypatch.setattr(LEDGER, 'prepare_scoped', failure)
    events = []
    with pytest.raises(ValueError): HOST.apply(h.engine, request, events.append)
    HOST.finish(h.engine, request, 'boundary failure', events.append)
    HOST.apply(h.engine, request, events.append); HOST.finish(h.engine, request, None, events.append)
    assert failure.call_count == 1 and events[0] == events[1]
    assert events[0]['outcome_unknown'] is claimed and not events[0]['success']
    assert R.claimed(h.engine, review['token']) is claimed and h.owner.fence == 7
    assert h.owner.snapshot() == h.state and not h.batch.ledger


def test_alias_publishes_existing_scoped_ledger_and_advances_every_member_once(host, monkeypatch):
    h = host; review = reviewed(h); serve(h, review); request = command(review)
    candidate, proof = R.confirm(h.engine, h.state, h.target, request)
    monkeypatch.setattr(LEDGER, 'prepare_scoped', lambda *args: None)
    monkeypatch.setattr(LEDGER, '_verify', lambda *args: None)
    published = []
    def publish(batch, engine, plans, targets):
        published.append((plans, targets)); h.owner.state = deepcopy(candidate); h.owner.fence += 1
        for item in engine._docs: h.versions.advance(item)
        return None
    monkeypatch.setattr(LEDGER, '_publish', publish)
    h.engine._people_receipts['alias-success'] = {}
    bid, frame = R.publish_alias(h.engine, h.state, h.target, request, candidate, proof, request_id='alias-success')
    R.verify_after_publish(h.engine, candidate, proof)
    assert len(published) == 1 and frame is None and h.owner.fence == 8
    assert h.row['document_revision'] == 5 and h.alias['document_revision'] == 9
    assert HISTORY.check(h.batch.ledger[bid])['document_ids'] == ['doc-alias', 'doc-eye']
    assert h.engine._people_receipts['alias-success']['side_effects_started']
    assert h.engine._people_receipts['alias-success']['batch_id'] == bid
    with pytest.raises(ValueError): R.publish_alias(h.engine, h.state, h.target, request, candidate, proof, request_id='alias-success')
    assert len(published) == 1
