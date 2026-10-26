# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit receipt-bound handoff to canonical save and export owners.

Session capabilities and dispatch deduplication only: batch remains the history
owner, project persistence owns CAS and export tasks own output truth. UNRUN.
"""
from copy import deepcopy
from .optics_candidate_identity import fingerprint
from . import full_candidate_render as full

BASE = {'cmd', 'action', 'request_id', 'preflight_token', 'batch_id'}
KEYS = {
    'portrait_preset_save': BASE,
    'portrait_preset_export_preview': BASE | {'export_options', 'policy', 'intent_revision'},
    'portrait_preset_export_start': BASE | {'plan_id', 'intent_revision'},
    'portrait_preset_export_status': BASE | {'task_id'},
    'portrait_preset_export_cancel': BASE | {'task_id'},
}
ACTIONS = frozenset(KEYS)
READS = frozenset(('portrait_preset_export_preview', 'portrait_preset_export_status'))


def command(p):
    if type(p) is not dict or p.get('cmd') != 'batch' or p.get('action') not in ACTIONS:
        return False
    if set(p) != KEYS[p['action']]:
        return False
    if any(type(p.get(k)) is not str or not 1 <= len(p[k]) <= 128
           for k in ('request_id', 'preflight_token', 'batch_id')):
        return False
    if len(p['preflight_token']) != 32 or any(c not in '0123456789abcdef' for c in p['preflight_token']):
        return False
    if 'intent_revision' in p and (type(p['intent_revision']) is not int or not 0 <= p['intent_revision'] <= 2**53-1):
        return False
    if any(type(p[k]) is not str or not 1 <= len(p[k]) <= 128 for k in ('plan_id', 'task_id') if k in p):
        return False
    return all(type(p[k]) is dict for k in ('export_options', 'policy') if k in p)


def identity(p):
    return {'delivery': True, **{k: deepcopy(p[k]) for k in
        ('preflight_token', 'batch_id', 'plan_id', 'intent_revision', 'task_id') if k in p}}


class GroupDelivery:
    def __init__(self, owner):
        self.owner = owner
        self.proofs = {}
        self.receipts = {}
        self.saves = {}
        from .portrait_preset_group_export import GroupExport
        self.export = GroupExport(owner.engine, self.documents)

    def capture(self, token, result):
        # Called after canonical BatchSync commit, before publishing success.
        if len(self.proofs) >= 64:
            raise ValueError('Group delivery session capacity reached; no output was started')
        ledger = self.owner.batch.ledger.get(result['batch_id'])
        if ledger is None or ledger.get('undone'):
            raise ValueError('Successful group has no canonical applied history')
        retained = 'people_scoped_changes' in ledger
        if retained and (ledger.get('ops') != ['lnx.people_graph.v1']
                or ledger.get('people_changes') != [] or not ledger['people_scoped_changes']):
            raise ValueError('Retained group needs canonical scoped graph history')
        rows = [self.owner._row(doc)[1] for doc in result['approved_document_ids']]
        targets = []
        for row in rows:
            version = self.owner.batch.versions.version(row)
            proof, _, _ = full.identity(self.owner.engine, row, row['state'], version.document_id, str(version.revision))
            targets.append({'row': row, 'proof': proof,
                           'history': fingerprint((row['undo'], row['redo']))})
        self.proofs[token] = {'batch_id': result['batch_id'], 'workspace': self.owner.batch.versions.workspace,
                              'targets': targets, 'project_path': self.owner.engine._project_path,
                              'retained_people': retained, 'ledger_sha256': fingerprint(ledger)}
        self.verify(token, result['batch_id'])
        return {'delivery_targets': [{'document_id': t['proof']['document_id'], 'revision': t['proof']['revision']}
                                     for t in targets], 'workspace_generation': self.owner.batch.versions.workspace}

    def verify(self, token, batch_id=None):
        record = self.proofs.get(token)
        if record is None or (batch_id is not None and record['batch_id'] != batch_id):
            raise ValueError('Original successful group delivery capability is unavailable')
        owner, engine = self.owner, self.owner.engine
        if record['workspace'] != owner.batch.versions.workspace or record['project_path'] != engine._project_path:
            raise ValueError('Group project/workspace changed; do not deliver a different project')
        recovery = engine.__dict__.get('_project_recovery_runtime')
        if recovery is not None and recovery.tainted:
            raise ValueError('Resolve uncertain project state before group delivery')
        ledger = owner.batch.ledger.get(record['batch_id'])
        if (ledger is None or ledger.get('undone')
                or fingerprint(ledger) != record['ledger_sha256']):
            raise ValueError('Original group history is unavailable, undone or changed')
        entries = list(ledger['targets'].values())
        docs = [t['proof']['document_id'] for t in record['targets']]
        if len(entries) != len(docs) or {e['document_id'] for e in entries} != set(docs):
            raise ValueError('Canonical group ledger membership changed')
        rows = []
        for target in record['targets']:
            expected = target['proof']; _, row = owner._row(expected['document_id'])
            actual, _, _ = full.identity(engine, row, row['state'], expected['document_id'], expected['revision'])
            entry = next(e for e in entries if e['document_id'] == expected['document_id'])
            if record['retained_people']:
                from .people_batch_ledger import reviewed_refs, verify_reviewed_refs
                refs = reviewed_refs(entry)
                if not refs or entry['revision'] + 1 != int(expected['revision']):
                    raise ValueError('Retained group lacks its exact applied face history revision')
                verify_reviewed_refs(engine, row, entry)
                recipe_matches = True  # Full identity below fences recipe AND graph/context.
            else:
                recipe_matches = fingerprint(entry['after']) == expected['candidate_sha256']
            if (row is not target['row'] or actual != expected
                    or fingerprint((row['undo'], row['redo'])) != target['history']
                    or not recipe_matches
                    or entry.get('source_proof') != expected['source_proof']):
                raise ValueError('Group target source, version, people context or history changed')
            rows.append(row)
        return rows

    def uncertain(self, p):
        old = self.receipts.get(p.get('request_id'))
        if old and old[1].get('outcome_unknown'):
            return True
        record = self.export.records.get(p.get('preflight_token'), {})
        return bool((p.get('action') == 'portrait_preset_export_start'
                     and record.get('claimed') and record.get('request_id') == p.get('request_id')
                     and not record.get('rejection'))
                    or (p.get('action') == 'portrait_preset_export_cancel' and record.get('cancel_requested')))

    def documents(self, token):
        return [row['document_id'] for row in self.verify(token)]

    def _reconcile_start(self, token, result):
        # A verified original task can settle a lost/unknown start reply, but
        # never manufactures a new dispatch or blesses a different request.
        record = self.export.records[token]
        request = {'cmd': 'batch', 'action': 'portrait_preset_export_start',
                   'request_id': record['request_id'], 'preflight_token': token,
                   'batch_id': self.proofs[token]['batch_id'],
                   'plan_id': record['destination']['plan_id'],
                   'intent_revision': record['destination']['intent_revision']}
        replay = {**result, **identity(request), 'export_reconciled': True}
        replay.pop('task_id', None)
        self.receipts[request['request_id']] = (fingerprint(request), deepcopy(replay))
        self.owner.batch.preflight.emit_result(request, replay)

    def run(self, p):
        if not command(p):
            raise ValueError('Invalid group delivery command')
        action, token, request_id = p['action'], p['preflight_token'], p['request_id']
        if action in ('portrait_preset_export_preview', 'portrait_preset_export_start') and self.saves.get(token, {}).get('outcome_unknown'):
            raise ValueError('Original group save is unresolved; do not start an output handoff')
        old = self.receipts.get(request_id)
        key = fingerprint(p)
        if old is not None:
            if old[0] != key:
                raise ValueError('Delivery request identity cannot authorize different work')
            return deepcopy(old[1])
        if action not in READS and len(self.receipts) >= 256:
            raise ValueError('Delivery receipt capacity reached; resolve existing session work')
        record = self.proofs.get(token)
        if record is None or record['batch_id'] != p['batch_id']:
            raise ValueError('Delivery must name its exact original successful batch')
        base = {'success': True, 'portrait_preset': True, 'outcome_unknown': False, **identity(p)}
        # No recipe mutation here. Save owns its disk CAS; export owns jobs.
        if action == 'portrait_preset_save':
            if token in self.saves:
                return {**deepcopy(self.saves[token]), **identity(p), 'replayed': True}
            rows = self.verify(token, p['batch_id'])
            why = self.owner.batch.editor.guard('group save')
            if why:
                raise ValueError(why)
            pending = {**base, 'success': False, 'outcome_unknown': True, 'save_status': 'unknown',
                       'error': 'Original group save is claimed; do not repeat it'}
            self.receipts[request_id] = (key, pending)
            self.saves[token] = pending
            from .portrait_preset_group_save import save
            try:
                outcome = save(self.owner.engine, rows, lambda: self.verify(token, p['batch_id']),
                               batch_id=p['batch_id'] if record['retained_people'] else None)
                if outcome.get('status') != 'succeeded':
                    result = {**pending, 'error': str(outcome.get('error') or 'Group project replacement outcome is unknown')}
                else:
                    result = {**base, 'save_status': 'saved', 'saved_project_sha256': outcome['sha256']}
            except Exception as error:
                # The persistence owner never throws after a possible replace;
                # it returns Unknown instead. A pre-replace rejection is retryable.
                result = {**base, 'success': False, 'no_write': True, 'save_status': 'not_saved', 'error': str(error)[:2000]}
                self.saves.pop(token, None)
            else:
                self.saves[token] = deepcopy(result)
        elif action == 'portrait_preset_export_preview':
            self.verify(token, p['batch_id'])
            result = {**base, **self.export.preview(token, request_id, p['export_options'], p['policy'], p['intent_revision'])}
        elif action == 'portrait_preset_export_start':
            self.verify(token, p['batch_id'])
            result = {**base, **self.export.start(token, request_id, p['plan_id'], p['intent_revision'])}
        elif action == 'portrait_preset_export_status':
            result = {**base, **self.export.observe(token, p['task_id'])}
            if result.get('export_status') != 'unknown':
                self._reconcile_start(token, result)
        else:
            result = {**base, **self.export.cancel(token, p['task_id'])}
        if result.get('export_no_start') is True:
            result.update(success=False, outcome_unknown=False, no_write=True)
        if result.get('export_status') == 'unknown':
            result.update(success=False, outcome_unknown=True, error=result.get('error') or 'Original export outcome is unknown')
        if action not in READS:
            self.receipts[request_id] = (key, deepcopy(result))
        return result

