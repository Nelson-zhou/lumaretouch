# SPDX-License-Identifier: GPL-3.0-or-later
"""Atomic shared recovery graph/bank publication, never recipe replay. UNRUN.

The existing batch ledger remains the sole history owner. Complete member
renders are prepared with a staged immutable bank, without changing live state.
Compensation is fenced and conservative: it never overwrites a changed owner.
"""
from copy import deepcopy
from . import eye_bag_recovery_alias_history as H, people_batch_ledger as L
from . import virtual_copy_people as V, creative_derived_source as SOURCE


def bank(engine):
    project = engine.__dict__.get('_people_project_context')
    if type(project) is not dict or project.get('owner') is None:
        raise ValueError('Recovery aliases need their retained shared project owner')
    return (engine._people_support if engine.__dict__.get('_people_active_context') is project
            else project.get('people_support_assets'))


def _set_bank(engine, project, assets):
    project['people_support_assets'] = assets
    if engine.__dict__.get('_people_active_context') is project: engine._people_support = assets


def prepare(engine, plans, targets, entry, *, redo, assets):
    from .full_candidate_render import render, people_context
    H.verify_restore(engine, entry, plans, targets, redo=redo, assets=assets)
    for target in targets.values():
        row = engine._document_versions().find(engine._docs, target['document_id'])[1]
        context = people_context(engine, row)
        context['people_graph'] = deepcopy(plans['project']['candidate'])
        context['people_support_assets'] = deepcopy(assets)
        render(engine, row, H.current_state(engine, row), target['document_id'], str(target['revision']),
               people_graph=plans['project']['candidate'], staged_people_context=context)
    H.verify_restore(engine, entry, plans, targets, redo=redo, assets=assets)


def publish(owner, engine, plans, targets, entry, *, redo, assets, verify_before=None):
    from .people_cross_owner_ledger import validate_plans
    marker = H.check(entry)
    if marker is None: raise ValueError('Recovery publication requires its distinct protected marker')
    if verify_before is not None: verify_before()
    H.verify_restore(engine, entry, plans, targets, redo=redo, assets=assets)
    validate_plans(plans, targets)
    plan = plans['project']; graph_owner = V.row_owner(engine, plan['row'])
    project = engine.__dict__.get('_people_project_context'); active = engine.__dict__.get('_people_active_context')
    expected_fence = graph_owner.fence; workspace = owner.versions.workspace
    live = V.current_row(engine); load_id = getattr(engine, '_load_id', None)
    old_assets = bank(engine); candidate_assets = deepcopy(assets)
    if any(candidate_assets.get(key) != value for key, value in old_assets.items()):
        raise ValueError('Recovery publication cannot replace an immutable retained vector')
    allowed = {H.BANK.content_digest(record) for record in marker['recovery_assets'].values() if record is not None}
    if set(candidate_assets) - set(old_assets) - allowed:
        raise ValueError('Recovery publication cannot append unrelated or donor support assets')
    rows = {target['document_id']: owner.versions.find(engine._docs, target['document_id'])[1] for target in targets.values()}
    revisions = {doc: owner.versions.version(row).revision for doc, row in rows.items()}
    if any(revisions[item['document_id']] != item['revision'] for item in targets.values()):
        raise ValueError('Recovery publication member revision changed')
    expected_side = 'before' if redo else 'after'; result_side = 'after' if redo else 'before'
    dependencies = {item['document_id']: item for item in marker['dependencies']}
    started = False; graph_written = False; bank_written = False; frame = None

    def require_identity():
        if (owner is not engine._batch_controller() or owner.versions.workspace != workspace
                or V.current_row(engine) is not live or getattr(engine, '_load_id', None) != load_id
                or engine.__dict__.get('_people_project_context') is not project
                or engine.__dict__.get('_people_active_context') is not active
                or project['owner'] is not graph_owner or graph_owner.fence != expected_fence):
            raise ValueError('Recovery publication workspace, selected document or shared owner changed')
        actual = H.targets(engine, marker, graph_owner.snapshot(), advance=False)
        expected = {item['document_id']: {**item, 'revision': revisions[item['document_id']]} for item in targets.values()}
        if {item['document_id']: item for item in actual.values()} != expected:
            raise ValueError('Recovery publication exact affected closure, source, path or revisions changed')
        from .face_style_alias_review import verify_dormant
        verify_dormant(engine, plan['row'], {marker['asset_sha256']})
        for doc, row in rows.items():
            found = owner.versions.find(engine._docs, doc)
            if found is None or found[1] is not row: raise ValueError('Recovery publication replaced an exact member')
            SOURCE.verify_row({**row, 'state': H.current_state(engine, row)}, expected[doc]['source_proof'])
            L.verify_reviewed_refs(engine, row, expected[doc])

    def verify_side(side, expected_assets):
        require_identity(); actual_assets = bank(engine)
        if actual_assets != expected_assets: raise ValueError('Recovery publication immutable support bank changed')
        graph = graph_owner.snapshot()
        if H.graph_digest(graph) != marker[side + '_graph_sha256']:
            raise ValueError('Recovery publication graph differs from its exact reviewed side')
        for doc, row in rows.items():
            if H.dependencies(engine, row, graph, actual_assets, marker['state_fields']) != dependencies[doc][side]:
                raise ValueError('Recovery publication changed a member source, repair, own recipe or support input')

    try:
        verify_side(expected_side, old_assets)
        if verify_before is not None: verify_before()
        verify_side(expected_side, old_assets)
        # Suppress the dispatcher's independent document-only undo step before
        # any fence or graph mutation, including later compensated/unknown paths.
        started = True; engine._people_shared_mutation = True
        for doc, row in rows.items():
            owner.versions.advance(row); revisions[doc] += 1
        _set_bank(engine, project, candidate_assets); bank_written = True
        graph_owner.commit(plan['candidate'], expected_fence=expected_fence)
        expected_fence = graph_owner.fence; graph_written = True
        engine._people_analysis_key = None
        require_identity()
        if live is not None and V.scope(live) == 'project':
            engine._people_sync(strict=True); frame = engine._write_current_frame('people')
        verify_side(result_side, candidate_assets)
        # No member recipe is assigned or replayed. Remember only the current
        # document's already-verified own editing view under its real owner.
        owner.documents.remember_current(); verify_side(result_side, candidate_assets)
        V.remember(engine); engine._project_dirty = True
        if frame is not None: frame['doc_state'] = engine.doc_state()
        verify_side(result_side, candidate_assets)
        return frame
    except Exception as error:
        rolled_back = False
        if started:
            try:
                require_identity()
                verify_side(result_side if graph_written else expected_side, candidate_assets if bank_written else old_assets)
                if graph_written:
                    previous = deepcopy(plan['before']); previous['association_revision'] = graph_owner.association_fence
                    graph_owner.commit(previous, expected_fence=expected_fence); expected_fence = graph_owner.fence
                if bank_written: _set_bank(engine, project, old_assets)
                engine._people_analysis_key = None
                if live is not None and V.scope(live) == 'project': engine._people_sync(strict=True)
                verify_side(expected_side, old_assets); owner.documents.remember_current(); V.remember(engine)
                verify_side(expected_side, old_assets); rolled_back = True
            except Exception:
                # An uncertain owner must retain all candidate bytes needed to
                # resolve any pointer that may have reached canonical state.
                owner.editor.invalidate()
        error.side_effects_started = started
        error.rolled_back = rolled_back
        error.requires_reload = started and not rolled_back
        raise
    finally:
        engine._people_staged = None


