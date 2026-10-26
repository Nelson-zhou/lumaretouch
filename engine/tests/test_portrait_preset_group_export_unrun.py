"""Authored UNRUN export-handoff contracts; no renderer or filesystem exercised.

These fixtures do not establish build success, real output completion, image
quality, no-clobber implementation correctness, or performance acceptance.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import pytest
from lumaretouch_engine.portrait_preset_group_export import GroupExport


@pytest.fixture
def harness(monkeypatch):
    from lumaretouch_engine import export_destination_policy
    monkeypatch.setattr(export_destination_policy, 'restore',
                        lambda value: SimpleNamespace(payload=lambda: deepcopy(value)))
    docs = ['one', 'two']
    keys = ['document:' + sha256(doc.encode()).hexdigest() for doc in docs]
    plan = {'plan_id': 'exact-plan', 'intent_revision': 7,
            'entries': [{'item_id': key, 'disposition': 'write', 'target': '/output/' + doc}
                        for key, doc in zip(keys, docs)]}
    trace, flags = [], {'live': True, 'reject': False, 'uncertain': False, 'drift': False}
    engine = SimpleNamespace(_tasks={}, _task_args={})

    def verify(token):
        assert token == 'group'
        if flags['drift']: raise ValueError('postcommit revision changed')
        return list(docs)

    def export(command, trusted_result):
        trace.append(deepcopy(command))
        if command['action'] == 'preview':
            trusted_result({'event': 'export_destination_result', 'request_id': command['request_id'],
                            'status': 'ready', 'value': deepcopy(plan)})
            return
        if flags['uncertain']: raise RuntimeError('lost admission result')
        if flags['reject']:
            trusted_result({'event': 'error', 'error': 'destination changed'})
            return
        entries = {key: {'document_id': doc, 'fingerprint': {'sha256': doc}}
                   for key, doc in zip(keys, docs)}
        options = {'destination_plan': deepcopy(plan), 'document_entries': entries}
        task = {'kind': 'export', 'attempt': 0, 'state': 'running', 'recipe_persisted': True,
                'inputs': deepcopy(options), 'items': [{'path': key, 'document_id': doc, 'state': 'pending'}
                                                      for key, doc in zip(keys, docs)]}
        engine._tasks['original-task'] = task
        engine._task_args['original-task'] = (None,) * 8 + (deepcopy(options),)

    def cancel(command):
        trace.append(deepcopy(command))
        assert command == {'cmd': 'task', 'action': 'cancel', 'task': 'original-task'}
        engine._tasks['original-task']['state'] = 'cancelling'

    engine.cmd_export, engine.cmd_task = export, cancel
    engine._task_worker_is_live = lambda task: flags['live']
    owner = GroupExport(engine, verify)
    def preview():
        return owner.preview('group', 'preview-1', {'format': 'jpg', 'output_profile': 'srgb'},
                             {'mode': 'chosen_root', 'chosen_root': '/output'}, 7)
    return SimpleNamespace(owner=owner, engine=engine, trace=trace, flags=flags, plan=plan, preview=preview)


def test_only_explicit_frozen_options_reach_canonical_owner(harness):
    h = harness
    h.preview()
    result = h.owner.start('group', 'start-1', 'exact-plan', 7)
    assert result['export_task_id'] == 'original-task'
    assert result['export_status'] == 'running'
    assert result['output_completion_verified'] is False
    assert h.trace[-1]['document_ids'] == ['one', 'two']
    assert h.trace[-1]['output_profile'] == 'srgb'
    assert h.trace[-1]['destination_plan_id'] == 'exact-plan'


def test_replay_never_starts_second_export(harness):
    h = harness
    h.preview()
    h.owner.start('group', 'start-1', 'exact-plan', 7)
    h.owner.start('group', 'start-1', 'exact-plan', 7)
    assert sum(c['action'] == 'start' for c in h.trace) == 1
    with pytest.raises(ValueError): h.owner.start('group', 'replacement', 'exact-plan', 7)
    with pytest.raises(ValueError): h.preview()


def test_exact_task_required_before_cancel(harness):
    h = harness
    h.preview(); h.owner.start('group', 'start-1', 'exact-plan', 7)
    with pytest.raises(ValueError): h.owner.cancel('group', 'other-task')
    assert not any(c['action'] == 'cancel' for c in h.trace)
    h.owner.cancel('group', 'original-task')
    h.owner.cancel('group', 'original-task')
    assert sum(c['action'] == 'cancel' for c in h.trace) == 1


def test_version_drift_rejected_before_dispatch(harness):
    h = harness
    h.preview(); h.flags['drift'] = True
    with pytest.raises(ValueError): h.owner.start('group', 'start-1', 'exact-plan', 7)
    assert not any(c['action'] == 'start' for c in h.trace)


def test_unknown_admission_retained_without_retry(harness):
    h = harness
    h.preview(); h.flags['uncertain'] = True
    assert h.owner.start('group', 'start-1', 'exact-plan', 7)['export_status'] == 'unknown'
    assert h.owner.observe('group', None)['export_status'] == 'unknown'
    h.owner.start('group', 'start-1', 'exact-plan', 7)
    assert sum(c['action'] == 'start' for c in h.trace) == 1
    with pytest.raises(ValueError): h.preview()


def test_affirmative_no_start_can_be_explicitly_repreviewed(harness):
    h = harness
    h.preview(); h.flags['reject'] = True
    result = h.owner.start('group', 'start-1', 'exact-plan', 7)
    assert result['export_status'] == 'failed' and result['export_no_start'] is True
    assert h.preview()['export_status'] == 'preview'


def test_conflict_confirmation_does_not_dispatch(harness):
    h = harness
    h.plan['entries'][0]['disposition'] = 'needs_confirmation'
    h.preview()
    with pytest.raises(ValueError): h.owner.start('group', 'start-1', 'exact-plan', 7)
    assert not any(c['action'] == 'start' for c in h.trace)


def test_partial_cancel_preserves_finished_item(harness):
    h = harness
    h.preview(); h.owner.start('group', 'start-1', 'exact-plan', 7)
    task = h.engine._tasks['original-task']
    task['items'][0].update(state='succeeded', out='/output/one', bytes=123, destination_plan_id='exact-plan')
    task['state'] = 'cancelled'; h.flags['live'] = False
    result = h.owner.observe('group', 'original-task')
    assert result['export_status'] == 'partial'
    assert result['export_task_state'] == 'cancelled'
    assert result['items'][0]['out'] == '/output/one'
    assert result['items'][1]['state'] == 'pending'
    assert result['output_completion_verified'] is False


def test_skipped_is_not_full_success(harness):
    h = harness
    h.preview(); h.owner.start('group', 'start-1', 'exact-plan', 7)
    task = h.engine._tasks['original-task']
    for item in task['items']: item['state'] = 'skipped'
    task['state'] = 'succeeded'; h.flags['live'] = False
    assert h.owner.observe('group', 'original-task')['export_status'] == 'partial'


def test_deleted_recipe_or_external_retry_remains_unknown(harness):
    h = harness
    h.preview(); h.owner.start('group', 'start-1', 'exact-plan', 7)
    h.engine._tasks['original-task']['attempt'] = 1
    assert h.owner.observe('group', 'original-task')['export_status'] == 'unknown'
    h.engine._tasks['original-task']['attempt'] = 0
    h.engine._task_args.clear()
    assert h.owner.observe('group', 'original-task')['export_status'] == 'unknown'


def test_old_output_ui_status_is_never_consulted(harness):
    h = harness
    h.engine._last_export = {'total': 2, 'failed': 0}
    h.preview(); h.owner.start('group', 'start-1', 'exact-plan', 7)
    h.flags['live'] = False
    assert h.owner.observe('group', 'original-task')['export_status'] == 'unknown'


def test_intent_revision_mismatch_never_dispatches(harness):
    h = harness
    h.preview()
    with pytest.raises(ValueError): h.owner.start('group', 'start-1', 'exact-plan', 8)
    assert not any(c['action'] == 'start' for c in h.trace)
