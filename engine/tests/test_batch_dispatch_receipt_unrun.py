# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Server-boundary refusal cannot reconcile started writes."""
import pytest
from lumaretouch_engine.batch_dispatch_receipt import rejected


def history():
    return {'cmd': 'batch', 'action': 'undo', 'request_id': 'history-one', 'batch_id': 'batch-001'}


def test_preguard_history_refusal_has_exact_identity_and_no_write_truth():
    request = history(); emitted = []
    rejected(request, 'Project recovery is pending', {'started': False, 'message': request}, emitted.append)
    assert len(emitted) == 1
    assert emitted[0]['batch_id'] == request['batch_id']
    assert emitted[0]['request_id'] == request['request_id']
    assert emitted[0]['success'] is False and emitted[0]['outcome_unknown'] is False
    assert 'restored' not in emitted[0] and 'doc_state' not in emitted[0]


@pytest.mark.parametrize('started', [True, None, 0, 'false'])
def test_only_exact_not_started_boundary_proves_no_write(started):
    request = history(); emitted = []
    rejected(request, 'Interrupted', {'started': started, 'message': request}, emitted.append)
    assert emitted == []


def test_other_request_boundary_cannot_authorize_settlement():
    request = history(); emitted = []
    rejected(request, 'Rejected', {'started': False, 'message': dict(request)}, emitted.append)
    assert emitted == []


def test_started_eye_commit_never_becomes_known_failed():
    request = {'cmd': 'batch', 'action': 'commit', 'request_id': 'eye-one',
        'preflight_token': 'a' * 32, 'eye_bag_review_ack': []}
    emitted = []
    rejected(request, 'Post-write failure', {'started': True, 'message': request}, emitted.append)
    assert emitted == []


def test_invalid_unicode_identity_is_not_echoed():
    request = {**history(), 'request_id': '\ud800'}; emitted = []
    rejected(request, 'Bad request', {'started': False, 'message': request}, emitted.append)
    assert emitted == []
