"""Owned workflow export bridge, layered on the saved-project ingestion lease.

Only serialized commands enter this module. The existing ingestion, preset,
project, source and export owners remain authoritative. No automatic project
save, editor selection, recipe mutation, preset ACK or export retry is present.
"""
from copy import deepcopy
import os
from . import workflow_owner_protocol as P
from . import workflow_owner_export as E


class WorkflowOwner:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.session = None
        self.requests = {}
        self.operations = {}
        self.plans = {}
        self.preflights = {}

    def _lease(self, session_id, *, idle=False):
        owner = getattr(self.engine, '_ingest_session_host', None)
        if owner is None:
            raise ValueError('No real saved-project ingestion lease exists')
        lease = owner._session(session_id)
        if lease['owner'] != 'workflow':
            raise ValueError('The ingestion lease belongs to another producer')
        owner._identity(lease)
        if idle:
            if lease.get('operation_id') or lease.get('uncertain') or lease.get('stop_reason'):
                raise ValueError('Original ingestion is pending, uncertain or stopped; query it before export')
            owner._exact(lease)
        return owner, lease

    def _result(self, request, status, **fields):
        result = {'event': 'workflow_owner_result', 'protocol': P.PROTOCOL,
                  'request_id': request.get('request_id'), 'action': request.get('action'),
                  'session_id': request.get('session_id'), 'status': status,
                  'runtime_verified': False, **fields}
        self.emit(deepcopy(result))
        return result

    @staticmethod
    def _profile():
        return {'recipe_sha256': P.RECIPE_SHA256, 'recipe_profile': deepcopy(P.RECIPE_PROFILE)}

    @staticmethod
    def _filesystem(ordered, *, expected_destination_roots=None):
        from .source_relocation_io import open_directory, open_regular
        source, imported, exported = ordered[0]['operation'], ordered[1]['operation'], ordered[-1]['operation']
        from .session import IMAGE_EXTS
        if any('.' + extension not in IMAGE_EXTS for extension in source['extensions']):
            raise ValueError('Graph source extension is not accepted by the genuine managed importer')
        roots = [source['root'], imported['managed_root'], exported['output_root']]
        destination_roots = {}
        for path in roots:
            fd = open_directory(path)
            try:
                if path == exported['output_root']:
                    info = os.fstat(fd)
                    destination_roots[path] = [str(info.st_dev), str(info.st_ino)]
            finally: os.close(fd)
        if expected_destination_roots is not None and destination_roots != expected_destination_roots:
            raise ValueError('Pinned workflow output directory was replaced; no new directory is adopted')
        fd = open_regular(imported['project_path']); os.close(fd)
        for index, first in enumerate(roots):
            for second in roots[index + 1:]:
                if os.path.commonpath([first, second]) in (first, second):
                    raise ValueError('Watched, managed-original and export roots must be disjoint')
            if os.path.commonpath([first, imported['project_path']]) == first:
                raise ValueError('Saved project cannot be inside a workflow data root')
        from .export_destination_policy import inspect_directory
        from pathlib import Path
        if inspect_directory(Path(exported['output_root'])):
            raise ValueError('Workflow output directory must already exist')
        return destination_roots

    def _preflight(self, request):
        prior = self.preflights.get(request['request_id'])
        if prior is not None:
            if prior['request'] != request: raise ValueError('Preflight request identity was reused')
            return self._result(request, 'readback', **deepcopy(prior['value']))
        if request['request_id'] in self.requests:
            raise ValueError('Request identity belongs to an original operation')
        if len(self.preflights) >= 64:
            raise ValueError('Preflight receipt bound reached; retained identities are not evicted')
        value = {'supported': False, 'diagnostics': [], **self._profile()}
        try:
            owner, lease = self._lease(request['session_id'], idle=True)
            graph, ordered = P.graph(request['graph'], request['graph_sha256'])
            imported = ordered[1]['operation']
            if (lease['binding']['project_id'] != imported['project_id']
                    or lease['binding']['path'] != imported['project_path']):
                raise ValueError('Graph project differs from the actual saved-project lease')
            existing = self.session if self.session and self.session['session_id'] == request['session_id'] else None
            destination_roots = self._filesystem(ordered, expected_destination_roots=existing['destination_roots'] if existing else None)
            if self.pending():
                raise ValueError('Original workflow export remains unresolved; query it first')
            if len(self.requests) + 2 * lease['max_operations'] > P.MAX_REQUESTS:
                raise ValueError('Owner receipt capacity cannot retain both export phases for this bounded session')
            if self.session is not None and self.session['session_id'] == request['session_id']:
                if self.session['graph_sha256'] != request['graph_sha256']:
                    raise ValueError('This ingestion session is already bound to a different immutable graph')
            if ordered[1]['error_policy'] != 'stop':
                value['diagnostics'].append({'severity': 'error', 'code': 'import_policy_requires_stop',
                    'message': 'The genuine ingestion lease stops after any failed or cancelled import; skip cannot continue this session. Select stop for the managed-import node.'})
            if any(node['operation']['kind'] == 'compatible_preset' for node in ordered):
                value['diagnostics'].append({'severity': 'error', 'code': 'preset_owner_not_bound',
                    'message': 'This lease preserves editor selection. The real preset owner requires a loaded target and target-image review; this workflow bridge cannot safely apply it. Remove the preset node or finish the session and review it in the editor. No preset is silently skipped and no review acknowledgment is fabricated.'})
            if ordered[-1]['operation']['recipe_sha256'] != P.RECIPE_SHA256:
                value['diagnostics'].append({'severity': 'error', 'code': 'export_profile_mismatch',
                    'message': 'Choose the returned explicit export profile, save the graph and preflight again; an arbitrary recipe hash is not export authority.'})
            if not value['diagnostics']:
                current = self.session
                self.session = {'session_id': request['session_id'], 'graph_sha256': request['graph_sha256'],
                    'graph': graph, 'ordered': ordered, 'binding': deepcopy(lease['binding']),
                    'destination_roots': deepcopy(destination_roots),
                    'run_id': current.get('run_id') if current and current['session_id'] == request['session_id'] else None}
                value['supported'] = True
                value['diagnostics'].append({'severity': 'info', 'code': 'bounded_import_export',
                    'message': 'Real saved-project managed import and per-document frozen export are supported. Output conflicts stop without overwrite, rename, skip or implicit directory creation. Preset nodes are unsupported.'})
        except Exception as error:
            value['diagnostics'].append({'severity': 'error', 'code': 'owner_preflight_failed', 'message': str(error)[:2048]})
        self.preflights[request['request_id']] = {'request': deepcopy(request), 'value': deepcopy(value)}
        return self._result(request, 'readback', **value)

    def _bound(self, request, command):
        owner, lease = self._lease(request['session_id'], idle=True)
        session = self.session
        if session is None or session['session_id'] != request['session_id']:
            raise ValueError('This exact ingestion session has no supported workflow preflight')
        identity = command['identity']
        graph = session['graph']
        for key, expected in (('workflow_id', graph['workflow_id']), ('workflow_revision', graph['revision']),
                              ('graph_sha256', session['graph_sha256']),
                              ('project_id', session['binding']['project_id']),
                              ('node_id', session['ordered'][-1]['id'])):
            if identity[key] != expected:
                raise ValueError('Owner command differs from its preflight graph/project/node')
        if session['run_id'] is not None and session['run_id'] != identity['run_id']:
            raise ValueError('An ingestion lease cannot be silently reassigned to another workflow run')
        self._filesystem(session['ordered'], expected_destination_roots=session['destination_roots'])
        document = command['operation']['document']
        if (document['document_id'] != identity['document_id']
                or document['project_id'] != identity['project_id']
                or document['source_sha256'] != identity['source_sha256']):
            raise ValueError('Command document receipt differs from its source identity')
        row = self._document(owner, lease, identity, document)
        operation = command['operation']
        expected_export = session['ordered'][-1]['operation']
        if operation['kind'] == 'freeze_export':
            if operation['output_root'] != expected_export['output_root'] or operation['recipe_sha256'] != P.RECIPE_SHA256:
                raise ValueError('Export settings differ from the preflight profile')
        session['run_id'] = identity['run_id']
        return row

    def _document(self, owner, lease, identity, document):
        imported = owner.operations.get(document['receipt_id'])
        if (imported is None or imported['session_id'] != lease['session_id']
                or imported.get('status') != 'succeeded'):
            raise ValueError('Document does not have a successful import owned by this lease')
        # Re-read the actual durable receipt and managed provenance, not caller
        # supplied document JSON. This never starts or repeats an import.
        proofs = owner._committed_documents(imported, lease)
        matches = [proof for proof in proofs if proof['document_id'] == document['document_id']]
        if len(matches) != 1:
            raise ValueError('Imported document identity is not unique')
        proof = matches[0]
        if (proof['occurrence_id'] != identity['input_occurrence_id']
                or proof['source_sha256'] != document['source_sha256']
                or proof['revision'] != document['document_revision']
                or proof['import_receipt_id'] != document['receipt_id']):
            raise ValueError('Imported source/revision/occurrence proof differs from the original receipt')
        source = self.session['ordered'][0]['operation']
        if os.path.commonpath([source['root'], proof['original_path']]) != source['root']:
            raise ValueError('Imported source is outside the pinned watched root')
        relative = os.path.relpath(proof['original_path'], source['root'])
        if not source['recursive'] and os.path.dirname(relative):
            raise ValueError('Imported occurrence violates the non-recursive watched root')
        import hashlib
        occurrence = hashlib.sha256(P.encoded([proof['original_path'], relative, proof['stat'], proof['source_sha256']])).hexdigest()
        if occurrence != identity['input_occurrence_id']:
            raise ValueError('Imported occurrence is not bound to its exact original path/stat/content')
        if os.path.splitext(proof['original_path'])[1].lower().lstrip('.') not in source['extensions']:
            raise ValueError('Imported source extension is outside the pinned graph')
        managed_root = self.session['ordered'][1]['operation']['managed_root']
        if imported['request']['root'] != managed_root:
            raise ValueError('Managed original root differs from the preflight graph')
        rows = [row for row in self.engine._docs if row.get('document_id') == document['document_id']]
        if len(rows) != 1 or rows[0].get('trashed'):
            raise ValueError('Imported document is unavailable')
        row = rows[0]
        saved = [item for item in self.engine._project['docs'] if item.get('document_id') == document['document_id']]
        versions = [] if len(saved) != 1 else [version for version in saved[0].get('versions', [])
            if version.get('id') == saved[0].get('active_version') == row['recipe_version_id']]
        if len(versions) != 1 or P.digest(versions[0]['recipe']) != P.digest(self._encoded_recipe(row)):
            raise ValueError('Imported image recipe differs from the saved document')
        if (0 <= self.engine._doc_index < len(self.engine._docs)
                and row is self.engine._docs[self.engine._doc_index]):
            raise ValueError('Workflow will not substitute active editor state for its immutable imported recipe')
        return row

    def _encoded_recipe(self, row):
        from . import project as PJ, white_balance_recipe as WB
        dropped = []
        encoded = PJ.encode(WB.normalize_state(row['state']), deepcopy(self.engine._project['assets']), dropped, 'recipe')
        if dropped: raise ValueError('Workflow recipe cannot be retained losslessly')
        return encoded

    def _row_stamp(self, row):
        from .virtual_copy_people import encode
        return P.digest({'people_context': encode(row), 'recipe': self._encoded_recipe(row), **{key: row.get(key) for key in (
            'document_id', 'document_revision', 'recipe_version_id', 'source_asset_id', 'path',
            'fingerprint', 'managed_import', 'import_origin', 'copy_number')}})

    def pending(self):
        return any(record['command']['operation']['kind'] == 'start_export'
                   and record['receipt']['result']['status'] in ('pending', 'unknown')
                   for record in self.operations.values())

    @staticmethod
    def _receipt(command, result):
        return {'schema_version': 1, 'identity': deepcopy(command['identity']), 'result': deepcopy(result)}

    def _publish(self, request, record, *, query=False):
        receipt = record['receipt']
        status = receipt['result']['status']
        outer = 'readback' if query else status if status in ('pending', 'unknown', 'failed') else 'succeeded'
        return self._result(request, outer, receipt=deepcopy(receipt))

    def _execute(self, request):
        command = P.command(request['command'])
        rid, oid = request['request_id'], command['identity']['operation_id']
        prior = self.requests.get(rid)
        if prior is not None:
            if prior['request'] != request: raise ValueError('Request identity conflicts with its retained original')
            return self._publish(request, prior)
        if rid in self.preflights: raise ValueError('Request identity belongs to a retained preflight')
        original = self.operations.get(oid)
        if original is not None:
            if original['command'] != command or original['request']['session_id'] != request['session_id']:
                raise ValueError('Operation identity conflicts with its retained original')
            # A different transport id is not permission to dispatch again.
            return self._publish(request, original)
        if len(self.requests) >= P.MAX_REQUESTS:
            return self._result(request, 'failed', dispatch_rejected=True, receipt=self._receipt(command,
                {'status': 'failed', 'code': 'owner_receipt_capacity',
                 'message': 'Workflow owner receipt capacity reached before dispatch; no original is evicted',
                 'retained_document': None}))
        unresolved = self.pending()
        operation = command['operation']
        record = {'request': deepcopy(request), 'command': command,
                  'receipt': self._receipt(command, {'status': 'unknown', 'reason': 'Original admission is not yet settled'}),
                  'dispatch_started': False, 'task_id': None}
        self.requests[rid] = record; self.operations[oid] = record
        try:
            if unresolved: raise ValueError('Original export is pending or uncertain; only query its receipt')
            row = self._bound(request, command)
            if operation['kind'] == 'freeze_export':
                frozen = E.freeze(self.engine, row, operation['document'], operation['output_root'],
                                  self.session['graph']['revision'], rid, self.session['destination_roots'])
                frozen['row_stamp'] = self._row_stamp(row)
                frozen['document'] = deepcopy(operation['document'])
                frozen['identity'] = deepcopy(command['identity'])
                frozen['start_operation'] = None
                if frozen['plan']['plan_id'] in self.plans:
                    raise ValueError('A frozen plan already exists; query the original freeze operation')
                self.plans[frozen['plan']['plan_id']] = frozen
                record['receipt'] = self._receipt(command, {'status': 'export_frozen', 'plan': frozen['plan']})
            else:
                plan = operation['plan']
                frozen = self.plans.get(plan['plan_id'])
                if (frozen is None or frozen['plan'] != plan or frozen['document'] != operation['document']
                        or frozen['row_stamp'] != self._row_stamp(row)):
                    raise ValueError('Export plan/recipe is not the exact retained owner freeze')
                for key in ('workflow_id', 'workflow_revision', 'graph_sha256', 'run_id', 'input_occurrence_id',
                            'source_sha256', 'project_id', 'document_id', 'node_id'):
                    if frozen['identity'][key] != command['identity'][key]:
                        raise ValueError('Frozen export belongs to another workflow/document/source')
                if frozen['start_operation'] is not None:
                    raise ValueError('Frozen export has an original start; only query it')
                # Last pre-dispatch real planner read catches external destination
                # changes. It never changes names or accepts a client plan.
                if E.preview(self.engine, frozen['command'], frozen['destination_roots']) != frozen['destination']:
                    raise ValueError('Export source/destination changed after freeze; no write was started')
                frozen['start_operation'] = oid
                record['frozen'] = frozen
                record['dispatch_started'] = True
                result, record['task_id'] = E.start(self.engine, frozen, rid)
                record['receipt'] = self._receipt(command, result)
        except Exception as error:
            result = ({'status': 'unknown', 'reason': str(error)[:2048]} if record['dispatch_started'] else
                      {'status': 'failed', 'code': 'owner_admission_rejected', 'message': str(error)[:2048], 'retained_document': None})
            record['receipt'] = self._receipt(command, result)
        return self._publish(request, record)

    def _query(self, request):
        record = self.requests.get(request['original_request_id'])
        if (record is None or record['command']['identity']['operation_id'] != request['operation_id']
                or record['request']['session_id'] != request['session_id']):
            return self._result(request, 'unknown', error='Original owner receipt is unavailable; no replay or replacement operation is authorized')
        self._lease(request['session_id'])
        if record['receipt']['result']['status'] in ('pending', 'unknown') and record['dispatch_started']:
            result = E.observe(self.engine, record['task_id'], record['frozen'], record['command']['operation']['document'])
            record['receipt'] = self._receipt(record['command'], result)
            if result['status'] in ('exported', 'failed', 'cancelled'):
                # Settle the ORIGINAL native mutation fence with its own exact
                # identity before returning the separate read-only query reply.
                self._publish(record['request'], record)
        return self._publish(request, record, query=True)

    def handle(self, payload):
        request = payload if type(payload) is dict else {}
        try:
            request = P.envelope(payload)
            if request['action'] == 'profile':
                return self._result(request, 'readback', supported=True, **self._profile())
            if request['action'] == 'preflight': return self._preflight(request)
            if request['action'] == 'execute': return self._execute(request)
            if request['action'] == 'query': return self._query(request)
            # There is no retained review in this bounded version. A review_id
            # is not authorization and cannot be exchanged for a synthetic ACK.
            self._lease(request['session_id'])
            return self._result(request, 'failed', error='No real preset review is owned by this workflow bridge; preset graphs fail preflight and must be reviewed in the editor after the session is safely released')
        except Exception as error:
            return self._result(request, 'unknown' if request.get('action') == 'query' else 'failed', error=str(error)[:2048])


