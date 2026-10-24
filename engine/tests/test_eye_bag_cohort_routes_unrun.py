# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Cohort read admission is not association write authority."""
from pathlib import Path
import pytest
from lumaretouch_engine.eye_bag_cohort_store import read_only, image_read_only
from lumaretouch_engine.creative_transfer_host import require_route
from lumaretouch_engine.batch_dispatch_receipt import rejected


def image_request():
    return {'cmd': 'batch', 'action': 'eye_bag_cohort_visual', 'request_id': 'cohort-page',
        'preflight_token': 'a' * 32, 'document_id': 'b' * 32, 'revision': '1',
        'side': 'after', 'sha256': 'c' * 64}


def test_exact_cohort_image_is_read_only_on_derived_route():
    request = image_request()
    assert read_only(request) and image_read_only(request)
    require_route('batch', request)


@pytest.mark.parametrize('field', ['module_scope', 'eye_bag_cohort_ack', 'people_transfer', 'force'])
def test_image_cannot_smuggle_new_cohort_intent(field):
    request = {**image_request(), field: True}
    assert not read_only(request) and not image_read_only(request)
    with pytest.raises(ValueError):
        require_route('batch', request)


@pytest.mark.parametrize('additional', [{}, {'portrait_cohort_ack': []}, {'collarbone_review_ack': []},
    {'portrait_cohort_ack': [], 'collarbone_review_ack': []}])
def test_derived_commit_transport_retains_exact_review_families(additional):
    request = {'cmd': 'batch', 'action': 'commit', 'request_id': 'cohort-commit',
        'preflight_token': 'a' * 32, 'module_scope': [], 'eye_bag_cohort_ack': [], **additional}
    assert not read_only(request)
    # Transport shape only: empty ACK is not a valid all-member confirmation.
    require_route('batch', request)
    with pytest.raises(ValueError):
        require_route('batch', {**request, 'replace_legacy': True})
    with pytest.raises(ValueError):
        require_route('batch', {**request, 'eye_bag_review_ack': []})


def test_started_cohort_write_cannot_be_settled_as_preguard_failure():
    request = {'cmd': 'batch', 'action': 'commit', 'request_id': 'cohort-commit',
        'preflight_token': 'a' * 32, 'module_scope': [], 'eye_bag_cohort_ack': []}
    emitted = []
    rejected(request, 'Interrupted write', {'started': True, 'message': request}, emitted.append)
    assert emitted == []


def test_cohort_read_branch_retains_prior_guards_and_capture_ownership():
    root = Path(__file__).parents[1] / 'src' / 'lumaretouch_engine'
    source = (root / 'server.py').read_text()
    index = source.index('if eye_bag_cohort_read_only(msg):')
    assert source.index('CDH.guard_command(self, name, msg)') < index
    assert index < source.index('invalidate_other(self,name,msg)')
    assert 'if eye_bag_cohort_read_only(message):return' in (root / 'project_recovery_runtime.py').read_text()


def test_known_unstarted_cohort_refusal_echoes_exact_empty_unlink_scope():
    ack = [{'document_id': 'b' * 32, 'revision': '1', 'before_sha256': 'c' * 64,
        'after_sha256': 'd' * 64, 'coverage_sha256': 'e' * 64, 'replace_legacy': False}]
    request = {'cmd': 'batch', 'action': 'commit', 'request_id': 'cohort-commit',
        'preflight_token': 'a' * 32, 'module_scope': [], 'eye_bag_cohort_ack': ack,
        'portrait_cohort_ack': [], 'collarbone_review_ack': []}
    emitted = []
    rejected(request, 'Existing recovery guard', {'started': False, 'message': request}, emitted.append)
    assert len(emitted) == 1 and emitted[0]['success'] is False
    assert emitted[0]['outcome_unknown'] is False and emitted[0]['module_scope'] == []
    assert emitted[0]['eye_bag_cohort'] is True and emitted[0]['eye_bag_cohort_ack'] == ack
    assert emitted[0]['portrait_cohort'] is True and emitted[0]['collarbone_cohort'] is True
    # This is request correlation, not validation or acceptance of the short ACK.
    assert 'batch_id' not in emitted[0] and 'target_outcomes' not in emitted[0]


def test_boundary_for_equal_but_different_request_cannot_claim_no_write():
    request = {'cmd': 'batch', 'action': 'commit', 'request_id': 'cohort-commit',
        'preflight_token': 'a' * 32, 'module_scope': [], 'eye_bag_cohort_ack': []}
    emitted = []
    rejected(request, 'Unknown boundary', {'started': False, 'message': dict(request)}, emitted.append)
    assert emitted == []
