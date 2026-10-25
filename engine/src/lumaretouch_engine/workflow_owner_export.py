"""Genuine export planner/start/readback adapter for an already-owned document.

No alternate renderer, selected-document switching, shadow recipe or fake task.
The trusted result sink observes the same command reply without changing it.
"""
from copy import deepcopy
import os
from . import workflow_owner_protocol as P


def export_command(document_id, root, revision, *, action, request_id):
    return {'cmd': 'export', 'action': action, 'request_id': request_id,
            **deepcopy(P.RECIPE_PROFILE['export_options']),
            'document_ids': [document_id], 'intent_revision': revision,
            'destination_policy': {**deepcopy(P.RECIPE_PROFILE['destination']), 'chosen_root': root}}


def preview(engine, command, destination_roots):
    events = []
    engine.cmd_export(command, trusted_result=events.append,
                      trusted_destination_roots=deepcopy(destination_roots))
    matches = [event for event in events if event.get('event') == 'export_destination_result'
               and event.get('request_id') == command['request_id']]
    if len(matches) != 1 or matches[0].get('status') != 'ready':
        errors = [event.get('error') for event in events if event.get('error')]
        raise ValueError(str(errors[0]) if errors else 'The real export planner returned no exact preview receipt')
    from .export_destination_policy import restore
    return restore(matches[0]['value']).payload()


def freeze(engine, row, document, root, revision, request_id, destination_roots):
    command = export_command(row['document_id'], root, revision, action='preview', request_id=request_id)
    if set(destination_roots) != {root}:
        raise ValueError('Output root lacks its exact preflight descriptor binding')
    payload = preview(engine, command, destination_roots)
    entries = payload['entries']
    if len(entries) != 1 or any(entry['disposition'] != 'write' for entry in entries):
        raise ValueError('Export destination collides and needs a real user destination decision; no rename, skip or ACK was invented')
    targets = [entry['target'] for entry in entries]
    if any(os.path.commonpath([root, target]) != root or target == root for target in targets):
        raise ValueError('Export planner target escaped the pinned output root')
    plan = {'plan_id': payload['plan_id'], 'plan_sha256': P.digest(payload),
            'document_revision': document['document_revision'], 'output_root': root,
            'recipe_sha256': P.RECIPE_SHA256, 'targets': targets}
    return {'plan': plan, 'destination': payload, 'command': command,
            'destination_roots': deepcopy(destination_roots)}


def start(engine, frozen, request_id):
    """Caller records dispatch-started BEFORE this invocation, even if it raises."""
    command = {**deepcopy(frozen['command']), 'action': 'start', 'request_id': request_id,
               'destination_plan_id': frozen['plan']['plan_id']}
    before = set(engine._tasks)
    events = []
    dispatch_error = None
    try:
        engine.cmd_export(command, trusted_result=events.append,
                          trusted_destination_roots=deepcopy(frozen['destination_roots']))
    except Exception as error: dispatch_error = str(error)
    created = set(engine._tasks) - before
    if not created:
        # With destination_policy the real command has no write before queue
        # admission. Its exact validation error is affirmative no-start proof.
        errors = [event['error'] for event in events if event.get('event') == 'error' and event.get('error')]
        if len(errors) == 1 and dispatch_error is None:
            return {'status': 'failed', 'code': 'export_admission_rejected',
                    'message': str(errors[0])[:2048], 'retained_document': None}, None
        return {'status': 'unknown', 'reason': 'Export dispatch returned without a unique task or definitive no-write rejection'}, None
    if len(created) != 1:
        return {'status': 'unknown', 'reason': 'Export dispatch did not produce one uniquely owned task'}, None
    task_id = created.pop()
    task = engine._tasks[task_id]
    if (task.get('kind') != 'export' or task.get('attempt') != 0
            or (task.get('inputs', {}).get('destination_plan') or {}).get('plan_id') != frozen['plan']['plan_id']):
        return {'status': 'unknown', 'reason': 'New task did not bind the exact frozen destination plan'}, None
    if dispatch_error is not None:
        return {'status': 'unknown', 'reason': dispatch_error[:2048] or 'Original export dispatch raised after task admission'}, task_id
    return {'status': 'pending', 'owner_receipt_id': task_id}, task_id