def controller(engine, emit):
    owner = getattr(engine, '_workflow_owner_host', None)
    if owner is None:
        owner = WorkflowOwner(engine, emit)
        engine._workflow_owner_host = owner
    return owner


def handle(engine, payload, emit):
    return controller(engine, emit).handle(payload)


def ingest_passthrough(engine, payload):
    """Strict lease-gate admission only; never bypasses other subsystem guards."""
    try:
        request = P.envelope(payload)
        if request['action'] == 'profile': return True
        ingestion = getattr(engine, '_ingest_session_host', None)
        if ingestion is None: return False
        lease = ingestion._session(request['session_id'])
        if lease['owner'] != 'workflow': return False
        ingestion._identity(lease)
        if request['action'] in ('query', 'open_review'):
            owner = getattr(engine, '_workflow_owner_host', None)
            if owner is None: return request['action'] == 'query'  # Unknown readback, never redispatch.
            if request['action'] == 'query':
                record = owner.requests.get(request['original_request_id'])
                return record is None or (record['request']['session_id'] == request['session_id']
                    and record['command']['identity']['operation_id'] == request['operation_id'])
            return False  # No synthetic or unretained preset review route.
        return not (lease.get('operation_id') or lease.get('uncertain') or lease.get('stop_reason'))
    except (ValueError, TypeError, KeyError, OSError):
        return False


def guard_command(engine, name, payload):
    """The ingestion lease cannot be released/reused while export is unresolved."""
    owner = getattr(engine, '_workflow_owner_host', None)
    if owner is None or not owner.pending(): return
    if name in ('hello', 'ping', 'status', 'shutdown'): return
    if name == 'workflow_owner' and payload.get('action') in ('query', 'profile'): return
    if name == 'ingest_session' and payload.get('action') in ('state', 'query'): return
    if name == 'project' and payload.get('action') == 'state': return
    if name == 'session' and payload.get('action') == 'query': return
    raise ValueError('Original workflow export is pending or uncertain; query its exact receipt before releasing the lease, importing, editing or starting another output')


def dispatch_rejected(engine, payload, error, started, emit):
    from .workflow_owner_dispatch import rejected
    return rejected(engine, payload, error, started, emit)
