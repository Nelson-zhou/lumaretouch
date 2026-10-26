# SPDX-License-Identifier: GPL-3.0-or-later
"""Same-lease, explicit target review/apply/save/return state machine.

This module does not own a second recipe/history graph. Every pixel mutation is
performed by the existing preset dispatcher after the durable core ApplyPreset
intent. A partial handoff cannot be released as an ordinary clean lease.
"""
from copy import deepcopy
import uuid
from . import workflow_owner_protocol as P
from .source_relocation_transaction import read_project
from .workflow_preset_dispatch import dispatch
from .workflow_preset_review import WorkflowPresetReviews, support_reason
from .workflow_preset_catalogue import resolve


def _source_file(row, document):
    """Bind physical managed bytes to the original durable import, not metadata."""
    from .source_relocation_io import Budget, hash_file
    fingerprint = row.get('fingerprint') or {}
    managed = row.get('managed_import') or {}
    expected = document['source_sha256']
    if (fingerprint.get('hash_level') != 'full' or fingerprint.get('sha256') != expected
            or managed.get('content_sha256') != expected or managed.get('mode') != 'copy'
            or type(fingerprint.get('bytes')) is not int or fingerprint['bytes'] <= 0):
        raise ValueError('Preset target lacks its original complete managed-import identity')
    proof = hash_file(row['path'], Budget(lambda: False), expected_size=fingerprint['bytes'])
    if proof['sha256'] != expected:
        raise ValueError('Managed source bytes differ from the original import receipt')
    return proof


def _scoped_project(saved, row, *, engine=None, people_baseline=None, expected_context=None):
    """Use the existing codec on one row, retaining every other saved record.

    A full _project_build rewrites version timestamps and may compact inactive
    rows/assets. It is not an appropriate owner for a target-only preset save.
    """
    from . import project as PJ
    from .virtual_copy_project import save_row
    project = deepcopy(saved)
    target = row['document_id']
    selected = [doc for doc in project['docs'] if doc.get('document_id') == target]
    if len(selected) != 1:
        raise ValueError('Scoped preset save requires one exact saved target')
    recipe = row['state']
    # Match ordinary save semantics: derived analysis is not persisted. The
    # complete user intent and normal undo/redo states remain codec-owned.
    if recipe.get('_precompute') is not None:
        recipe = {**recipe, '_precompute': None}
    dropped = deepcopy(project.get('dropped', []))
    stored = PJ.add_doc(project, row['path'], recipe, fp=row['fingerprint'],
        budget=row.get('budget'), version_id=selected[0]['active_version'],
        **{key: row[key] for key in ('document_id', 'source_asset_id',
                                   'root_document_id', 'copy_number', 'recipe_version_id')})
    save_row(project, row, stored, PJ)
    stored['budget'] = row.get('budget')
    allowed = {'docs', 'assets'}
    if people_baseline is not None:
        from .workflow_preset_people_save import stage, PEOPLE_PROJECT_FIELDS
        project = stage(engine, saved, project, row, people_baseline, expected_context)
        allowed |= PEOPLE_PROJECT_FIELDS
    elif expected_context is not None:
        raise ValueError('Portrait save context has no original preparation owner')
    if project.get('dropped', []) != dropped:
        raise ValueError('Scoped preset recipe cannot be saved without data loss')
    old_others = [doc for doc in saved['docs'] if doc.get('document_id') != target]
    new_others = [doc for doc in project['docs'] if doc.get('document_id') != target]
    if old_others != new_others or project.get('source_assets') != saved.get('source_assets'):
        raise ValueError('Scoped preset save changed another document or source registration')
    if {key: value for key, value in project.items() if key not in allowed} != {
            key: value for key, value in saved.items() if key not in allowed}:
        raise ValueError('Scoped preset save changed unrelated project data')
    if any(project['assets'].get(key) != value for key, value in saved['assets'].items()):
        raise ValueError('Scoped preset save replaced an existing immutable project asset')
    # _prepare_save also runs this existing migration. Refuse a hidden rewrite
    # of old saved rows before the transaction can publish any manifest bytes.
    if PJ._migrate(project) != project:
        raise ValueError('Scoped preset save requires an already canonical saved project')
    return project


