# SPDX-License-Identifier: GPL-3.0-or-later
"""SOURCE-AUTHORED / UNRUN: one-target canonical automatic portrait adapter.

Mocks establish dispatch/fence contracts only, never photographic acceptance.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from lumaretouch_engine import workflow_auto_portrait as A
from lumaretouch_engine import people_batch_ledger as L
from lumaretouch_engine import full_candidate_render as F


def fixture(monkeypatch):
    monkeypatch.setattr(F, 'render', lambda *args, **kwargs: None)
    owner = object.__new__(A.TargetPortraitPlan)
    owner.engine = SimpleNamespace()
    owner.row = {'document_id': 'target'}
    owner.batch = SimpleNamespace(emit=lambda frame: None)
    owner._committed = False
    owner._assessment = None
    owner.candidate_graph = owner.prepared_context = owner.face_refs = None
    target = {'document_id': 'target', 'revision': '4', 'load_id': 'load'}
    evidence = {'target': target, 'face_refs': [{'face_instance_id': 'face-own'}],
                'before': {'source': 'own'}, 'after': {'source': 'own'}}
    graph = {'own': ['candidate']}
    staged = {'project': {'row': owner.row, 'before': {'own': []}, 'candidate': graph}}
    state = {'_exposure': 0.0}
    owner._inputs = lambda preset, target: (deepcopy(evidence), staged, state, graph, {'people_graph': graph})
    return owner, target, evidence, graph, staged, state


def test_assessment_freezes_detached_graph_and_face_references(monkeypatch):
    owner, target, evidence, graph, _, _ = fixture(monkeypatch)
    result = owner.assess({'modules': {}}, target)
    assert result == evidence
    graph['own'].append('later')
    result['face_refs'][0]['face_instance_id'] = 'foreign'
    assert owner.candidate_graph == {'own': ['candidate']}
    assert owner.face_refs == [{'face_instance_id': 'face-own'}]
    assert owner._assessment == evidence


def test_changed_assessment_refuses_before_render_or_history(monkeypatch):
    owner, target, evidence, _, _, _ = fixture(monkeypatch)
    owner.assess({'modules': {}}, target)
    monkeypatch.setattr(F, 'render', lambda *args, **kwargs: pytest.fail('must not render'))
    with pytest.raises(ValueError, match='exact frozen assessment'):
        owner.commit({'modules': {}}, target, 'request', {**evidence, 'foreign': True})
    assert owner._committed is False


def test_commit_uses_full_source_and_existing_scoped_ledger_once(monkeypatch):
    owner, target, evidence, graph, staged, state = fixture(monkeypatch)
    preset = {'modules': {'lnx.skin_finish.v1': {'recipe': {'fixture': True}}}}
    calls = []
    monkeypatch.setattr(F, 'render', lambda *args, **kwargs: calls.append(('render', args, kwargs)))
    owner.assess(preset, target)
    targets = {'2': {'document_id': 'target'}}
    monkeypatch.setattr(L, '_targets', lambda batch, engine, plans: targets)
    def commit(batch, engine, plans, **kwargs):
        assert owner._committed is True
        assert batch is owner.batch and engine is owner.engine and plans is staged
        assert kwargs == {'request_id': 'request', 'prepare': False, 'prepared_targets': targets}
        calls.append(('ledger',))
        return 'batch-existing', None
    monkeypatch.setattr(L, 'commit_scoped', commit)
    result = owner.commit(preset, target, 'request', evidence)
    assert [call[0] for call in calls] == ['render', 'ledger']
    assert calls[0][1] == (owner.engine, owner.row, state, 'target', '4')
    assert calls[0][2] == {'people_graph': graph}
    assert result['batch_id'] == 'batch-existing'
    with pytest.raises(ValueError):
        owner.commit(preset, target, 'request', evidence)


def test_source_alias_closure_refuses_before_history(monkeypatch):
    owner, target, evidence, _, _, _ = fixture(monkeypatch)
    preset = {'modules': {}}
    owner.assess(preset, target)
    monkeypatch.setattr(F, 'render', lambda *args, **kwargs: None)
    monkeypatch.setattr(L, '_targets', lambda *args: {'1': {'document_id': 'target'}, '2': {'document_id': 'alias'}})
    monkeypatch.setattr(L, 'commit_scoped', lambda *args, **kwargs: pytest.fail('must not commit'))
    with pytest.raises(ValueError, match='unselected source alias'):
        owner.commit(preset, target, 'request', evidence)
    assert owner._committed is False


def test_unknown_ledger_failure_is_one_shot_not_retryable(monkeypatch):
    owner, target, evidence, _, _, _ = fixture(monkeypatch)
    preset = {'modules': {}}
    owner.assess(preset, target)
    monkeypatch.setattr(F, 'render', lambda *args, **kwargs: None)
    monkeypatch.setattr(L, '_targets', lambda *args: {'1': {'document_id': 'target'}})
    def fail(*args, **kwargs):
        raise ValueError('unknown publication outcome')
    monkeypatch.setattr(L, 'commit_scoped', fail)
    with pytest.raises(ValueError, match='unknown publication'):
        owner.commit(preset, target, 'request', evidence)
    assert owner._committed is True
    with pytest.raises(ValueError, match='exact frozen assessment'):
        owner.commit(preset, target, 'request', evidence)


def test_render_refusal_is_preflight_only_and_no_assessment_is_published(monkeypatch):
    owner, target, _, _, _, _ = fixture(monkeypatch)
    def refuse(*args, **kwargs):
        raise ValueError('target native support unavailable')
    monkeypatch.setattr(F, 'render', refuse)
    with pytest.raises(ValueError, match='native support unavailable'):
        owner.assess({'modules': {}}, target)
    assert owner._assessment is None
    assert owner._committed is False


def test_reassessment_checks_identity_without_repeating_full_render(monkeypatch):
    owner, target, evidence, _, _, _ = fixture(monkeypatch)
    calls = []
    monkeypatch.setattr(F, 'render', lambda *args, **kwargs: calls.append('render'))
    assert owner.assess({'modules': {}}, target) == evidence
    assert owner.assess({'modules': {}}, target) == evidence
    assert calls == ['render']
