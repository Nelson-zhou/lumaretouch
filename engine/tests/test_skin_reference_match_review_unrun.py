# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN current-photo source/full-image review contracts.

Real scalar/relation/graph validators, synthetic retained source evidence and
mocked authenticated decode/full-render/publication boundaries. No test was
collected/executed; no product import, native inference, build or photographic
acceptance ran while authoring. Fake display bytes are explicitly not real PNG.
"""
from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import skin_reference_match_host as H
from lumaretouch_engine import skin_reference_match_project as PROJECT
from lumaretouch_engine import skin_reference_match_state as S
from lumaretouch_engine import skin_reference_match_support as SUPPORT
from lumaretouch_engine import people_state as P, virtual_copy_people as V
from lumaretouch_engine import face_style_alias_review as ALIASES
from lumaretouch_engine import full_candidate_render as FULL
from lumaretouch_engine import people_transfer_inventory as INVENTORY
from lumaretouch_engine import people_host_commands as COMMANDS
from lumaretouch_engine import skin_colour_support as SEM

ASSET = 'a' * 64


class Owner:
    def __init__(self, state):
        self.state = deepcopy(state); self.fence = 7
    def snapshot(self):
        return deepcopy(self.state)


def face(state, key, x):
    points = np.full((478, 3), [x, .5, 0.], dtype='<f4')
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': sha256(points.tobytes()).hexdigest(),
        'status': 'verified', 'source_width': 256, 'source_height': 128,
        'orientation': 'exif_normalized_once'}
    value = P.new_face(ASSET, [x-.06, .2, x+.06, .8], evidence)
    value['face_instance_id'] = key; state['faces'][key] = value
    ref = P.face_ref(value)
    return ref, {'face_ref': ref, 'evidence': deepcopy(evidence), 'landmarks': points,
        'face_skin': np.full((64, 128), .7, np.float32), 'excluded': np.zeros((64, 128), np.float32),
        'face_skin_observation': {'contract': SEM.CONTRACT, 'source_sha256': ASSET,
            'semantic_model_sha256': 'c'*64, 'producer_width': 128, 'producer_height': 64}}


def display(raw):
    return {'mime': 'image/png', 'width': 256, 'height': 128, 'sha256': sha256(raw).hexdigest(),
            'base64': b64encode(raw).decode('ascii')}


@pytest.fixture
def host(monkeypatch):
    state = P.empty(); refs = {}; analyses = {}
    for key, x in (('first', .15), ('second', .38), ('reference', .62), ('other-reference', .85)):
        refs[key], analyses[key] = face(state, key, x)
    state = P.set_override(state, 'face', 'first', 'lnx.nose_shape.v1', '/wing', -.12)
    owner = Owner(state)
    row = {'path': '/synthetic/source.png', 'src_w': 256, 'src_h': 128, 'document_id': 'document-one'}
    version = SimpleNamespace(document_id='document-one', revision=5)
    source = {'sha256': ASSET, 'width': 256, 'height': 128}
    source_proof = {'asset_sha256': ASSET, 'original_sha256': ASSET, 'creative_source': None}
    target = {'scope': 'all_people', 'target_id': ASSET, 'face_ref': None}
    engine = SimpleNamespace(_people_graph_owner=owner, _people_active_context={'owner': owner}, _people_scope_row=row,
        _load_id='load-one', _people_support={}, _people_analyses={ASSET: analyses}, _docs=[row],
        _people_cursors={ASSET: 'other-reference'}, _people_targets={ASSET: {'scope': 'person', 'target_id': 'unrelated'}},
        current={'source': ASSET, 'repair': 'repair-0'}, row=row, version=version, context='context-0',
        renders=[], writes=[], _people_staged=None)
    engine._people_source = lambda: deepcopy(source)
    engine._people_preset_capture = lambda: deepcopy(engine.current)
    engine._document_versions = lambda: SimpleNamespace(version=lambda r: version)
    monkeypatch.setattr(V, 'current_row', lambda e: e.row)
    monkeypatch.setattr(V, 'scope_rows', lambda e, row=None: e._docs)
    monkeypatch.setattr(ALIASES, 'verify_dormant', lambda *args: None)
    monkeypatch.setattr(H.SOURCE, 'binding', lambda *args: deepcopy(source))
    monkeypatch.setattr(H.SOURCE, 'row_asset', lambda r: r.get('state', engine.current)['source'])
    monkeypatch.setattr(H.SOURCE, 'row_proof', lambda r: {**source_proof, 'asset_sha256': r.get('state', engine.current)['source']})
    def verify(r, proof):
        if H.SOURCE.row_proof(r) != proof:
            raise ValueError('Synthetic source changed')
    monkeypatch.setattr(H.SOURCE, 'verify_row', verify)
    monkeypatch.setattr(S, 'capability', lambda: {'skin_reference_match_available': True, 'skin_reference_match_reason': None})
    monkeypatch.setattr(H, '_source_display', lambda e, s: (display(b'FAKE SOURCE DISPLAY'), 'd'*64))
    monkeypatch.setattr(INVENTORY, 'proof', lambda e, r, s, source_row: {
        'document_id': version.document_id, 'revision': str(version.revision), 'people_scope': 'project',
        'state_revision': s['revision'], 'association_revision': s['association_revision'], 'source_proof': source_proof})
    monkeypatch.setattr(FULL, 'people_context', lambda e, r: {
        'people_graph': owner.snapshot(), 'people_support_assets': deepcopy(e._people_support), 'other': e.context})
    def key(e, r, current, graph, *, staged_people_context=None):
        context = FULL.people_context(e, r) if staged_people_context is None else staged_people_context
        normalized = deepcopy(graph); normalized['revision'] = 0
        return {'render_sha256': H.digest(current), 'graph_sha256': H.digest(normalized),
                'context_sha256': H.digest({k: v for k, v in context.items() if k != 'people_graph'})}
    monkeypatch.setattr(H, 'snapshot_key', key)
    def render(e, r, current, graph, document, revision, *, staged_people_context=None):
        e.renders.append({'graph': deepcopy(graph), 'live_bank': deepcopy(e._people_support),
                          'context': deepcopy(staged_people_context)})
        pixels = display(('FAKE MIXED DISPLAY ' + H.digest(key(e, r, current, graph,
            staged_people_context=staged_people_context))).encode())
        compact = {k: v for k, v in pixels.items() if k != 'base64'}
        proof = {'source_proof': source_proof, 'source_size': [256, 128], 'output_size': [256, 128],
                 'candidate_sha256': H.digest(current), 'people_sha256': H.digest(graph)}
        return compact, pixels, proof
    monkeypatch.setattr(H, 'render_image', render)
    def publish(e, before, candidate, request, *, shared=False, before_publish=None):
        assert shared is False
        PROJECT.require_transition(e, before, candidate)
        if before_publish:
            before_publish()
        e.writes.append(request); owner.state = deepcopy(candidate); owner.fence += 1; version.revision += 1
        return None, {'event': 'frame'}
    monkeypatch.setattr(COMMANDS, 'publish', publish)
    yield SimpleNamespace(engine=engine, owner=owner, refs=refs, target=target, source=source, version=version)
    if '_skin_reference_match_reviews' in engine.__dict__:
        engine._skin_reference_match_reviews['images'].directory.cleanup()


def catalog(h):
    return H.catalogue(h.engine, h.owner.snapshot(), h.target, {})


def payload(h, *, reference='reference', targets=('first', 'second'), amount=.5):
    source = catalog(h)
    return {'version': 1, 'reference_face_ref': deepcopy(h.refs[reference]),
        'target_face_refs': [deepcopy(h.refs[key]) for key in targets], 'amount': amount,
        'source_review_sha256': source['source_review_sha256'], 'ownership_confirmed': True}


def review(h, **kwargs):
    return H.preview(h.engine, h.owner.snapshot(), h.target, payload(h, **kwargs))['review']


def loaded(h, r):
    for side in ('before', 'after'):
        result = H.image(h.engine, h.owner.snapshot(), h.target, {'token': r['token'], 'side': side,
            'sha256': r['visual'][side]['sha256'], 'review_sha256': r['review_sha256']})
        assert result['image']['sha256'] == r['visual'][side]['sha256']
    return {'token': r['token'], 'ack': H._ack(r)}


def commit(h, r):
    p = loaded(h, r); state = h.owner.snapshot()
    candidate, proof = H.confirm(h.engine, state, h.target, p)
    started = []
    result = H.publish(h.engine, state, h.target, p, candidate, proof, 'request-one', lambda: started.append(True))
    assert result[0] is None and started == [True]
    return candidate, proof


def test_catalog_actual_source_proof_and_cursor_independent_selection(host):
    h = host; before = h.owner.snapshot(); result = catalog(h)
    assert result['source_image']['base64'] == b64encode(b'FAKE SOURCE DISPLAY').decode()
    assert result['source'] == h.source and len(result['faces']) == 4
    assert result['body_matching'] is False and result['automatic_reference'] is False
    assert all(row['available'] for row in result['faces'])
    assert result['current']['reference_face_ref'] is None
    assert h.owner.snapshot() == before and h.engine._people_support == {} and h.engine.writes == []
    assert h.engine._people_cursors[ASSET] == 'other-reference'


@pytest.mark.parametrize('change', ['ownership', 'source-proof', 'missing-proof', 'same-reference', 'duplicate', 'foreign', 'empty', 'zero', 'extra', 'body'])
def test_preview_cannot_infer_reference_targets_or_borrow_confirmation(host, change):
    h = host; p = payload(h)
    if change == 'ownership': p['ownership_confirmed'] = False
    elif change == 'source-proof': p['source_review_sha256'] = 'e'*64
    elif change == 'missing-proof': del p['source_review_sha256']
    elif change == 'same-reference': p['target_face_refs'].append(p['reference_face_ref'])
    elif change == 'duplicate': p['target_face_refs'].append(p['target_face_refs'][0])
    elif change == 'foreign': p['target_face_refs'][0]['asset_sha256'] = 'f'*64
    elif change == 'empty': p['target_face_refs'] = []
    elif change == 'zero': p['amount'] = 0
    else: p[change] = True
    with pytest.raises(ValueError): H.preview(h.engine, h.owner.snapshot(), h.target, p)
    assert h.engine._people_support == {} and h.engine.writes == []


def test_preview_stages_support_only_and_renders_actual_complete_before_and_after(host):
    h = host; before = h.owner.snapshot(); r = review(h)
    assert h.owner.snapshot() == before and h.engine._people_support == {}
    assert len(h.engine.renders) == 2 and h.engine.renders[0]['graph'] == before
    assert h.engine.renders[0]['context'] is None
    after = h.engine.renders[1]; candidate = after['graph']
    assert after['live_bank'] == {} and len(after['context']['people_support_assets']) == 2
    assert candidate['revision'] == before['revision'] + 1
    assert candidate['faces']['reference'] == before['faces']['reference']
    assert [row for row in candidate['overrides'] if row['operation_id'] != S.OP] == before['overrides']
    assert PROJECT.active_refs(candidate, ASSET) == [h.refs['first'], h.refs['second']]
    assert r['support_sha256'].keys() == {'first', 'second'} and h.engine.writes == []


def test_confirm_requires_loaded_exact_images_not_metadata_ack_alone(host):
    h = host; r = review(h); p = {'token': r['token'], 'ack': H._ack(r)}
    with pytest.raises(ValueError, match='Load both'): H.confirm(h.engine, h.owner.snapshot(), h.target, p)
    p = loaded(h, r); bad = deepcopy(p); bad['ack']['after_sha256'] = '0'*64
    with pytest.raises(ValueError): H.confirm(h.engine, h.owner.snapshot(), h.target, bad)
    candidate, proof = H.confirm(h.engine, h.owner.snapshot(), h.target, p)
    assert proof['target_face_refs'] == r['target_face_refs']
    assert candidate['revision'] == r['candidate_state_revision'] and h.engine.writes == []


@pytest.mark.parametrize('mode', ['repair', 'context', 'source', 'load', 'revision', 'fence', 'path', 'analysis', 'support', 'alias', 'disabled'])
def test_review_rejects_stale_source_repair_document_support_or_face_evidence(host, mode):
    h = host; r = review(h); p = loaded(h, r)
    if mode == 'repair': h.engine.current['repair'] = 'repair-1'
    elif mode == 'context': h.engine.context = 'context-1'
    elif mode == 'source': h.engine.current['source'] = 'f'*64
    elif mode == 'load': h.engine._load_id = 'load-two'
    elif mode == 'revision': h.version.revision += 1
    elif mode == 'fence': h.owner.fence += 1
    elif mode == 'path': h.engine.row['path'] = '/synthetic/replaced.png'
    elif mode == 'analysis': h.engine._people_analyses[ASSET]['first']['excluded'][0, 0] = .5
    elif mode == 'support': h.engine._people_support['e'*64] = {}
    elif mode == 'alias': h.engine._docs.append({**h.engine.row, 'document_id': 'alias-document'})
    else: h.owner.state['faces']['reference']['enabled'] = False
    with pytest.raises(ValueError): H.confirm(h.engine, h.owner.snapshot(), h.target, p)
    assert h.engine.writes == []


def test_commit_uses_canonical_publication_once_and_exact_after_report(host):
    h = host; r = review(h); candidate, proof = commit(h, r)
    assert h.engine.writes == ['request-one'] and h.owner.fence == 8 and h.version.revision == 6
    current = H.report(h.engine)
    assert current['bank_sha256'] == proof['candidate_bank_sha256']
    assert current['reference_face_ref'] == h.refs['reference']
    assert current['amounts'] == [{'face_ref': h.refs[key], 'amount': .5,
        'support_sha256': proof['support_sha256'][key]} for key in ('first', 'second')]
    assert PROJECT._ADMISSION not in h.engine.__dict__
    with pytest.raises(ValueError): H.confirm(h.engine, candidate, h.target, {'token': r['token'], 'ack': H._ack(r)})


def test_new_review_atomically_replaces_complete_previous_target_set(host):
    h = host; commit(h, review(h)); old = h.owner.snapshot(); old_bank = deepcopy(h.engine._people_support)
    r = review(h, reference='other-reference', targets=('reference',), amount=.7)
    store, entry = H._entry(h.engine, r['token']); candidate = entry['candidate']
    assert h.owner.snapshot() == old and h.engine._people_support == old_bank
    assert PROJECT.active_refs(candidate, ASSET) == [h.refs['reference']]
    assert all(SUPPORT.KIND not in candidate['faces'][key]['local_assets'] for key in ('first', 'second', 'other-reference'))
    assert all(entry['assets'][key] == value for key, value in old_bank.items())
    candidate, proof = commit(h, r)
    assert H.report(h.engine)['reference_face_ref'] == h.refs['other-reference']
    assert len(h.engine._people_support) == 3


def test_generic_patch_cannot_activate_change_reenable_or_modify_donor_anatomy(host):
    h = host; commit(h, review(h)); before = h.owner.snapshot()
    for candidate in (
        P.set_override(before, 'face', 'first', S.OP, '/amount', .6),
        P.set_override(before, 'face', 'other-reference', S.OP, '/amount', .5),
    ):
        with pytest.raises(ValueError): PROJECT.require_unreviewed_transition(before, candidate)
    candidate = deepcopy(before); candidate['faces']['reference']['box'][0] += .01
    with pytest.raises(ValueError): PROJECT.require_unreviewed_transition(before, candidate)
    candidate = deepcopy(before); candidate['faces']['first']['enabled'] = False
    PROJECT.require_unreviewed_transition(before, candidate)
    with pytest.raises(ValueError): PROJECT.require_unreviewed_transition(candidate, before)


def test_exact_review_authority_cannot_admit_other_candidate_bank_or_nested_context(host):
    h = host; r = review(h); p = loaded(h, r)
    candidate, proof = H.confirm(h.engine, h.owner.snapshot(), h.target, p)
    _, entry = H._entry(h.engine, r['token']); h.engine._people_support = deepcopy(entry['assets'])
    with PROJECT.reviewed_transition(h.engine, h.owner.snapshot(), candidate, entry['assets'], r['review_sha256']):
        PROJECT.require_transition(h.engine, h.owner.snapshot(), candidate)
        wrong = P.set_override(candidate, 'face', 'first', S.OP, '/amount', .8)
        with pytest.raises(ValueError): PROJECT.require_transition(h.engine, h.owner.snapshot(), wrong)
        with pytest.raises(ValueError):
            with PROJECT.reviewed_transition(h.engine, h.owner.snapshot(), candidate, entry['assets'], r['review_sha256']): pass
    with pytest.raises(ValueError): PROJECT.require_transition(h.engine, h.owner.snapshot(), candidate)


def test_clear_remains_native_independent_and_preserves_unrelated_recipe_and_history_bank(host, monkeypatch):
    h = host; commit(h, review(h)); before = h.owner.snapshot(); bank = deepcopy(h.engine._people_support)
    monkeypatch.setattr(S, 'capability', lambda: (_ for _ in ()).throw(AssertionError('Clear must not query native')))
    candidate, proof = H.clear(h.engine, before, h.target, {})
    assert proof['cleared_face_refs'] == [h.refs['first'], h.refs['second']]
    assert candidate['overrides'] == [row for row in before['overrides'] if row['operation_id'] != S.OP]
    H.publish(h.engine, before, h.target, {}, candidate, proof, 'clear-request')
    assert h.engine._people_support == bank
    assert H.report(h.engine)['reference_face_ref'] is None
    assert H.report(h.engine)['target_face_refs'] == []
    with pytest.raises(ValueError): H.clear(h.engine, h.owner.snapshot(), h.target, {})


def test_saved_history_relations_are_strict_and_neutral_graph_is_not_rewritten(host):
    h = host; before = h.owner.snapshot(); document = {'people_graph': deepcopy(before)}
    assert PROJECT.validate(document) == {} and document == {'people_graph': before}
    commit(h, review(h)); graph = h.owner.snapshot(); bank = deepcopy(h.engine._people_support)
    project = {'people_graph': before, 'people_support_assets': bank,
               'undo': [{'people_graph': graph}], 'redo': []}
    assert PROJECT.validate(project) == bank
    bad = deepcopy(project); bad['people_support_assets'].clear()
    with pytest.raises(ValueError): PROJECT.validate(bad)
    bad = deepcopy(project); descriptor = bad['undo'][0]['people_graph']['faces']['first']['local_assets'][SUPPORT.KIND]
    descriptor['content_sha256'] = '0'*64
    with pytest.raises(ValueError): PROJECT.validate(bad)
    with pytest.raises(ValueError): PROJECT.validate(project, allowed=False)


def test_document_history_slice_and_sparse_scalar_rows_are_validated(host):
    from lumaretouch_engine.people_graph_owner import document_slice
    h = host; commit(h, review(h)); bank = deepcopy(h.engine._people_support)
    saved = {'people_support_assets': bank,
             'undo': [{'_people_history': document_slice(h.owner.snapshot(), ASSET)}]}
    PROJECT.validate(saved)
    bad = deepcopy(saved)
    bad['undo'][0]['_people_history']['faces']['first']['local_assets'].clear()
    with pytest.raises(ValueError): PROJECT.validate(bad)
    bad = {'people_support_assets': bank, 'changes': [{'before': {
        'scope': 'face', 'target_id': 'first', 'operation_id': S.OP,
        'parameter_path': '/reference', 'value': 'reference'}}]}
    with pytest.raises(ValueError): PROJECT.validate(bad)


def test_failed_canonical_preparation_never_reports_graph_publication(host, monkeypatch):
    h = host; r = review(h); p = loaded(h, r); state = h.owner.snapshot()
    candidate, proof = H.confirm(h.engine, state, h.target, p); started = []
    def fail(*args, **kwargs): raise MemoryError('Synthetic full preparation refusal')
    monkeypatch.setattr(COMMANDS, 'publish', fail)
    with pytest.raises(MemoryError): H.publish(h.engine, state, h.target, p, candidate, proof, 'failed-request', lambda: started.append(True))
    assert h.owner.snapshot() == state and h.owner.fence == 7 and h.version.revision == 5
    assert started == [] and PROJECT._ADMISSION not in h.engine.__dict__
    assert h.engine.writes == []  # Only unused append-only metadata may remain.


def test_source_catalog_and_image_receipts_are_bounded_without_reusing_requests():
    records = {}
    for i in range(5):
        records[str(i)] = {'result': {'payload': {'kind': 'skin_reference_match_image', 'image': {'base64': 'fake'}}, 'request_id': str(i)}}
    H.bound_receipt_images(records)
    assert sum('payload' in row['result'] for row in records.values()) == 2
    assert all(row['result']['request_id'] == key for key, row in records.items())
