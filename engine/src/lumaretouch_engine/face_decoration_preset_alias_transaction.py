# SPDX-License-Identifier: GPL-3.0-or-later
"""Atomic mixed current-state/shared-graph adapter for the existing ledger.

No parallel undo stack, no planner replay and no sibling recipe replacement.
Prepublication rendering uses complete per-member states. Compensation retains
monotonic document/graph fences and never overwrites a changed owner. UNRUN.
"""
from copy import deepcopy
from . import face_decoration_preset_alias_history as H, people_batch_ledger as L
from . import virtual_copy_people as V, creative_derived_source as SOURCE
from .people_preset_plan import clone_state
from .people_graph_patch import between
from .face_decoration_support_alias_transaction import bank


def _state(engine, row):
    return engine._people_preset_capture() if row is V.current_row(engine) else row['state']


def _desired(engine, row, marker, side):
    current = _state(engine, row)
    if row['document_id'] != marker['current_document_id']: return clone_state(current)
    return {**clone_state(current), **clone_state(marker['current_states'][side])}


def prepare(engine, plans, targets, entry, *, redo):
    """Never substitute the selected current crop/repair for a sibling input."""
    from .full_candidate_render import render
    marker = H.check(entry); side = 'after' if redo else 'before'
    H.verify_restore(engine, entry, plans, targets, redo=redo)
    for target in targets.values():
        row = engine._document_versions().find(engine._docs, target['document_id'])[1]
        state = _desired(engine, row, marker, side)
        render(engine, row, state, target['document_id'], str(target['revision']),
            people_graph=plans['project']['candidate'])
    H.verify_restore(engine, entry, plans, targets, redo=redo)


def _replay(engine, state, *, mode, request_id):
    # A managed graph is the sole deform authority. _apply_state's legacy
    # migration otherwise promotes a nonzero UI mirror into durable defaults.
    # Keep exact default/override intent, then let strict graph sync remirror.
    state = clone_state(state)
    if '_deform' in state: state['_deform'] = {'amounts': {}, 'built': False}
    if '_deform_defer' in state: state['_deform_defer'] = False
    return engine._replay_state(state, mode=mode, replayed_for=request_id, strict_local=True)


