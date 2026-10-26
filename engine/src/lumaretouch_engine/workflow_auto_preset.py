# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit automatic target-owned job owner, NOT a human-image review owner.

The native start gate owns fresh graph-bound user intent. This owner additionally
requires the exact automatic node in its preflighted graph. It uses the existing
loaded-target dispatcher/history, scoped project CAS and verified return path.
Portrait opt-in uses genuine target-local analysis; no image-view ACK, second
scheduler or substitute renderer is created.
Source authored only; runtime and photographic acceptance are UNRUN.
"""
from copy import deepcopy
import uuid
from . import workflow_owner_protocol as P
from .workflow_preset_handoff import PresetHandoff
from .workflow_preset_catalogue import resolve
from .workflow_preset_dispatch import dispatch

INTENT = P.AUTOMATIC_INTENT
MODULES = frozenset(('lnx.exposure.v1', 'lnx.white_balance.v1'))
PORTRAIT_MODULES = frozenset(('lnx.skin_finish.v1', 'lnx.skin_texture.v1'))


def support_reason(preset, intent=None):
    if (type(preset) is not dict or type(preset.get('modules')) is not dict
            or not preset['modules']):
        return 'invalid_automatic_preset_modules'
    if 'xmp_import' in preset:
        return 'automatic_xmp_not_supported'
    from . import portrait_group_reference as reference
    if reference.selected(preset):
        reason = reference.support(preset)['reason']
        if reason:
            return reason
        if intent is not None and intent != P.AUTOMATIC_REFERENCE_INTENT:
            return 'automatic_requires_explicit_stored_reference_per_target_fit_scope'
        return None
    if intent == P.AUTOMATIC_REFERENCE_INTENT:
        return 'automatic_reference_requires_reference_only_preset'
    if set(preset['modules']) - (MODULES | PORTRAIT_MODULES):
        return 'automatic_requires_supported_global_or_per_face_modules'
    if set(preset['modules']) & PORTRAIT_MODULES:
        from .portrait_group_retained import support
        reason = support(preset)['reason']
        if reason:
            return reason
        # No intent is catalogue-only admission, never job authority.
        if intent is not None and intent != P.AUTOMATIC_PORTRAIT_INTENT:
            return 'automatic_requires_explicit_all_verified_detected_faces_scope'
    return None


class AutomaticPresetHandoff(PresetHandoff):
    def node(self):
        return next((node for node in self.owner.session['ordered']
                     if node['operation']['kind'] == 'automatic_preset'), None)

    def _intent(self):
        node = self.node()
        if node is None:
            raise ValueError('Automatic work requires its exact separate job intent')
        P.automatic_intent(node['operation'].get('intent'))
        if node['error_policy'] not in ('stop', 'skip'):
            raise ValueError('Automatic jobs cannot keep uncertain partial effects')
        return node

    def public(self):
        value = super().public()
        if value is not None:
            # Intermediate synchronous phases never invite a reviewed-mode step.
            value.update(mode='automatic', review=None,
                         phase='unknown' if self.active['phase'] == 'unknown' else 'authorized')
        return value

    def _support_reason(self, preset):
        return support_reason(preset, self._intent()['operation']['intent'])

    def start(self, record, row):
        self._intent()
        operation = record['command']['operation']
        reason = self._support_reason(resolve(operation['preset_id'], operation['preset_sha256']))
        if reason:
            raise ValueError(reason + ': complete preset refused; no module is omitted')
        super().start(record, row)
        # Loading is an actual editor transition. Any lost outcome after this
        # boundary stays query-only, even though no recipe has yet been applied.
        record['dispatch_started'] = True
        try:
            self._open()
        except Exception as error:
            entry = self.active
            # Only a known, observed preparation/read-only assessment failure can
            # become a safe skip. Lost load, rollback, save or commit stays Unknown.
            if entry is None or entry['phase'] != 'awaiting_preparation':
                raise
            preparation = entry.get('preparation')
            if preparation is not None and preparation.started and preparation.expected is None:
                raise
            if preparation is not None and not preparation.started:
                entry['preparation'] = None
            entry['target']['revision'] = self._version(row)
            self._check(target_loaded=True)
            if entry.get('reference_plan') is not None:
                entry['reference_plan'].assert_unchanged()
            entry['automatic_rejection'] = str(error)[:1800]
            self._return()  # exact rollback and editor return must both succeed
            record['dispatch_started'] = False

    def _cancel_result(self, entry, row):
        if 'automatic_rejection' not in entry:
            return super()._cancel_result(entry, row)
        if entry.get('reference_plan') is not None:
            entry['reference_plan'].assert_unchanged(loaded=False)
        return {'status': 'failed', 'code': 'automatic_target_ineligible',
            'message': entry['automatic_rejection'],
            'retained_document': {**entry['initial_document'], 'document_revision': self._version(row)}}

    def _inputs(self):
        """Canonical target/candidate proofs only, never prepare/consume a review."""
        from .workflow_preset_review import _loaded, _candidate, _proof
        from .optics_candidate_identity import fingerprint
        entry = self.active
        self._intent()
        _, row = self._check(target_loaded=True)
        preset = resolve(entry['preset_id'], entry['preset_sha256'])
        reason = self._support_reason(preset)
        if reason:
            raise ValueError(reason)
        loaded = _loaded(self.engine, entry['target'])
        plan = entry.get('portrait_plan') or entry.get('reference_plan')
        if plan is not None:
            evidence = plan.assess(preset, entry['target'])
            self._verify_review_source(evidence['before']['render']['source_proof'])
            return evidence, loaded
        before = self.engine._people_preset_capture()
        after = _candidate(before, preset)
        left, graph = _proof(self.engine, row, before, entry['target'])
        right, candidate_graph = _proof(self.engine, row, after, entry['target'])
        if (left['render']['source_proof'] != right['render']['source_proof']
                or left['render']['people_sha256'] != right['render']['people_sha256']
                or left['repair_sha256'] != right['repair_sha256'] or graph != candidate_graph):
            raise ValueError('Automatic scalar candidate changed source, repairs or people')
        current = _loaded(self.engine, entry['target'])
        if (any(old is not new for old, new in zip(loaded, current))
                or fingerprint(self.engine._people_preset_capture()) != left['render']['candidate_sha256']):
            raise ValueError('Automatic target changed during canonical candidate assessment')
        self._verify_review_source(left['render']['source_proof'])
        return {'before': left, 'after': right}, loaded

    def _review(self):
        # Polymorphic opening hook; deliberately DOES NOT create a review.
        entry = self.active
        # This phase denotes observed target load, not a claimed image review.
        entry['phase'] = 'awaiting_preparation'
        preset = resolve(entry['preset_id'], entry['preset_sha256'])
        if set(preset['modules']) & PORTRAIT_MODULES:
            from .portrait_group_people import PeoplePreparation
            from .workflow_preset_people_save import capture, context
            from .workflow_auto_portrait import TargetPortraitPlan
            _, row = self._check(target_loaded=True)
            entry['portrait_modules'] = deepcopy(preset['modules'])
            entry['people_save_baseline'] = capture(self.engine, row, entry['saved_project'])
            preparation = PeoplePreparation(self.engine, row, self._check)
            entry['preparation'] = preparation
            preparation.analyse()
            preparation.assert_current()
            self.engine._remember_current()
            entry['target']['revision'] = self._version(row)
            self._check(target_loaded=True)
            entry['prepared_people_context'] = context(self.engine, row)
            entry['portrait_plan'] = TargetPortraitPlan(self.engine, row, self._check)
        from .portrait_group_reference import selected as reference_selected
        if reference_selected(preset):
            from .workflow_auto_reference import TargetReferencePlan
            _, row = self._check(target_loaded=True)
            entry['reference_plan'] = TargetReferencePlan(self.engine, row, self._check)
        evidence, loaded = self._inputs()
        entry['automatic_evidence'] = evidence
        entry['people_owner'], entry['people_context'] = loaded[2:]
        report = {'schema': 'lrt.automatic-preset-assessment.v1',
                  'graph_sha256': self.owner.session['graph_sha256'],
                  'identity': entry['preflight']['command']['identity'],
                  'intent': deepcopy(self._intent()['operation']['intent']),
                  'target': deepcopy(entry['target']), 'evidence': evidence}
        assessment = {'report_id': 'automatic:' + entry['operation_id'],
                      'report_sha256': P.digest(report),
                      'document_revision': entry['initial_document']['document_revision'],
                      'preset_sha256': entry['preset_sha256'],
                      'requires_review': False, 'review': None}
        entry.update(assessment=assessment, phase='authorized',
                     message='Automatic job target checked; waiting for journaled application, not human review')
        record = entry['preflight']
        record['receipt'] = self.owner._receipt(record['command'],
            {'status': 'preset_preflight', 'assessment': deepcopy(assessment)})

    def apply(self, record):
        entry = self.active
        if entry is None or entry['phase'] != 'authorized':
            raise ValueError('No exact automatic target assessment is retained')
        command = record['command']; operation = command['operation']
        if (operation['assessment'] != entry['assessment']
                or operation['document'] != entry['initial_document']
                or operation['preset_id'] != entry['preset_id']
                or any(command['identity'][key] != value for key, value in
                       entry['preflight']['command']['identity'].items() if key != 'operation_id')):
            raise ValueError('Automatic apply differs from its journaled exact target assessment')
        entry.update(operation_id=command['identity']['operation_id'], apply=record)
        from . import preset_store as PS, preset_organisation_store as PO
        with PO.catalogue_lock(PS.preset_dir()):
            evidence, loaded = self._inputs()
            if (evidence != entry['automatic_evidence'] or loaded[2] is not entry['people_owner']
                    or loaded[3] is not entry['people_context']):
                raise ValueError('Automatic candidate changed before application')
            request = {'cmd': 'preset', 'action': 'apply', 'request_id': str(uuid.uuid4()),
                       'id': entry['preset_id'], 'document_id': entry['document_id']}
            entry.update(phase='applying', preset_request=deepcopy(request))
            record['dispatch_started'] = True
            plan = entry.get('portrait_plan') or entry.get('reference_plan')
            if plan is not None:
                preset = resolve(entry['preset_id'], entry['preset_sha256'])
                result = plan.commit(preset, entry['target'], request['request_id'], evidence)
            else:
                dispatch(self.engine, request, lambda: self._check(target_loaded=True))
                retained = self.engine._preset_controller()._receipts.get(request['request_id'])
                if retained is None:
                    raise ValueError('Original automatic preset post-history receipt is missing; never retry')
                result = deepcopy(retained[1])
        if result.get('success') is not True or result.get('outcome_unknown'):
            raise ValueError('Automatic preset has no definite successful post-history receipt')
        self.engine._remember_current()
        entry['target']['revision'] = self._version(entry['row'])
        self._verify_applied()
        if entry.get('portrait_plan') is not None:
            from .workflow_preset_people_save import context
            entry['applied_people_context'] = context(self.engine, entry['row'])
        entry.update(applied_recipe=self.owner._encoded_recipe(entry['row']), preset_result=result,
                     phase='awaiting_save')
        # These existing owners validate source, unrelated rows, manifest CAS,
        # actual durable save and exact editor return before publishing success.
        self._save()
        self._return()

    def _stage_save(self):
        entry = self.active
        if entry.get('portrait_plan') is None:
            return super()._stage_save()
        from .workflow_auto_portrait_save import stage
        return stage(self.engine, entry['saved_project'], entry['row'],
            entry['people_save_baseline'], entry['applied_people_context'],
            batch_id=entry['preset_result']['batch_id'],
            prepared_context=entry['prepared_people_context'],
            candidate_graph=entry['automatic_evidence']['candidate_graph'],
            face_refs=entry['automatic_evidence']['face_refs'], modules=entry['portrait_modules'])

    def _verify_applied(self):
        from .workflow_preset_review import _proof
        from .optics_candidate_identity import fingerprint
        entry = self.active
        _, row = self._check(target_loaded=True)
        if (self.engine.__dict__.get('_people_graph_owner') is not entry['people_owner']
                or self.engine.__dict__.get('_people_active_context') is not entry['people_context']):
            raise ValueError('Automatic target people ownership changed')
        plan = entry.get('portrait_plan') or entry.get('reference_plan')
        if plan is not None:
            actual = plan.verify_applied(entry['automatic_evidence'], entry['target'])
            self._verify_review_source(actual['render']['source_proof'])
            self._check(target_loaded=True)
            return
        state = self.engine._people_preset_capture()
        actual, _ = _proof(self.engine, row, state, entry['target'])
        expected = entry['automatic_evidence']['after']
        self._verify_review_source(actual['render']['source_proof'])
        if (any(actual['render'][key] != expected['render'][key]
                for key in ('source_proof', 'candidate_sha256', 'people_sha256'))
                or actual['repair_sha256'] != expected['repair_sha256']
                or actual['snapshot_sha256'] != expected['snapshot_sha256']
                or fingerprint(state) != expected['render']['candidate_sha256']):
            raise ValueError('Actual automatic result differs from its canonical candidate')
        self._check(target_loaded=True)

    def step(self, request):
        raise ValueError('Automatic jobs do not accept reviewed-mode steps or image acknowledgments')

    def image(self, request):
        raise ValueError('Automatic job assessment is not a human-image review')
