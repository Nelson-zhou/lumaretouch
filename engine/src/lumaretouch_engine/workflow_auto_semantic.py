# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit automatic global six-class colour transfer, never generic presets.

One retained reference analysis; one full-canvas semantic fit per managed target.
Assessment is machine evidence, not a human image-view ACK. Publication uses the
existing semantic owned-field ledger and normal live history. Save/CAS/editor
return and finite directory scheduling remain the existing workflow's owners.
Runtime, models, photographic quality and durability acceptance are UNRUN.
"""
from copy import deepcopy
import uuid

from . import workflow_owner_protocol as P, workflow_preset_review as review
from . import semantic_colour_batch_target as T, semantic_colour_state as S
from .workflow_auto_preset import AutomaticPresetHandoff
from .optics_candidate_identity import fingerprint
from .full_candidate_render import people_context


class TargetSemanticPlan:
    def __init__(self, engine, row, recheck, archive, authority):
        self.engine, self.row, self.recheck = engine, row, recheck
        self.archive, self.authority = archive, deepcopy(authority)
        self.batch = engine._batch_controller()
        self.workspace = self.batch.versions.workspace
        self.load_id = engine._load_id
        self._baseline = fingerprint(row['state'])
        self._live_baseline = fingerprint(engine._capture_state())
        self._history = fingerprint((row['undo'], row['redo']))
        self._people = fingerprint(people_context(engine, row))
        self._fit_started = self._committed = False
        self._record = self._assessment = self._after = None

    def _row(self, target):
        review.check_target(target)
        self.recheck(target_loaded=True)
        rows = [(i, row) for i, row in enumerate(self.engine._docs)
                if row.get('document_id') == target['document_id'] and not row.get('trashed')]
        if (len(rows) != 1 or rows[0][1] is not self.row
                or not 0 <= self.engine._doc_index < len(self.engine._docs)
                or self.engine._docs[self.engine._doc_index] is not self.row
                or self.engine._load_id != self.load_id or target['load_id'] != self.load_id
                or self.engine._batch_controller() is not self.batch
                or self.batch.versions.workspace != self.workspace
                or str(self.batch.versions.version(self.row).revision) != target['revision']
                or fingerprint(people_context(self.engine, self.row)) != self._people):
            raise ValueError('Semantic target, people context, revision or canonical owner changed')
        self.archive.assert_current()
        return rows[0]

    def assert_unchanged(self, *, loaded=True):
        if (self._committed or fingerprint(self.row['state']) != self._baseline
                or fingerprint((self.row['undo'], self.row['redo'])) != self._history
                or fingerprint(people_context(self.engine, self.row)) != self._people
                or loaded and fingerprint(self.engine._capture_state()) != self._live_baseline):
            raise ValueError('Semantic preparation has no exact no-effect proof; outcome unknown')

    def _inputs(self, target):
        self._row(target); self.assert_unchanged()
        before = self.engine._capture_state()
        if fingerprint(before) != fingerprint(self.row['state']):
            raise ValueError('Semantic live/remembered target differ before preparation')
        if self._record is None:
            raise ValueError('No frozen semantic target fit exists; verification never refits')
        T.verify(self.engine, self.row, before, target['document_id'], target['revision'], self.archive.intent, self._record)
        left, graph = review._proof(self.engine, self.row, before, target)
        right, candidate_graph = review._proof(self.engine, self.row, self._after, target)
        if (left['render']['source_proof'] != right['render']['source_proof']
                or left['render']['people_sha256'] != right['render']['people_sha256']
                or left['repair_sha256'] != right['repair_sha256'] or graph != candidate_graph):
            raise ValueError('Semantic-only candidate changed source, people, repairs or graph')
        evidence = {'before': left, 'after': right, 'target': deepcopy(target),
            'proposal_proof': self._record['proof'], 'reference_analysis_proof': self._record['reference_analysis_proof'],
            'authorization': deepcopy(self.authority)}
        self._row(target); self.assert_unchanged()
        return evidence, graph

    def assess(self, target):
        self._row(target); self.assert_unchanged()
        if self._record is None:
            if self._fit_started:
                raise ValueError('Original semantic target analysis was attempted; never refit')
            # Reject the reference original and byte-identical aliases. No silent
            # omission or output falsely described as a corrected target.
            from .local_mask_state import source_digest
            if source_digest(self.row['path']) == self.archive.intent['reference']['source']['sha256']:
                raise ValueError('automatic_semantic_same_source_rejected')
            self._fit_started = True
            cache = self.archive.reference_analysis()
            self._record = T.prepare(self.engine, self.row, self.engine._capture_state(),
                target['document_id'], target['revision'], self.archive.intent, cache, preview=False)
            if self._record['reference_analysis_proof'] != cache['proof']:
                raise ValueError('Semantic target did not use this exact one reference analysis')
            from .cpu_memory_budget import available_estimate
            retained_bytes = sum(part.size for part in self.archive.bundle)
            if available_estimate() < 2*retained_bytes + 2*24*1024*1024 + 768*1024*1024:
                raise ValueError('Semantic complete candidate copy/render exceeds retained reference budget')
            self._after = T.install(self.row['state'], self._record, self.archive.bundle,
                                    automatic_authority=self.authority)
        evidence, graph = self._inputs(target)
        if self._assessment is None:
            # The renderer deep-copies state before its own full-source peak
            # admission. Admit that retained-reference copy first, never proxy.
            from .cpu_memory_budget import available_estimate
            if available_estimate() < 2*sum(part.size for part in self.archive.bundle) + 2*24*1024*1024 + 768*1024*1024:
                raise ValueError('Semantic full render cannot safely copy its retained reference')
            from .full_candidate_render import render
            render(self.engine, self.row, self._after, target['document_id'], target['revision'], people_graph=graph)
            checked, _ = self._inputs(target)  # verify only: no inference or fit
            if checked != evidence:
                raise ValueError('Semantic candidate changed during complete render')
            self._assessment = deepcopy(evidence)
        elif evidence != self._assessment:
            raise ValueError('Semantic candidate differs from its frozen target assessment')
        return evidence

    def commit(self, target, request_id, expected):
        if self._committed or self._assessment is None or expected != self._assessment:
            raise ValueError('Semantic application requires its exact unclaimed assessment')
        evidence, _ = self._inputs(target)
        if evidence != expected:
            raise ValueError('Semantic candidate changed; never refit at commit')
        from .cpu_memory_budget import available_estimate
        if available_estimate() < 2*24*1024*1024 + 128*1024*1024:
            raise ValueError('Semantic publication exceeds retained-mask memory budget')
        index, row = self._row(target)
        before = self.engine._capture_state()
        history = self.engine._history_capture()
        self.assert_unchanged()
        # The durable core ApplyPreset intent already exists. Any exception from
        # this point remains query-only, including rollback/history/save failure.
        self._committed = True
        try:
            from .semantic_colour_batch_ledger import publish
            bid, frame = publish(self.batch, [(index, row, before, self._after)], policy='recheck',
                source_snapshot={'document_id': target['document_id'], 'revision': target['revision'],
                    'archive_sha256': self.archive.metadata['file_sha256']}, review_token=None,
                automatic_authority=self.authority)
        finally:
            if (not 0 <= self.engine._doc_index < len(self.engine._docs)
                    or self.engine._docs[self.engine._doc_index] is not row or self.engine._load_id != self.load_id):
                raise ValueError('Lost exact editor during semantic publication; history outcome unknown')
            self.engine._history_record('automatic-semantic:' + request_id, history, coalesce=False)
        if frame is not None: self.batch.emit(frame)
        return {'success': True, 'outcome_unknown': False, 'batch_id': bid, 'targets': [index],
                'request_id': request_id, 'skipped': [], 'rejected_docs': []}

    def verify_applied(self, expected, target):
        if not self._committed or expected != self._assessment:
            raise ValueError('Semantic target has no exact claimed assessment')
        self._row(target)
        state = self.engine._capture_state()
        actual, _ = review._proof(self.engine, self.row, state, target)
        wanted = expected['after']
        if (any(actual['render'][key] != wanted['render'][key]
                for key in ('source_proof', 'candidate_sha256', 'people_sha256'))
                or actual['repair_sha256'] != wanted['repair_sha256']
                or actual['snapshot_sha256'] != wanted['snapshot_sha256']
                or fingerprint(state) != fingerprint(self._after)
                or T.owned_key(state) != T.owned_key(self._after)):
            raise ValueError('Applied semantic contribution differs from its frozen complete candidate')
        self._row(target)
        return actual


class AutomaticSemanticHandoff(AutomaticPresetHandoff):
    def __init__(self, owner, archive):
        super().__init__(owner)
        self.archive = archive

    def _resolve(self, preset_id, preset_sha256):
        intent = self._intent()['operation']['intent']
        if (intent.get('semantic_scope') != 'global_six_class_per_target_fit'
                or intent.get('semantic_archive') != self.archive.metadata
                or preset_sha256 != self.archive.metadata['file_sha256']
                or preset_id != 'semantic:' + preset_sha256):
            raise ValueError('Automatic semantic intent differs from its pre-consent frozen archive')
        self.archive.assert_current()
        # Private handoff admission DTO only. Never register/dispatch this as a
        # generic text preset or combine it with scalar/portrait/reference edits.
        return {'modules': {S.OP: deepcopy(self.archive.intent)}}

    def _support_reason(self, preset):
        return None if set(preset.get('modules', {})) == {S.OP} else 'automatic_semantic_only'

    def _review(self):
        entry = self.active
        entry['phase'] = 'awaiting_preparation'
        _, row = self._check(target_loaded=True)
        authority = {'schema': 'lrt.automatic-semantic-assessment.v1',
            'graph_sha256': self.owner.session['graph_sha256'],
            'operation_id': entry['preflight']['command']['identity']['operation_id'],
            'archive_sha256': self.archive.metadata['file_sha256'], 'reviewed': False}
        plan = entry['semantic_plan'] = TargetSemanticPlan(self.engine, row, self._check, self.archive, authority)
        evidence = plan.assess(entry['target'])
        self._verify_review_source(evidence['before']['render']['source_proof'])
        entry['automatic_evidence'] = evidence
        report = {'schema': 'lrt.automatic-semantic-assessment.v1',
            'identity': entry['preflight']['command']['identity'], 'evidence': evidence,
            'archive': deepcopy(self.archive.metadata), 'reviewed': False}
        assessment = {'report_id': 'automatic-semantic:' + entry['operation_id'],
            'report_sha256': P.digest(report), 'document_revision': entry['initial_document']['document_revision'],
            'preset_sha256': entry['preset_sha256'], 'requires_review': False, 'review': None}
        entry.update(assessment=assessment, phase='authorized',
            message='One own-canvas semantic fit retained; no human image review is claimed')
        record = entry['preflight']
        record['receipt'] = self.owner._receipt(record['command'], {'status': 'preset_preflight', 'assessment': deepcopy(assessment)})

    def apply(self, record):
        entry = self.active
        if entry is None or entry['phase'] != 'authorized':
            raise ValueError('No automatic semantic target assessment is retained')
        command = record['command']; operation = command['operation']
        if (operation['assessment'] != entry['assessment'] or operation['document'] != entry['initial_document']
                or operation['preset_id'] != entry['preset_id']
                or any(command['identity'][key] != value for key, value in
                       entry['preflight']['command']['identity'].items() if key != 'operation_id')):
            raise ValueError('Semantic apply differs from the exact journaled target assessment')
        entry.update(operation_id=command['identity']['operation_id'], apply=record)
        self._resolve(entry['preset_id'], entry['preset_sha256'])
        self._check(target_loaded=True)
        request_id = str(uuid.uuid4())
        entry.update(phase='applying', preset_request={'request_id': request_id})
        record['dispatch_started'] = True
        result = entry['semantic_plan'].commit(entry['target'], request_id, entry['automatic_evidence'])
        if result.get('success') is not True or result.get('outcome_unknown'):
            raise ValueError('Semantic publication lacks a definite successful post-history result')
        self.engine._remember_current()
        entry['target']['revision'] = self._version(entry['row'])
        self._verify_applied()
        entry.update(applied_recipe=self.owner._encoded_recipe(entry['row']), preset_result=result, phase='awaiting_save')
        self._save()
        self._return()

    def _verify_applied(self):
        entry = self.active
        actual = entry['semantic_plan'].verify_applied(entry['automatic_evidence'], entry['target'])
        self._verify_review_source(actual['render']['source_proof'])
        self._check(target_loaded=True)