def publish(owner, engine, plans, targets, entry, *, redo, verify_before=None, mark_started=lambda: None):
    """One publication/compensation boundary for graph and current recipe."""
    from .people_cross_owner_ledger import validate_plans
    marker = H.check(entry)
    if marker is None: raise ValueError('Composite publication requires its distinct protected marker')
    expected_side = 'before' if redo else 'after'; result_side = 'after' if redo else 'before'
    if verify_before is not None: verify_before()
    H.verify_restore(engine, entry, plans, targets, redo=redo)
    validate_plans(plans, targets)
    plan = plans['project']; graph_owner = V.row_owner(engine, plan['row'])
    graph_fence = graph_owner.fence; expected_fence = graph_fence
    live = V.current_row(engine); load_id = getattr(engine, '_load_id', None)
    project = engine.__dict__.get('_people_project_context'); active = engine.__dict__.get('_people_active_context')
    frozen_assets = deepcopy(bank(engine)); H.require_assets(marker, frozen_assets)
    workspace = owner.versions.workspace
    rows = {target['document_id']: owner.versions.find(engine._docs, target['document_id'])[1] for target in targets.values()}
    revisions = {doc: owner.versions.version(row).revision for doc, row in rows.items()}
    if any(revisions[target['document_id']] != target['revision'] for target in targets.values()):
        raise ValueError('Mixed decoration publication target revision changed')
    selected = rows[marker['current_document_id']]
    selected_before = clone_state(_state(engine, selected)); selected_after = _desired(engine, selected, marker, result_side)
    dependencies = {item['document_id']: item for item in marker['dependencies']}
    started = False; graph_written = False; state_written = False; frame = None

    def require_identity():
        from . import face_style_alias_review as CLOSURE
        CLOSURE._pending(engine, plan['row'])
        CLOSURE.verify_dormant(engine, plan['row'], {marker['asset_sha256']})
        if (owner is not engine._batch_controller() or owner.versions.workspace != workspace
                or V.current_row(engine) is not live or getattr(engine, '_load_id', None) != load_id
                or engine.__dict__.get('_people_project_context') is not project
                or engine.__dict__.get('_people_active_context') is not active
                or project.get('owner') is not graph_owner or bank(engine) != frozen_assets
                or V.row_owner(engine, plan['row']) is not graph_owner or graph_owner.fence != expected_fence):
            raise ValueError('Mixed decoration preset publication owner, workspace or active document changed')
        seen = set()
        for row in engine._docs:
            if V.scope(row) != 'project': continue
            proof = SOURCE.row_proof({**row, 'state': _state(engine, row)})
            if proof['asset_sha256'] == marker['asset_sha256']:
                if row.get('trashed') or row.get('_people_new_import'): raise ValueError('Mixed decoration preset alias became unavailable')
                if row['document_id'] in seen:
                    raise ValueError('Mixed decoration publication repeats a source-alias document identity')
                seen.add(row['document_id'])
        if seen != set(rows): raise ValueError('Mixed decoration preset alias closure changed during publication')
        for target in targets.values():
            doc = target['document_id']; found = owner.versions.find(engine._docs, doc)
            if (found is None or found[1] is not rows[doc] or found[1]['path'] != target['path']
                    or V.scope(found[1]) != 'project' or owner.versions.version(found[1]).revision != revisions[doc]):
                raise ValueError('Mixed decoration preset exact target identity, path or revision changed')
            SOURCE.verify_row({**found[1], 'state': _state(engine, found[1])}, target['source_proof'])
            L.verify_reviewed_refs(engine, found[1], target)

    def verify_side(side):
        require_identity(); graph = graph_owner.snapshot()
        if H.graph_digest(graph) != marker[side + '_graph_sha256']:
            raise ValueError('Mixed decoration preset publication graph differs from the reviewed content')
        for doc, row in rows.items():
            if H.dependencies(engine, row, _state(engine, row), graph, marker['state_fields']) != dependencies[doc][side]:
                raise ValueError('Mixed decoration preset publication changed a complete member recipe or support dependency')

    try:
        require_identity(); verify_side(expected_side)
        if verify_before is not None: verify_before()
        # Recheck immediately after the callback, before the one-way mutation
        # claim. This flag suppresses the host's independent document undo path
        # even if publication or compensation later becomes outcome-unknown.
        verify_side(expected_side); started = True; engine._people_shared_mutation = True
        mark_started(); verify_side(expected_side)
        for doc, row in rows.items():
            owner.versions.advance(row); revisions[doc] += 1
        if between(plan['before'], plan['candidate']):
            graph_owner.commit(plan['candidate'], expected_fence=expected_fence)
            expected_fence = graph_owner.fence; graph_written = True
        engine._people_analysis_key = None
        require_identity()
        if selected is live:
            state_written = True
            frame = _replay(engine, selected_after, mode='preset', request_id='preset_alias:' + str(entry.get('request_id', 'history')))
        else:
            selected['state'] = clone_state(selected_after); state_written = True
            if live is not None and V.scope(live) == 'project':
                engine._people_sync(strict=True); frame = engine._write_current_frame('people')
        verify_side(result_side)
        # No sibling state is assigned here. Remembering the active row only
        # synchronizes its already verified own recipe and graph editing views.
        owner.documents.remember_current(); verify_side(result_side)
        V.remember(engine); engine._project_dirty = True
        if frame is not None: frame['doc_state'] = engine.doc_state()
        verify_side(result_side)
        return frame
    except Exception as error:
        rolled_back = False
        if started:
            try:
                require_identity()
                graph = graph_owner.snapshot()
                expected_graph = plan['candidate'] if graph_written else plan['before']
                if H.graph_digest(graph) != H.graph_digest(expected_graph):
                    raise ValueError('Mixed decoration preset rollback cannot overwrite a later graph mutation')
                # Only exact old/new document states are admitted, not an
                # arbitrary partial write or an unrelated intervening edit.
                current_digest = H.stable(H.project_state(_state(engine, selected), marker['state_fields']))
                allowed = {dependencies[marker['current_document_id']][side]['state_sha256'] for side in ('before', 'after')}
                if current_digest not in allowed: raise ValueError('Mixed decoration preset rollback encountered an unrecognized partial document state')
                for doc, row in rows.items():
                    if row is selected: continue
                    if H.dependencies(engine, row, _state(engine, row), graph, marker['state_fields']) != dependencies[doc][result_side if graph_written else expected_side]:
                        raise ValueError('Mixed decoration preset rollback cannot overwrite changed sibling inputs')
                if graph_written:
                    previous = deepcopy(plan['before']); previous['association_revision'] = graph_owner.association_fence
                    graph_owner.commit(previous, expected_fence=expected_fence); expected_fence = graph_owner.fence
                engine._people_analysis_key = None
                if state_written and selected is live:
                    _replay(engine, {**_state(engine, selected), **marker['current_states'][expected_side]},
                        mode='preset_rollback', request_id='preset_alias_rollback:' + str(entry.get('request_id', 'history')))
                elif state_written: selected['state'] = clone_state(selected_before)
                if selected is not live and live is not None and V.scope(live) == 'project': engine._people_sync(strict=True)
                verify_side(expected_side); owner.documents.remember_current(); verify_side(expected_side)
                V.remember(engine); verify_side(expected_side); rolled_back = True
            except Exception:
                owner.editor.invalidate()
        error.side_effects_started = started
        error.rolled_back = rolled_back
        error.requires_reload = started and not rolled_back
        raise
    finally:
        engine._people_staged = None


