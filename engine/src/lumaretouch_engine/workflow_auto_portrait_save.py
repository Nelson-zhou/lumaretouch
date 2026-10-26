# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded automatic portrait staging through the existing group save codec.

No new graph, history or persistence owner. The caller freezes preparation,
canonical candidate and actual applied context, then retains its normal workflow
CAS/persist/return boundary. Source authored; durability and quality are UNRUN.
"""
from copy import deepcopy
from . import people_state as S, people_algorithms as A, virtual_copy_people as V
from . import workflow_preset_people_save as SAVE
from .people_preset_plan import graph_content
from .people_graph_patch import between
from .workflow_owner_protocol import digest


def candidate(prepared_context, asset, face_refs, modules):
    """Reconstruct only the explicitly opted-in face leaves, never observations."""
    from .portrait_group_retained import FAMILIES, support
    prepared = V.check(prepared_context)
    graph = prepared['people_graph']
    admission = support({'modules': modules})
    if not admission['supported'] or admission['mode'] != 'retained_people':
        raise ValueError('Automatic portrait save requires complete supported per-face intent')
    if type(face_refs) is not list or not 1 <= len(face_refs) <= 8:
        raise ValueError('Automatic portrait save requires bounded frozen target face references')
    refs = [S.check_ref(ref) for ref in face_refs]
    faces = sorted((face for face in graph['faces'].values() if face['asset_sha256'] == asset),
                   key=lambda face: face['face_instance_id'])
    if refs != [S.face_ref(face) for face in faces]:
        raise ValueError('Automatic portrait save must include every verified detected target face')
    ids = {ref['face_instance_id'] for ref in refs}
    run = graph['analysis_runs'].get(asset)
    if (run is None or run['limit_reached'] or any(face['manual'] or not face['enabled']
            or face['evidence']['status'] != 'verified' or face['evidence']['backend'] != 'mediapipe'
            for face in faces)
            or any(link['face_instance_id'] in ids for link in graph['links'])
            or any(ids.intersection(group['face_ids']) for group in graph['groups'].values())
            or any(item['scope'] == 'face' and item['target_id'] in ids
                   or item['scope'] == 'all_people' and item['target_id'] == asset
                   for item in graph['overrides'])
            or any(item['asset_sha256'] == asset and item['status'] == 'unresolved'
                   for item in graph['unresolved_legacy'])):
        raise ValueError('Automatic portrait save cannot authorize edited, associated or ambiguous faces')
    for ref in refs:
        for op, params in modules.items():
            if op not in FAMILIES:
                continue  # support() admitted the complete global + portrait set above.
            recipe = FAMILIES[op].check_params(params)['recipe']
            for path, value in A.leaves(recipe).items():
                graph = S.set_override(graph, 'face', ref['face_instance_id'], op, path, value)
    return graph


def stage(engine, saved, row, baseline, expected_context, *, batch_id,
          prepared_context, candidate_graph, face_refs, modules):
    """Stage one exact target and its existing canonical protected batch history."""
    if (type(baseline) is not SAVE.Baseline or baseline.row is not row
            or baseline.owner is not engine.__dict__.get('_people_graph_owner')
            or baseline.context_owner is not engine.__dict__.get('_people_active_context')
            or baseline.private != V.is_private(row) or baseline.saved_sha256 != digest(saved)
            or SAVE._source(row) != (baseline.asset, baseline.source)
            or engine.__dict__.get('_creative_base') is not None):
        raise ValueError('Automatic portrait save lost its original preparation/source/project owner')
    prepared = V.check(prepared_context)
    current, expected = SAVE.context(engine, row), V.check(expected_context)
    if current != expected:
        raise ValueError('Automatic portrait save differs from its frozen applied context')
    from .portrait_preset_group_save import _retained_context_delta, stage as stage_group
    _retained_context_delta(baseline.before, prepared, baseline.asset)
    planned = candidate(prepared, baseline.asset, face_refs, modules)
    actual = current['people_graph']
    if (S.check(candidate_graph) != planned or graph_content(actual) != graph_content(planned)
            or actual['association_revision'] != planned['association_revision']
            or actual['revision'] < planned['revision']
            or {k: v for k, v in current.items() if k != 'people_graph'} !=
               {k: v for k, v in prepared.items() if k != 'people_graph'}):
        raise ValueError('Automatic portrait save changed observations, support or unapproved face intent')
    batch = engine.__dict__.get('_batch_sync')
    entry = None if batch is None else batch.ledger.get(batch_id)
    scope = V.scope(row)
    if (entry is None or entry.get('people_scoped_changes') != [
            {'scope': scope, 'document_id': row['document_id'],
             'changes': between(prepared['people_graph'], planned)}]):
        raise ValueError('Automatic portrait save history differs from its exact canonical plan')
    from .people_batch_ledger import reviewed_refs
    targets = list(entry.get('targets', {}).values())
    if (len(targets) != 1 or targets[0]['document_id'] != row['document_id']
            or reviewed_refs(targets[0]) != face_refs):
        raise ValueError('Automatic portrait history omitted or changed authorized target faces')
    from . import portrait_group_mixed_history as MIXED
    marker = MIXED.check(entry)
    globals_ = {op: params for op, params in modules.items() if op in MIXED.OPS}
    if (globals_ and (marker is None or marker['modules'] != globals_)
            or not globals_ and marker is not None):
        raise ValueError('Automatic portrait history differs from its complete global recipe intent')
    # Managed import writes its durable neutral row before source classification.
    # Opening a byte-identical independent original may establish a new EMPTY
    # private context. Carry that proven pre-analysis baseline into detached
    # staging only; never migrate/inherit a populated context or alter disk CAS.
    staging_saved = saved
    selected = [doc for doc in saved['docs'] if doc.get('document_id') == row['document_id']]
    if len(selected) != 1:
        raise ValueError('Automatic portrait save lost its exact saved target')
    if baseline.private and V.KEY not in selected[0]:
        empty = {'version': 1, 'people_graph': S.empty(), **{key: {} for key in V.FIELDS}}
        if baseline.before != empty:
            raise ValueError('New private import context must have an exactly empty preparation baseline')
        staging_saved = deepcopy(saved)
        next(doc for doc in staging_saved['docs'] if doc['document_id'] == row['document_id'])[V.KEY] = deepcopy(empty)
    result = stage_group(engine, staging_saved, [row], batch_id=batch_id)
    if SAVE.context(engine, row) != expected:
        raise ValueError('Automatic portrait context changed during detached save staging')
    return result
