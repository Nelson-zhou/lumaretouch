# SPDX-License-Identifier: GPL-3.0-or-later
"""One loaded automatic target through the existing retained portrait owners.

This adapter owns neither a graph nor history and creates no image-view ACK.
It only freezes target-local analysis/plans, validates the complete candidate,
and invokes the normal protected batch transaction. Source authored / UNRUN.
"""
from copy import deepcopy

from . import portrait_group_retained as retained, virtual_copy_people as V
from . import workflow_preset_review as review
from .optics_candidate_identity import fingerprint
from .people_preset_plan import graph_content, require_active_owner


class TargetPortraitPlan:
    def __init__(self, engine, row, recheck):
        if not callable(recheck):
            raise ValueError('Automatic portrait requires its exclusive workflow lease')
        self.engine, self.row, self.recheck = engine, row, recheck
        self.batch = engine._batch_controller()
        self.owner = require_active_owner(engine)
        self.context = engine.__dict__.get('_people_active_context')
        self.load_id = engine._load_id
        self.workspace = self.batch.versions.workspace
        self.candidate_graph = None
        self.prepared_context = None
        self.face_refs = None
        self._assessment = None
        self._committed = False

    def _row(self, document_id):
        self.recheck()
        rows = [(i, row) for i, row in enumerate(self.engine._docs)
                if row.get('document_id') == document_id and not row.get('trashed')]
        if (len(rows) != 1 or rows[0][1] is not self.row
                or V.current_row(self.engine) is not self.row
                or self.engine._load_id != self.load_id
                or require_active_owner(self.engine) is not self.owner
                or self.engine.__dict__.get('_people_active_context') is not self.context
                or self.engine._batch_controller() is not self.batch
                or self.batch.versions.workspace != self.workspace):
            raise ValueError('Automatic portrait lost its exact loaded target or canonical owner')
        return rows[0]

    def _inputs(self, preset, target):
        review.check_target(target)
        self._row(target['document_id'])
        if (target['load_id'] != self.load_id
                or str(self.batch.versions.version(self.row).revision) != target['revision']):
            raise ValueError('Automatic portrait target revision changed')
        admission = retained.support(preset)
        if not retained.retained(preset) or not admission['supported']:
            raise ValueError(admission['reason'] or 'Automatic portrait requires retained skin intent')
        # The existing group planner reads remembered state, not a second live
        # recipe. Caller remembers preparation once; this read cannot do so.
        if fingerprint(self.row['state']) != fingerprint(self.engine._capture_state()):
            raise ValueError('Prepared target row differs from the live canonical recipe')
        fence = self.owner.fence
        before_state = fingerprint(self.engine._capture_state())
        staged = retained.plans(self, [target['document_id']], preset)
        owned, before, after, graph = retained.inputs(self, target['document_id'], preset, staged)
        from .full_candidate_render import people_context
        context = people_context(self.engine, self.row)
        evidence = {key: deepcopy(owned[key]) for key in ('before', 'after', 'face_refs', 'history')}
        evidence.update(target=deepcopy(target), candidate_graph=deepcopy(graph), context_sha256=fingerprint(context),
                        owner_fence=self.owner.fence, preset_sha256=fingerprint(preset))
        self._row(target['document_id'])
        if (self.owner.fence != fence or fingerprint(self.engine._capture_state()) != before_state
                or fingerprint(people_context(self.engine, self.row)) != fingerprint(context)):
            raise ValueError('Automatic portrait changed while its candidate was being assessed')
        return evidence, staged, after, graph, context

    def assess(self, preset, target):
        if self._committed:
            raise ValueError('A committed automatic portrait plan cannot be assessed again')
        evidence, _, after, graph, context = self._inputs(preset, target)
        if self._assessment is None:
            # Real source/candidate validation belongs to preflight, so a known
            # unsupported target can be restored and skipped before apply intent.
            # This is not a human-view or photographic-quality acknowledgment.
            from .full_candidate_render import render
            render(self.engine, self.row, after, target['document_id'], target['revision'], people_graph=graph)
            checked, _, _, checked_graph, _ = self._inputs(preset, target)
            if checked != evidence or checked_graph != graph:
                raise ValueError('Automatic portrait changed during canonical preparation')
        if self._assessment is not None and evidence != self._assessment:
            raise ValueError('Automatic target evidence changed after its first assessment')
        self._assessment = deepcopy(evidence)
        self.candidate_graph = deepcopy(graph)
        self.prepared_context = deepcopy(context)
        self.face_refs = deepcopy(evidence['face_refs'])
        return evidence

    def commit(self, preset, target, request_id, expected):
        if self._committed or self._assessment is None or expected != self._assessment:
            raise ValueError('Automatic portrait requires its one exact frozen assessment')
        evidence, staged, after, graph, _ = self._inputs(preset, target)
        if evidence != expected or graph != self.candidate_graph:
            raise ValueError('Automatic portrait candidate changed before application')
        # The first assessment validated the complete own-source render. Never
        # substitute another photo or rerun inference at the apply boundary.
        def verify():
            actual, _, _, candidate, _ = self._inputs(preset, target)
            if actual != expected or candidate != self.candidate_graph:
                raise ValueError('Automatic portrait changed during canonical preparation')
        verify()
        from . import people_batch_ledger as ledger, portrait_group_mixed_history as mixed
        targets = ledger._targets(self.batch, self.engine, staged)
        if (len(targets) != 1 or {item['document_id'] for item in targets.values()} != {target['document_id']}):
            raise ValueError('Automatic portrait transaction acquired an unselected source alias')
        global_modules = {op: params for op, params in preset['modules'].items() if op in retained.GLOBAL_OPERATIONS}
        extra = {}
        if global_modules:
            marker = mixed.capture(self.engine, staged, targets, global_modules, {target['document_id']: after})
            extra = {'portrait_group_global_history': marker, 'portrait_group_global_verify': verify}
        verify()
        # Claim precedes the canonical effect boundary. Failure is never an
        # invitation to retry; outer workflow owns durable Unknown/reconciliation.
        self._committed = True
        result = ledger.commit_scoped(self.batch, self.engine, staged,
            request_id=request_id, prepare=False, prepared_targets=targets, **extra)
        if result is None:
            raise ValueError('Automatic portrait produced no canonical batch receipt')
        batch_id, frame = result
        if frame is not None:
            self.batch.emit(frame)
        return {'kind': 'commit', 'batch_id': batch_id, 'targets': [int(i) for i in targets],
                'skipped': [], 'rejected_docs': [], 'success': True, 'outcome_unknown': False}

    def verify_applied(self, expected, target):
        """Verify content, not stale candidate context/revision bookkeeping hashes."""
        if not self._committed or expected != self._assessment:
            raise ValueError('Automatic portrait has no exact claimed assessment')
        self._row(target['document_id'])
        review.check_target(target)
        if (target['load_id'] != self.load_id
                or str(self.batch.versions.version(self.row).revision) != target['revision']):
            raise ValueError('Applied automatic portrait target revision changed')
        from .full_candidate_render import people_context
        from .people_state import face_ref
        context = people_context(self.engine, self.row)
        graph = context['people_graph']
        if (graph_content(graph) != graph_content(self.candidate_graph)
                or fingerprint({k: v for k, v in context.items() if k != 'people_graph'}) !=
                   fingerprint({k: v for k, v in self.prepared_context.items() if k != 'people_graph'})
                or any(face_ref(graph['faces'][ref['face_instance_id']]) != ref for ref in self.face_refs)):
            raise ValueError('Applied automatic portrait graph or own evidence differs from its plan')
        state = self.engine._capture_state()
        actual, _ = review._proof(self.engine, self.row, state, target)
        wanted = expected['after']
        if (actual['render']['source_proof'] != wanted['render']['source_proof']
                or actual['render']['candidate_sha256'] != wanted['render']['candidate_sha256']
                or actual['repair_sha256'] != wanted['repair_sha256']):
            raise ValueError('Applied automatic portrait changed source, repairs or complete recipe')
        self._row(target['document_id'])
        return actual
