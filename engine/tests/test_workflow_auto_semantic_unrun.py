# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic contracts, never photographic acceptance.

No fixture, model, renderer or runtime was executed during source development.
Qoder owns full inference/history/save/reopen/export and interruption acceptance.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest

from lumaretouch_engine import workflow_auto_semantic as A
from lumaretouch_engine import workflow_semantic_archive as F
from lumaretouch_engine import workflow_owner_protocol as P
from lumaretouch_engine import semantic_colour_portable as I
from lumaretouch_engine import semantic_colour_state as S


def archive_metadata():
    intent = I.check({'version': 1, 'algorithm': S.ALGORITHM,
        'reference': {'source': {'sha256': 'a'*64, 'width': 64, 'height': 64},
                      'asset_id': 'b'*64, 'render_sha256': 'c'*64},
        'enabled': True, 'mode': 'harmonious', 'strengths': [100, 80, 90],
        'offset_policy': I.OFFSET_POLICY, 'class_policy': I.CLASS_POLICY,
        'groups': [{'id': 'global', 'enabled': True, 'offsets': [0]*50},
                   {'id': 'face_skin', 'enabled': False, 'offsets': [0]*50}]})
    return F.metadata({'path': '/fixture/selected.lrtcolour', 'file_bytes': 8192,
        'file_sha256': 'd'*64, 'intent_sha256': P.digest(intent),
        'portable_intent_json': P.encoded(intent, sorted_keys=True).decode()})


def test_exact_semantic_intent_does_not_enter_generic_preset_or_mixed_scopes():
    from lumaretouch_engine.workflow_auto_preset import support_reason
    value = {**P.AUTOMATIC_INTENT, 'reference_source_policy': 'reject_same_source',
             'semantic_scope': 'global_six_class_per_target_fit', 'semantic_archive': archive_metadata()}
    assert P.automatic_intent(value) == value
    assert support_reason({'modules': {'lnx.exposure.v1': {'ev': .2}}}, value) == 'automatic_semantic_requires_dedicated_archive_owner'
    for extra in ({'portrait_scope': 'all_verified_detected_faces'},
                  {'reference_scope': 'stored_reference_per_target_fit'}, {'reviewed': True},
                  {'semantic_scope': 'local_masks'}, {'reference_source_policy': 'silently_omit'}):
        with pytest.raises(ValueError): P.automatic_intent({**value, **extra})


def test_complete_portable_intent_keeps_canonical_numeric_bytes():
    value = archive_metadata()
    assert sha256(value['portable_intent_json'].encode()).hexdigest() == value['intent_sha256']
    changed = deepcopy(value)
    changed['portable_intent_json'] = value['portable_intent_json'].replace('100.0', '100')
    # JSON numeric equality is NOT exact byte equality in the frozen graph.
    assert json.loads(changed['portable_intent_json']) == json.loads(value['portable_intent_json'])
    with pytest.raises(ValueError): F.metadata(changed)
    for extra in ({'file_bytes': True}, {'file_bytes': F.E.MAX_FILE_BYTES + 1},
                  {'path': '/fixture/ref.json'}, {'intent_sha256': '0'*64}, {'extra': 'refit'}):
        with pytest.raises(ValueError): F.metadata({**value, **extra})


def target_fixture(monkeypatch):
    row = {'document_id': 'target', 'state': {'own': 'target'}, 'undo': [], 'redo': [], 'path': '/own'}
    history = []
    engine = SimpleNamespace(_capture_state=lambda: row['state'], _docs=[row], _doc_index=0, _load_id='load',
        _history_capture=lambda: {'before': True}, _history_record=lambda *args, **kwargs: history.append((args, kwargs)))
    plan = object.__new__(A.TargetSemanticPlan)
    plan.engine, plan.row, plan.load_id = engine, row, 'load'
    plan.batch = SimpleNamespace(emit=lambda frame: None)
    plan.archive = SimpleNamespace(intent=json.loads(archive_metadata()['portable_intent_json']),
        metadata=archive_metadata(), bundle=[SimpleNamespace(size=8)], reference_analysis=lambda: {'proof': 'cache'})
    plan.authority = {'schema': 'lrt.automatic-semantic-assessment.v1', 'graph_sha256': 'e'*64,
        'operation_id': 'f'*64, 'archive_sha256': 'd'*64, 'reviewed': False}
    plan._record = plan._assessment = plan._after = None
    plan._fit_started = plan._committed = False
    plan._baseline = plan._live_baseline = A.fingerprint(row['state'])
    plan._history = A.fingerprint(([], [])); plan._people = A.fingerprint({})
    monkeypatch.setattr(A, 'people_context', lambda *args: {})
    plan._row = lambda target: (0, row)
    evidence = {'before': {'own': 'before'}, 'after': {'own': 'after'}}
    plan._inputs = lambda target: (deepcopy(evidence), {})
    from lumaretouch_engine import local_mask_state as LM, cpu_memory_budget as M, full_candidate_render as R
    monkeypatch.setattr(LM, 'source_digest', lambda path: '9'*64)
    monkeypatch.setattr(M, 'available_estimate', lambda: 8*1024**3)
    monkeypatch.setattr(R, 'render', lambda *args, **kwargs: None)
    calls = []
    def prepare(*args, **kwargs):
        calls.append(args[3]); assert kwargs == {'preview': False}
        return {'reference_analysis_proof': 'cache', 'proof': 'own-frozen-fit'}
    monkeypatch.setattr(A.T, 'prepare', prepare)
    monkeypatch.setattr(A.T, 'install', lambda state, record, bundle, **kwargs: {**state, 'fit': record['proof']})
    return plan, {'document_id': 'target', 'load_id': 'load', 'revision': '4'}, calls, history


