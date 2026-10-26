# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepared-original preset groups over the existing frozen batch/history owners.

Read-only review requires already prepared parked targets. Explicit preparation
is delegated to the real serial load/analysis owner; this module never saves or
exports directly. Runtime
and image-quality acceptance remain UNRUN.
"""
from base64 import b64encode
from copy import deepcopy
from hashlib import sha256

from . import workflow_preset_catalogue as catalogue, workflow_preset_review as review
from . import batch_preflight as frozen, optics_auto_scope as candidate_owner
from . import creative_derived_source as SOURCE, full_candidate_render as full
from . import virtual_copy_people as V, people_state as S, scope
from .optics_candidate_identity import fingerprint
from .workflow_preset_preparation import DERIVED_FIELDS
from . import portrait_preset_delivery as delivery, portrait_group_retained as retained
from . import portrait_group_reference as reference

ACTIONS = frozenset(('portrait_preset_catalogue', 'portrait_preset_preflight',
                     'portrait_preset_commit', 'portrait_preset_image', 'portrait_preset_prepare')) | delivery.ACTIONS
MAX_TARGETS = 8
BASE_KEYS = {'cmd', 'action', 'request_id'}
KEYS = {
    **delivery.KEYS,
    'portrait_preset_catalogue': BASE_KEYS,
    'portrait_preset_prepare': BASE_KEYS | {'docs', 'preset_id', 'preset_sha256'},
    'portrait_preset_preflight': BASE_KEYS | {'docs', 'preset_id', 'preset_sha256'},
    'portrait_preset_commit': BASE_KEYS | {'preflight_token', 'portrait_preset_ack', 'accepted'},
    'portrait_preset_image': BASE_KEYS | {'preflight_token', 'document_id', 'side', 'page'},
}


def read_only(p):
    """Strict fast-path classification; never infer a mutation from malformed keys."""
    if type(p) is not dict or p.get('cmd') != 'batch':
        return False
    action = p.get('action')
    if action in delivery.ACTIONS:
        return action in delivery.READS and delivery.command(p)
    if action not in ACTIONS - {'portrait_preset_commit', 'portrait_preset_prepare'} or set(p) != KEYS[action]:
        return False
    if type(p.get('request_id')) is not str or not 1 <= len(p['request_id']) <= 128:
        return False
    if action == 'portrait_preset_catalogue':
        return True
    if action == 'portrait_preset_preflight':
        docs = p.get('docs')
        return (type(docs) is list and 1 <= len(docs) <= MAX_TARGETS
            and all(type(doc) is str and 1 <= len(doc) <= 128 for doc in docs)
            and len(set(docs)) == len(docs) and type(p.get('preset_id')) is str
            and 1 <= len(p['preset_id']) <= 128 and _sha(p.get('preset_sha256')))
    return (type(p.get('preflight_token')) is str and len(p['preflight_token']) == 32
        and type(p.get('document_id')) is str and 1 <= len(p['document_id']) <= 128
        and p.get('side') in ('before', 'after') and type(p.get('page')) is int
        and 0 <= p['page'] < (review.MAX_PNG_BYTES + review.PAGE_BYTES - 1) // review.PAGE_BYTES)


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def acknowledgment(target):
    return {key: target[key] for key in ('document_id', 'revision', 'review_sha256')} | {
        'before_sha256': target['before']['sha256'], 'after_sha256': target['after']['sha256']}


def _admit(engine, row, state):
    """Parked equivalent of retained-skin admission, without activating an owner."""
    if (row.get('trashed') or row.get('copy_number', 0) != 0 or SOURCE.record(state) is not None
            or row.get('_people_new_import') or row.get('undo') != [] or row.get('redo') != []):
        raise ValueError('Group presets require prepared unedited original targets, without history')
    recovery = engine.__dict__.get('_project_recovery_runtime')
    if recovery is not None and recovery.tainted:
        raise ValueError('Uncertain project recovery must be resolved before group review')
    fresh = engine._fresh_doc_state()
    omitted = DERIVED_FIELDS | {'_proxy'}
    if fingerprint({k: v for k, v in state.items() if k not in omitted}) != fingerprint(
            {k: v for k, v in fresh.items() if k not in omitted}):
        raise ValueError('Group preset target is edited; prepare a fresh original instead')
    if (state.get('_strength') != 0.0 or state.get('_channel') != 'skin'
            or state.get('_deform', {}).get('amounts') != fresh.get('_deform', {}).get('amounts')
            or state.get('_enhance', {}).get('amounts') != fresh.get('_enhance', {}).get('amounts')):
        raise ValueError('Preparation must be pixel-neutral, with target-owned skin selected')
    context = full.people_context(engine, row)
    graph = context['people_graph']
    source = SOURCE.row_proof({**row, 'state': state})
    asset = source['asset_sha256']
    pc = state.get('_precompute')
    if (pc is None or getattr(pc, 'backend', None) != 'mediapipe'
            or type(getattr(pc, 'num_faces', None)) is not int or pc.num_faces != 1
            or getattr(pc, 'masks', {}).get('skin') is None):
        raise ValueError('Every target needs its own real single-face MediaPipe skin analysis')
    SOURCE.verify_precompute(state, pc)
    faces = [face for face in graph['faces'].values() if face['asset_sha256'] == asset]
    run = graph['analysis_runs'].get(asset)
    if (len(faces) != 1 or faces[0]['manual'] or not faces[0]['enabled']
            or run is None or run['limit_reached']):
        raise ValueError('Missing, manual, multiple or detection-limited target faces are not supported')
    face = faces[0]; ref = S.face_ref(face)
    from .people_binding import evidence, landmark_digest
    measured = evidence(pc, pc.landmarks, (row['src_w'], row['src_h']))
    runtime = row.get(V.RUNTIME) if V.is_private(row) else engine.__dict__.get('_people_project_context')
    analyses = (engine.__dict__.get('_people_analyses', {})
                if runtime is not None and runtime is engine.__dict__.get('_people_active_context')
                else (runtime or {}).get('analyses', {}))
    analysis = analyses.get(asset, {}).get(ref['face_instance_id'])
    if (measured['status'] != 'verified' or face['evidence'] != measured
            or analysis is None or analysis.get('face_ref') != ref or analysis.get('evidence') != measured
            or landmark_digest(analysis.get('landmarks')) != measured['landmark_digest']
            or analysis.get('skin') is None
            or context['people_cursors'].get(asset) != ref['face_instance_id']
            or context['people_targets'].get(asset) != {
                'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}):
        raise ValueError('Target skin, retained face evidence and explicit face selection differ')
    if (any(link['face_instance_id'] == ref['face_instance_id'] for link in graph['links'])
            or any(ref['face_instance_id'] in group['face_ids'] for group in graph['groups'].values())
            or any(item['scope'] == 'face' and item['target_id'] == ref['face_instance_id']
                   or item['scope'] == 'all_people' and item['target_id'] == asset
                   for item in graph['overrides'])
            or any(item['asset_sha256'] == asset and item['status'] == 'unresolved'
                   for item in graph['unresolved_legacy'])):
        raise ValueError('Group scalar presets cannot replace retained edits or shared-person intent')
    return context


class PortraitPresetBatch:
    def __init__(self, engine, batch):
        self.engine, self.batch = engine, batch
        # Disposable image evidence only; token lifecycle/history belong to batch.
        self.records = {}
        from .portrait_preset_preparation import GroupPreparation
        self.preparation = GroupPreparation(self)
        self.delivery = delivery.GroupDelivery(self)

    @property
    def store(self):
        return self.batch.preflight.store

    def owns(self, token):
        if token in self.records:
            return True
        if type(token) is not str or len(token) != 32:
            return False
        result = self.store.completed(token, self.batch.versions.workspace)
        return result is not None and result.get('portrait_preset') is True

    def _prune(self):
        self.store._prune(self.store.clock())
        self.records = {token: record for token, record in self.records.items()
                        if token in self.store.pending or token in self.store.terminal}
        for token, record in self.records.items():
            if token not in self.store.pending:
                record['images'] = {}

    def _row(self, document_id):
        rows = [(index, row) for index, row in enumerate(self.engine._docs)
                if row.get('document_id') == document_id and not row.get('trashed')]
        if len(rows) != 1 or rows[0][0] == self.engine._doc_index:
            raise ValueError('Select exact parked targets, excluding the current editor photograph')
        return rows[0]

    def _inputs(self, document_id, preset, staged=None):
        if reference.selected(preset):
            return reference.inputs(self, document_id, preset, staged)
        if retained.retained(preset):
            return retained.inputs(self, document_id, preset, staged)
        index, row = self._row(document_id)
        version = self.batch.versions.version(row)
        state = row['state']
        context = _admit(self.engine, row, state)
        after = candidate_owner.candidate(state, preset['modules'])
        # Identical normal-batch WB preparation must precede the frozen render.
        from . import white_balance_recipe as WB
        WB.prepare_state(after)
        target = {'document_id': document_id, 'revision': str(version.revision)}
        left, graph = review._proof(self.engine, row, state, target)
        right, candidate_graph = review._proof(self.engine, row, after, target)
        if (graph != candidate_graph or left['render']['source_proof'] != right['render']['source_proof']
                or left['render']['people_sha256'] != right['render']['people_sha256']
                or left['repair_sha256'] != right['repair_sha256']):
            raise ValueError('Group candidate changed source, repairs or retained portrait ownership')
        return {'index': index, 'row': row, 'target': target, 'before': left, 'after': right,
                'context': fingerprint(context), 'history': fingerprint((row['undo'], row['redo']))}, state, after, graph

    def _verify(self, record, planned=None):
        preset = retained.resolve(record['preset_id'], record['preset_sha256'])
        staged = retained.plans(self, [old['target']['document_id'] for old in record['inputs']], preset) if retained.retained(preset) else None
        if self.batch.versions.workspace != record['workspace']:
            raise ValueError('Prepared group workspace changed')
        for old in record['inputs']:
            new, _, after, _ = self._inputs(old['target']['document_id'], preset,
                old['reference_fit'] if reference.selected(preset) else staged)
            if new['row'] is not old['row'] or any(new[k] != old[k] for k in new if k != 'row'):
                raise ValueError('Frozen group target, source, history, candidate or people context changed')
            if planned is not None:
                match = [item for item in planned if item[0] == old['index']]
                if (len(match) != 1 or fingerprint(match[0][1]) != old['before']['render']['candidate_sha256']
                        or fingerprint(match[0][2]) != fingerprint(after)):
                    raise ValueError('Canonical batch candidate differs from the approved group render')
        if planned is not None and len(planned) != len(record['inputs']):
            raise ValueError('Canonical batch changed the frozen group membership')

    def _prepare(self, p):
        docs = p.get('docs')
        if (type(docs) is not list or not 1 <= len(docs) <= MAX_TARGETS
                or any(type(doc) is not str or not doc for doc in docs) or len(set(docs)) != len(docs)):
            raise ValueError('Select one to eight distinct prepared original document IDs')
        preset = retained.resolve(p.get('preset_id'), p.get('preset_sha256'))
        is_retained = retained.retained(preset)
        staged = retained.plans(self, docs, preset) if is_retained else None
        if len(self.store.pending) >= frozen.MAX_PENDING:
            raise ValueError('Pending group reviews are full; resolve the existing plans first')
        inputs = []; targets = []; images = {}; frozen_targets = []; total = 0
        physical_sources = set()
        for document in docs:
            owned, before, after, graph = self._inputs(document, preset, staged)
            target = owned['target']; row = owned['row']
            if reference.selected(preset):
                asset = owned['before']['render']['source_proof']['asset_sha256']
                if asset in physical_sources:
                    raise ValueError('Reference group requires distinct physical target originals')
                physical_sources.add(asset)
            left, a, proof_a = review._image(self.engine, row, before, owned.get('before_graph', graph), target, owned['before'], lambda: False)
            right, b, proof_b = review._image(self.engine, row, after, graph, target, owned['after'], lambda: False)
            if proof_a['source_size'] != proof_b['source_size'] or proof_a['output_size'] != proof_b['output_size']:
                raise ValueError('Group preset candidate changed source or output geometry')
            total += len(a) + len(b)
            if total + sum(sum(len(raw) for pair in rec['images'].values() for raw in pair.values())
                           for rec in self.records.values()) > review.MAX_CACHE_BYTES:
                raise ValueError('Group image evidence exceeds its bounded cache; no target was omitted')
            public = {**target, 'path': row['path'], 'before': left, 'after': right,
                      'source_size': proof_a['source_size'], 'output_size': proof_a['output_size']}
            if reference.selected(preset):
                public['reference_color'] = deepcopy(owned['reference_fit'])
            if is_retained:
                public.update(face_count=len(owned['face_refs']), face_refs=deepcopy(owned['face_refs']))
            public['review_sha256'] = review._digest({**public, 'preset_id': p['preset_id'],
                'preset_sha256': p['preset_sha256'], 'proofs': [owned['before'], owned['after']]})
            inputs.append(owned); targets.append(public); images[document] = {'before': a, 'after': b}
            frozen_targets.append(frozen.FrozenTarget(document, int(target['revision']), owned['index'], row['path'],
                None, frozen.canonical({} if is_retained else scope.params_of(before, list(preset['modules']))),
                source_proof_json=frozen.canonical(owned['before']['render']['source_proof'])))
        record = {'inputs': inputs, 'targets': targets, 'images': images, 'served': {
            doc: {'before': set(), 'after': set()} for doc in docs},
            'preset_id': p['preset_id'], 'preset_sha256': p['preset_sha256'],
            'workspace': self.batch.versions.workspace, 'mode': retained.MODE if is_retained else reference.MODE if reference.selected(preset) else 'legacy_scalar'}
        self._verify(record)
        first = frozen_targets[0]
        plan = self.store.create(record['workspace'], first.document_id, first.revision, first.path,
            list(preset['modules']), preset['modules'], 'recheck', frozen_targets, [],
            source_proof=inputs[0]['before']['render']['source_proof'])
        self.records[plan.token] = record
        return {'success': True, 'portrait_preset': True, 'preflight_token': plan.token,
                'preset_id': p['preset_id'], 'preset_sha256': p['preset_sha256'],
                'module_scope': list(plan.modules), 'mode': record['mode'], 'targets': targets, 'rejected_docs': [], 'policy': 'recheck'}

    def _image(self, p):
        plan = self.store.get(p.get('preflight_token'), self.batch.versions.workspace)
        record = self.records.get(plan.token)
        if record is None:
            raise ValueError('Group image evidence is unavailable; prepare a new group')
        document, side, page = p.get('document_id'), p.get('side'), p.get('page')
        target = next((item for item in record['targets'] if item['document_id'] == document), None)
        if target is None or side not in ('before', 'after') or type(page) is not int or not 0 <= page < target[side]['page_count']:
            raise ValueError('Request an exact group target image page')
        raw = record['images'][document][side]
        chunk = raw[page * review.PAGE_BYTES:(page + 1) * review.PAGE_BYTES]
        record['served'][document][side].add(page)
        return {'success': True, 'portrait_preset': True, 'preflight_token': plan.token,
                'document_id': document, 'side': side, 'page': page,
                'page_count': target[side]['page_count'], 'byte_length': len(raw),
                'sha256': target[side]['sha256'], 'page_sha256': sha256(chunk).hexdigest(),
                'revision': target['revision'], 'review_sha256': target['review_sha256'],
                'mime': target[side]['mime'], 'width': target[side]['width'], 'height': target[side]['height'],
                'page_bytes': review.PAGE_BYTES, 'offset': page * review.PAGE_BYTES, 'page_byte_length': len(chunk),
                'base64': b64encode(chunk).decode('ascii')}

    def _commit(self, p):
        token = p.get('preflight_token')
        cached = self.store.completed(token, self.batch.versions.workspace)
        if cached is not None:
            if (cached.get('portrait_preset') is not True or p.get('accepted') is not True
                    or p.get('portrait_preset_ack') != cached.get('portrait_preset_ack')):
                raise ValueError('Group replay requires its exact original acceptance')
            return {**cached, 'replayed': True}
        plan = self.store.get(token, self.batch.versions.workspace)
        record = self.records.get(token)
        if record is None:
            raise ValueError('Missing private group review; a generic preflight cannot authorize this operation')
        expected = [acknowledgment(target) for target in record['targets']]
        if p.get('accepted') is not True or p.get('portrait_preset_ack') != expected:
            raise ValueError('Explicitly accept the exact complete frozen group')
        for target in record['targets']:
            for side in ('before', 'after'):
                raw = record['images'][target['document_id']][side]
                if (sha256(raw).hexdigest() != target[side]['sha256']
                        or record['served'][target['document_id']][side] != set(range(target[side]['page_count']))):
                    raise ValueError('Read every page of every exact before/after image before group acceptance')
        self._verify(record)
        rows = [{'index': t.index, 'path': t.path, 'blocked': None,
                 '_source_proof': old['before']['render']['source_proof'],
                 **({'_reference_prepared': old['reference_fit']} if 'reference_fit' in old else {})}
                for t, old in zip(plan.targets, record['inputs'])]
        base = {'portrait_preset': True, 'portrait_preset_ack': expected, 'accepted': True,
                'preset_id': record['preset_id'], 'preset_sha256': record['preset_sha256'],
                'approved_document_ids': [t['document_id'] for t in record['targets']],
                'preflight_token': token, 'module_scope': list(plan.modules), 'request_id': p.get('request_id'),
                'mode': record['mode']}
        if len(self.delivery.proofs) >= 64:
            raise ValueError('Group delivery session capacity reached; no group edit was started')
        self.store.claim(plan, request_id=p.get('request_id'))
        self.store.finish(plan, {**base, 'success': False, 'outcome_unknown': True,
                                'error': 'Group commit claimed; actual result not yet recorded'})
        try:
            if record['mode'] == retained.MODE:
                body = retained.commit(self, record, p.get('request_id'))
            else:
                body = self.batch.commit(list(plan.modules), plan.params(), rows, 'recheck', [],
                    source_snapshot={'document_id': plan.source_id, 'revision': str(plan.source_revision),
                        'path': plan.source_path, 'source_proof': record['inputs'][0]['before']['render']['source_proof']},
                    before_publish=lambda planned: self._verify(record, planned))
            result = {**body, **base, 'success': True, 'outcome_unknown': False}
            result.update(self.delivery.capture(token, result))
            self.store.finish(plan, result)
            return result
        except Exception as error:
            result = {**base, 'success': False, 'outcome_unknown': True, 'error': str(error)[:2000]}
            self.store.finish(plan, result)
            return result
        finally:
            record['images'] = {}

    def handle(self, p):
        try:
            action = p.get('action')
            if action not in ACTIONS or set(p) - KEYS[action]:
                raise ValueError('Unknown group-preset action or options')
            request = p.get('request_id')
            if type(request) is not str or not 1 <= len(request) <= 128:
                raise ValueError('Group operation requires an exact bounded request identity')
            self._prune()
            if action in ('portrait_preset_preflight', 'portrait_preset_commit', 'portrait_preset_prepare'):
                why = self.batch.editor.guard('batch ' + action)
                if why:
                    raise ValueError(why)
            if action in delivery.ACTIONS:
                result = self.delivery.run(p)
            elif action == 'portrait_preset_catalogue':
                result = {'success': True, 'portrait_preset': True, 'catalogue': catalogue.list_catalogue(group_support=True)}
            elif action == 'portrait_preset_prepare': result = self.preparation.run(p)
            elif action == 'portrait_preset_preflight': result = self._prepare(p)
            elif action == 'portrait_preset_image': result = self._image(p)
            else: result = self._commit(p)
        except Exception as error:
            claimed = False
            if p.get('action') in delivery.ACTIONS:
                claimed = self.delivery.uncertain(p)
            if p.get('action') == 'portrait_preset_commit':
                token = p.get('preflight_token')
                claimed = type(token) is str and token in self.store.terminal and token in self.records
            if p.get('action') == 'portrait_preset_prepare':
                claimed = type(p.get('request_id')) is str and p['request_id'] in self.preparation.receipts
            result = {'success': False, 'portrait_preset': True, 'no_write': not claimed,
                      'outcome_unknown': claimed, 'error': str(error)[:2000]}
            correlated = {
                'portrait_preset_commit': ('preflight_token', 'portrait_preset_ack', 'accepted'),
                'portrait_preset_prepare': ('preset_id', 'preset_sha256', 'docs'),
                'portrait_preset_preflight': ('preset_id', 'preset_sha256', 'docs'),
                'portrait_preset_image': ('preflight_token', 'document_id', 'side', 'page'),
            }.get(p.get('action'), ())
            result.update({key: deepcopy(p.get(key)) for key in correlated})
            if p.get('action') in delivery.ACTIONS:
                result.update(delivery.identity(p))
            if p.get('action') == 'portrait_preset_prepare':
                result.update(preparation=True, portrait_preset_docs=deepcopy(p.get('docs')),
                    preparation_results=[], editor_restored=not claimed)
        if p.get('action') == 'portrait_preset_prepare':
            from .portrait_preset_preparation import observe_outcome
            observe_outcome(self.engine, p, result)
        return self.batch.preflight.emit_result(p, result)
