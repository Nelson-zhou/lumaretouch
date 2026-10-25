"""Authored, NOT executed: retained scalar preset handoff contracts.

These fixtures cover ownership, codec scope and failure/readback boundaries.
They do not establish image quality, GPU/native behavior or end-to-end acceptance.
"""
from contextlib import nullcontext
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import pytest

from lumaretouch_engine import workflow_preset_handoff as H
from lumaretouch_engine import workflow_preset_review as R
from lumaretouch_engine import workflow_preset_save as SAVE
from lumaretouch_engine import project as PJ
from lumaretouch_engine import preset_store as PS, preset_organisation_store as PO
from lumaretouch_engine import optics_candidate_identity as ID


def fingerprint(path, data=b'original-managed-bytes'):
    digest = sha256(data).hexdigest()
    return {'path': str(path), 'bytes': len(data), 'sha256': digest,
            'head_sha256': digest, 'hash_level': 'full', 'mtime_ns': 10, 'readonly': True}


def source_row(path, data=b'original-managed-bytes'):
    fp = fingerprint(path, data)
    return {'path': str(path), 'fingerprint': fp,
            'managed_import': {'mode': 'copy', 'content_sha256': fp['sha256']}}, {
                'source_sha256': fp['sha256']}


def test_actual_source_rejects_substituted_bytes_despite_matching_metadata(tmp_path):
    path = tmp_path / 'managed.jpg'
    row, document = source_row(path)
    path.write_bytes(b'original-managed-bytes')
    first = H._source_file(row, document)
    assert first['sha256'] == document['source_sha256']
    path.write_bytes(b'substituted-file-bytes')
    with pytest.raises(ValueError, match='differ|changed'):
        H._source_file(row, document)


def test_source_rejects_symlink_and_detects_same_content_replacement(tmp_path):
    path = tmp_path / 'managed.jpg'
    row, document = source_row(path)
    path.write_bytes(b'original-managed-bytes')
    first = H._source_file(row, document)
    old = tmp_path / 'old.jpg'
    path.rename(old)
    path.write_bytes(b'original-managed-bytes')
    assert H._source_file(row, document) != first  # Physical owner changed, even with equal pixels.
    path.unlink()
    path.symlink_to(old)
    with pytest.raises((ValueError, OSError)):
        H._source_file(row, document)


def recipe(ev=0.):
    from lumaretouch_engine import manual_liquify_state as ML, studio_background_state as SB
    from lumaretouch_engine import optics_state as OP, sky_replacement_state as SK
    from lumaretouch_engine import fringe_repair_state as FR, white_balance_recipe as WB
    return {'_manual_liquify': ML.empty(), '_studio_background': SB.empty(),
            '_optics': OP.empty(), '_sky_replacement': SK.empty(), '_fringe_repair': FR.neutral(),
            '_exposure': (ev, 0., 0., 0., 0., 0., 0.), '_wb_options': WB.default_options(),
            '_exposure_ref_k': 6500., '_precompute': None, '_proxy': None}


def saved_project(tmp_path):
    project = PJ.new_project('Scoped preset fixture', str(tmp_path))
    other_path, target_path = tmp_path / 'original.jpg', tmp_path / 'target.jpg'
    other = PJ.add_doc(project, str(other_path), None, fp=fingerprint(other_path), version_id='other-live')
    target = PJ.add_doc(project, str(target_path), recipe(), fp=fingerprint(target_path), version_id='target-live')
    PJ.add_doc(project, str(target_path), None, fp=fingerprint(target_path),
               document_id=target['document_id'], version_id='retained-named-version')
    target['active_version'] = 'target-live'
    project['active_document_id'] = other['document_id']
    project['tasks'] = [{'task_id': 'already-retained', 'state': 'paused'}]
    project['managed_import_receipts'] = {}
    PJ.encode(b'retained-old-asset', project['assets'], [], 'fixture')
    project = PJ._migrate(project)
    runtime = {**deepcopy(target), 'state': recipe(0.5), 'document_revision': 1,
               'undo': [recipe()], 'redo': [], 'budget': 640 * 480}
    return project, runtime, other['document_id']


def test_scoped_codec_preserves_other_rows_named_versions_assets_and_selection(tmp_path):
    saved, target, other_id = saved_project(tmp_path)
    original = deepcopy(saved)
    result = H._scoped_project(saved, target)
    assert saved == original
    assert next(doc for doc in result['docs'] if doc['document_id'] == other_id) == next(
        doc for doc in original['docs'] if doc['document_id'] == other_id)
    assert result['source_assets'] == original['source_assets']
    assert result['active_document_id'] == original['active_document_id']
    assert result['tasks'] == original['tasks']
    assert all(result['assets'][key] == value for key, value in original['assets'].items())
    stored = next(doc for doc in result['docs'] if doc['document_id'] == target['document_id'])
    before = next(doc for doc in original['docs'] if doc['document_id'] == target['document_id'])
    assert next(v for v in stored['versions'] if v['id'] == 'retained-named-version') == next(
        v for v in before['versions'] if v['id'] == 'retained-named-version')
    assert stored['document_revision'] == 1 and stored['budget'] == target['budget']
    assert next(v for v in stored['versions'] if v['id'] == 'target-live')['recipe']['_exposure'][0] == 0.5
    assert stored['document_history']['undo'] and not stored['document_history']['redo']