class PresetHandoff:
    def __init__(self, owner):
        self.owner = owner
        self.engine = owner.engine
        self.reviews = WorkflowPresetReviews(self.engine)
        self.active = None
        self.completed = {}
        self.steps = {}

    def node(self):
        return next((node for node in self.owner.session['ordered']
                     if node['operation']['kind'] == 'compatible_preset'), None)

    def public(self):
        entry = self.active
        if entry is None:
            return None
        return {key: deepcopy(entry[key]) for key in ('version', 'operation_id', 'document_id',
            'preset_id', 'preset_sha256', 'phase', 'review', 'message')}

    def _row(self, document_id):
        found = [row for row in self.engine._docs if row.get('document_id') == document_id and not row.get('trashed')]
        if len(found) != 1:
            raise ValueError('Workflow review target is unavailable or ambiguous')
        return found[0]

    def _version(self, row):
        return str(self.engine._document_versions().version(row).revision)

    def _others(self, target):
        return {row['document_id']: P.digest({'recipe': self.owner._encoded_recipe(row),
            'revision': self._version(row), 'path': row['path'],
            'source_asset_id': row.get('source_asset_id'), 'fingerprint': row.get('fingerprint'),
            'managed_import': row.get('managed_import')}) for row in self.engine._docs if row is not target}

    def _check(self, *, target_loaded=None):
        entry = self.active
        if entry is None:
            raise ValueError('No retained preset handoff exists')
        ingestion = self.engine._ingest_session_host
        lease = ingestion._session(entry['session_id'])
        actual = ingestion._binding()
        if actual != entry['binding'] or read_project(actual['path'])[1] != actual['disk_sha256']:
            raise ValueError('Workflow handoff saved-project CAS or workspace changed')
        row = self._row(entry['document_id'])
        if row is not entry['row'] or self._others(row) != entry['others']:
            raise ValueError('Another document changed during the exclusive preset handoff')
        if {key: row.get(key) for key in entry['source']} != entry['source']:
            raise ValueError('Imported target provenance changed')
        if _source_file(row, entry['initial_document']) != entry['source_file']:
            raise ValueError('Managed source file changed during the retained handoff')
        if target_loaded is True:
            if (self.engine._doc_index < 0 or self.engine._docs[self.engine._doc_index] is not row
                    or self.engine._load_id != entry['target']['load_id']
                    or self._version(row) != entry['target']['revision']):
                raise ValueError('Loaded preset target no longer matches its retained owner')
        return lease, row

    def _support_reason(self, preset):
        return support_reason(preset)

    def start(self, record, row):
        if self.active is not None:
            raise ValueError('An earlier preset handoff remains unresolved')
        operation = record['command']['operation']
        preset = resolve(operation['preset_id'], operation['preset_sha256'])
        reason = self._support_reason(preset)
        if reason:
            raise ValueError(reason)
        engine = self.engine
        if not engine._image_loaded or not engine._load_id or not 0 <= engine._doc_index < len(engine._docs):
            raise ValueError('Preset workflows require a distinct loaded original editor document for verified return')
        original = engine._docs[engine._doc_index]
        if original is row:
            raise ValueError('Workflow preset target must be distinct from the prior editor selection')
        engine._remember_current()
        _, lease = self.owner._lease(record['request']['session_id'], idle=True)
        source_file = _source_file(row, operation['document'])
        saved = deepcopy({key: value for key, value in engine._project.items()
                          if key not in ('_source_path', '_source_sha256')})
        target = {'document_id': row['document_id'], 'load_id': '', 'revision': self._version(row)}
        self.active = {'version': 1, 'operation_id': record['command']['identity']['operation_id'],
            'document_id': row['document_id'], 'preset_id': operation['preset_id'],
            'preset_sha256': operation['preset_sha256'], 'phase': 'awaiting_open', 'review': None,
            'message': 'Open this exact imported image to review the selected preset; no preset has been applied',
            'session_id': lease['session_id'], 'binding': deepcopy(lease['binding']),
            'row': row, 'target': target, 'original': original,
            'original_revision': self._version(original), 'original_recipe': self.owner._encoded_recipe(original),
            'original_selection': lease['selection'], 'others': self._others(row),
            'source': deepcopy({key: row.get(key) for key in ('path', 'source_asset_id', 'fingerprint', 'managed_import', 'import_origin')}),
            'source_file': source_file, 'saved_project': saved,
            'preflight': record, 'apply': None, 'approval': None,
            'needs_skin': 'lnx.skin.v1' in preset['modules'], 'preparation': None,
            'initial_document': deepcopy(operation['document']), 'step_effect_started': False}
        record['receipt'] = self.owner._receipt(record['command'], {'status': 'pending',
            'owner_receipt_id': record['command']['identity']['operation_id']})

    def _open(self):
        entry = self.active
        if entry['phase'] != 'awaiting_open':
            raise ValueError('Target opening is not available in this handoff phase')
        _, row = self._check()
        entry['phase'] = 'opening'
        payload = {'cmd': 'load_image', 'path': row['path'], 'document_id': row['document_id']}
        if self.engine._proxy_budget:
            payload['max_px'] = int(self.engine._proxy_budget)
        entry['step_effect_started'] = True
        dispatch(self.engine, payload, self._check)
        if (not self.engine._image_loaded or not self.engine._load_id
                or self.engine._docs[self.engine._doc_index] is not row
                or self._version(row) != entry['target']['revision']):
            raise ValueError('Target load did not preserve the exact imported document revision')
        entry['target']['load_id'] = self.engine._load_id
        self._check(target_loaded=True)
        if self.engine._project_dirty:
            raise ValueError('Opening this target changed the saved recipe; no silent review rebase is allowed')
        if entry['needs_skin']:
            entry.update(phase='awaiting_preparation', message='Choose target-local analysis and skin-only scope explicitly; no analysis or preset has run')
            return
        self._review()

    def _prepare_skin(self):
        entry = self.active
        if entry['phase'] != 'awaiting_preparation' or not entry['needs_skin']:
            raise ValueError('No explicit skin preparation is awaiting this action')
        _, row = self._check(target_loaded=True)
        preparation = entry['preparation']
        if preparation is None:
            from .workflow_preset_preparation import SkinPreparation
            from .workflow_preset_people_save import capture
            baseline = capture(self.engine, row, entry['saved_project'])
            preparation = SkinPreparation(self.engine, row, self._check)
            entry.update(preparation=preparation, people_save_baseline=baseline)
            entry['step_effect_started'] = True
            try:
                preparation.analyse()
            except Exception:
                # Only exact observed own effects may be cancelled. A failed
                # rollback propagates with the effect flag set and locks Unknown.
                if preparation.started:
                    if preparation.expected is None:
                        raise  # Preserve the actual source/recovery uncertainty.
                    preparation.restore()
                entry['target']['revision'] = self._version(row)
                self._check(target_loaded=True)
                entry.update(preparation=None, review=None, step_effect_started=False,
                    message='Target analysis was refused and its original neutral state restored; no preset was applied')
                raise
            entry['target']['revision'] = self._version(row)
            self._check(target_loaded=True)
        preparation.assert_current()
        try:
            self._review()
        except Exception as error:
            # A read-only render failure is not permission to repeat inference.
            # Retain the prepared owner and offer review retry or exact cancel.
            preparation.assert_current()
            if entry.get('review') is not None:
                raise  # A partially published review must be reconciled.
            entry.update(phase='awaiting_preparation', message='Analysis retained; review failed: ' + str(error)[:1800] + '. Retry prepares review only, or cancel to restore the original target.')

    def _review(self):
        entry = self.active
        review = self.reviews.prepare(entry['preset_id'], entry['preset_sha256'], entry['target'])
        self._check(target_loaded=True)
        self._verify_review_source(review['source_proof'])
        entry['people_owner'] = self.engine.__dict__.get('_people_graph_owner')
        entry['people_context'] = self.engine.__dict__.get('_people_active_context')
        entry.update(phase='reviewing', review=review, message='Review both complete images and explicitly approve; approval alone does not apply')
        assessment = {'report_id': review['review_id'], 'report_sha256': review['review_sha256'],
            'document_revision': entry['initial_document']['document_revision'],
            'preset_sha256': entry['preset_sha256'], 'requires_review': True, 'review': None}
        entry['assessment'] = assessment
        record = entry['preflight']
        record['receipt'] = self.owner._receipt(record['command'], {'status': 'preset_preflight', 'assessment': deepcopy(assessment)})
        self.owner._publish(record['request'], record)

    def _approve(self, payload):
        entry = self.active
        if entry['phase'] != 'reviewing':
            raise ValueError('There is no current unapproved image review')
        self._check(target_loaded=True)
        approval = self.reviews.acknowledge(payload)
        entry['approval'] = approval
        entry['assessment']['review'] = {'receipt_id': approval['approval_id'],
            'report_sha256': entry['assessment']['report_sha256'], 'document_id': entry['document_id'],
            'document_revision': entry['initial_document']['document_revision'], 'preset_sha256': entry['preset_sha256']}
        entry.update(phase='authorized', message='Approval retained; waiting for the workflow to journal the actual preset application')
        record = entry['preflight']
        record['receipt'] = self.owner._receipt(record['command'], {'status': 'preset_preflight', 'assessment': deepcopy(entry['assessment'])})
        self.owner._publish(record['request'], record)

    def apply(self, record):
        entry = self.active
        if entry is None or entry['phase'] != 'authorized':
            raise ValueError('No retained user-authorized preset handoff exists')
        command = record['command']; operation = command['operation']
        if (operation['assessment'] != entry['assessment'] or operation['preset_id'] != entry['preset_id']
                or operation['document'] != entry['initial_document']
                or command['identity']['input_occurrence_id'] != entry['preflight']['command']['identity']['input_occurrence_id']):
            raise ValueError('Journaled preset application differs from the exact approved operation')
        # Once this exact journaled command is admitted, failures (including an
        # expired approval) belong to ApplyPreset, never its terminal preflight.
        entry.update(operation_id=command['identity']['operation_id'], apply=record)
        self._check(target_loaded=True)
        from . import preset_store as PS, preset_organisation_store as PO
        with PO.catalogue_lock(PS.preset_dir()):
            authority = self.reviews.consume(entry['approval'], entry['target'], entry['preset_id'], entry['preset_sha256'])
            self._verify_review_source(authority['source_proof'])
            request = {**authority['preset_command'], 'request_id': str(uuid.uuid4())}
            entry.update(phase='applying', operation_id=command['identity']['operation_id'], apply=record,
                         preset_request=deepcopy(request), message='Applying the exact approved preset through normal history')
            record['dispatch_started'] = True
            dispatch(self.engine, request, lambda: self._check(target_loaded=True))
            retained = self.engine._preset_controller()._receipts.get(request['request_id'])
            if retained is None:
                raise ValueError('Original preset post-history receipt is unavailable; never redispatch')
            result = deepcopy(retained[1])
            entry['authority'] = authority
        if result.get('success') is not True or result.get('outcome_unknown'):
            raise ValueError('Preset did not produce a definite successful post-history receipt; inspect original operation')
        self.engine._remember_current()
        row = entry['row']
        entry['target']['revision'] = self._version(row)
        self._verify_applied()
        if entry.get('people_save_baseline') is not None:
            from .workflow_preset_people_save import context
            entry['applied_people_context'] = context(self.engine, row)
        entry['applied_recipe'] = self.owner._encoded_recipe(row)
        entry['preset_result'] = result
        entry.update(phase='awaiting_save', message='Preset applied in normal history; explicitly save this exact project before export can continue')
        record['receipt'] = self.owner._receipt(command, {'status': 'pending', 'owner_receipt_id': request['request_id']})

    def _verify_review_source(self, proof):
        from .creative_derived_source import check_row_proof, verify_row
        entry = self.active
        proof = check_row_proof(proof)
        if proof['original_sha256'] != entry['initial_document']['source_sha256']:
            raise ValueError('Reviewed image source differs from the durable imported bytes')
        verify_row({**entry['row'], 'state': self.engine._people_preset_capture()}, proof)

    def _verify_applied(self):
        """Compare the actual complete result to reviewed render inputs, not UI pixels."""
        from .workflow_preset_review import _proof
        from .optics_candidate_identity import fingerprint
        entry = self.active
        _, row = self._check(target_loaded=True)
        if (self.engine.__dict__.get('_people_graph_owner') is not entry['people_owner']
                or self.engine.__dict__.get('_people_active_context') is not entry['people_context']):
            raise ValueError('Applied target portrait ownership changed after review')
        state = self.engine._people_preset_capture()
        proof, _ = _proof(self.engine, row, state, entry['target'])
        review = entry['review']
        self._verify_review_source(proof['render']['source_proof'])
        if (proof['render']['source_proof'] != review['source_proof']
                or proof['render']['candidate_sha256'] != review['candidate_state_sha256']
                or proof['render']['people_sha256'] != review['people_sha256']
                or proof['repair_sha256'] != review['repair_sha256']
                or proof['snapshot_sha256'] != review['candidate_render_sha256']
                or fingerprint(self.engine._people_preset_capture()) != review['candidate_state_sha256']):
            raise ValueError('Actual applied state, source, people or render differs from the reviewed candidate')
        self._check(target_loaded=True)

    def _stage_save(self):
        entry = self.active
        return _scoped_project(entry['saved_project'], entry['row'], engine=self.engine,
            people_baseline=entry.get('people_save_baseline'), expected_context=entry.get('applied_people_context'))

    def _cancel_result(self, entry, row):
        return {'status': 'failed', 'code': 'user_declined_preset',
            'message': 'User returned without applying this preset',
            'retained_document': {**entry['initial_document'], 'document_revision': self._version(row)}}

    def _save(self):
        entry = self.active
        if entry['phase'] != 'awaiting_save':
            raise ValueError('There is no verified applied preset awaiting save')
        self._verify_applied()
        row = entry['row']
        def check():
            self._verify_applied()
            if self.owner._encoded_recipe(row) != entry['applied_recipe']:
                raise ValueError('Applied target recipe changed before the explicit save')
        self.engine._remember_current()
        project = self._stage_save()
        from .workflow_preset_save import persist
        outcome = persist(project, entry['binding']['path'], entry['binding']['disk_sha256'], check)
        if outcome['status'] != 'succeeded':
            entry['step_effect_started'] = True
            entry['save_outcome'] = outcome
            raise ValueError('Project replacement outcome is uncertain; retained original save must be reconciled')
        from . import creative_document_storage as CS
        entry['step_effect_started'] = True
        entry['save_outcome'] = outcome
        self.engine._project = CS.hydrate(outcome['project'], CS.read_blobs(outcome['project'], entry['binding']['path']))
        self.engine._project_disk_sha256 = outcome['sha256']
        self.engine._project_saved_ns = outcome['updated_ns']
        self.engine._project_dirty = False
        entry['binding'] = self.engine._ingest_session_host._binding()
        entry['save_outcome'] = outcome
        entry.update(phase='awaiting_return', message='Exact preset project saved; return to the prior document to resume the run')

    def _return(self):
        entry = self.active
        if entry['phase'] not in ('awaiting_open', 'awaiting_preparation', 'reviewing', 'awaiting_return'):
            raise ValueError('Return is not safe before the original apply/save outcome is settled')
        cancelled = entry['phase'] != 'awaiting_return'
        lease, row = self._check(target_loaded=entry['phase'] != 'awaiting_open')
        if self.engine._project_dirty:
            raise ValueError('Uncommitted target state cannot be discarded by returning')
        if cancelled and entry.get('preparation') is not None:
            entry['step_effect_started'] = True
            entry['preparation'].restore()
            entry['target']['revision'] = self._version(row)
            self._check(target_loaded=True)
        original = entry['original']
        if self._row(original['document_id']) is not original:
            raise ValueError('Original editor document was replaced')
        if entry['phase'] != 'awaiting_open':
            payload = {'cmd': 'load_image', 'path': original['path'], 'document_id': original['document_id']}
            if self.engine._proxy_budget:
                payload['max_px'] = int(self.engine._proxy_budget)
            entry['step_effect_started'] = True
            dispatch(self.engine, payload, self._check)
        if (not self.engine._image_loaded or not self.engine._load_id
                or self.engine._docs[self.engine._doc_index] is not original
                or self._version(original) != entry['original_revision']):
            raise ValueError('Original editor return did not preserve its exact document revision')
        self.engine._remember_current()
        if self.owner._encoded_recipe(original) != entry['original_recipe'] or self.engine._project_dirty:
            raise ValueError('Original editor recipe changed while returning; do not resume')
        self._check()
        lease['selection'] = self.engine._ingest_session_host._selection()
        lease['binding'] = deepcopy(entry['binding'])
        self.engine._ingest_session_host._exact(lease)
        record = entry['preflight'] if cancelled else entry['apply']
        if cancelled:
            record['receipt'] = self.owner._receipt(record['command'], self._cancel_result(entry, row))
        else:
            document = {**entry['initial_document'], 'document_revision': self._version(row),
                        'receipt_id': record['command']['identity']['operation_id']}
            record['receipt'] = self.owner._receipt(record['command'], {'status': 'preset_applied',
                'document': document, 'preset_receipt_id': entry['preset_request']['request_id']})
            self.completed[document['receipt_id']] = {'document': deepcopy(document),
                'import_document': deepcopy(entry['initial_document']), 'row_stamp': self.owner._row_stamp(row),
                'identity': deepcopy(record['command']['identity'])}
        record['handoff'] = None  # Only this completed operation clears its retained public snapshot.
        self.active = None
        self.owner._publish(record['request'], record)

    def step(self, request):
        rid = request['request_id']
        if rid in self.steps:
            prior = self.steps[rid]
            if prior['request'] != request:
                raise ValueError('Preset handoff request identity was reused')
            return self.owner._result(request, **deepcopy(prior['result']))
        entry = self.active
        if entry is None or request['session_id'] != entry['session_id'] or request['operation_id'] != entry['operation_id']:
            raise ValueError('Preset handoff request is not bound to its current core operation')
        if len(self.steps) >= 512:
            raise ValueError('Preset handoff receipt budget exhausted; no identity is evicted')
        prior = {'request': deepcopy(request), 'result': {'status': 'unknown',
            'operation_id': request['operation_id'], 'step': request['step']}}
        self.steps[rid] = prior
        started = False
        try:
            if request['step'] != 'approve' and request['payload'] != {}:
                raise ValueError('Unexpected arguments for this exact handoff step')
            allowed = {'open_target': ('awaiting_open',), 'prepare_skin': ('awaiting_preparation',), 'approve': ('reviewing',),
                       'save_project': ('awaiting_save',),
                       'return_target': ('awaiting_open', 'awaiting_preparation', 'reviewing', 'awaiting_return')}
            if entry['phase'] not in allowed[request['step']]:
                raise ValueError('This action is stale or unavailable in the retained handoff phase')
            self._check()
            started = True
            entry['step_effect_started'] = False
            {'open_target': self._open, 'prepare_skin': self._prepare_skin, 'approve': lambda: self._approve(request['payload']),
             'save_project': self._save, 'return_target': self._return}[request['step']]()
            prior['result'].update(status='succeeded', handoff=self.public())
        except Exception as error:
            uncertain = started and entry.get('step_effect_started', False)
            if uncertain and self.active is not None and request['step'] != 'approve':
                self.active.update(phase='unknown', message=str(error)[:2048])
                current = entry.get('apply') or entry['preflight']
                result = current['receipt']['result']
                if result['status'] in ('pending', 'unknown') or (result['status'] == 'preset_preflight' and result['assessment']['review'] is None):
                    current['receipt'] = self.owner._receipt(current['command'], {'status': 'unknown', 'reason': str(error)[:2048]})
                    self.owner._publish(current['request'], current)
            known = not uncertain and (request['step'] != 'approve' or self.active is not None and self.active['phase'] == 'reviewing')
            prior['result'].update(status='failed' if known else 'unknown', error=str(error)[:2048], handoff=self.public())
            if known: prior['result']['dispatch_rejected'] = True
        return self.owner._result(request, **deepcopy(prior['result']))

    def image(self, request):
        entry = self.active
        if (entry is None or entry['phase'] != 'reviewing' or request['session_id'] != entry['session_id']
                or request['operation_id'] != entry['operation_id']):
            raise ValueError('Image request is not bound to the current review operation')
        self._check(target_loaded=True)
        image = self.reviews.retrieve(request['review_id'], request['review_sha256'], entry['target'],
                                      request['side'], request['sha256'], request['page'])
        return self.owner._result(request, 'readback', operation_id=request['operation_id'], image=image)
