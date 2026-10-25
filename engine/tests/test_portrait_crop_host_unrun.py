# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN portrait-crop ownership/review/receipt fixtures.

All imagery, source/model hashes and detector-tagged rows below are synthetic
contract doubles, NOT detector output, photographic acceptance, renderer parity,
real canonical history, UI proof, performance evidence or package acceptance.
No product imports, collection, tests, inference, build or typecheck ran while
these fixtures were authored. Real-photo/rotation/repair/history coverage remains
an explicit release prerequisite even if these fixtures later pass.
"""
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from lumaretouch_engine import portrait_crop_controller as J
from lumaretouch_engine import portrait_crop_capture as C
from lumaretouch_engine import portrait_crop_host as H
from lumaretouch_engine import portrait_crop_project as P
from lumaretouch_engine import portrait_crop_review as R
from lumaretouch_engine.optics_candidate_identity import fingerprint

A, B, D = 'a' * 64, 'b' * 64, 'd' * 64


def request(action, ident='request-1', **fields):
    return {'cmd': 'portrait_crop', 'action': action, 'request_id': ident, **fields}


def test_exact_command_identity_rejects_nonfinite_and_unknown_envelope():
    with pytest.raises(ValueError):
        J.command_hash(request('preview', value=float('nan')))
    with pytest.raises(ValueError):
        H._validate(request('current', path='/another/photo'))
    with pytest.raises(ValueError):
        H._validate(request('apply', reviewed=True))
    with pytest.raises(ValueError):
        H._validate(request('current', ident='request with spaces'))


def test_hash_and_echo_keep_original_numeric_request_not_solver_coercion():
    value = request('preview', anchors={'crown': [1, 0.000001]}, other=True)
    sha = J.command_hash(value)
    event = H._event(value, sha, 'working', no_write=True)
    value['anchors']['crown'][0] = 99
    assert event['original_request']['anchors']['crown'] == [1, .000001]
    assert event['command_sha256'] == sha
    assert J.command_hash(event['original_request']) == sha


@pytest.mark.parametrize('rotation', (.001, -.001, .49, .5, 90, -90, 180, float('nan'), True, None))
def test_every_nonzero_rotation_or_invalid_value_is_refused_without_snap(rotation):
    state = {'_crop_rotation': rotation, '_crop_rect': (.1, .2, .9, .8)}
    before = deepcopy(state)
    assert not C.rotation_supported(state)
    assert state.keys() == before.keys() and state['_crop_rect'] == before['_crop_rect']


@pytest.mark.parametrize('rotation', (0, 0., -0.))
def test_exact_zero_rotation_is_only_supported_domain(rotation):
    assert C.rotation_supported({'_crop_rotation': rotation})


def test_non_crop_hash_keeps_repairs_geometry_optics_and_original_identity():
    state = {'_crop_rect': (0., 0., 1., 1.), '_crop_rotation': 0.,
             '_repair_ops': ['synthetic-retained-repair'], '_manual_liquify': {'v': 3},
             '_optics': {'profile': 'fixture'}, '_creative_base': {'id': 'immutable-fixture'}}
    other = deepcopy(state)
    other['_crop_rect'] = (.2, .2, .8, .9)
    assert P.non_crop_hash(state) == P.non_crop_hash(other)
    for key in ('_repair_ops', '_manual_liquify', '_optics', '_creative_base'):
        bad = deepcopy(other)
        bad[key] = None
        assert P.non_crop_hash(bad) != P.non_crop_hash(state)


def test_reader_cancel_is_exact_and_reports_only_actual_unwind():
    jobs = J.Jobs()
    value = request('current')
    sha = J.command_hash(value)
    assert jobs.ingress(json.dumps(value)) is False
    assert jobs.ingress(json.dumps({'cmd': 'portrait_crop_cancel', 'request_id': value['request_id'], 'command_sha256': B})) is False
    called = []
    assert jobs.request_cancel(value['request_id'], sha)
    with pytest.raises(InterruptedError):
        jobs.run(value, lambda stopped: called.append('not reached'))
    assert called == []
    with pytest.raises(ValueError):
        jobs.run(value, lambda stopped: None)


def test_apply_is_never_registered_or_cancelled_by_reader_ingress():
    jobs = J.Jobs()
    assert jobs.ingress(json.dumps(request('apply'))) is False
    assert jobs.events == {}
    assert jobs.ingress(json.dumps({'cmd': 'portrait_crop_cancel', 'request_id': 'x', 'command_sha256': 'bad'})) is False


def test_cancel_during_read_discards_complete_but_unpublished_result():
    jobs = J.Jobs()
    value = request('current')
    def work(stopped):
        jobs.request_cancel(value['request_id'], J.command_hash(value))
        return 'never published'
    with pytest.raises(InterruptedError):
        jobs.run(value, work)


def test_controller_rejects_same_request_id_different_read_content():
    jobs = J.Jobs()
    first = request('current')
    jobs.register(first['request_id'], J.command_hash(first))
    with pytest.raises(ValueError):
        jobs.register(first['request_id'], B)


class CaptureDouble:
    def __init__(self, state):
        self.state = deepcopy(state)
        self.capture_sha256 = A
        self.row = {'path': '/synthetic-fixture-never-opened', 'document_id': 'document-1'}
        self.binding = {'document_id': 'document-1', 'revision': '7',
                        'original_sha256': D, 'non_crop_sha256': P.non_crop_hash(state)}
        self.invalid = False

    def stale(self, engine):
        return False  # Keep the explicit verify refusal distinct from lazy expiry.

    def verify(self, engine, cancelled=lambda: False):
        if self.invalid or cancelled():
            raise ValueError('Synthetic edited-source proof became stale')


def service_fixture(monkeypatch, *, commit_error=False, corrupt_non_crop=False):
    state = {'_crop_rect': (0., 0., 1., 1.), '_crop_rotation': -0.,
             '_repair_ops': ['retained-repair-fixture'], '_optics': {'profile': 'synthetic'},
             '_manual_liquify': {'field': 'synthetic'}}
    holder = {'state': deepcopy(state), 'revision': 7, 'writes': 0}
    row = {'path': '/synthetic-fixture-never-opened', 'document_id': 'document-1'}
    versions = SimpleNamespace(version=lambda value: SimpleNamespace(document_id='document-1', revision=holder['revision']))
    engine = SimpleNamespace(_docs=[row], _doc_index=0,
                             _capture_state=lambda: deepcopy(holder['state']),
                             _document_versions=lambda: versions)
    events = []
    host = H.Service(engine, events.append)
    monkeypatch.setattr(host, '_guard', lambda: None)
    host.capture = CaptureDouble(state)
    host.session_id = 'session-1'
    host.deadline = float('inf')
    host.candidate_deadline = float('inf')
    candidate = deepcopy(state)
    candidate['_crop_rect'] = (.1, .2, .8, .9)
    preview = {'capture_sha256': A, 'preview_request_id': 'preview-1', 'preview_token': 'token-1',
               'candidate_sha256': fingerprint(candidate), 'before': {'sha256': A}, 'after': {'sha256': B}}
    host.candidate = R.Candidate(candidate, {'synthetic_contract_double': True}, preview)
    monkeypatch.setattr(P, 'verify_commit', lambda *args: None)
    monkeypatch.setattr(C, 'file_hash', lambda *args, **kwargs: D)
    def commit(*args, **kwargs):
        holder['writes'] += 1
        holder['state'] = deepcopy(candidate)
        holder['revision'] += 1
        if corrupt_non_crop:
            holder['state']['_repair_ops'] = []
        if commit_error:
            raise RuntimeError('Synthetic transport failed after mutation')
        return {'status': 'applied', 'document_id': 'document-1', 'revision': str(holder['revision'])}
    monkeypatch.setattr(P, 'commit', commit)
    apply = request('apply', 'apply-1', session_id='session-1', capture_sha256=A,
                    preview_request_id='preview-1', preview_token='token-1',
                    candidate_sha256=preview['candidate_sha256'], before_image_sha256=A,
                    after_image_sha256=B, review='full_before_after_confirmed')
    return host, engine, holder, events, apply


def test_one_apply_calls_only_canonical_port_and_exact_duplicate_returns_receipt(monkeypatch):
    host, engine, holder, events, apply = service_fixture(monkeypatch)
    host.handle(apply)
    assert events[-1]['phase'] == 'committed'
    assert events[-1]['original_request'] == apply
    assert holder['writes'] == 1 and holder['state']['_repair_ops'] == ['retained-repair-fixture']
    terminal = deepcopy(events[-1])
    host.handle(deepcopy(apply))
    assert events[-1] == terminal and holder['writes'] == 1
    assert host.capture is None and host.candidate is None


@pytest.mark.parametrize('field,value', [('preview_token', 'other-token'), ('preview_request_id', 'other-preview'),
                                        ('capture_sha256', B), ('before_image_sha256', B),
                                        ('after_image_sha256', A), ('candidate_sha256', D)])
def test_forged_or_stale_full_review_never_enters_write(monkeypatch, field, value):
    host, engine, holder, events, apply = service_fixture(monkeypatch)
    apply[field] = value
    host.handle(apply)
    assert events[-1]['phase'] == 'rejected' and events[-1]['no_write'] is True
    assert holder['writes'] == 0


def test_changed_capture_analysis_or_repair_state_rejects_before_publication(monkeypatch):
    host, engine, holder, events, apply = service_fixture(monkeypatch)
    host.capture.invalid = True
    host.handle(apply)
    assert events[-1]['phase'] == 'rejected' and holder['writes'] == 0


def test_unknown_commit_cannot_be_cancelled_retried_or_forgotten(monkeypatch):
    host, engine, holder, events, apply = service_fixture(monkeypatch, commit_error=True)
    host.handle(apply)
    assert events[-1]['phase'] == 'unknown' and 'no_write' not in events[-1]
    assert holder['writes'] == 1 and host.uncertain is not None
    host.handle(deepcopy(apply))
    assert events[-1]['phase'] == 'unknown' and holder['writes'] == 1
    # Restore the real uncertainty guard instead of the admission double.
    monkeypatch.setattr(host, '_guard', lambda: H.Service._guard(host))
    host.handle(request('cancel', 'cancel-1', session_id='session-1'))
    assert events[-1]['phase'] == 'rejected' and host.uncertain is not None
    assert holder['writes'] == 1


def test_postcommit_non_crop_corruption_is_unknown_never_false_success(monkeypatch):
    host, engine, holder, events, apply = service_fixture(monkeypatch, corrupt_non_crop=True)
    host.handle(apply)
    assert events[-1]['phase'] == 'unknown' and host.uncertain is not None
    assert holder['writes'] == 1


def test_status_reconciles_only_original_canonical_receipt_without_replay(monkeypatch):
    host, engine, holder, events, apply = service_fixture(monkeypatch, commit_error=True)
    host.handle(apply)
    engine._portrait_crop_candidate_status = lambda ident: {'status': 'applied', 'document_id': 'document-1', 'revision': '8'}
    status = request('status', 'status-1', target_request_id='apply-1')
    host.handle(status)
    assert events[-1]['phase'] == 'status'
    recovered = events[-1]['receipt']
    assert recovered['phase'] == 'committed' and recovered['recovered'] is True
    assert recovered['original_request'] == apply and events[-1]['original_request'] == status
    assert holder['writes'] == 1 and host.uncertain is None


def test_absent_status_is_unknown_not_permission_to_retry(monkeypatch):
    host, engine, holder, events, apply = service_fixture(monkeypatch)
    host.handle(request('status', 'status-absent', target_request_id='absent-apply'))
    assert events[-1]['phase'] == 'unknown' and events[-1]['outcome_unknown'] is True
    assert holder['writes'] == 0


def test_status_works_even_when_receipt_admission_has_no_capacity(monkeypatch):
    host, engine, holder, events, apply = service_fixture(monkeypatch)
    host.handle(apply)
    monkeypatch.setattr(host, '_admit', lambda request: (_ for _ in ()).throw(ValueError('full')))
    host.handle(request('status', 'status-full', target_request_id='apply-1'))
    assert events[-1]['phase'] == 'status' and events[-1]['receipt']['phase'] == 'committed'


def test_conflicting_original_request_id_never_overwrites_completed_write(monkeypatch):
    host, engine, holder, events, apply = service_fixture(monkeypatch)
    host.handle(apply)
    original = deepcopy(host.receipts['apply-1'])
    changed = deepcopy(apply)
    changed['after_image_sha256'] = D
    host.handle(changed)
    assert events[-1]['phase'] == 'rejected'
    assert host.receipts['apply-1'] == original and holder['writes'] == 1


def test_missing_canonical_commit_port_refuses_instead_of_fallback(monkeypatch):
    engine = SimpleNamespace()
    with pytest.raises(ValueError, match='integration is unavailable'):
        P.commit(engine, before_state={}, candidate_state={}, proof={}, request_id='x')


def test_no_source_landmark_crown_fallback_in_authored_capture_contract():
    # Source-level regression fixture: no detector-index implementation can be
    # substituted for the actual photographic crown confirmation.
    from pathlib import Path
    source = Path(C.__file__).read_text(encoding='utf-8')
    assert 'points[10]' not in source and 'landmarks[10]' not in source
    assert "'chin_proposal'" in source and "'center_proposal'" in source
    assert "'crown_proposal'" not in source


def test_safe_schema_rejection_has_exact_hash_echo_and_retires_reader_registration(monkeypatch):
    host, engine, holder, events, apply = service_fixture(monkeypatch)
    malformed = request('current', 'invalid-read-1', extra='unknown field')
    jobs = J.controller(engine)
    jobs.ingress(json.dumps(malformed))
    host.handle(malformed)
    assert events[-1]['phase'] == 'rejected' and events[-1]['no_write'] is True
    assert events[-1]['command_sha256'] == J.command_hash(malformed)
    assert events[-1]['original_request'] == malformed
    assert jobs.events == {} and holder['writes'] == 0


def test_reader_digest_ignores_only_dispatch_ack_identity():
    jobs = J.Jobs()
    value = request('current')
    wire = {**value, '_host_request_id': 'dispatcher-42'}
    assert jobs.ingress(json.dumps(wire)) is False
    expected = J.command_hash(value)
    assert (value['request_id'], expected) in jobs.events
    assert jobs.run(value, lambda stopped: not stopped()) is True
    cancel = {'cmd': 'portrait_crop_cancel', 'request_id': value['request_id'],
              'command_sha256': expected, '_host_request_id': 'not-permitted'}
    assert jobs.ingress(json.dumps(cancel)) is False