def test_scoped_codec_refuses_hidden_migration_or_source_registration_change(tmp_path, monkeypatch):
    saved, target, _ = saved_project(tmp_path)
    migrate = PJ._migrate
    def changed(value):
        result = migrate(value)
        result['docs'][0]['label'] = 'unexpected-migration'
        return result
    monkeypatch.setattr(PJ, '_migrate', changed)
    with pytest.raises(ValueError, match='canonical'):
        H._scoped_project(saved, target)
    monkeypatch.setattr(PJ, '_migrate', migrate)
    target['fingerprint']['mtime_ns'] = 999
    with pytest.raises(ValueError, match='source registration'):
        H._scoped_project(saved, target)


def handoff():
    engine = SimpleNamespace()
    owner = SimpleNamespace(engine=engine,
        _result=lambda request, **fields: deepcopy(fields),
        _receipt=lambda command, result: {'identity': deepcopy(command['identity']), 'result': result})
    return H.PresetHandoff(owner)


def public_entry(phase='authorized'):
    return {'version': 1, 'operation_id': 'preflight-operation', 'document_id': 'stable-document',
        'preset_id': 'color-warm', 'preset_sha256': 'a' * 64, 'phase': phase,
        'review': None, 'message': 'Fixture only', 'session_id': 'session', 'step_effect_started': False}


def test_expired_approval_is_correlated_to_admitted_apply_before_consumption(monkeypatch):
    value = handoff()
    document, assessment = {'document_id': 'stable-document'}, {'review': 'owned'}
    value.active = {**public_entry(), 'assessment': assessment, 'initial_document': document,
        'preflight': {'command': {'identity': {'input_occurrence_id': 'occurrence'}}},
        'target': {'document_id': 'stable-document', 'load_id': 'transient-load', 'revision': '0'},
        'approval': {'approval_id': 'exact-approval'}}
    record = {'command': {'identity': {'operation_id': 'apply-operation', 'input_occurrence_id': 'occurrence'},
        'operation': {'assessment': assessment, 'preset_id': 'color-warm', 'document': document}},
        'dispatch_started': False}
    monkeypatch.setattr(value, '_check', lambda **kwargs: None)
    monkeypatch.setattr(PO, 'catalogue_lock', lambda _: nullcontext())
    monkeypatch.setattr(PS, 'preset_dir', lambda: '/unused')
    def expired(*args):
        assert value.active['operation_id'] == 'apply-operation'
        raise ValueError('Exact approval expired')
    monkeypatch.setattr(value.reviews, 'consume', expired)
    monkeypatch.setattr(H, 'dispatch', lambda *args: pytest.fail('Expired approval must never dispatch'))
    with pytest.raises(ValueError, match='expired'):
        value.apply(record)
    assert value.active['apply'] is record and not record['dispatch_started']


def test_stale_step_is_definitive_no_dispatch_and_does_not_poison_handoff(monkeypatch):
    value = handoff()
    value.active = public_entry('reviewing')
    monkeypatch.setattr(value, '_check', lambda **kwargs: pytest.fail('Stale phase must reject first'))
    request = {'request_id': 'new-click', 'session_id': 'session', 'operation_id': 'preflight-operation',
               'step': 'open_target', 'payload': {}}
    result = value.step(request)
    assert result['status'] == 'failed' and result['dispatch_rejected'] is True
    assert value.active['phase'] == 'reviewing'
    assert value.step(request) == result