def verify_destination_roots(expected):
    from .source_relocation_io import open_directory
    for path, pin in expected.items():
        fd = open_directory(path)
        try:
            info = os.fstat(fd)
            if [str(info.st_dev), str(info.st_ino)] != pin:
                raise ValueError('Original output directory identity changed; output readback is unknown')
        finally: os.close(fd)


def observe(engine, task_id, frozen, document):
    if task_id is None:
        return {'status': 'unknown', 'reason': 'Original dispatch has no retained task identity; it must not be started again'}
    task = deepcopy(engine._tasks.get(task_id))
    if task is None:
        return {'status': 'unknown', 'reason': 'Original export task receipt is unavailable; no restart is authorized'}
    from .export_destination_policy import restore
    try:
        retained = restore(task['inputs']['destination_plan'])
        if (task.get('kind') != 'export' or task.get('attempt') != 0
                or retained.payload() != frozen['destination'] or task.get('recipe_persisted') is not True
                or task['inputs'].get('_trusted_destination_roots') != frozen['destination_roots']):
            raise ValueError('Original export snapshot identity changed')
        args = engine._task_args.get(task_id)
        if (args is None or args[8].get('destination_plan') != frozen['destination']
                or args[8].get('_trusted_destination_roots') != frozen['destination_roots']):
            raise ValueError('Original immutable export recipe is unavailable')
        entries = args[8].get('document_entries', {})
        if len(entries) != 1:
            raise ValueError('Original export contains unexpected documents')
        entry_id, entry = next(iter(entries.items()))
        if (entry.get('document_id') != document['document_id']
                or (entry.get('fingerprint') or {}).get('sha256') != document['source_sha256']
                or len(task.get('items', [])) != 1 or task['items'][0].get('path') != entry_id):
            raise ValueError('Original export source/document receipt changed')
        worker = getattr(engine, '_export', None)
        worker_live = bool(getattr(engine, '_export_task', None) is engine._tasks.get(task_id)
                           and worker is not None and worker.is_alive())
        if worker_live:
            return {'status': 'pending', 'owner_receipt_id': task_id}
        if task['state'] not in ('succeeded', 'failed', 'cancelled'):
            raise ValueError('Export worker ended without a terminal owner receipt')
        # Terminal observations must refer to the originally authorized directory,
        # never a same-path replacement that may hide a committed output.
        verify_destination_roots(frozen['destination_roots'])
        item = task['items'][0]
        targets = frozen['plan']['targets']
        if (item.get('state') == 'succeeded' and item.get('out') == targets[0]
                and item.get('destination_plan_id') == frozen['plan']['plan_id']):
            from .source_relocation_io import Budget, hash_file
            verify_destination_roots(frozen['destination_roots'])
            proof = hash_file(targets[0], Budget(lambda: False), expected_size=item.get('bytes'))
            verify_destination_roots(frozen['destination_roots'])
            if proof['bytes'] <= 0:
                raise ValueError('Export output is empty')
            return {'status': 'exported', 'plan_id': frozen['plan']['plan_id'],
                    'export_receipt_id': task_id,
                    'outputs': [{'path': proof['path'], 'sha256': proof['sha256'], 'size_bytes': proof['bytes']}]}
        # A failed worker may have crossed an atomic write boundary. A visible
        # target or derivative is never relabelled a clean failure/cancellation.
        if item.get('outputs') or any(os.path.lexists(path) for path in targets):
            raise ValueError('Export ended with possible committed output; retain and inspect the original task')
        verify_destination_roots(frozen['destination_roots'])
        # The legacy task does not carry an affirmative never-committed bit.
        # A writer can publish and then fail reading output metadata; another
        # actor can remove that path. Absence therefore cannot prove rollback.
        raise ValueError('Post-admission export has no affirmative no-commit receipt; retain the original task and do not retry')
    except Exception as error:
        return {'status': 'unknown', 'reason': str(error)[:2048] or 'Export outcome could not be verified'}
