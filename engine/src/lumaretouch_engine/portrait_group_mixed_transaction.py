# SPDX-License-Identifier: GPL-3.0-or-later
"""One graph/global-state publication boundary of people_batch_ledger. UNRUN.

All desired states, graph patches and dependency fences are staged before writes.
The same compensation boundary owns every graph and recipe, including history
replay. No separate BatchSync mutation or second undo stack is involved.
"""
from copy import deepcopy
from . import portrait_group_mixed_history as H, people_batch_ledger as L
from . import virtual_copy_people as V, creative_derived_source as SOURCE
from .people_preset_plan import clone_state
from .eye_bag_alias_history import graph_digest


def prepare(engine, plans, targets, entry, *, redo):
    from .full_candidate_render import render
    marker = H.verify(engine, entry, plans, targets, redo=redo)
    side = 'after' if redo else 'before'
    for target in targets.values():
        row = engine._document_versions().find(engine._docs, target['document_id'])[1]
        candidate = H.desired(H.state(engine, row), marker['members'][target['document_id']][side])
        render(engine, row, candidate, target['document_id'], str(target['revision']),
               people_graph=plans[target['people_scope']]['candidate'])
    H.verify(engine, entry, plans, targets, redo=redo)


def publish(owner, engine, plans, targets, entry, *, redo, verify_before=None):
    from .people_cross_owner_ledger import validate_plans
    from .eye_bag_preset_alias_transaction import _replay
    marker = H.verify(engine, entry, plans, targets, redo=redo)
    validate_plans(plans, targets); L._verify(owner, engine, plans, targets)
    old_side, new_side = ('before', 'after') if redo else ('after', 'before')
    rows = {t['document_id']: owner.versions.find(engine._docs, t['document_id'])[1] for t in targets.values()}
    graphs = {key: V.row_owner(engine, plan['row']) for key, plan in plans.items()}
    fences = {key: graph.fence for key, graph in graphs.items()}
    revisions = {doc: owner.versions.version(row).revision for doc, row in rows.items()}
    originals = {doc: clone_state(H.state(engine, row)) for doc, row in rows.items()}
    desired = {doc: H.desired(originals[doc], marker['members'][doc][new_side]) for doc in rows}
    live, load = V.current_row(engine), getattr(engine, '_load_id', None)
    workspace = owner.versions.workspace
    from .people_graph_owner import affected_assets
    affected = {key: affected_assets(plan['before'], plan['candidate']) for key, plan in plans.items()}
    written_graphs = []; written_states = []; started = False; frame = None

    def identity():
        if (owner is not engine._batch_controller() or owner.versions.workspace != workspace
                or V.current_row(engine) is not live or getattr(engine, '_load_id', None) != load):
            raise ValueError('Mixed group publication workspace or current owner changed')
        for key, graph in graphs.items():
            if V.row_owner(engine, plans[key]['row']) is not graph or graph.fence != fences[key]:
                raise ValueError('Mixed group graph changed during publication')
        closure = [row['document_id'] for row in engine._docs if V.scope(row) in affected
            and SOURCE.row_proof(row)['asset_sha256'] in affected[V.scope(row)]]
        if len(closure) != len(rows) or set(closure) != set(rows):
            raise ValueError('Mixed group acquired an unreviewed source alias')
        for target in targets.values():
            doc = target['document_id']; found = owner.versions.find(engine._docs, doc)
            if (found is None or found[1] is not rows[doc] or found[1].get('trashed')
                    or found[1].get('_people_new_import') or found[1]['path'] != target['path']
                    or V.scope(found[1]) != target['people_scope']
                    or owner.versions.version(found[1]).revision != revisions[doc]):
                raise ValueError('Mixed group exact target or revision changed')
            SOURCE.verify_row({**found[1], 'state': H.state(engine, found[1])}, target['source_proof'])
            L.verify_reviewed_refs(engine, found[1], target)

    def content(side, *, partial=False):
        identity()
        for key, graph in graphs.items():
            graph_side = 'candidate' if (key in written_graphs if partial else side == new_side) else 'before'
            if graph_digest(graph.snapshot()) != graph_digest(plans[key][graph_side]):
                raise ValueError('Mixed group graph differs from its staged content')
        for doc, row in rows.items():
            graph = graphs[V.scope(row)].snapshot()
            wanted = new_side if (doc in written_states if partial else side == new_side) else old_side
            if H.BASE.dependencies(engine, row, H.state(engine, row), graph, marker['fields']) != marker['members'][doc]['dependencies'][wanted]:
                raise ValueError('Mixed group recipe or support differs from the reviewed content')

    try:
        content(old_side)
        if verify_before is not None:
            verify_before()
        content(old_side)
        # Explicit claim precedes every potential mutation. Fences remain
        # monotonic on compensation; never roll revisions back to stale tokens.
        started = True; engine._people_shared_mutation = True
        for doc, row in rows.items():
            owner.versions.advance(row); revisions[doc] += 1
        for key, graph in graphs.items():
            graph.commit(plans[key]['candidate'], expected_fence=fences[key])
            fences[key] = graph.fence; written_graphs.append(key)
        engine._people_analysis_key = None
        for doc, row in rows.items():
            identity()
            written_states.append(doc)  # Replay can fail after a partial write.
            if row is live:
                frame = _replay(engine, desired[doc], mode='preset', request_id='portrait_group:' + str(entry.get('request_id', 'history')))
            else:
                row['state'] = clone_state(desired[doc])
        if live is not None and live['document_id'] not in rows and V.scope(live) in plans:
            engine._people_sync(strict=True); frame = engine._write_current_frame('people')
        content(new_side)
        owner.documents.remember_current(); content(new_side)
        V.remember(engine); engine._project_dirty = True
        content(new_side)
        if frame is not None:
            frame['doc_state'] = engine.doc_state()
        return frame
    except Exception as error:
        rolled_back = False
        if started:
            try:
                # Only recognized staged partial content may be compensated.
                # Any foreign mutation or partial replay failure stays unknown.
                content(old_side, partial=True)
                for key in reversed(written_graphs):
                    prior = deepcopy(plans[key]['before'])
                    prior['association_revision'] = graphs[key].association_fence
                    graphs[key].commit(prior, expected_fence=fences[key]); fences[key] = graphs[key].fence
                written_graphs.clear(); engine._people_analysis_key = None
                for doc in reversed(written_states):
                    row = rows[doc]
                    if row is live:
                        _replay(engine, originals[doc], mode='preset_rollback', request_id='portrait_group_rollback')
                    else:
                        row['state'] = clone_state(originals[doc])
                written_states.clear()
                if live is not None and live['document_id'] not in rows and V.scope(live) in plans:
                    engine._people_sync(strict=True)
                content(old_side); owner.documents.remember_current(); V.remember(engine)
                content(old_side); rolled_back = True
            except Exception:
                owner.editor.invalidate()
        error.side_effects_started = started; error.rolled_back = rolled_back
        error.requires_reload = started and not rolled_back
        raise
    finally:
        engine._people_staged = None
