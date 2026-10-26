"""Bounded group handoff into the canonical export planner and task owner.

The caller owns successful-batch/version verification. This adapter owns no
renderer, file writer, retry loop, or parallel task ledger. Records retain only
handoff identities; all item outcomes come from the original canonical task.
"""
from copy import deepcopy
from hashlib import sha256

_OPTIONS = frozenset(('out_dir', 'format', 'quality', 'tile', 'target_size',
    'scale', 'sharpen', 'upscale_backend', 'bit_depth', 'output_profile',
    'tiff_compression', 'metadata_include_gps', 'conflict_policy', 'watermark', 'layout'))
_TERMINAL = frozenset(('succeeded', 'failed', 'cancelled'))


def _identity(value):
    if type(value) is not str or not 1 <= len(value) <= 128:
        raise ValueError('Group export requires a bounded exact request identity')
    return value


class GroupExport:
    def __init__(self, engine, verify):
        self.engine, self.verify = engine, verify
        self.records = {}

    def _documents(self, token):
        # verify must check original successful group receipt, workspace, source
        # proofs and post-commit versions, not the current UI selection.
        docs = self.verify(token)
        if (type(docs) is not list or not 1 <= len(docs) <= 8
                or any(type(doc) is not str or not doc for doc in docs)
                or len(set(docs)) != len(docs)):
            raise ValueError('Export needs the exact successful bounded group')
        return list(docs)

    def preview(self, token, request_id, export_options, policy, intent_revision):
        _identity(request_id)
        previous = self.records.get(token)
        if previous and previous.get('claimed') and not previous.get('rejection'):
            raise ValueError('Original export was dispatched; query that task, do not create another')
        docs = self._documents(token)
        if type(export_options) is not dict or set(export_options) - _OPTIONS:
            raise ValueError('Group export accepts only existing export settings, never replacement targets')
        if export_options.get('layout') is not None:
            raise ValueError('Group delivery supports individual photos only; disable layout or use ordinary layout export')
        if type(policy) is not dict or type(intent_revision) is not int or intent_revision < 0:
            raise ValueError('Choose an explicit export destination and settings revision')
        # The canonical planner validates profiles, layouts, paths and conflicts.
        # No fallback to a plan from a previous preview if this attempt fails.
        self.records.pop(token, None)
        command = {**deepcopy(export_options), 'cmd': 'export', 'action': 'preview',
            'request_id': request_id, 'document_ids': docs,
            'destination_policy': deepcopy(policy), 'intent_revision': intent_revision}
        events = []
        self.engine.cmd_export(command, trusted_result=events.append)
        replies = [e for e in events if e.get('event') == 'export_destination_result'
                   and e.get('request_id') == request_id]
        if len(replies) != 1 or replies[0].get('status') != 'ready':
            raise ValueError(str(replies[0].get('error')) if len(replies) == 1
                             else 'Canonical export planner returned no exact preview')
        from .export_destination_policy import restore
        plan = restore(replies[0]['value']).payload()
        expected = {'document:' + sha256(doc.encode('utf-8')).hexdigest() for doc in docs}
        primary = {e['item_id'] for e in plan['entries'] if e['item_id'] in expected}
        if primary != expected or len([e for e in plan['entries'] if e['item_id'] in expected]) != len(docs):
            raise ValueError('Canonical export preview does not contain the complete group')
        if self._documents(token) != docs:
            raise ValueError('Group changed during destination preview')
        self.records[token] = {'command': command, 'destination': plan, 'documents': docs,
                               'claimed': False, 'task_id': None, 'cancel_requested': False}
        return {'export_status': 'preview', 'destination': deepcopy(plan),
                'export_document_ids': docs, 'output_completion_verified': False}

    def start(self, token, request_id, plan_id, intent_revision):
        _identity(request_id)
        record = self.records.get(token)
        if (record is None or record['destination']['plan_id'] != plan_id
                or type(intent_revision) is not int
                or record['destination']['intent_revision'] != intent_revision):
            raise ValueError('Preview the exact group destination before export')
        if record['claimed']:
            if request_id != record.get('request_id'):
                raise ValueError('An original export already exists; only query its result')
            return self._observe(token)
        docs = self._documents(token)
        if docs != record['documents']:
            raise ValueError('Successful batch identity changed before export')
        if any(e['disposition'] == 'needs_confirmation' for e in record['destination']['entries']):
            raise ValueError('Resolve conflicts with the existing destination controls and preview again')
        command = {**deepcopy(record['command']), 'action': 'start', 'request_id': request_id,
                   'destination_plan_id': plan_id}
        before = set(self.engine._tasks)
        events, error = [], None
        # Record uncertainty before invoking the canonical mutation boundary.
        record.update(claimed=True, request_id=request_id)
        try:
            self.engine.cmd_export(command, trusted_result=events.append)
        except Exception as exc:
            error = str(exc)[:2000]
        created = set(self.engine._tasks) - before
        if not created:
            errors = [e for e in events if e.get('event') == 'error' and e.get('error')]
            if error is None and len(errors) == 1:
                # With destination_policy there is no output/dir write before
                # task admission; one exact canonical rejection proves no start.
                record['rejection'] = str(errors[0]['error'])[:2000]
                return self._observe(token)
            record['unknown'] = error or 'No unique task or definitive no-start rejection was returned'
            return self._observe(token)
        if len(created) != 1:
            record['unknown'] = 'Export dispatch did not produce one unique original task'
            return self._observe(token)
        task_id = created.pop()
        task = self.engine._tasks[task_id]
        if (task.get('kind') != 'export' or task.get('attempt') != 0
                or task.get('inputs', {}).get('destination_plan') != record['destination']):
            record['unknown'] = 'Created task does not own the exact frozen destination plan'
            return self._observe(token)
        record['task_id'] = task_id
        record['entries'] = deepcopy(task['inputs'].get('document_entries'))
        if error:
            record['dispatch_error'] = error
        return self._observe(token)

    def observe(self, token, task_id):
        record = self.records.get(token)
        if record is None or task_id != record.get('task_id'):
            raise ValueError('Only the exact original task may be observed')
        return self._observe(token)

    def _observe(self, token):
        record = self.records.get(token)
        if record is None:
            raise ValueError('Original group export handoff is unavailable; no automatic restart')
        base = {'export_task_id': record['task_id'], 'export_document_ids': list(record['documents']),
                'destination': deepcopy(record['destination']), 'output_completion_verified': False}
        if record.get('rejection'):
            return {**base, 'export_status': 'failed', 'export_no_start': True,
                    'error': record['rejection']}
        if not record['claimed']:
            return {**base, 'export_status': 'preview'}
        if record['task_id'] is None:
            return {**base, 'export_status': 'unknown', 'error': record.get('unknown', 'Task identity unavailable')}
        try:
            task = deepcopy(self.engine._tasks.get(record['task_id']))
            args = self.engine._task_args.get(record['task_id'])
            if (not task or task.get('kind') != 'export' or task.get('attempt') != 0
                    or task.get('recipe_persisted') is not True
                    or task.get('inputs', {}).get('destination_plan') != record['destination']
                    or task['inputs'].get('document_entries') != record['entries']
                    or args is None or args[8].get('destination_plan') != record['destination']
                    or args[8].get('document_entries') != record['entries']):
                raise ValueError('Original immutable task/recipe was removed, retried or changed')
            entries = record['entries']
            if (type(entries) is not dict or len(entries) != len(record['documents'])
                    or [entry.get('document_id') for entry in entries.values()] != record['documents']):
                raise ValueError('Original task contains a different document group')
            expected_items = list(entries)
            if record['command'].get('layout'):
                from .layout_spec import LAYOUT_ITEM
                expected_items.append(LAYOUT_ITEM)
            if [item.get('path') for item in task['items']] != expected_items:
                raise ValueError('Original task item identity changed')
            items = deepcopy(task['items'])
            primary = {entry['item_id']: entry for entry in record['destination']['entries']}
            for item in items:
                if item.get('state') not in ('pending', 'succeeded', 'failed', 'skipped'):
                    raise ValueError('Original item outcome is not recognized')
                if item.get('document_id') != entries[item['path']]['document_id']:
                    raise ValueError('Original item document identity changed')
                if item['state'] == 'succeeded' and (
                        item.get('out') != primary[item['path']]['target']
                        or item.get('destination_plan_id') != record['destination']['plan_id']):
                    raise ValueError('Successful item does not name its exact frozen output')
            counts = {state: sum(item.get('state') == state for item in items)
                      for state in ('pending', 'succeeded', 'failed', 'skipped')}
            worker_live = self.engine._task_worker_is_live(self.engine._tasks[record['task_id']])
            state = task.get('state')
            # A terminal ledger row while its worker still unwinds is not a
            # reason to start another batch or erase already committed items.
            if not worker_live and state not in _TERMINAL:
                raise ValueError('Original worker ended without a terminal task receipt')
            public_state = ('queued' if state == 'queued' else 'running') if worker_live else state
            if not worker_live and ((counts['succeeded'] and (counts['failed'] or counts['skipped'] or counts['pending']))
                                    or (state == 'succeeded' and (counts['skipped'] or counts['failed'] or counts['pending']))):
                public_state = 'partial'
            if public_state == 'succeeded' and any(
                    output.get('skipped') or output.get('error')
                    for item in items for output in item.get('outputs', [])):
                public_state = 'partial'
            return {**base, 'export_status': public_state,
                    'export_task_state': state, 'export_item_counts': counts, 'items': items,
                    'cancel_requested': record['cancel_requested'],
                    'export_receipt_only': True,
                    'note': 'Canonical task receipts only; outputs are not independently hash-verified, and partial/skipped/cancelled items remain distinct'}
        except Exception as exc:
            return {**base, 'export_status': 'unknown', 'error': str(exc)[:2000]}

    def cancel(self, token, task_id):
        result = self.observe(token, task_id)
        record = self.records[token]
        if result['export_status'] not in ('queued', 'running') or record['cancel_requested']:
            return result
        # Existing lifecycle owns the safe item boundary; no file cleanup or
        # rollback. Never address "all" or a presumed most-recent export.
        record['cancel_requested'] = True
        self.engine.cmd_task({'cmd': 'task', 'action': 'cancel', 'task': record['task_id']})
        return self._observe(token)
