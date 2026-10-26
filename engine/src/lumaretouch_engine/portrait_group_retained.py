# SPDX-License-Identifier: GPL-3.0-or-later
"""Target-local retained skin presets, never source-person/mask transfer.

Bounded families: genuine skin_finish and skin_texture per-face intent. Legacy smoothing
is deliberately NOT converted. Canonical graph/ledger/render owners retain all
publication and image work. Source integration only; acceptance is UNRUN.
"""
from copy import deepcopy
from . import people_state as S, people_algorithms as A, virtual_copy_people as V
from . import skin_finish_scope as FINISH, skin_texture_scope as TEXTURE
from . import workflow_preset_review as review, workflow_preset_catalogue as catalogue
from . import creative_derived_source as SOURCE
from .optics_candidate_identity import fingerprint

MODE = 'retained_people'
FAMILIES = {family.OP: family for family in (FINISH, TEXTURE)}
OPERATIONS = frozenset(FAMILIES)
GLOBAL_OPERATIONS = frozenset(('lnx.exposure.v1', 'lnx.white_balance.v1'))


def retained(preset):
    return bool(set(preset['modules']) & OPERATIONS)


def support(preset):
    from . import portrait_group_reference as reference
    if reference.selected(preset):
        return reference.support(preset)
    if not retained(preset):
        reason = review.support_reason(preset)
        return {'supported': reason is None, 'reason': reason, 'mode': 'legacy_scalar'}
    try:
        if 'xmp_import' in preset or set(preset['modules']) - (OPERATIONS | GLOBAL_OPERATIONS):
            raise ValueError('retained_skin_requires_supported_per_face_and_global_modules')
        from .scope import check_params
        for op, params in preset['modules'].items():
            if op in GLOBAL_OPERATIONS:
                check_params(op, params)
        recipes = {op: FAMILIES[op].check_params(params)['recipe']
                   for op, params in preset['modules'].items() if op in OPERATIONS}
        if not any(FAMILIES[op].S.active(recipe) for op, recipe in recipes.items()):
            raise ValueError('retained_skin_requires_nonzero_intent')
    except (ValueError, TypeError, KeyError) as error:
        return {'supported': False, 'reason': str(error), 'mode': MODE}
    return {'supported': True, 'reason': None, 'mode': MODE}


def resolve(identity, digest):
    review._token(identity); review._hash(digest)
    preset = catalogue.resolve(identity, digest)
    admission = support(preset)
    if not admission['supported']:
        raise ValueError(str(admission['reason']) + ': complete group preset rejected; no module omitted')
    return preset


def plans(group, docs, preset):
    """Stage exact per-face leaves in each existing context, without activation."""
    from .portrait_group_people import admit
    recipes = {op: FAMILIES[op].check_params(params)['recipe']
               for op, params in preset['modules'].items() if op in OPERATIONS}
    result = {}; assets = set()
    for doc in docs:
        _, row = group._row(doc)
        context, refs = admit(group.engine, row, row['state'])
        asset = refs[0]['asset_sha256']
        if asset in assets:
            raise ValueError('Multi-person group requires distinct physical target sources')
        assets.add(asset)
        identity = V.scope(row)
        graph = context['people_graph']
        plan = result.setdefault(identity, {'row': row, 'before': graph,
            'candidate': deepcopy(graph), 'reviewed_face_refs': []})
        if plan['before'] != graph:
            raise ValueError('Shared portrait context differs across selected targets')
        for ref in refs:
            for operation, recipe in recipes.items():
                for path, value in A.leaves(recipe).items():
                    plan['candidate'] = S.set_override(plan['candidate'], 'face',
                        ref['face_instance_id'], operation, path, value)
            plan['reviewed_face_refs'].append(ref)
    # Canonical affected-assets membership must not acquire another original,
    # virtual copy, or the editor merely because it shares source bytes.
    from .people_graph_owner import affected_assets
    selected = set(docs)
    affected = {identity: affected_assets(plan['before'], plan['candidate'])
                for identity, plan in result.items()}
    actual = {row['document_id'] for row in group.engine._docs
        if V.scope(row) in affected and SOURCE.row_proof(row)['asset_sha256'] in affected[V.scope(row)]}
    if actual != selected:
        raise ValueError('Canonical graph transaction would affect an unselected document')
    return result


def inputs(group, document, preset, staged):
    from .portrait_group_people import admit
    index, row = group._row(document)
    context, refs = admit(group.engine, row, row['state'])
    version = group.batch.versions.version(row)
    target = {'document_id': document, 'revision': str(version.revision)}
    graph = staged[V.scope(row)]['candidate']
    left, before_graph = review._proof(group.engine, row, row['state'], target)
    from .portrait_group_mixed_history import OPS
    global_modules = {op: params for op, params in preset['modules'].items() if op in OPS}
    after = review._candidate(row['state'], {'modules': global_modules}) if global_modules else row['state']
    from .white_balance_recipe import prepare_state
    if global_modules:
        prepare_state(after)
    right, _ = review._proof(group.engine, row, after, target, people_graph=graph)
    if (left['render']['source_proof'] != right['render']['source_proof']
            or left['repair_sha256'] != right['repair_sha256']):
        raise ValueError('Retained candidate changed source or repairs')
    owned = {'index': index, 'row': row, 'target': target, 'before': left, 'after': right,
        'context': fingerprint(context), 'history': fingerprint((row['undo'], row['redo'])),
        'face_refs': refs, 'before_graph': before_graph, 'candidate_graph': graph}
    return owned, row['state'], after, graph


def commit(group, record, request_id):
    from . import people_batch_ledger as ledger
    preset = resolve(record['preset_id'], record['preset_sha256'])
    staged = plans(group, [item['target']['document_id'] for item in record['inputs']], preset)
    group._verify(record)
    targets = ledger._targets(group.batch, group.engine, staged)
    expected = {item['target']['document_id'] for item in record['inputs']}
    if {target['document_id'] for target in targets.values()} != expected or len(targets) != len(expected):
        raise ValueError('Canonical retained history membership differs from group approval')
    from . import portrait_group_mixed_history as mixed
    global_modules = {op: params for op, params in preset['modules'].items() if op in GLOBAL_OPERATIONS}
    extra = {}
    if global_modules:
        candidates = {doc: inputs(group, doc, preset, staged)[2] for doc in expected}
        marker = mixed.capture(group.engine, staged, targets, global_modules, candidates)
        extra = {'portrait_group_global_history': marker, 'portrait_group_global_verify': lambda: group._verify(record)}
    result = ledger.commit_scoped(group.batch, group.engine, staged,
        request_id=request_id, prepare=False, prepared_targets=targets, **extra)
    if result is None:
        raise ValueError('Retained group unexpectedly contains no effective graph changes')
    batch_id, frame = result
    if frame is not None:
        group.batch.emit(frame)
    return {'kind': 'commit', 'batch_id': batch_id, 'targets': [int(index) for index in targets],
        'skipped': [], 'rejected_docs': []}