def commit(engine, *, review, plans, targets, current_before, current_after, modules, request_id, ack, verify_before=None, mark_started=lambda: None):
    """The preset controller retains receipts; the existing batch owns history."""
    started = False
    try:
        if not callable(verify_before):
            raise ValueError('Mixed decoration publication requires its exact retained image/authority verifier')
        verify_before()
        marker = H.prepare(engine, review, plans, targets, current_before=current_before,
            current_after=current_after, modules=modules, ack=ack)
        # Do not remember_current before the review callback: it freezes the
        # retained dormant-history closure as well as all live document inputs.
        return L.commit_scoped(engine._batch_controller(), engine, plans, request_id=request_id,
            prepare=True, prepared_targets=targets, face_decoration_preset_alias_history=marker,
            decoration_preset_alias_verify=verify_before, decoration_preset_alias_started=mark_started)
    except Exception as error:
        if not hasattr(error, 'side_effects_started'): error.side_effects_started = started
        if not hasattr(error, 'rolled_back'): error.rolled_back = False
        if not hasattr(error, 'requires_reload'): error.requires_reload = bool(error.side_effects_started)
        bid = getattr(error, 'batch_id', None)
        if bid is not None:
            # A ledger identity is known even if a later status/dirty hook failed.
            # Echo member outcomes only when the complete published states still
            # match, never by inferring success from a claimed request.
            try:
                owner = engine._batch_controller(); saved = owner.ledger[bid]; frozen = H.check(saved)
                if (frozen is None or frozen['review_sha256'] != review['review_sha256']
                        or frozen['ack'] != ack or saved.get('request_id') != request_id or saved['targets'] != targets):
                    raise ValueError('Mixed decoration late receipt differs from its exact reviewed publication')
                actual = H.targets(engine, frozen, V.row_snapshot(engine, plans['project']['row']), advance=False)
                inverse = {'project': {**plans['project'], 'before': V.row_snapshot(engine, plans['project']['row']),
                    'candidate': plans['project']['before']}}
                H.verify_restore(engine, saved, inverse, actual, redo=False, advance=False)
                members = []
                for member in review['members']:
                    visual = member['visual']; row = owner.versions.find(engine._docs, visual['document_id'])[1]
                    if owner.versions.version(row).revision != int(visual['revision']) + 1: raise ValueError('Published member revision changed')
                    members.append({'document_id': visual['document_id'], 'expected_revision': visual['revision'],
                        'result_revision': str(int(visual['revision']) + 1)})
                error.alias_members = members; error.face_decoration_preset_alias_review = H.status_summary(saved)
            except Exception: pass
        raise


def failure_context(owner, request):
    """Echo only a validated existing ledger marker, never client proof fields."""
    if request.get('action') not in ('undo', 'redo'): return {}
    bid = request.get('batch_id'); entry = owner.ledger.get(str(bid or ''), {})
    try: marker = H.status_summary(entry)
    except (ValueError, TypeError, KeyError): return {}
    return {} if marker is None else {'batch_id': bid, 'module_scope': [L.OP], H.KEY: marker}


def require_history_request(owner, request, batch):
    """Composite history must use the native-correlated exact command envelope.

    Native text limits count UTF-8 bytes and reject C0/C1 control characters.
    Old unmarked history keeps its historical uncorrelated request contract.
    """
    if (type(request) is not dict or set(request) != {'cmd', 'action', 'request_id', 'batch_id'}
            or request['cmd'] != 'batch' or request['action'] not in ('undo', 'redo')):
        raise ValueError('Mixed decoration preset history requires an exact correlated batch undo/redo command')
    for key in ('request_id', 'batch_id'):
        value = request[key]
        if (type(value) is not str or not value.strip() or len(value.encode('utf-8')) > 128
                or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
            raise ValueError('Mixed decoration preset history requires bounded nonempty native request and batch identities')
    if owner.ledger.get(request['batch_id']) is not batch:
        raise ValueError('Mixed decoration preset history requires its exact existing ledger identity')
