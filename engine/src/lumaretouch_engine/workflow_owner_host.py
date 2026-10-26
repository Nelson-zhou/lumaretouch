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
        from .workflow_preset_handoff import PresetHandoff
        self.presets = PresetHandoff(self)

    def _lease(self, session_id, *, idle=False):
        owner = getattr(self.engine, '_ingest_session_host', None)
        if owner is None:
            raise ValueError('No real saved-project ingestion lease exists')
        lease = owner._session(session_id)
        if lease['owner'] != 'workflow':
            raise ValueError('The ingestion lease belongs to another producer')
        if self.presets.active is not None:
            if self.presets.active['session_id'] != session_id:
                raise ValueError('Preset handoff belongs to another lease')
            self.presets._check()
            if idle: raise ValueError('Preset handoff is not back at its clean armed boundary')
            return owner, lease
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
        return {'recipe_sha256': P.RECIPE_SHA256, 'recipe_profile': deepcopy(P.RECIPE_PROFILE),
                'export_profiles': P.export_profiles()}

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
            receipt_phases = 4 if any(node['operation']['kind'] in ('compatible_preset', 'automatic_preset') for node in ordered) else 2
            if len(self.requests) + receipt_phases * lease['max_operations'] > P.MAX_REQUESTS:
                raise ValueError('Owner receipt capacity cannot retain every preset and export phase for this bounded session')
            if self.session is not None and self.session['session_id'] == request['session_id']:
                if self.session['graph_sha256'] != request['graph_sha256']:
                    raise ValueError('This ingestion session is already bound to a different immutable graph')
            if ordered[1]['error_policy'] != 'stop':
                value['diagnostics'].append({'severity': 'error', 'code': 'import_policy_requires_stop',
                    'message': 'The genuine ingestion lease stops after any failed or cancelled import; skip cannot continue this session. Select stop for the managed-import node.'})
            preset_nodes = [node for node in ordered if node['operation']['kind'] in ('compatible_preset', 'automatic_preset')]
            automatic = bool(preset_nodes and preset_nodes[0]['operation']['kind'] == 'automatic_preset')
            if preset_nodes:
                from .workflow_preset_catalogue import resolve
                from .workflow_preset_review import support_reason
                selected = preset_nodes[0]
                if automatic:
                    from .workflow_auto_preset import support_reason
                preset = resolve(selected['operation']['preset_id'], selected['operation']['preset_sha256'])
                reason = support_reason(preset, selected['operation']['intent']) if automatic else support_reason(preset)
                if reason: raise ValueError(reason)
                if not automatic and selected['error_policy'] != 'stop': raise ValueError('Reviewed preset handoff currently requires stop-on-error')
                if not self.engine._image_loaded or not self.engine._load_id or self.engine._doc_index < 0:
                    raise ValueError('Open a saved editor document before starting a preset workflow; review must return to that exact document')
            selected_hash = ordered[-1]['operation']['recipe_sha256']
            try:
                selected_profile = P.resolve_export_profile(selected_hash, automatic=automatic)
                value.update(recipe_sha256=selected_hash, recipe_profile=selected_profile)
            except ValueError as error:
                value['diagnostics'].append({'severity': 'error', 'code': 'export_profile_mismatch',
                    'message': str(error)})
            if not value['diagnostics']:
                current = self.session
                if automatic:
                    from .workflow_auto_preset import AutomaticPresetHandoff
                    if not isinstance(self.presets, AutomaticPresetHandoff):
                        self.presets = AutomaticPresetHandoff(self)
                else:
                    from .workflow_preset_handoff import PresetHandoff
                    if type(self.presets) is not PresetHandoff:
                        self.presets = PresetHandoff(self)
                self.session = {'session_id': request['session_id'], 'graph_sha256': request['graph_sha256'],
                    'graph': graph, 'ordered': ordered, 'binding': deepcopy(lease['binding']),
                    'destination_roots': deepcopy(destination_roots),
                    'run_id': current.get('run_id') if current and current['session_id'] == request['session_id'] else None}
                value['supported'] = True
                value['diagnostics'].append({'severity': 'info', 'code': 'bounded_import_export',
                    'message': ('Explicit automatic directory job: fixed exposure/WB and explicitly opted-in own-face finish/texture, canonical apply/history/save/return, then frozen export. Native start requires fresh graph-bound opt-in. No human image review is claimed; unknown outcomes remain query-only.' if automatic else
                        'Real saved-project managed import and per-document frozen export are supported. Output conflicts do not overwrite or rename. Supported reviewed presets pause for actual image approval, explicit save and verified editor return.')})
        except Exception as error:
            value['diagnostics'].append({'severity': 'error', 'code': 'owner_preflight_failed', 'message': str(error)[:2048]})
        self.preflights[request['request_id']] = {'request': deepcopy(request), 'value': deepcopy(value)}
        return self._result(request, 'readback', **value)

    def _bound(self, request, command):
        applying = command['operation']['kind'] == 'apply_preset'
        owner, lease = self._lease(request['session_id'], idle=not applying)
        session = self.session
        if session is None or session['session_id'] != request['session_id']:
            raise ValueError('This exact ingestion session has no supported workflow preflight')
        identity = command['identity']
        graph = session['graph']
        for key, expected in (('workflow_id', graph['workflow_id']), ('workflow_revision', graph['revision']),
                              ('graph_sha256', session['graph_sha256']),
                              ('project_id', session['binding']['project_id']),
                              ('node_id', (self.presets.node() if command['operation']['kind'] in ('preflight_preset', 'apply_preset') else session['ordered'][-1])['id'])):
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
        row = self.presets._check(target_loaded=True)[1] if applying else self._document(owner, lease, identity, document)
        operation = command['operation']
        if operation['kind'] in ('preflight_preset', 'apply_preset'):
            expected_preset = self.presets.node()['operation']
            if operation['preset_id'] != expected_preset['preset_id']:
                raise ValueError('Preset differs from the exact preflight graph')
            actual_hash = operation.get('preset_sha256', (operation.get('assessment') or {}).get('preset_sha256'))
            if actual_hash != expected_preset['preset_sha256']:
                raise ValueError('Preset version differs from the exact preflight graph')
            if operation['kind'] == 'apply_preset':
                automatic = expected_preset['kind'] == 'automatic_preset'
                assessment = operation['assessment']
                if (assessment['requires_review'] is not (not automatic)
                        or (automatic and assessment['review'] is not None)
                        or (not automatic and assessment['review'] is None)):
                    raise ValueError('Assessment authority mode differs from the exact graph node')
        expected_export = session['ordered'][-1]['operation']
        if operation['kind'] == 'freeze_export':
            if operation['output_root'] != expected_export['output_root'] or operation['recipe_sha256'] != expected_export['recipe_sha256']:
                raise ValueError('Export settings differ from the preflight profile')
        session['run_id'] = identity['run_id']
        return row

    def _document(self, owner, lease, identity, document, *, expected_current_revision=None):
        completed = self.presets.completed.get(document['receipt_id'])
        if completed is not None:
            if document != completed['document'] or identity['input_occurrence_id'] != completed['identity']['input_occurrence_id']:
                raise ValueError('Preset-result chain does not match this exact occurrence')
            # The original durable import proves origin, not the new applied
            # revision. The completed row stamp separately proves the saved edit.
            original = deepcopy(completed['import_document'])
            row = self._document(owner, lease, identity, original,
                                 expected_current_revision=document['document_revision'])
            if self._row_stamp(row) != completed['row_stamp']:
                raise ValueError('Saved reviewed preset target changed after its verified return')
            return row
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
                or proof['revision'] != (expected_current_revision if expected_current_revision is not None else document['document_revision'])
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
        state = row['state']
        # Match _scoped_project / normal save: runtime inference buffers are
        # not persisted recipe leaves. Review separately fences their contents.
        if state.get('_precompute') is not None:
            state = {**state, '_precompute': None}
        encoded = PJ.encode(WB.normalize_state(state), deepcopy(self.engine._project['assets']), dropped, 'recipe')
        if dropped: raise ValueError('Workflow recipe cannot be retained losslessly')
        return encoded

    def _row_stamp(self, row):
        from .virtual_copy_people import encode
        return P.digest({'people_context': encode(row), 'recipe': self._encoded_recipe(row), **{key: row.get(key) for key in (
            'document_id', 'document_revision', 'recipe_version_id', 'source_asset_id', 'path',
            'fingerprint', 'managed_import', 'import_origin', 'copy_number')}})

    def pending(self):
        return self.presets.active is not None or any(record['command']['operation']['kind'] == 'start_export'
                   and record['receipt']['result']['status'] in ('pending', 'unknown')
                   for record in self.operations.values())

    @staticmethod
    def _receipt(command, result):
        return {'schema_version': 1, 'identity': deepcopy(command['identity']), 'result': deepcopy(result)}

    def _publish(self, request, record, *, query=False):
        receipt = record['receipt']
        status = receipt['result']['status']
        outer = 'readback' if query else status if status in ('pending', 'unknown', 'failed') else 'succeeded'
        extra = {}
        if record['command']['operation']['kind'] in ('preflight_preset', 'apply_preset'):
            current = self.presets.public()
            if current is not None and current['operation_id'] == record['command']['identity']['operation_id']:
                record['handoff'] = deepcopy(current)
            extra['handoff'] = deepcopy(record.get('handoff'))
        return self._result(request, outer, receipt=deepcopy(receipt), **extra)

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
            if unresolved and not (operation['kind'] == 'apply_preset' and self.presets.active is not None
                    and self.presets.active['phase'] == 'authorized'):
                raise ValueError('Original owner work is pending or uncertain; query it first')
            if operation['kind'] == 'apply_preset' and self.presets.active is not None:
                entry = self.presets.active
                previous = entry['preflight']['command']['identity']
                same_identity = all(command['identity'][key] == value for key, value in previous.items() if key != 'operation_id')
                if (entry['phase'] == 'authorized' and request['session_id'] == entry['session_id'] and same_identity
                        and operation['assessment'] == entry['assessment'] and operation['document'] == entry['initial_document']
                        and operation['preset_id'] == entry['preset_id']):
                    # Correlate an exact admitted intent before source/CAS checks
                    # can fail. This changes no recipe and grants no dispatch.
                    entry.update(operation_id=oid, apply=record)
            row = self._bound(request, command)
            if operation['kind'] == 'preflight_preset':
                self.presets.start(record, row)
            elif operation['kind'] == 'apply_preset':
                self.presets.apply(record)
            elif operation['kind'] == 'freeze_export':
                frozen = E.freeze(self.engine, row, operation['document'], operation['output_root'],
                                  self.session['graph']['revision'], rid, self.session['destination_roots'],
                                  recipe_sha256=operation['recipe_sha256'])
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
            entry = self.presets.active
            retained_handoff = (entry is not None and (entry.get('apply') is record
                or (entry.get('preflight') is record and record['dispatch_started'])))
            if retained_handoff:
                entry.update(phase='unknown', message=str(error)[:2048])
            result = ({'status': 'unknown', 'reason': str(error)[:2048]} if record['dispatch_started'] or retained_handoff else
                      {'status': 'failed', 'code': 'owner_admission_rejected', 'message': str(error)[:2048], 'retained_document': None})
            record['receipt'] = self._receipt(command, result)
        return self._publish(request, record)

    def _query(self, request):
        step = self.presets.steps.get(request['original_request_id'])
        if step is not None:
            original = step['request']
            if original['session_id'] != request['session_id'] or original['operation_id'] != request['operation_id']:
                raise ValueError('Step query differs from its original handoff identity')
            result = self._result(original, **deepcopy(step['result']))
            return self._result(request, 'readback', operation_id=request['operation_id'], step_result=result)
        record = self.requests.get(request['original_request_id'])
        if (record is None or record['command']['identity']['operation_id'] != request['operation_id']
                or record['request']['session_id'] != request['session_id']):
            return self._result(request, 'unknown', error='Original owner receipt is unavailable; no replay or replacement operation is authorized')
        # Read retained facts even if a partial save changed the disk CAS. This
        # grants no new mutation and never retries the original command.
        if record['command']['operation']['kind'] in ('preflight_preset', 'apply_preset'):
            self._publish(record['request'], record)
            return self._publish(request, record, query=True)
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
                from .workflow_preset_catalogue import list_catalogue, resolve
                from .workflow_preset_review import support_reason
                catalogue = list_catalogue()
                for row in catalogue['presets']:
                    try:
                        reason = support_reason(resolve(row['id'], row['preset_sha256']))
                        row.update(workflow_supported=reason is None, support_reason=reason or 'target_image_review_required')
                    except Exception as error:
                        row.update(workflow_supported=False, support_reason=str(error)[:2048])
                    try:
                        from .workflow_auto_preset import support_reason as automatic_reason
                        preset = resolve(row['id'], row['preset_sha256'])
                        reason = automatic_reason(preset)
                        if reason is None and 'lnx.reference_color.v1' in preset['modules']:
                            reference = preset['modules']['lnx.reference_color.v1']['reference']
                            row['automatic_reference'] = {
                                'asset_id': reference['asset_id'], 'render_sha256': reference['render_sha256'],
                                'source_sha256': reference['source']['sha256']}
                        row.update(automatic_supported=reason is None,
                                   automatic_support_reason=reason or 'explicit_automatic_job_start_required')
                    except Exception as error:
                        row.update(automatic_supported=False, automatic_support_reason=str(error)[:2048])
                return self._result(request, 'readback', supported=True,
                    preset_catalogue=catalogue, **self._profile())
            if request['action'] == 'preflight': return self._preflight(request)
            if request['action'] == 'execute': return self._execute(request)
            if request['action'] == 'query': return self._query(request)
            if request['action'] == 'review_step': return self.presets.step(request)
            if request['action'] == 'review_image': return self.presets.image(request)
            self._lease(request['session_id'])
            handoff = self.presets.public()
            if handoff is not None and handoff.get('mode') == 'automatic':
                raise ValueError('Automatic job does not expose a human-image review')
            if handoff is None or request['operation_id'] != handoff['operation_id'] or (handoff['review'] or {}).get('review_id') != request['review_id']:
                raise ValueError('Original preset review is not available')
            return self._result(request, 'readback', opened=True, handoff=handoff)
        except Exception as error:
            extra = {'dispatch_rejected': True, 'operation_id': request.get('operation_id'), 'step': request.get('step')} if request.get('action') == 'review_step' else {}
            if request.get('action') == 'review_image':
                extra['operation_id'] = request.get('operation_id')
            return self._result(request, 'unknown' if request.get('action') == 'query' else 'failed', error=str(error)[:2048], **extra)