def test_one_target_fit_then_verify_only_commit_and_no_review_token(monkeypatch):
    from lumaretouch_engine import semantic_colour_batch_ledger as L
    plan, target, calls, history = target_fixture(monkeypatch)
    evidence = plan.assess(target)
    assert plan.assess(target) == evidence
    published = []
    def publish(owner, planned, **kwargs):
        assert plan._committed and owner is plan.batch
        assert kwargs['review_token'] is None and kwargs['automatic_authority']['reviewed'] is False
        published.append(planned)
        return 'canonical-batch', None
    monkeypatch.setattr(L, 'publish', publish)
    assert plan.commit(target, 'request', evidence)['success']
    assert calls == ['target'] and len(published) == 1 and len(history) == 1
    with pytest.raises(ValueError): plan.commit(target, 'request', evidence)


def test_failed_fit_cannot_be_repeated_and_rollback_proof_is_required(monkeypatch):
    plan, target, _, _ = target_fixture(monkeypatch)
    def rejected(*args, **kwargs): raise ValueError('missing requested class')
    monkeypatch.setattr(A.T, 'prepare', rejected)
    with pytest.raises(ValueError, match='missing requested'): plan.assess(target)
    plan.assert_unchanged()
    with pytest.raises(ValueError, match='never refit'): plan.assess(target)
    plan.row['state']['foreign'] = True
    with pytest.raises(ValueError, match='no exact no-effect proof'): plan.assert_unchanged()


def test_same_reference_source_refused_before_analysis(monkeypatch):
    from lumaretouch_engine import local_mask_state as LM
    plan, target, calls, _ = target_fixture(monkeypatch)
    monkeypatch.setattr(LM, 'source_digest', lambda path: 'a'*64)
    with pytest.raises(ValueError, match='same_source_rejected'): plan.assess(target)
    assert calls == [] and not plan._fit_started


def test_lost_publication_keeps_claim_and_records_history_without_retry(monkeypatch):
    from lumaretouch_engine import semantic_colour_batch_ledger as L
    plan, target, _, history = target_fixture(monkeypatch)
    evidence = plan.assess(target)
    def lost(*args, **kwargs): raise OSError('publication result lost')
    monkeypatch.setattr(L, 'publish', lost)
    with pytest.raises(OSError): plan.commit(target, 'request', evidence)
    assert plan._committed and len(history) == 1
    with pytest.raises(ValueError): plan.assert_unchanged()
    with pytest.raises(ValueError): plan.commit(target, 'another-request', evidence)


def test_reference_analysis_is_one_attempt_and_is_not_a_target_cache(monkeypatch):
    from lumaretouch_engine import semantic_colour_batch_fit as B
    archive = object.__new__(F.FrozenArchive)
    archive.path = None; archive._cache = None; archive._analysis_started = False
    archive.intent = {'reference': {'owned': True}}; archive.bundle = []
    archive.assert_current = lambda: None
    calls = []
    monkeypatch.setattr(A.T, 'reference_analysis', lambda intent, bundle: calls.append(True) or {'reference': {'owned': True}, 'proof': 'exact'})
    monkeypatch.setattr(B, 'check_reference', deepcopy)
    assert archive.reference_analysis() == archive.reference_analysis()
    assert calls == [True]
    archive._cache = None
    with pytest.raises(ValueError, match='never silently rerun'): archive.reference_analysis()


def test_machine_authority_is_not_a_view_ack_or_portable_review(monkeypatch):
    from lumaretouch_engine import semantic_colour_review as R
    from test_semantic_colour_portable import recipe
    authority = {'schema': 'lrt.automatic-semantic-assessment.v1', 'graph_sha256': 'e'*64,
        'operation_id': 'f'*64, 'archive_sha256': 'd'*64, 'reviewed': False}
    assert R.automatic_authority(authority)['reviewed'] is False
    for changed in ({'reviewed': True}, {'accepted': True}, {'review_id': 'fake'}):
        with pytest.raises(ValueError): R.automatic_authority({**authority, **changed})
    state = recipe(); state['last_review']['authorization'] = authority
    assert S.check(state)['last_review']['authorization'] == authority
    with pytest.raises(ValueError): I.extract(state)


def test_archive_freezes_selected_bytes_and_refuses_changed_expected(monkeypatch, tmp_path):
    from lumaretouch_engine import cpu_memory_budget as M
    source = tmp_path / 'selected.lrtcolour'
    source.write_bytes(b'fixture opaque bytes, not authentic pixels')
    intent = json.loads(archive_metadata()['portable_intent_json'])
    monkeypatch.setattr(M, 'available_estimate', lambda: 8*1024**3)
    # Byte-retention fixture only; real archive/NPZ authentication is separately
    # covered by the existing portable-preset fixtures and required local QA.
    monkeypatch.setattr(F.E, 'load_file', lambda path: {'intent': intent, 'chunks': []})
    monkeypatch.setattr(F.E, 'hydrate', lambda envelope: intent)
    monkeypatch.setattr(F.FrozenArchive, 'assert_current', lambda self: None)
    frozen = F.FrozenArchive(str(source))
    try:
        original = source.read_bytes()
        source.write_bytes(b'replaced after selection')
        assert F.E._file_identity(frozen.path)['file_sha256'] == sha256(original).hexdigest()
        with pytest.raises(ValueError, match='changed; reselect'):
            F.FrozenArchive(str(source), frozen.metadata)
    finally:
        private = frozen.path
        frozen.close()
    from pathlib import Path
    assert not Path(private).exists()
