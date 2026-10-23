"""Authored UNRUN: review ownership and typed rejection/receipt contracts."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import fringe_repair_review as R
from lumaretouch_engine import fringe_repair_controller as C
from lumaretouch_engine import fringe_repair_state as S
from lumaretouch_engine.fringe_repair_host import dispatch_rejected


def request(**updates):
    value = dict(cmd='fringe_repair', action='apply', request_id='request-one',
                 preview_id='preview-one', session_id='session-one', document_id='doc-one')
    value.update(updates)
    return value


def test_dispatch_before_controller_is_known_rejection_not_unknown_commit():
    events = []
    dispatch_rejected(request(), ValueError('source changed'), False, events.append)
    assert events[-1]['event'] == 'fringe_repair_result'
    assert not events[-1]['outcome_unknown']
    assert not events[-1]['requires_reload']
    dispatch_rejected(request(), ValueError('interrupted'), True, events.append)
    assert events[-1]['outcome_unknown'] and events[-1]['requires_reload']


def test_preview_dispatch_rejection_releases_preview_request():
    events = []
    dispatch_rejected(request(cmd='fringe_repair_preview'), ValueError('blocked'), False, events.append)
    assert events[-1]['event'] == 'fringe_repair_preview'
    assert events[-1]['state'] == 'failed'
    assert events[-1]['preview_id'] == 'preview-one'


def test_known_rejection_receipt_is_replayed_without_retrying_edit():
    calls = []
    engine = SimpleNamespace(_guard_editable=lambda reason: calls.append(reason) or 'blocked')
    events = []
    owner = C.Controller(engine, events.append)
    owner.handle(request()); first = deepcopy(events[-1])
    owner.handle(request())
    assert events[-1] == first and len(calls) == 1
    owner.handle(request(document_id='different-doc'))
    assert not events[-1]['success']
    assert 'reused' in events[-1]['error']
    owner.handle(request())
    assert events[-1] == first


def test_receipt_capacity_does_not_evict_or_submit():
    engine = SimpleNamespace(_guard_editable=lambda reason: pytest.fail('must not submit'))
    events = []; owner = C.Controller(engine, events.append)
    owner.cache = {str(i): ('digest', {}) for i in range(4096)}
    owner.handle(request())
    assert len(owner.cache) == 4096 and 'capacity' in events[-1]['error']


def test_entry_is_enabled_candidate_not_saved_recipe(monkeypatch):
    saved = S.neutral(); engine = SimpleNamespace(_fringe_repair=saved)
    bound = {'source': {'sha256': 'a' * 64, 'width': 800, 'height': 600}}
    monkeypatch.setattr(R, 'proof', lambda engine: deepcopy(bound))
    owner = R.Preview(engine, lambda event: None)
    value = owner.candidate({'mutation': {'action': 'enter'}, 'session_id': 'session-one'})
    assert value['enabled'] and not saved['enabled']
    assert owner.session['baseline'] == saved
    value['coverage']['strokes'].append({'invalid': 'draft-only'})
    assert not saved['coverage']['strokes']


def test_apply_requires_same_presented_source_and_upstream_state(monkeypatch):
    bound = {'state': 'unchanged'}
    monkeypatch.setattr(R, 'proof', lambda engine: deepcopy(bound))
    owner = R.Preview(object(), lambda event: None)
    owner.record = {'request': request(), 'proof': deepcopy(bound),
                    'value': S.neutral(), 'presented': False}
    with pytest.raises(ValueError, match='View'): owner.prepare(request())
    owner.record['presented'] = True
    assert owner.prepare(request()) == S.neutral()
    bound['state'] = 'changed'
    with pytest.raises(ValueError, match='changed'): owner.prepare(request())
