# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN alias-ledger membership and persistence contracts.

Synthetic graph and source fixtures only. No real FaceRef, inference, image,
native runtime, execution, collection, build or typecheck acceptance is claimed.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from lumaretouch_engine import face_style_alias_history as H
from lumaretouch_engine import people_batch_ledger as L
from lumaretouch_engine import people_history_persistence as P
from lumaretouch_engine import people_state as S, face_style_recipes as R
from lumaretouch_engine.people_graph_patch import between

ASSET = 'a' * 64
REVIEW = 'b' * 64


@pytest.fixture
def fixture():
    before = S.empty()
    face = S.new_face(ASSET, [.2, .1, .8, .9], {
        'backend': 'synthetic', 'detector_model_sha256': None,
        'semantic_model_sha256': None, 'landmark_digest': None,
        'status': 'synthetic', 'source_width': 128, 'source_height': 160,
        'orientation': 'exif_normalized_once'})
    before['faces'][face['face_instance_id']] = face
    ref = S.face_ref(face)
    candidate = before
    for patch in R.patches('classic', .5):
        candidate = S.set_override(candidate, 'face', face['face_instance_id'],
            patch['operation_id'], patch['parameter_path'], patch['value'])
    proof = {'asset_sha256': ASSET, 'original_sha256': ASSET, 'creative_source': None}
    targets = {str(index): {'path': '/fixture/' + identity + '.png',
        'document_id': identity, 'revision': 4, 'asset_sha256': ASSET,
        'people_scope': 'project', 'source_proof': deepcopy(proof),
        'reviewed_face_refs': [deepcopy(ref)]}
        for index, identity in enumerate(('document-a', 'document-b'))}
    entry = {'ops': [L.OP], 'targets': targets, 'at_ns': 1, 'undone': False,
        'policy': 'protected_scoped_graph', 'people_changes': [],
        'people_scoped_changes': [{'scope': 'project', 'document_id': 'document-a',
                                   'changes': between(before, candidate)}],
        'request_id': 'request-one'}
    review = {'review_sha256': REVIEW, 'face_ref': ref,
        'members': [{'path': target['path'], 'visual': {'document_id': target['document_id'],
            'revision': str(target['revision']), 'source_proof': deepcopy(target['source_proof'])}}
                    for target in targets.values()]}
    owner = SimpleNamespace(ledger={'batch-one': entry})
    row = {'document_id': 'document-a'}
    forward = {'project': {'row': row, 'before': before, 'candidate': candidate,
                           'reviewed_face_refs': [ref]}}
    entry[H.KEY] = H.prepare(review, forward, targets)
    return SimpleNamespace(before=before, candidate=candidate, ref=ref, entry=entry,
        owner=owner, review=review, row=row, forward=forward,
        plans={'project': {'row': row, 'before': candidate, 'candidate': before}})


def test_marker_prepares_only_from_exact_reviewed_visual_members(fixture):
    h = fixture
    assert H.check(h.entry)['document_ids'] == ['document-a', 'document-b']
    assert H.check(h.entry)['face_ref'] == h.ref
    changed = deepcopy(h.review)
    changed['members'][0]['visual']['revision'] = '5'
    with pytest.raises(ValueError, match='reviewed member proof'):
        H.prepare(changed, h.forward, h.entry['targets'])
    changed = deepcopy(h.review)
    changed['members'][0]['visual']['source_proof']['asset_sha256'] = 'c' * 64
    with pytest.raises(ValueError, match='reviewed member proof'):
        H.prepare(changed, h.forward, h.entry['targets'])


@pytest.mark.parametrize('mode', (
    'null', 'extra-field', 'bool-version', 'duplicate', 'unsorted', 'private-scope',
    'foreign-ref', 'missing-target', 'extra-target', 'foreign-target-proof',
    'stale-analysis', 'missing-refs', 'foreign-leaf', 'association-change', 'empty-change'))