@pytest.mark.parametrize('changed', ['state', 'source', 'people', 'repair', 'snapshot'])
def test_actual_candidate_verification_covers_all_complete_render_inputs(monkeypatch, changed):
    value = handoff()
    state, row, people_owner, context = {'scalar': 0.5}, {}, object(), {}
    source = {'original_sha256': 'b' * 64}
    state_hash = ID.fingerprint(state)
    review = {'source_proof': source, 'candidate_state_sha256': state_hash, 'people_sha256': 'c' * 64,
              'repair_sha256': 'd' * 64, 'candidate_render_sha256': 'e' * 64}
    proof = {'render': {'source_proof': deepcopy(source), 'candidate_sha256': state_hash,
                       'people_sha256': 'c' * 64}, 'repair_sha256': 'd' * 64, 'snapshot_sha256': 'e' * 64}
    value.active = {'target': {}, 'review': review, 'people_owner': people_owner, 'people_context': context}
    value.engine._people_graph_owner = people_owner
    value.engine._people_active_context = context
    value.engine._people_preset_capture = lambda: deepcopy(state)
    monkeypatch.setattr(value, '_check', lambda **kwargs: (None, row))
    monkeypatch.setattr(value, '_verify_review_source', lambda _: None)
    monkeypatch.setattr(R, '_proof', lambda *args: (deepcopy(proof), {}))
    value._verify_applied()
    if changed == 'state': proof['render']['candidate_sha256'] = 'f' * 64
    elif changed == 'source': proof['render']['source_proof']['original_sha256'] = 'f' * 64
    elif changed == 'people': proof['render']['people_sha256'] = 'f' * 64
    elif changed == 'repair': proof['repair_sha256'] = 'f' * 64
    else: proof['snapshot_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='differs'):
        value._verify_applied()


def test_unknown_save_remains_retained_and_same_step_never_persists_twice(monkeypatch):
    value = handoff()
    row = {}
    value.active = {**public_entry('awaiting_save'), 'row': row, 'saved_project': {},
                    'binding': {'path': '/saved.lrt', 'disk_sha256': 'a' * 64}}
    value.engine._remember_current = lambda: None
    monkeypatch.setattr(value, '_check', lambda **kwargs: (None, row))
    monkeypatch.setattr(value, '_verify_applied', lambda: None)
    monkeypatch.setattr(H, '_scoped_project', lambda *args: {})
    calls = []
    def uncertain(*args):
        calls.append(args)
        return {'status': 'unknown', 'requires_readback': True, 'expected_sha256': 'b' * 64}
    monkeypatch.setattr(SAVE, 'persist', uncertain)
    request = {'request_id': 'save-once', 'session_id': 'session', 'operation_id': 'preflight-operation',
               'step': 'save_project', 'payload': {}}
    result = value.step(request)
    assert result['status'] == 'unknown' and value.active['phase'] == 'unknown'
    assert value.step(request) == result and len(calls) == 1
    fresh = value.step({**request, 'request_id': 'never-retry'})
    assert fresh['status'] == 'failed' and len(calls) == 1


def test_precommit_cas_loss_is_not_reported_as_success_or_uncertain_replacement(monkeypatch):
    value = handoff()
    value.active = {**public_entry('awaiting_save'), 'row': {}, 'saved_project': {},
                    'binding': {'path': '/saved.lrt', 'disk_sha256': 'a' * 64}}
    value.engine._remember_current = lambda: None
    monkeypatch.setattr(value, '_check', lambda **kwargs: (None, {}))
    monkeypatch.setattr(value, '_verify_applied', lambda: None)
    monkeypatch.setattr(H, '_scoped_project', lambda *args: {})
    def refused(*args):
        raise ValueError('Saved project CAS changed before replacement')
    monkeypatch.setattr(SAVE, 'persist', refused)
    result = value.step({'request_id': 'cas-loss', 'session_id': 'session',
        'operation_id': 'preflight-operation', 'step': 'save_project', 'payload': {}})
    assert result['status'] == 'failed' and result['dispatch_rejected'] is True
    assert value.active['phase'] == 'awaiting_save' and 'save_outcome' not in value.active


def test_successful_save_publishes_stamped_hydrated_body_and_still_awaits_return(monkeypatch):
    from lumaretouch_engine import creative_document_storage as CS
    value = handoff()
    value.active = {**public_entry('awaiting_save'), 'row': {}, 'saved_project': {},
                    'binding': {'path': '/saved.lrt', 'disk_sha256': 'a' * 64}}
    value.engine._remember_current = lambda: None
    value.engine._project_dirty = True
    value.engine._ingest_session_host = SimpleNamespace(_binding=lambda: {
        'path': '/saved.lrt', 'disk_sha256': value.engine._project_disk_sha256})
    monkeypatch.setattr(value, '_verify_applied', lambda: None)
    monkeypatch.setattr(H, '_scoped_project', lambda *args: {'unprepared': True})
    stamped = {'assets': {}, 'updated_ns': 123456, 'writer': {'engine': 'actual-codec-stamp'}}
    stamped['payload'] = CS.encode_bytes(b'full-precision-immutable-creative-bytes', stamped['assets'])
    packed, blobs = CS.pack(stamped)
    monkeypatch.setattr(CS, 'read_blobs', lambda body, path: deepcopy(blobs))
    monkeypatch.setattr(SAVE, 'persist', lambda *args: {
        'status': 'succeeded', 'project': packed, 'sha256': 'b' * 64, 'updated_ns': 123456})
    monkeypatch.setattr(H, 'dispatch', lambda *args: pytest.fail('Save must not automatically return or export'))
    value._save()
    assert value.engine._project == stamped and value.engine._project != packed
    assert value.engine._project_saved_ns == 123456 and value.engine._project_disk_sha256 == 'b' * 64
    assert value.engine._project_dirty is False and value.active['phase'] == 'awaiting_return'
    assert value.active['save_outcome']['project'] == packed


def test_review_proof_cannot_replace_the_durable_import_source():
    value = handoff()
    value.active = {'initial_document': {'source_sha256': 'a' * 64}}
    with pytest.raises(ValueError, match='durable imported bytes'):
        value._verify_review_source({'asset_sha256': 'b' * 64,
            'original_sha256': 'b' * 64, 'creative_source': None})
