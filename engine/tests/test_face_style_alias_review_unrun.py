# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: complete source-identical face-style visual review.

Actual people stage/resolver and review/cache boundaries, with synthetic retained
face evidence and mocked source/full-render boundaries. The fake display blobs
are not real PNGs, and these fixtures make no native/model/photo-quality claim.
No product imports, collection, tests, builds, typechecks, inference or downloads
were executed while authoring. Only source reading and static AST parsing were
performed.
"""
from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lumaretouch_engine import face_style_review as R, face_style_alias_review as ALIAS
from lumaretouch_engine import face_style_alias_history as HISTORY
from lumaretouch_engine import face_style_recipes as REC
from lumaretouch_engine import people_state as S, people_algorithms as A
from lumaretouch_engine import people_batch_ledger as LEDGER, virtual_copy_people as V
from lumaretouch_engine.people_resolver import resolve


ASSET = 'a' * 64
PAYLOAD = {'version': 1, 'style': 'classic', 'amount': .5}


class Owner:
    def __init__(self, state):
        self.state = deepcopy(state)
        self.fence = 9
    def snapshot(self):
        return deepcopy(self.state)


class Versions:
    workspace = 'workspace-alias'
    def version(self, row):
        return SimpleNamespace(document_id=row['document_id'], revision=row['document_revision'])
    def check_advance(self, row):
        value = self.version(row)
        if value.revision == 2**64 - 1: raise ValueError('Fixture document fence exhausted')
        return value
    def find(self, rows, document_id):
        return next(((index, row) for index, row in enumerate(rows)
                     if row['document_id'] == document_id), None)
    def advance(self, row):
        row['document_revision'] += 1
        return self.version(row)


def make_row(document, revision, *, repair, crop, asset=ASSET):
    return {'document_id': document, 'document_revision': revision,
        'path': '/fixture/' + document + '.png', 'src_w': 128, 'src_h': 160,
        'copy_number': 0, 'trashed': False,
        'fingerprint': {'hash_level': 'full', 'sha256': asset},
        'state': {'source': asset, 'repair': repair, 'crop': crop, 'exposure': revision / 10}}


@pytest.fixture
def host(monkeypatch):
    state = S.empty()
    evidence = {'backend': 'synthetic', 'detector_model_sha256': None,
        'semantic_model_sha256': None, 'landmark_digest': None,
        'status': 'synthetic', 'source_width': 128, 'source_height': 160,
        'orientation': 'exif_normalized_once'}
    face = S.new_face(ASSET, [.2, .1, .8, .9], evidence)
    face_id = face['face_instance_id']; state['faces'][face_id] = face
    state = S.set_override(state, 'face', face_id, 'lnx.nose_shape.v1', '/wing', -.12)
    owner = Owner(state)
    target = {'scope': 'face', 'target_id': face_id, 'face_ref': S.face_ref(face)}
    # Current is intentionally not the first filmstrip row. A review must put
    # its source first while preserving each parked member's own full state.
    parked = make_row('doc-alias', 8, repair='alias-repair', crop=[91, 107])
    current_row = make_row('doc-source', 4, repair='stale-saved-repair', crop=[128, 160])
    current = {**deepcopy(current_row['state']), 'repair': 'current-live-repair', 'crop': [120, 150]}
    rows = [parked, current_row]; versions = Versions()
    engine = SimpleNamespace(_docs=rows, _doc_index=1, _load_id='load-alias-one',
        _people_graph_owner=owner, _people_scope_row=current_row,
        _people_active_context={'owner': owner}, _people_project_context={'owner': owner},
        _people_cursors={ASSET: face_id}, _people_targets={ASSET: deepcopy(target)},
        current=current, context={row['document_id']: 'support-' + row['document_id'] for row in rows},
        render_calls=[], verified=[], history=[], _project=None,
        _people_bind=Mock(side_effect=AssertionError('A review must not activate/migrate owners')),
        _people_publish_graph=Mock(side_effect=AssertionError('An alias review must not publish locally')))
    engine._people_preset_capture = lambda: deepcopy(engine.current)
    engine._document_versions = lambda: versions
    engine._people_owner = lambda: owner
    engine._people_binding = lambda: {'document_id': current_row['document_id'],
        'document_epoch': versions.workspace, 'document_revision': current_row['document_revision'],
        'asset_sha256': ASSET}
    def remember_current():
        current_row['state'] = deepcopy(engine.current)
    batch = SimpleNamespace(documents=SimpleNamespace(rows=lambda: engine._docs,
        remember_current=remember_current), versions=versions, ledger={}, sequence=0,
        clock=lambda: 1., monotonic=lambda: 1, editor=SimpleNamespace(mark_dirty=Mock()))
    engine._batch_controller = lambda: batch
    def source_proof(row):
        captured = row.get('state') or {}
        asset = captured.get('source', row['fingerprint']['sha256'])
        original = captured.get('original_source', asset)
        creative = None if original == asset else {'sha256': asset, 'width': 128, 'height': 160}
        return {'asset_sha256': asset, 'original_sha256': original, 'creative_source': creative}
    monkeypatch.setattr(R.SOURCE, 'row_proof', source_proof)
    monkeypatch.setattr(R.SOURCE, 'row_asset', lambda row: source_proof(row)['asset_sha256'])
    monkeypatch.setattr(R.SOURCE, 'binding', lambda captured, *args: {
        'sha256': captured['source'], 'width': 128, 'height': 160})
    monkeypatch.setattr(R.SOURCE, 'record', lambda captured: None)
    def verify(row, proof):
        if source_proof(row) != proof: raise ValueError('Fixture source bytes changed')
        engine.verified.append((row['document_id'], deepcopy(proof)))
        return deepcopy(proof)
    monkeypatch.setattr(R.SOURCE, 'verify_row', verify)
    def key(actual, row, captured, graph):
        normalized = deepcopy(graph); normalized['revision'] = 0
        return {'render_sha256': R.digest(captured),
            'context_sha256': R.digest(actual.context[row['document_id']]),
            'graph_sha256': R.digest(normalized)}
    monkeypatch.setattr(R, 'snapshot_key', key)
    monkeypatch.setattr(ALIAS, 'snapshot_key', key)
    def render(actual, row, captured, graph, document, revision):
        actual.render_calls.append({'document_id': document, 'row': row,
            'state': deepcopy(captured), 'graph': deepcopy(graph), 'revision': revision})
        raw = ('FAKE DISPLAY ' + document + R.digest(captured) + R.digest(graph)).encode()
        compact = {'mime': 'image/png', 'width': captured['crop'][0],
                   'height': captured['crop'][1], 'sha256': sha256(raw).hexdigest()}
        proof = {'source_proof': source_proof({**row, 'state': captured}),
            'source_size': [128, 160], 'output_size': list(captured['crop']),
            'candidate_sha256': R.digest(captured), 'people_sha256': R.digest(graph)}
        return compact, {**compact, 'base64': b64encode(raw).decode()}, proof
    monkeypatch.setattr(R, 'render_image', render)
    monkeypatch.setattr(ALIAS, 'render_image', render)
    yield SimpleNamespace(engine=engine, owner=owner, state=state, target=target,
        face_id=face_id, source=current_row, alias=parked, versions=versions, batch=batch)
    if '_face_style_reviews' in engine.__dict__:
        engine._face_style_reviews['images'].directory.cleanup()


def preview(host, payload=None):
    return R.preview(host.engine, host.owner.snapshot(), host.target,
                     PAYLOAD if payload is None else payload)['review']


def confirmation(review):
    return {'token': review['token'], 'ack': {'review_sha256': review['review_sha256'],
        'members': [{'document_id': item['visual']['document_id'],
            'revision': item['visual']['revision'],
            'before_sha256': item['visual']['before']['sha256'],
            'after_sha256': item['visual']['after']['sha256']} for item in review['members']]}}


def pending(host, review):
    return host.engine._face_style_reviews['pending'][review['token']]


def add_alias(host, document='doc-added'):
    row = make_row(document, 12, repair='new-own-repair', crop=[80, 99])
    host.engine._docs.append(row); host.engine.context[document] = 'support-' + document
    return row


def test_alias_review_has_actual_source_first_and_each_own_full_snapshot(host):
    h = host; before = h.owner.snapshot(); rows_before = deepcopy(h.engine._docs)
    review = preview(h)
    assert review['version'] == 2 and review['recipe'] == PAYLOAD
    assert [item['visual']['document_id'] for item in review['members']] == ['doc-source', 'doc-alias']
    assert [item['path'] for item in review['members']] == [h.source['path'], h.alias['path']]
    assert review['visual'] == review['members'][0]['visual']
    assert [call['document_id'] for call in h.engine.render_calls] == ['doc-source', 'doc-source', 'doc-alias', 'doc-alias']
    for first, second, row, captured in (
            (0, 1, h.source, h.engine.current), (2, 3, h.alias, h.alias['state'])):
        left, right = h.engine.render_calls[first], h.engine.render_calls[second]
        assert left['row'] is row and right['row'] is row
        assert left['state'] == right['state'] == captured
        assert left['graph'] == before and right['graph'] == h.engine.render_calls[1]['graph']
    candidate = h.engine.render_calls[1]['graph']
    values = A.recipes(resolve(candidate, h.face_id, A.defaults()))
    for patch in REC.patches('classic', .5):
        assert A.leaves(values[patch['operation_id']])[patch['parameter_path']] == patch['value']
    assert values['lnx.nose_shape.v1']['wing'] == -.12
    assert review['members'][0]['visual']['before_output_size'] == [120, 150]
    assert review['members'][1]['visual']['before_output_size'] == [91, 107]
    assert review['members'][0]['visual']['before']['sha256'] != review['members'][1]['visual']['before']['sha256']
    assert review['patches_sha256'] == R.digest(REC.patches('classic', .5))
    assert review['face_ref'] == h.target['face_ref']
    assert h.owner.snapshot() == before and h.owner.fence == 9 and h.engine._docs == rows_before
    assert not h.engine.history and not h.batch.ledger
    h.engine._people_bind.assert_not_called(); h.engine._people_publish_graph.assert_not_called()


def test_complete_alias_bound_refuses_seventeen_without_partial_render(host):
    h = host
    for index in range(15): add_alias(h, 'doc-extra-' + str(index))
    with pytest.raises(ValueError): preview(h)
    assert not h.engine.render_calls and h.owner.snapshot() == h.state and not h.batch.ledger


def test_sixteen_aliases_each_receive_both_images_without_detail_reduction(host):
    h = host
    for index in range(14): add_alias(h, 'doc-extra-' + str(index))
    review = preview(h)
    assert len(review['members']) == 16 and len(h.engine.render_calls) == 32
    assert len({member['visual']['document_id'] for member in review['members']}) == 16
    assert review['members'][0]['visual']['document_id'] == 'doc-source'
    assert len(confirmation(review)['ack']['members']) == 16


@pytest.mark.parametrize('fault', ('trash', 'missing-state', 'unknown-pending-import', 'duplicate-document',
    'missing-project-owner', 'foreign-project-owner'))
def test_unreviewable_alias_refuses_before_any_claim_or_publication(host, fault):
    h = host
    if fault == 'trash': h.alias['trashed'] = True
    elif fault == 'missing-state': h.alias.pop('state')
    elif fault == 'unknown-pending-import':
        row = add_alias(h, 'doc-pending'); row['_people_new_import'] = True; row['fingerprint'] = {}
    elif fault == 'missing-project-owner': h.engine._people_project_context = None
    elif fault == 'foreign-project-owner': h.engine._people_project_context = {'owner': Owner(h.state)}
    else: h.alias['document_id'] = h.source['document_id']
    with pytest.raises(ValueError): preview(h)
    assert h.owner.snapshot() == h.state and h.owner.fence == 9 and not h.batch.ledger
    assert '_face_style_reviews' not in h.engine.__dict__


@pytest.mark.parametrize('fault', ('new-alias', 'missing-alias', 'row-replacement', 'source',
    'repair', 'crop', 'full-state', 'support', 'graph', 'face-analysis', 'path', 'revision',
    'scope', 'trash', 'load', 'owner-fence', 'cursor', 'target', 'order'))
def test_pending_alias_review_refuses_any_changed_complete_member_or_owner(host, fault):
    h = host; review = preview(h)
    if fault == 'new-alias': add_alias(h)
    elif fault == 'missing-alias': h.engine._docs.pop(0); h.engine._doc_index = 0
    elif fault == 'row-replacement': h.engine._docs[0] = deepcopy(h.alias)
    elif fault == 'source': h.alias['state']['source'] = 'b' * 64
    elif fault == 'repair': h.alias['state']['repair'] = 'changed-repair'
    elif fault == 'crop': h.alias['state']['crop'] = [60, 80]
    elif fault == 'full-state': h.alias['state']['exposure'] += .1
    elif fault == 'support': h.engine.context['doc-alias'] = 'changed-support'
    elif fault == 'graph': h.owner.state['faces'][h.face_id]['labels']['changed'] = True
    elif fault == 'face-analysis': h.owner.state['faces'][h.face_id]['analysis_revision'] += 1
    elif fault == 'path': h.alias['path'] = '/fixture/replaced.png'
    elif fault == 'revision': h.alias['document_revision'] += 1
    elif fault == 'scope': h.alias['copy_number'] = 1
    elif fault == 'trash': h.alias['trashed'] = True
    elif fault == 'load': h.engine._load_id = 'load-alias-two'
    elif fault == 'owner-fence': h.owner.fence += 1
    elif fault == 'cursor': h.engine._people_cursors[ASSET] = 'another-face'
    elif fault == 'order': h.engine._docs.reverse(); h.engine._doc_index = 0
    else: h.engine._people_targets[ASSET] = {'scope': 'all_people'}
    with pytest.raises(ValueError):
        R.confirm(h.engine, h.owner.snapshot(), h.target, confirmation(review))
    assert not pending(h, review)['claimed'] and not h.batch.ledger


@pytest.mark.parametrize('fault', ('review', 'document', 'revision', 'before', 'after',
    'reverse', 'duplicate', 'missing', 'extra', 'tuple', 'extra-member-field', 'extra-ack-field'))
def test_alias_ack_requires_exact_ordered_complete_document_pairs_without_claim(host, fault):
    h = host; review = preview(h); payload = confirmation(review); ack = payload['ack']
    if fault == 'review': ack['review_sha256'] = '0' * 64
    elif fault == 'document': ack['members'][1]['document_id'] = 'foreign'
    elif fault == 'revision': ack['members'][1]['revision'] = '9'
    elif fault == 'before': ack['members'][1]['before_sha256'] = '0' * 64
    elif fault == 'after': ack['members'][1]['after_sha256'] = '0' * 64
    elif fault == 'reverse': ack['members'].reverse()
    elif fault == 'duplicate': ack['members'][1] = deepcopy(ack['members'][0])
    elif fault == 'missing': ack['members'].pop()
    elif fault == 'extra': ack['members'].append(deepcopy(ack['members'][-1]))
    elif fault == 'tuple': ack['members'] = tuple(ack['members'])
    elif fault == 'extra-member-field': ack['members'][1]['recipe_sha256'] = '0' * 64
    else: ack['coverage_sha256'] = '0' * 64
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    assert not pending(h, review)['claimed'] and h.owner.snapshot() == h.state


def test_v1_pair_ack_cannot_authorize_v2_alias_set(host):
    h = host; review = preview(h); visual = review['visual']
    payload = {'token': review['token'], 'ack': {'review_sha256': review['review_sha256'],
        'before_sha256': visual['before']['sha256'], 'after_sha256': visual['after']['sha256']}}
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    assert not pending(h, review)['claimed']


def test_member_images_require_document_identity_and_return_exact_review_hash(host):
    h = host; review = preview(h)
    for member in review['members']:
        visual = member['visual']
        for side in ('before', 'after'):
            payload = {'token': review['token'], 'document_id': visual['document_id'],
                       'side': side, 'sha256': visual[side]['sha256']}
            result = R.image(h.engine, h.owner.snapshot(), h.target, payload)
            assert result['document_id'] == visual['document_id']
            assert result['image']['sha256'] == visual[side]['sha256']
            assert result['review_sha256'] == review['review_sha256']
    payload = {'token': review['token'], 'document_id': 'doc-alias',
               'side': 'before', 'sha256': review['visual']['before']['sha256']}
    with pytest.raises(ValueError): R.image(h.engine, h.owner.snapshot(), h.target, payload)
    payload.pop('document_id')
    with pytest.raises(ValueError): R.image(h.engine, h.owner.snapshot(), h.target, payload)


@pytest.mark.parametrize('fault', ('missing-pair', 'changed-bytes', 'missing-one-member', 'expired'))
def test_every_member_cache_pair_must_remain_available_before_claim(host, fault):
    h = host; review = preview(h); store = h.engine._face_style_reviews
    cache = store['images']; token = review['token']
    if fault == 'missing-pair': cache.discard(token)
    elif fault == 'changed-bytes':
        cache.plans[token]['doc-alias']['after']['path'].write_bytes(b'CHANGED FAKE DISPLAY')
    elif fault == 'missing-one-member':
        cache.plans[token]['doc-alias']['before']['path'].unlink()
    else: pending(h, review)['expires'] = -1
    with pytest.raises(ValueError):
        R.confirm(h.engine, h.owner.snapshot(), h.target, confirmation(review))
    assert h.owner.snapshot() == h.state and h.owner.fence == 9 and not h.batch.ledger


def test_canonical_noop_alias_preview_refuses_before_render_and_cannot_invent_batch(host):
    h = host
    for patch in REC.patches('classic', .5):
        h.owner.state = S.set_override(h.owner.state, 'face', h.face_id,
            patch['operation_id'], patch['parameter_path'], patch['value'])
    before = h.owner.snapshot()
    with pytest.raises(ValueError, match='no canonical change'): preview(h)
    assert h.owner.snapshot() == before and not h.engine.render_calls and not h.batch.ledger
    assert '_face_style_reviews' not in h.engine.__dict__


def test_detached_confirmation_returns_actual_plus_one_member_fences_without_claim(host):
    h = host; review = preview(h)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, confirmation(review))
    assert proof['alias_members'] == [
        {'document_id': 'doc-source', 'expected_revision': '4', 'result_revision': '5'},
        {'document_id': 'doc-alias', 'expected_revision': '8', 'result_revision': '9'}]
    assert proof['ack'] == confirmation(review)['ack']
    candidate['faces'][h.face_id]['labels']['outside-edit'] = True
    assert pending(h, review)['candidate'] != candidate
    assert not pending(h, review)['claimed'] and h.owner.snapshot() == h.state
    assert h.source['document_revision'] == 4 and h.alias['document_revision'] == 8


def test_mid_member_render_change_discards_whole_review_without_partial_cache(host, monkeypatch):
    h = host; original = ALIAS.render_image
    def changed(*args):
        result = original(*args)
        if len(h.engine.render_calls) == 4: h.alias['state']['repair'] = 'changed-mid-review'
        return result
    monkeypatch.setattr(ALIAS, 'render_image', changed)
    with pytest.raises(ValueError): preview(h)
    assert h.owner.snapshot() == h.state and h.owner.fence == 9
    assert '_face_style_reviews' not in h.engine.__dict__ and not h.batch.ledger


def dormant_row(host):
    row = make_row('doc-dormant', 6, repair='dormant-own-repair', crop=[100, 140], asset='b' * 64)
    row['state']['original_source'] = ASSET
    host.engine._docs.append(row); host.engine.context['doc-dormant'] = 'support-dormant'
    return row


@pytest.mark.parametrize('retained', ('undo', 'redo', 'named-version', 'saved-document-history', 'saved-people-history'))
def test_dormant_shared_source_in_any_baseline_history_refuses_complete_review(host, retained):
    h = host; row = dormant_row(h)
    saved = {'document_id': row['document_id'], 'versions': []}
    h.engine._project = {'docs': [saved]}
    if retained in ('undo', 'redo'): row[retained] = [{}]
    elif retained == 'named-version': saved['versions'] = [{'id': 'original', 'recipe': {}}]
    elif retained == 'saved-document-history': saved['document_history'] = {'undo': [{}], 'redo': []}
    else:
        h.engine._project['people_document_history'] = {'document:doc-dormant': {
            'document_id': 'doc-dormant', 'asset_sha256': ASSET,
            'stacks': {'undo': [], 'redo': [{}]}}}
    with pytest.raises(ValueError): preview(h)
    assert not h.engine.render_calls and not h.batch.ledger and h.owner.snapshot() == h.state


def test_explicit_owned_cleared_runtime_history_does_not_resurrect_stale_saved_stack(host):
    h = host; row = dormant_row(h)
    row.update(_history_owned=True, undo=[], redo=[])
    h.engine._project = {'docs': [{'document_id': row['document_id'], 'versions': [],
        'document_history': {'undo': [{}], 'redo': []}}],
        'people_document_history': {'document:doc-dormant': {'document_id': 'doc-dormant',
            'asset_sha256': ASSET, 'stacks': {'undo': [{}], 'redo': []}}}}
    review = preview(h)
    assert [member['visual']['document_id'] for member in review['members']] == ['doc-source', 'doc-alias']
    assert row['undo'] == row['redo'] == []


@pytest.mark.parametrize('fault', ('active-source', 'trash', 'named-dormant-source', 'document-history',
    'people-history', 'unknown-active-version', 'ambiguous-active-version'))
def test_project_only_shared_document_cannot_be_silently_omitted(host, fault):
    h = host
    base = {'id': 'sha256:' + 'b' * 64, 'kind': 'rgba', 'width': 128, 'height': 160}
    saved = {'document_id': 'doc-unavailable', 'copy_number': 0, 'trashed': fault == 'trash',
        'fingerprint': {'hash_level': 'full', 'sha256': ASSET},
        'active_version': 'active', 'versions': [{'id': 'active', 'recipe': {'_creative_base': base}}]}
    h.engine._project = {'docs': [saved]}
    if fault in ('active-source', 'trash'): saved['versions'][0]['recipe'] = {}
    elif fault == 'named-dormant-source': saved['versions'].append({'id': 'older', 'recipe': {}})
    elif fault == 'document-history': saved['document_history'] = {'undo': [{}], 'redo': []}
    elif fault == 'people-history':
        h.engine._project['people_document_history'] = {'document:doc-unavailable': {
            'document_id': 'doc-unavailable', 'asset_sha256': ASSET,
            'stacks': {'undo': [], 'redo': [{}]}}}
    elif fault == 'unknown-active-version': saved['active_version'] = 'missing'
    else: saved['versions'].append(deepcopy(saved['versions'][0]))
    with pytest.raises(ValueError): preview(h)
    assert not h.engine.render_calls and not h.batch.ledger and h.owner.fence == 9


def test_known_independent_import_and_private_copy_are_not_borrowed_as_shared_aliases(host):
    h = host
    fresh = add_alias(h, 'doc-independent'); fresh['_people_new_import'] = True
    private = add_alias(h, 'doc-private-copy'); private['copy_number'] = 1
    before_fresh = deepcopy(fresh); before_private = deepcopy(private)
    review = preview(h)
    assert [member['visual']['document_id'] for member in review['members']] == ['doc-source', 'doc-alias']
    assert fresh == before_fresh and private == before_private
    assert V.KEY not in fresh and V.RUNTIME not in fresh and V.RUNTIME not in private


def install_publication_boundary(host, monkeypatch, review):
    """Real commit_scoped/history admission, fake final graph/frame boundary."""
    h = host; order = []; captured = {}; original = LEDGER.commit_scoped
    def prepare(actual, plans, targets):
        assert actual is h.engine and not pending(h, review)['claimed']
        order.append('prepare')
    def publish(batch, actual, plans, targets):
        assert pending(h, review)['claimed']
        order.append('publish')
        h.owner.state = deepcopy(plans[V.PROJECT]['candidate']); h.owner.fence += 1
        for target in targets.values():
            _, row = h.versions.find(h.engine._docs, target['document_id']); h.versions.advance(row)
        return None
    def commit(batch, actual, plans, **kwargs):
        assert pending(h, review)['claimed'] and kwargs['prepare'] is False
        assert kwargs['prepared_targets'] == pending(h, review)['targets']
        assert kwargs['alias_history']['review_sha256'] == review['review_sha256']
        captured.update(deepcopy(kwargs)); order.append('commit-with-marker')
        return original(batch, actual, plans, **kwargs)
    monkeypatch.setattr(LEDGER, 'prepare_scoped', prepare)
    monkeypatch.setattr(LEDGER, '_publish', publish)
    monkeypatch.setattr(LEDGER, 'commit_scoped', commit)
    return order, captured


def test_alias_publishes_one_existing_ledger_batch_with_marker_before_publication(host, monkeypatch):
    h = host; review = preview(h); payload = confirmation(review)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    order, captured = install_publication_boundary(h, monkeypatch, review)
    bid, frame = R.publish_alias(h.engine, h.owner.snapshot(), h.target, payload,
                                 candidate, proof, request_id='publish-alias')
    assert order == ['prepare', 'commit-with-marker', 'publish'] and frame is None
    assert list(h.batch.ledger) == [bid]
    receipt = h.batch.ledger[bid]; marker = HISTORY.check(receipt)
    assert marker == captured['alias_history']
    assert marker['document_ids'] == ['doc-alias', 'doc-source']
    assert receipt['request_id'] == 'publish-alias'
    assert receipt['targets'] == pending(h, review)['targets']
    assert h.owner.fence == 10 and h.source['document_revision'] == 5 and h.alias['document_revision'] == 9
    assert h.owner.snapshot() == candidate and h.engine._people_staged is None
    R.verify_after_publish(h.engine, candidate, proof)
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    h.engine._people_publish_graph.assert_not_called()


@pytest.mark.parametrize('fault', ('new-alias', 'missing-alias', 'repair', 'source', 'trash', 'cache', 'dormant-history'))
def test_final_prepare_rechecks_complete_closure_and_pixels_before_one_way_claim(host, monkeypatch, fault):
    h = host; review = preview(h); payload = confirmation(review)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    def prepare(actual, plans, targets):
        assert not pending(h, review)['claimed']
        if fault == 'new-alias': add_alias(h)
        elif fault == 'missing-alias': h.engine._docs.pop(0); h.engine._doc_index = 0
        elif fault == 'repair': h.alias['state']['repair'] = 'changed-in-prepare'
        elif fault == 'source': h.alias['state']['source'] = 'b' * 64
        elif fault == 'trash': h.alias['trashed'] = True
        elif fault == 'cache': h.engine._face_style_reviews['images'].discard(review['token'])
        else: dormant_row(h)['undo'] = [{}]
    monkeypatch.setattr(LEDGER, 'prepare_scoped', prepare)
    commit = Mock(side_effect=AssertionError('Do not claim or publish a changed set'))
    monkeypatch.setattr(LEDGER, 'commit_scoped', commit)
    with pytest.raises(ValueError):
        R.publish_alias(h.engine, h.owner.snapshot(), h.target, payload,
                        candidate, proof, request_id='changed-before-claim')
    assert not pending(h, review)['claimed'] and h.owner.snapshot() == h.state and h.owner.fence == 9
    assert not h.batch.ledger and h.engine._people_staged is None
    commit.assert_not_called()


@pytest.mark.parametrize('fault', ('candidate', 'proof', 'ack', 'member-order'))
def test_publication_cannot_swap_review_candidate_or_proof_before_claim(host, monkeypatch, fault):
    h = host; review = preview(h); payload = confirmation(review)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    if fault == 'candidate': candidate['faces'][h.face_id]['labels']['foreign'] = True
    elif fault == 'proof': proof['review_sha256'] = '0' * 64
    elif fault == 'ack': payload['ack']['members'][1]['after_sha256'] = '0' * 64
    else: proof['alias_members'].reverse()
    prepare = Mock(side_effect=AssertionError('Reject before staging publication'))
    monkeypatch.setattr(LEDGER, 'prepare_scoped', prepare)
    with pytest.raises(ValueError):
        R.publish_alias(h.engine, h.owner.snapshot(), h.target, payload,
                        candidate, proof, request_id='foreign-proof')
    assert not pending(h, review)['claimed'] and not h.batch.ledger
    prepare.assert_not_called()


def test_claimed_alias_token_is_not_released_after_uncertain_publication_failure(host, monkeypatch):
    h = host; review = preview(h); payload = confirmation(review)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    monkeypatch.setattr(LEDGER, 'prepare_scoped', lambda *args: None)
    def failed(*args, **kwargs):
        assert pending(h, review)['claimed']
        h.owner.fence += 1
        raise ValueError('Fixture publication side effects have an uncertain outcome')
    monkeypatch.setattr(LEDGER, 'commit_scoped', failed)
    with pytest.raises(ValueError):
        R.publish_alias(h.engine, h.owner.snapshot(), h.target, payload,
                        candidate, proof, request_id='uncertain-publish')
    assert pending(h, review)['claimed'] and h.owner.fence == 10 and h.engine._people_staged is None
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, payload)


@pytest.mark.parametrize('fault', ('owner', 'graph', 'graph-revision', 'double-fence', 'no-alias-advance',
    'double-alias-advance', 'row-replacement', 'repair', 'new-alias', 'source', 'marker', 'receipt-target', 'proof'))
def test_postpublication_accepts_only_own_exact_plus_one_and_original_marked_closure(host, monkeypatch, fault):
    h = host; review = preview(h); payload = confirmation(review)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    install_publication_boundary(h, monkeypatch, review)
    bid, _ = R.publish_alias(h.engine, h.owner.snapshot(), h.target, payload,
                             candidate, proof, request_id='verify-postpublication')
    if fault == 'owner':
        replacement = Owner(candidate); replacement.fence = h.owner.fence
        h.engine._people_graph_owner = replacement; h.engine._people_active_context = {'owner': replacement}
    elif fault == 'graph': h.owner.state['faces'][h.face_id]['labels']['foreign'] = True
    elif fault == 'graph-revision': h.owner.state['revision'] += 1
    elif fault == 'double-fence': h.owner.fence += 1
    elif fault == 'no-alias-advance': h.alias['document_revision'] -= 1
    elif fault == 'double-alias-advance': h.alias['document_revision'] += 1
    elif fault == 'row-replacement': h.engine._docs[0] = deepcopy(h.alias)
    elif fault == 'repair': h.alias['state']['repair'] = 'changed-after-publication'
    elif fault == 'new-alias': add_alias(h)
    elif fault == 'source': h.alias['state']['source'] = 'b' * 64
    elif fault == 'marker': h.batch.ledger[bid].pop(HISTORY.KEY)
    elif fault == 'receipt-target': h.batch.ledger[bid]['targets'].pop('0')
    else: proof['alias_members'][1]['result_revision'] = '10'
    with pytest.raises(ValueError): R.verify_after_publish(h.engine, candidate, proof)
    assert pending(h, review)['claimed']


def test_maximum_exact_ui_revision_is_accepted_only_as_own_plus_one_result(host, monkeypatch):
    h = host; h.source['document_revision'] = ALIAS.MAX_REVISION - 1
    h.alias['document_revision'] = ALIAS.MAX_REVISION - 1
    review = preview(h); payload = confirmation(review)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    install_publication_boundary(h, monkeypatch, review)
    R.publish_alias(h.engine, h.owner.snapshot(), h.target, payload,
                    candidate, proof, request_id='exact-max-revision')
    assert {item['result_revision'] for item in proof['alias_members']} == {str(ALIAS.MAX_REVISION)}
    R.verify_after_publish(h.engine, candidate, proof)


@pytest.mark.parametrize('revision', (True, 8, '08', '-1', '', '1.0', str(2**53), str(2**64)))
def test_alias_ack_revisions_require_exact_bounded_decimal_strings(host, revision):
    h = host; review = preview(h); payload = confirmation(review)
    payload['ack']['members'][1]['revision'] = revision
    with pytest.raises(ValueError): R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    assert not pending(h, review)['claimed']


def test_full_recipe_graph_revision_must_remain_exactly_representable_before_render(host):
    h = host
    # The existing real recipe stage owns 30 canonical patches, not a synthetic
    # one-step graph counter. Its prospective revision must still fit the UI.
    patch_count = len(REC.patches('classic', .5))
    assert patch_count == 30
    h.owner.state['revision'] = ALIAS.MAX_REVISION - patch_count + 1
    before = h.owner.snapshot()
    with pytest.raises(ValueError): preview(h)
    assert not h.engine.render_calls and h.owner.snapshot() == before and not h.batch.ledger
    assert '_face_style_reviews' not in h.engine.__dict__


@pytest.mark.parametrize('hash_level', ('head', None))
def test_partial_or_unqualified_saved_fingerprint_cannot_exclude_unavailable_shared_document(host, hash_level):
    h = host
    fingerprint = {'sha256': 'b' * 64}
    if hash_level is not None: fingerprint['hash_level'] = hash_level
    h.engine._project = {'docs': [{'document_id': 'doc-unavailable', 'fingerprint': fingerprint,
        'active_version': 'active', 'versions': [{'id': 'active', 'recipe': {}}]}]}
    with pytest.raises(ValueError): preview(h)
    assert not h.engine.render_calls and not h.batch.ledger


def test_unavailable_truly_unrelated_full_fingerprint_does_not_invent_an_alias(host):
    h = host
    h.engine._project = {'docs': [{'document_id': 'doc-unrelated',
        'fingerprint': {'hash_level': 'full', 'sha256': 'b' * 64},
        'active_version': 'active', 'versions': [{'id': 'active', 'recipe': {}}]}]}
    review = preview(h)
    assert [member['visual']['document_id'] for member in review['members']] == ['doc-source', 'doc-alias']


def test_none_ledger_result_cannot_be_reported_as_a_fabricated_alias_batch(host, monkeypatch):
    h = host; review = preview(h); payload = confirmation(review)
    candidate, proof = R.confirm(h.engine, h.owner.snapshot(), h.target, payload)
    monkeypatch.setattr(LEDGER, 'prepare_scoped', lambda *args: None)
    commit = Mock(return_value=None); monkeypatch.setattr(LEDGER, 'commit_scoped', commit)
    with pytest.raises(ValueError):
        R.publish_alias(h.engine, h.owner.snapshot(), h.target, payload,
                        candidate, proof, request_id='no-fabricated-batch')
    assert commit.call_count == 1 and pending(h, review)['claimed']
    assert 'batch_id' not in pending(h, review) and not h.batch.ledger