def test_marker_rejects_malformed_or_expanded_history(fixture, mode):
    entry = deepcopy(fixture.entry)
    marker = entry[H.KEY]
    if mode == 'null': entry[H.KEY] = None
    elif mode == 'extra-field': marker['implicit'] = True
    elif mode == 'bool-version': marker['version'] = True
    elif mode == 'duplicate': marker['document_ids'][1] = marker['document_ids'][0]
    elif mode == 'unsorted': marker['document_ids'].reverse()
    elif mode == 'private-scope': marker['people_scope'] = 'document-a'
    elif mode == 'foreign-ref': marker['face_ref']['asset_sha256'] = 'c' * 64
    elif mode == 'missing-target': entry['targets'].pop('1')
    elif mode == 'extra-target': entry['targets']['2'] = deepcopy(entry['targets']['0'])
    elif mode == 'foreign-target-proof': entry['targets']['1']['source_proof']['original_sha256'] = 'c' * 64
    elif mode == 'stale-analysis': entry['targets']['1']['reviewed_face_refs'][0]['analysis_revision'] += 1
    elif mode == 'missing-refs': entry['targets']['1'].pop('reviewed_face_refs')
    elif mode == 'foreign-leaf': entry['people_scoped_changes'][0]['changes'][0]['key'][1] = 'another-face'
    elif mode == 'association-change': entry['people_scoped_changes'][0]['changes'][0]['collection'] = 'persons'
    elif mode == 'empty-change': entry['people_scoped_changes'][0]['changes'] = []
    with pytest.raises(ValueError):
        H.check(entry)


def test_legacy_without_marker_keeps_its_old_contract(fixture):
    entry = deepcopy(fixture.entry)
    entry.pop(H.KEY)
    entry['policy'] = 'legacy'
    assert H.check(entry) is None
    H.verify_restore(None, entry, {}, {})


def test_restore_needs_same_members_and_rechecks_dormant_sources(fixture, monkeypatch):
    from lumaretouch_engine import face_style_alias_review as ALIAS
    h = fixture
    calls = []
    monkeypatch.setattr(ALIAS, 'verify_dormant', lambda *args: calls.append(args))
    H.verify_restore('engine', h.entry, h.plans, h.entry['targets'])
    assert calls == [('engine', h.row, {ASSET})]
    expanded = deepcopy(h.entry['targets'])
    expanded['2'] = {**deepcopy(expanded['0']), 'document_id': 'unreviewed-document'}
    with pytest.raises(ValueError, match='exact reviewed members'):
        H.verify_restore('engine', h.entry, h.plans, expanded)
    assert len(calls) == 1
    def dormant(*args):
        raise ValueError('Dormant sibling source is not reviewed')
    monkeypatch.setattr(ALIAS, 'verify_dormant', dormant)
    with pytest.raises(ValueError, match='Dormant sibling'):
        H.verify_restore('engine', h.entry, h.plans, h.entry['targets'])


def test_saved_marker_is_retained_and_malformed_marker_refuses_reopen(fixture):
    saved = {'people_batch_history': {'batch-one': deepcopy(fixture.entry)}, 'assets': {}}
    stacks, entries = P.prepare(saved, [], 64)
    assert stacks == {}
    assert entries['batch-one'][H.KEY] == fixture.entry[H.KEY]
    saved['people_batch_history']['batch-one'][H.KEY]['document_ids'].pop()
    with pytest.raises(ValueError, match='two to sixteen'):
        P.prepare(saved, [], 64)


def test_commit_validates_and_records_marker_before_publication(fixture, monkeypatch):
    h = fixture
    owner = SimpleNamespace(ledger={}, sequence=0, clock=lambda: 1., monotonic=lambda: 1,
        documents=SimpleNamespace(remember_current=lambda: None),
        editor=SimpleNamespace(mark_dirty=lambda: None))
    engine = SimpleNamespace()
    monkeypatch.setattr(L, '_verify', lambda *args: None)
    calls = []
    monkeypatch.setattr(L, '_publish', lambda *args: calls.append(args))
    invalid = {**deepcopy(h.entry[H.KEY]), 'document_ids': ['document-a']}
    with pytest.raises(ValueError, match='two to sixteen'):
        L.commit_scoped(owner, engine, h.forward, request_id='request-one',
            prepare=False, prepared_targets=h.entry['targets'], alias_history=invalid)
    assert calls == [] and owner.ledger == {}
    batch_id, frame = L.commit_scoped(owner, engine, h.forward, request_id='request-two',
        prepare=False, prepared_targets=h.entry['targets'], alias_history=h.entry[H.KEY])
    assert len(calls) == 1 and frame is None
    assert owner.ledger[batch_id][H.KEY] == h.entry[H.KEY]
    assert engine._people_shared_mutation is True


