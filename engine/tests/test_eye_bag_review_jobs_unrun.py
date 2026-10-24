# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: cancellation ownership and race contracts, no runtime claim."""
from types import SimpleNamespace
import json
import pytest
from lumaretouch_engine import eye_bag_review_jobs as J


def control(ident):
    return json.dumps({'cmd': 'eye_bag_cancel', 'request_id': ident})


def test_early_cancel_is_seen_before_original_read_runs():
    e = SimpleNamespace(); calls = []
    assert J.controller(e).ingress(control('read'))
    with pytest.raises(J.Cancelled):
        J.run(e, 'read', lambda *args: calls.append(True), {}, {}, {})
    assert not calls and 'read' in J.controller(e).finished


def test_request_event_does_not_certify_stop_until_method_unwinds():
    e = SimpleNamespace(); jobs = J.controller(e); visited = []
    def method(*args):
        jobs.ingress(control('read')); visited.append('still in method')
        assert 'read' not in jobs.finished
        return {'unsafe_late_candidate': True}
    with pytest.raises(J.Cancelled): J.run(e, 'read', method, {}, {}, {})
    assert visited == ['still in method'] and 'read' in jobs.finished
    assert e._eye_bag_reference is None


def test_completed_read_wins_late_cancel_without_rewriting_terminal():
    e = SimpleNamespace(); jobs = J.controller(e)
    result = J.run(e, 'read', lambda *args: {'complete': True}, {}, {}, {})
    jobs.ingress(control('read'))
    assert result == {'complete': True} and 'read' not in jobs.early
    with pytest.raises(ValueError): jobs.begin('read')


def test_mutating_confirm_never_registers_and_control_does_not_apply_it():
    jobs = J.Jobs()
    assert not jobs.ingress(json.dumps({'cmd': 'people', 'action': 'eye_bag_confirm', 'request_id': 'commit'}))
    assert 'commit' not in jobs.events
    jobs.ingress(control('commit'))
    assert 'commit' not in jobs.events  # Only a future read could consume this event.
    assert 'eye_bag_confirm' not in J.READS


def test_cancel_invalidates_private_tokens_not_committed_data():
    class Images:
        def prune(self, entries): self.entries = entries
    images = Images(); committed = {'unchanged': object()}
    e = SimpleNamespace(_eye_bag_reference={'pixels': b'x'},
        _eye_bag_reviews={'pending': {'token': {}}, 'images': images}, _people_support=committed)
    def method(*args): J.controller(e).ingress(control('read')); return {}
    with pytest.raises(J.Cancelled): J.run(e, 'read', method, {}, {}, {})
    assert e._people_support is committed and e._eye_bag_reference is None
    assert '_eye_bag_reviews' not in vars(e) and images.entries == {}


def test_failed_read_preserves_actual_error_without_fake_cancellation():
    e = SimpleNamespace()
    def method(*args): raise ValueError('actual error')
    with pytest.raises(ValueError, match='actual error'): J.run(e, 'read', method, {}, {}, {})
    assert '_eye_bag_read_cancelled' not in vars(e)


def test_eof_and_capacity_fail_closed_without_unbounded_events():
    jobs = J.Jobs()
    for n in range(J.MAX_RECORDS): jobs.ingress(control(str(n)))
    jobs.ingress(control('overflow'))
    assert jobs.overflow and len(jobs.early) == J.MAX_RECORDS
    event = jobs.begin('read'); assert event.is_set()
    jobs.stop(); assert jobs.complete('read', event)


def test_strict_control_rejects_extra_fields_and_nonstring_identity():
    jobs = J.Jobs()
    assert not jobs.ingress(json.dumps({'cmd':'eye_bag_cancel','request_id':'x','action':'confirm'}))
    assert not jobs.ingress(json.dumps({'cmd':'eye_bag_cancel','request_id':42}))
    assert not jobs.events and not jobs.early