def commit(engine, *, review, plans, targets, before_assets, after_assets, request_id, verify_before=None):
    if verify_before is not None: verify_before()
    # No-op never installs an inert vector, advances a member fence or creates
    # a ledger identity. The review/controller still owns its original receipt.
    if set(plans) == {'project'} and H.graph_digest(plans['project']['before']) == H.graph_digest(plans['project']['candidate']):
        if bank(engine) != before_assets: raise ValueError('No-op recovery bank changed')
        if verify_before is not None: verify_before()
        return None, None
    try:
        if bank(engine) != before_assets: raise ValueError('Recovery review original immutable bank changed')
        marker = H.prepare(engine, review, plans, targets, before_assets=before_assets, after_assets=after_assets)
        return L.commit_scoped(engine._batch_controller(), engine, plans, request_id=request_id,
            prepare=True, prepared_targets=targets, eye_bag_recovery_alias_history=marker,
            recovery_alias_assets=after_assets, recovery_alias_verify=verify_before)
    except Exception as error:
        if not hasattr(error, 'side_effects_started'): error.side_effects_started = False
        if not hasattr(error, 'rolled_back'): error.rolled_back = False
        if not hasattr(error, 'requires_reload'): error.requires_reload = bool(error.side_effects_started)
        bid = getattr(error, 'batch_id', None)
        if bid is not None:
            # A known ledger ID alone is never success or membership evidence.
            # Only the exact complete published graph/bank/own-input state may
            # supply diagnostic member transitions, while outcome stays unknown.
            try:
                owner = engine._batch_controller(); saved = owner.ledger[bid]; marker = H.check(saved)
                if (marker is None or marker['review_sha256'] != review['review_sha256']
                        or saved.get('request_id') != request_id or saved['targets'] != targets):
                    raise ValueError('Recovery late receipt differs from the original reviewed transaction')
                graph = V.row_snapshot(engine, plans['project']['row'])
                actual = H.targets(engine, marker, graph, advance=False)
                inverse = {'project': {**plans['project'], 'before': graph, 'candidate': plans['project']['before']}}
                H.verify_restore(engine, saved, inverse, actual, redo=False, assets=bank(engine), advance=False)
                members = []
                for member in review['members']:
                    visual = member['visual']; row = owner.versions.find(engine._docs, visual['document_id'])[1]
                    expected = int(visual['revision']) + 1
                    if owner.versions.version(row).revision != expected:
                        raise ValueError('Recovery late receipt member revision changed')
                    members.append({'document_id': visual['document_id'], 'expected_revision': visual['revision'],
                                    'result_revision': str(expected)})
                error.eye_bag_recovery_alias_review = H.status_summary(saved)
                error.alias_members = members
            except Exception:
                pass
        raise


def failure_context(owner, request):
    if request.get('action') not in ('undo', 'redo'): return {}
    bid = request.get('batch_id'); entry = owner.ledger.get(str(bid or ''), {})
    try: marker = H.status_summary(entry)
    except (ValueError, TypeError, KeyError): return {}
    return {} if marker is None else {'batch_id': bid, 'module_scope': [L.OP], H.KEY: marker}


def require_history_request(owner, request, batch):
    if (type(request) is not dict or set(request) != {'cmd', 'action', 'request_id', 'batch_id'}
            or request['cmd'] != 'batch' or request['action'] not in ('undo', 'redo')):
        raise ValueError('Recovery alias history needs an exact correlated batch undo/redo command')
    for key in ('request_id', 'batch_id'):
        value = request[key]
        if (type(value) is not str or not value.strip() or len(value.encode('utf-8')) > 128
                or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
            raise ValueError('Recovery alias history needs bounded native request and batch identities')
    if owner.ledger.get(request['batch_id']) is not batch:
        raise ValueError('Recovery alias history requires its exact existing ledger identity')