def test_publication_failure_never_records_unmarked_alias_entry(fixture, monkeypatch):
    h = fixture
    owner = SimpleNamespace(ledger={}, sequence=0, clock=lambda: 1., monotonic=lambda: 1,
        documents=SimpleNamespace(remember_current=lambda: None),
        editor=SimpleNamespace(mark_dirty=lambda: None))
    monkeypatch.setattr(L, '_verify', lambda *args: None)
    def fail(*args):
        raise ValueError('Canonical publication rolled back')
    monkeypatch.setattr(L, '_publish', fail)
    with pytest.raises(ValueError, match='rolled back'):
        L.commit_scoped(owner, SimpleNamespace(), h.forward, request_id='request-one',
            prepare=False, prepared_targets=h.entry['targets'], alias_history=h.entry[H.KEY])
    assert owner.ledger == {}


def test_restore_rechecks_members_after_expensive_preparation(fixture, monkeypatch):
    """A later alias cannot be silently added between prepare and publication."""
    from lumaretouch_engine import face_style_alias_review as ALIAS
    h = fixture
    rows = [{'document_id': target['document_id'], 'path': target['path']}
            for target in h.entry['targets'].values()]
    owner = SimpleNamespace(versions=SimpleNamespace(find=lambda docs, identity:
        next(((index, row) for index, row in enumerate(docs)
              if row['document_id'] == identity), None)))
    engine = SimpleNamespace(_docs=rows, _batch_controller=lambda: owner)
    monkeypatch.setattr(L.V, 'scope', lambda row: 'project')
    monkeypatch.setattr(L.V, 'row_snapshot', lambda engine, row: deepcopy(h.candidate))
    monkeypatch.setattr(L.SOURCE, 'verify_row_target', lambda *args: None)
    monkeypatch.setattr(L, 'verify_reviewed_refs', lambda *args: None)
    monkeypatch.setattr(ALIAS, 'verify_dormant', lambda *args: None)
    targets = deepcopy(h.entry['targets'])
    monkeypatch.setattr(L, '_targets', lambda *args: deepcopy(targets))
    def prepare(*args):
        targets['2'] = {**deepcopy(targets['0']), 'document_id': 'late-alias'}
    monkeypatch.setattr(L, 'prepare_scoped', prepare)
    published = []
    monkeypatch.setattr(L, '_publish', lambda *args: published.append(args))
    with pytest.raises(ValueError, match='exact reviewed members'):
        L.restore_scoped(engine, h.entry, False)
    assert published == []


def test_readonly_status_classifies_restored_alias_without_inventing_mutation_consent(fixture):
    from lumaretouch_engine.batch_sync import BatchSyncController
    before = deepcopy(fixture.entry)
    owner = SimpleNamespace(ledger={'restored-alias': fixture.entry},
                            versions=SimpleNamespace(workspace='workspace-reopened'))
    status = BatchSyncController.summary(owner)
    assert status['workspace_generation'] == 'workspace-reopened'
    assert status['batches'] == [{'batch_id': 'restored-alias', 'module_scope': [L.OP],
        'targets': 2, 'undone': False, 'face_style_alias_review': {
            'version': 1, 'review_sha256': REVIEW, 'member_count': 2}}]
    assert fixture.entry == before and status['last'] == 'restored-alias'
    assert H.status_summary({}) is None
    malformed = deepcopy(fixture.entry)
    malformed[H.KEY]['document_ids'].append('unreviewed')
    with pytest.raises(ValueError): H.status_summary(malformed)