def controller(engine, emit):
    owner = getattr(engine, '_workflow_owner_host', None)
    if owner is None:
        owner = WorkflowOwner(engine, emit)
        engine._workflow_owner_host = owner
    return owner


def handle(engine, payload, emit):
    return controller(engine, emit).handle(payload)


def ingest_passthrough(engine, payload):
    """Exact same-lease transitions only; no general editor exemption."""
    try:
        request = P.envelope(payload)
        if request['action'] == 'profile': return True
        ingestion = getattr(engine, '_ingest_session_host', None)
        if ingestion is None: return False
        lease = ingestion._session(request['session_id'])
        if lease['owner'] != 'workflow': return False
        owner = getattr(engine, '_workflow_owner_host', None)
        if owner is not None and owner.presets.active is not None:
            entry = owner.presets.active
            if entry['session_id'] != request['session_id']: return False
            if request['action'] == 'query':
                original = owner.requests.get(request['original_request_id']) or owner.presets.steps.get(request['original_request_id'])
                return original is not None and original['request']['session_id'] == request['session_id']
            if request['action'] in ('review_step', 'review_image', 'open_review'):
                return request['operation_id'] == entry['operation_id']
            return (request['action'] == 'execute' and entry['phase'] == 'authorized'
                    and P.command(request['command'])['operation']['kind'] == 'apply_preset')
        ingestion._identity(lease)
        if request['action'] == 'query':
            return True  # Missing receipts return Unknown, never redispatch.
        if request['action'] in ('review_step', 'review_image', 'open_review'):
            return request['action'] == 'review_step' and owner is not None and request['request_id'] in owner.presets.steps
        return not (lease.get('operation_id') or lease.get('uncertain') or lease.get('stop_reason'))
    except (ValueError, TypeError, KeyError, OSError):
        return False


def guard_command(engine, name, payload):
    """The ingestion lease cannot be released/reused while export is unresolved."""
    from .workflow_preset_dispatch import permits
    if permits(engine, name, payload): return
    owner = getattr(engine, '_workflow_owner_host', None)
    if owner is None or not owner.pending(): return
    if name in ('hello', 'ping', 'status', 'shutdown'): return
    if name == 'workflow_owner' and ingest_passthrough(engine, payload): return
    if name == 'ingest_session' and payload.get('action') in ('state', 'query'): return
    if name == 'project' and payload.get('action') == 'state': return
    if name == 'session' and payload.get('action') == 'query': return
    raise ValueError('Original workflow export is pending or uncertain; query its exact receipt before releasing the lease, importing, editing or starting another output')


def dispatch_rejected(engine, payload, error, started, emit):
    from .workflow_owner_dispatch import rejected
    return rejected(engine, payload, error, started, emit)
