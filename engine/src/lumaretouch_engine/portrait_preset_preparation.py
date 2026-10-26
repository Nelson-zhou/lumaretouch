# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit serial preparation using real load, portrait and history owners.

Session receipts are dispatch deduplication, not another document/history store.
There is no candidate freeze until all targets are parked and the editor restored.
Source integration only; runtime, quality and performance acceptance are UNRUN.
"""
from copy import deepcopy
from . import creative_derived_source as SOURCE, virtual_copy_people as V
from .optics_candidate_identity import fingerprint
from .workflow_preset_dispatch import dispatch
from .workflow_preset_preparation import SkinPreparation
from .portrait_group_retained import resolve as _preset, retained

MAX_RECEIPTS = 64


def _neutral(state):
    return {k: v for k, v in state.items() if k != '_proxy'}


class GroupPreparation:
    def __init__(self, group):
        self.group = group
        self.receipts = {}

    def run(self, request):
        identity = request['request_id']
        key = fingerprint(request)
        old = self.receipts.get(identity)
        if old is not None:
            if old[0] != key:
                raise ValueError('Preparation request identity cannot be reused for another selection')
            return deepcopy(old[1])
        if len(self.receipts) >= MAX_RECEIPTS:
            raise ValueError('Preparation receipt capacity reached; no attempt was started')
        docs = request.get('docs')
        if (type(docs) is not list or not 1 <= len(docs) <= 8
                or any(type(doc) is not str or not 1 <= len(doc) <= 128 for doc in docs)
                or len(set(docs)) != len(docs)):
            raise ValueError('Select one to eight distinct fresh originals')
        preset = _preset(request.get('preset_id'), request.get('preset_sha256'))
        from .portrait_group_reference import selected
        if selected(preset):
            raise ValueError('Reference-only groups use direct review; no face preparation is required')
        engine = self.group.engine
        original = V.current_row(engine)
        if original is None or not engine._load_id or engine._project_dirty:
            raise ValueError('Preparation needs a clean loaded editor and no unsaved project edits')
        engine._remember_current()
        rows = [self.group._row(doc)[1] for doc in docs]
        fresh = fingerprint(_neutral(engine._fresh_doc_state()))
        for row in rows:
            if (row.get('copy_number', 0) != 0 or SOURCE.record(row['state']) is not None
                    or row.get('undo') != [] or row.get('redo') != []
                    or fingerprint(_neutral(row['state'])) != fresh):
                raise ValueError('Every selected target must be a fresh neutral original without history')
            # Unclassified imports are classified by activate(), never by this
            # coordinator. The canonical classifier gives duplicate roots their
            # own empty context rather than borrowing another source's masks.
            graph = V.peek_graph(engine, row)
            asset = SOURCE.row_proof(row)['asset_sha256']
            if graph is not None and (asset in graph['analysis_runs']
                    or any(face['asset_sha256'] == asset for face in graph['faces'].values())
                    or any(item['asset_sha256'] == asset for item in graph['unresolved_legacy'])
                    or any(item['scope'] == 'all_people' and item['target_id'] == asset for item in graph['overrides'])):
                raise ValueError('Fresh preparation cannot replace existing retained portrait intent')
        workspace = self.group.batch.versions.workspace
        recovery = engine.__dict__.get('_project_recovery_runtime')
        proofs = [(row, SOURCE.row_proof(row)) for row in [original, *rows]]
        if len({proof['asset_sha256'] for _, proof in proofs}) != len(proofs):
            raise ValueError('Fresh group requires distinct physical sources, including the editor')
        original_state = fingerprint(original['state'])
        original_history = fingerprint((original['undo'], original['redo']))
        original_revision = self.group.batch.versions.version(original)
        budget = int(engine._proxy_budget)
        original_source = proofs[0][1]
        original_owner = engine._people_owner()
        original_context = engine.__dict__.get('_people_active_context')
        original_asset = original_source['asset_sha256']

        def editor_people():
            if (engine._people_owner() is not original_owner
                    or engine.__dict__.get('_people_active_context') is not original_context):
                raise ValueError('Original editor portrait owner was replaced')
            return fingerprint({'slice': original_owner.capture_document(original_asset),
                'analysis': engine.__dict__.get('_people_analyses', {}).get(original_asset),
                'cursor': engine.__dict__.get('_people_cursors', {}).get(original_asset),
                'target': engine.__dict__.get('_people_targets', {}).get(original_asset),
                'landmarks': {key: value for key, value in engine.__dict__.get('_people_landmarks', {}).items()
                    if value.get('face_ref', {}).get('asset_sha256') == original_asset}})

        original_people = editor_people()

        def check():
            if (self.group.batch.versions.workspace != workspace
                    or engine.__dict__.get('_project_recovery_runtime') is not recovery
                    or recovery is not None and recovery.tainted):
                raise ValueError('Workspace or recovery ownership changed; do not repeat preparation')
            for row, proof in proofs:
                matches = [item for item in engine._docs if item.get('document_id') == row['document_id']]
                if len(matches) != 1 or matches[0] is not row or row.get('trashed'):
                    raise ValueError('Preparation document ownership changed')
                SOURCE.verify_row(row, proof)

        def load(row, max_px):
            check()
            previous_load = engine._load_id
            dispatch(engine, {'cmd': 'load_image', 'path': row['path'],
                'document_id': row['document_id'], 'max_px': max_px}, check)
            check()
            if (V.current_row(engine) is not row or not engine._image_loaded
                    or not engine._load_id or engine._load_id == previous_load):
                raise ValueError('Canonical load did not establish a new exact target load identity')

        check()
        result = {'success': False, 'portrait_preset': True, 'preparation': True,
            'portrait_preset_docs': list(docs), 'docs': list(docs),
            'preset_id': request['preset_id'], 'preset_sha256': request['preset_sha256'],
            'preparation_results': [{'document_id': doc, 'status': 'not_started'} for doc in docs],
            'editor_restored': False, 'outcome_unknown': True, 'no_write': False}
        # Claim before the first load. Replays query this exact receipt and never
        # redispatch analysis after a timeout, partial failure or missing result.
        self.receipts[identity] = (key, deepcopy(result))
        known = True
        error = None
        try:
            for row, outcome in zip(rows, result['preparation_results']):
                preparation = None
                known = False
                try:
                    load(row, budget)
                    from .portrait_group_people import PeoplePreparation
                    preparation_type = PeoplePreparation if retained(preset) else SkinPreparation
                    preparation = preparation_type(engine, row, check)
                    preparation.analyse()
                    preparation.assert_current()
                    engine._remember_current()
                    outcome['status'] = 'prepared'
                    known = True
                except Exception as failure:
                    outcome.update(status='failed', error=str(failure)[:2000])
                    # Only the exact current attempt may roll back its own
                    # target. Never replay a previous target's stale load proof.
                    if preparation is not None and preparation.expected is not None:
                        preparation.restore()
                        known = True
                    raise
        except Exception as failure:
            error = str(failure)[:2000]
        if known:
            try:
                check()
                if (fingerprint(original['state']) != original_state
                        or fingerprint((original['undo'], original['redo'])) != original_history
                        or self.group.batch.versions.version(original) != original_revision):
                    raise ValueError('Original editor changed while group preparation owned the session')
                if V.current_row(engine) is not original:
                    load(original, budget)
                engine._remember_current()
                SOURCE.verify_row(original, original_source)
                if (fingerprint(original['state']) != original_state
                        or fingerprint((original['undo'], original['redo'])) != original_history
                        or self.group.batch.versions.version(original) != original_revision
                        or engine._project_dirty or editor_people() != original_people):
                    raise ValueError('Original editor recipe/history restoration did not match')
                result['editor_load_id'] = engine._load_id
                result['editor_restored'] = True
                result['outcome_unknown'] = False
            except Exception as failure:
                error = str(failure)[:2000]
        if error is None and result['editor_restored']:
            try:
                # Later preparations advance shared portrait context; freezing
                # any earlier target before this point would create stale proof.
                result.update(self.group._prepare({**request, 'action': 'portrait_preset_preflight'}))
            except Exception as failure:
                error = str(failure)[:2000]
        if error is not None:
            result.update(success=False, error=error)
        self.receipts[identity] = (key, deepcopy(result))
        return result


def observe_outcome(engine, request, result):
    """Private committed-boundary fact; JSON cannot supply this proof."""
    from .project_recovery_runtime import _local
    boundary = getattr(_local, 'boundary', None)
    if (boundary is not None and boundary['engine'] is engine
            and boundary['message'] is request and boundary['started']):
        boundary['portrait_preparation_outcome'] = {key: result.get(key) for key in
            ('outcome_unknown', 'editor_restored', 'no_write')}
