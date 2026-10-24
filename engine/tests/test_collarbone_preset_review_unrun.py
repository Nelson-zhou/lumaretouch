# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: exact mixed-preset evidence and guarded failure recovery.

Stubs exercise coordinator boundaries, not image algorithms, native execution,
model quality or successful integration. No test collection/execution was run.
"""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from lumaretouch_engine import collarbone_preset_review as R
from lumaretouch_engine import people_scope as PLANNER
from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import optics_candidate_identity as IDENTITY


def key(state, graph):
    return json.dumps([state, graph], sort_keys=True)


def setup(monkeypatch):
    before = {'exposure': 0., 'repair': ['retained']}
    candidate_input = {'exposure': .2, 'transport_only': True, R.SCOPE.TARGET: {'face': 'owned'}}
    normalized = {'exposure': .2, 'repair': ['retained'], 'normalized': True}
    owner = SimpleNamespace(value={'graph': 'before'}, fence=3)
    owner.snapshot = lambda: deepcopy(owner.value)
    plan = SimpleNamespace(before=owner.snapshot(), candidate={'graph': 'mixed-candidate'},
        state=normalized, owner=owner, owner_fence=3, managed=True, target_ref={'face': 'owned'})
    row = {'path': 'owned.png'}; live = {'state': deepcopy(before)}
    engine = SimpleNamespace(_people_preset_capture=lambda: deepcopy(live['state']))
    wrapper = {'load_id': 'load', 'visual': {'document_id': 'doc'}, 'owner': {'source_proof': {'source': 'owned'}}}
    entry = {'row': row, 'plan': plan, 'before': deepcopy(before), 'before_key': key(before, plan.before),
        'after_key': key(normalized, plan.candidate), 'failed_key': key(normalized, plan.before),
        'candidate_input_sha256': IDENTITY.fingerprint(candidate_input), 'write_fence': None}
    monkeypatch.setattr(R, '_entry', lambda *a: entry)
    monkeypatch.setattr(R, '_target', lambda *a: (owner, 'doc'))
    monkeypatch.setattr(R, '_snapshot_key', lambda engine, row, state, graph: key(state, graph))
    monkeypatch.setattr(SOURCE, 'verify_row', lambda *a: None)
    calls = []
    def execute(engine, exact, **kwargs):
        assert exact is plan
        owner.value = deepcopy(exact.candidate); owner.fence += 1
        live['state'] = deepcopy(exact.state); calls.append(('execute', exact))
        return {'frame': 'candidate'}
    def restore(engine, exact, state, *, expected_owner_fence, **kwargs):
        assert exact is plan and expected_owner_fence == owner.fence
        assert state == before
        owner.value = deepcopy(exact.before); owner.fence += 1
        live['state'] = deepcopy(state); calls.append(('restore', exact))
        return {'frame': 'before'}
    monkeypatch.setattr(PLANNER, 'execute_plan', execute)
    monkeypatch.setattr(PLANNER, 'restore_plan', restore)
    return engine, row, before, candidate_input, plan, owner, live, wrapper, entry, calls


def test_forward_binds_input_but_executes_reviewed_normalized_state(monkeypatch):
    engine, row, before, incoming, plan, owner, live, wrapper, entry, calls = setup(monkeypatch)
    assert incoming != plan.state
    assert R.replay(engine, row, incoming, 'load', '7', wrapper) == {'frame': 'candidate'}
    assert live['state'] == plan.state and owner.value == plan.candidate and entry['write_fence'] == 4
    R.verify_applied(engine, row, live['state'], 'load', '7', wrapper)
    assert [item[0] for item in calls] == ['execute']


def test_equivalent_render_input_cannot_replace_exact_reviewed_transport(monkeypatch):
    engine, row, before, incoming, plan, owner, live, wrapper, entry, calls = setup(monkeypatch)
    with pytest.raises(ValueError, match='dependencies changed'):
        R.replay(engine, row, plan.state, 'load', '7', wrapper)
    assert entry['write_fence'] is None and not calls and owner.fence == 3


def test_changed_frozen_candidate_is_refused_before_publication(monkeypatch):
    engine, row, before, incoming, plan, owner, live, wrapper, entry, calls = setup(monkeypatch)
    plan.state['exposure'] = .9
    with pytest.raises(ValueError, match='dependencies changed'):
        R.replay(engine, row, incoming, 'load', '7', wrapper)
    assert not calls and owner.fence == 3


def test_internal_graph_rollback_with_candidate_state_can_restore_exact_before(monkeypatch):
    engine, row, before, incoming, plan, owner, live, wrapper, entry, calls = setup(monkeypatch)
    def fail(engine, exact, **kwargs):
        live['state'] = deepcopy(exact.state)
        # Exact consumer published then restored graph, advancing both fences.
        owner.value = deepcopy(exact.before); owner.fence += 2
        raise RuntimeError('frame failed after state application')
    monkeypatch.setattr(PLANNER, 'execute_plan', fail)
    with pytest.raises(RuntimeError): R.replay(engine, row, incoming, 'load', '7', wrapper)
    assert entry['write_fence'] == 5 and key(live['state'], owner.value) == entry['failed_key']
    assert R.replay(engine, row, before, 'load', '7', wrapper, rollback=True) == {'frame': 'before'}
    R.verify_applied(engine, row, live['state'], 'load', '7', wrapper, rollback=True)
    assert live['state'] == before and [item[0] for item in calls] == ['restore']


@pytest.mark.parametrize('mutation', ['foreign-state', 'foreign-graph', 'newer-fence', 'wrong-before'])
def test_rollback_does_not_bless_arbitrary_partial_or_foreign_state(monkeypatch, mutation):
    engine, row, before, incoming, plan, owner, live, wrapper, entry, calls = setup(monkeypatch)
    R.replay(engine, row, incoming, 'load', '7', wrapper)
    requested = deepcopy(before)
    if mutation == 'foreign-state': live['state']['exposure'] = .7
    if mutation == 'foreign-graph': owner.value = {'graph': 'foreign'}
    if mutation == 'newer-fence': owner.fence += 1
    if mutation == 'wrong-before': requested['exposure'] = -.5
    with pytest.raises(ValueError): R.replay(engine, row, requested, 'load', '7', wrapper, rollback=True)
    assert [item[0] for item in calls] == ['execute']


def test_commit_verification_rejects_candidate_state_with_before_graph(monkeypatch):
    engine, row, before, incoming, plan, owner, live, wrapper, entry, calls = setup(monkeypatch)
    R.replay(engine, row, incoming, 'load', '7', wrapper)
    owner.value = deepcopy(plan.before)
    with pytest.raises(ValueError, match='publication'):
        R.verify_applied(engine, row, live['state'], 'load', '7', wrapper)


def test_prepare_images_use_complete_planned_graph_and_full_state(monkeypatch):
    engine, row, before, incoming, plan, owner, live, wrapper, entry, calls = setup(monkeypatch)
    from lumaretouch_engine import people_transfer_inventory as INVENTORY
    monkeypatch.setattr(PLANNER, 'plan_preset', lambda *a, **k: plan)
    proof = {'source_proof': {'source': 'owned'}}
    monkeypatch.setattr(INVENTORY, 'proof', lambda *a, **k: proof)
    monkeypatch.setattr(R, '_coverage', lambda *a: {'target': 'owned'})
    monkeypatch.setattr(R, 'checked', lambda value: deepcopy(value))
    monkeypatch.setattr(R.VISUAL, 'checked', lambda value: deepcopy(value))
    monkeypatch.setattr(R.VISUAL, 'coverage_digest', lambda value: 'c' * 64)
    rendered = []
    def image(engine, row, state, graph, document, revision):
        rendered.append((deepcopy(state), deepcopy(graph)))
        compact = {'mime': 'image/png', 'width': 8, 'height': 6, 'sha256': str(len(rendered))*64}
        return compact, {**compact, 'base64': 'fixture'}, {'source_proof': {'source': 'owned'},
            'source_size': [80, 60], 'output_size': [80, 60],
            'candidate_sha256': IDENTITY.fingerprint(state), 'people_sha256': IDENTITY.fingerprint(graph)}
    monkeypatch.setattr(R, '_image', image)
    # OrderedDict required by actual preparation retention.
    from collections import OrderedDict
    monkeypatch.setattr(R, '_ENTRIES', OrderedDict())
    result, duplicated = R.prepare(engine, row, before, incoming, 'load', '7', {'preset': 'mixed'}, [R.SCOPE.OP])
    assert rendered == [(before, plan.before), (plan.state, plan.candidate)]
    stored = R._ENTRIES[R.digest(result)]
    assert stored['failed_key'] == key(plan.state, plan.before)
    assert stored['candidate_input_sha256'] == IDENTITY.fingerprint(incoming)
    assert stored['after_key'] == key(plan.state, plan.candidate)
    assert result == duplicated and not calls and live['state'] == before
