# SPDX-License-Identifier: GPL-3.0-or-later
"""One automatic reference target, using the existing fit and batch owners.

The stored reference is immutable; every target gets one own correspondence/fit.
After assessment every read is verify-only. No image-view ACK is manufactured.
Source authored only: runtime, quality and durability acceptance are UNRUN.
"""
from copy import deepcopy
from . import portrait_group_reference as reference
from . import reference_color_scope as RC, creative_derived_source as SOURCE
from . import workflow_preset_review as review
from .workflow_auto_portrait import TargetPortraitPlan
from .optics_candidate_identity import fingerprint
from .full_candidate_render import people_context


class TargetReferencePlan(TargetPortraitPlan):
    def __init__(self, engine, row, recheck):
        super().__init__(engine, row, recheck)
        self._fit = None
        self._fit_started = False
        self._baseline = fingerprint(row['state'])
        self._live_baseline = fingerprint(engine._capture_state())
        self._history = fingerprint((row['undo'], row['redo']))
        self._people_baseline = fingerprint(people_context(engine, row))

    def assert_unchanged(self, *, loaded=True):
        """A preparation failure is skippable only with exact no-effect proof."""
        if (self._committed or fingerprint(self.row['state']) != self._baseline
                or fingerprint((self.row['undo'], self.row['redo'])) != self._history
                or fingerprint(people_context(self.engine, self.row)) != self._people_baseline
                or loaded and fingerprint(self.engine._capture_state()) != self._live_baseline):
            raise ValueError('Automatic reference preparation has no exact no-effect proof; outcome unknown')

    def _inputs(self, preset, target):
        review.check_target(target)
        self._row(target['document_id'])
        if (target['load_id'] != self.load_id
                or str(self.batch.versions.version(self.row).revision) != target['revision']):
            raise ValueError('Automatic reference target revision changed')
        admission = reference.support(preset)
        if not admission['supported']:
            raise ValueError(admission['reason'])
        self.assert_unchanged()
        if fingerprint(self.row['state']) != fingerprint(self.engine._capture_state()):
            raise ValueError('Automatic reference live and remembered target recipes differ')
        # Reject before correspondence: copied imports of the reference are not
        # silently omitted or exported as if they had been corrected.
        if SOURCE.row_proof(self.row)['asset_sha256'] == preset['modules'][RC.OP]['reference']['source']['sha256']:
            raise ValueError('automatic_reference_same_source_rejected: reference photograph/source alias is unchanged; no corrected output')
        if self._fit is None:
            if self._fit_started:
                raise ValueError('Automatic reference fit already attempted; never refit this assessment')
            self._fit_started = True
        owned, before, after, graph = reference.inputs(self, target['document_id'], preset, self._fit)
        if self._fit is None:
            self._fit = deepcopy(owned['reference_fit'])
        evidence = {key: deepcopy(owned[key]) for key in ('before', 'after', 'history', 'context', 'reference_fit')}
        evidence.update(target=deepcopy(target), preset_sha256=fingerprint(preset))
        self._row(target['document_id'])
        self.assert_unchanged()
        return evidence, after, graph

    def assess(self, preset, target):
        if self._committed:
            raise ValueError('A claimed automatic reference assessment cannot be reused')
        evidence, after, graph = self._inputs(preset, target)
        if self._assessment is None:
            from .full_candidate_render import render
            render(self.engine, self.row, after, target['document_id'], target['revision'], people_graph=graph)
            checked, _, _ = self._inputs(preset, target)  # frozen verification, never fit
            if checked != evidence:
                raise ValueError('Automatic reference changed during complete candidate render')
            self._assessment = deepcopy(evidence)
        elif evidence != self._assessment:
            raise ValueError('Automatic reference differs from its frozen assessment')
        return evidence

    def commit(self, preset, target, request_id, expected):
        if self._committed or self._assessment is None or expected != self._assessment:
            raise ValueError('Automatic reference requires its one exact frozen assessment')
        evidence, _, _ = self._inputs(preset, target)
        if evidence != expected:
            raise ValueError('Automatic reference changed before canonical batch application')
        index, row = self._row(target['document_id'])
        # Existing live batch commit validates the frozen target again, performs
        # strict replay, and owns normal history. No reviewed-group ACK/claim is used.
        rows = [{'index': index, 'path': row['path'], 'blocked': None,
                 '_source_proof': evidence['before']['render']['source_proof'],
                 '_reference_prepared': deepcopy(self._fit)}]
        # A direct live batch call owns its ledger/replay, while the normal
        # dispatcher surrounds it with the existing live history owner. Retain
        # that same finally semantics here, including on partial/lost outcomes.
        before_history = self.engine._history_capture()
        self._row(target['document_id'])
        self.assert_unchanged()
        self._committed = True  # any exception after this boundary stays Unknown
        try:
            result = self.batch.commit([RC.OP], preset['modules'], rows, 'recheck', [],
                source_snapshot={'document_id': target['document_id'], 'revision': target['revision'],
                    'path': row['path'], 'source_proof': evidence['before']['render']['source_proof']})
        finally:
            # Never write history into a different editor after a lost renderer.
            self._row(target['document_id'])
            self.engine._history_record('automatic-reference:' + request_id, before_history, coalesce=False)
        if result.get('targets') != [index] or result.get('skipped') or result.get('rejected_docs'):
            raise ValueError('Automatic reference canonical batch did not apply its one exact target')
        return {**result, 'success': True, 'outcome_unknown': False, 'request_id': request_id}

    def verify_applied(self, expected, target):
        if not self._committed or expected != self._assessment:
            raise ValueError('Automatic reference has no exact claimed assessment')
        self._row(target['document_id'])
        review.check_target(target)
        if (target['load_id'] != self.load_id
                or str(self.batch.versions.version(self.row).revision) != target['revision']
                or fingerprint(people_context(self.engine, self.row)) != self._people_baseline):
            raise ValueError('Applied automatic reference target or people context changed')
        # Group reference and BatchEditor both use canonical document capture,
        # not the preset DTO decorated with ephemeral per-face selection fields.
        state = self.engine._capture_state()
        actual, _ = review._proof(self.engine, self.row, state, target)
        wanted = expected['after']
        if (any(actual['render'][key] != wanted['render'][key]
                for key in ('source_proof', 'candidate_sha256', 'people_sha256'))
                or actual['repair_sha256'] != wanted['repair_sha256']
                or actual['snapshot_sha256'] != wanted['snapshot_sha256']):
            raise ValueError('Applied automatic reference differs from its complete frozen candidate')
        self._row(target['document_id'])
        return actual
