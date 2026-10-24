"""Reviewed persistent scalar inheritance through the existing frozen batch ledger.

Every endpoint owns its source, analysis and support. This coordinator never
copies masks, invents FaceRefs, or publishes only part of an association.
"""
from copy import deepcopy

from . import people_state as S, people_algorithms as A
from . import people_cross_owner as C, people_transfer_inventory as I
from . import virtual_copy_people as V, creative_derived_source as SOURCE
from .batch_preflight import FrozenTarget, canonical
from .people_resolver import resolve
from . import collarbone_cohort_review as CLAVICLE
from . import portrait_cohort_review as PORTRAIT

MARKER = '_people_transfer'
POLICY = 'persistent_association'


def options(value, modules):
    fields = {'target_policy', 'operation', 'association_id', 'source_ref', 'selection', 'source', 'targets'}
    if type(value) is dict and 'face_style' in value:fields.add('face_style')
    if type(value) is not dict or set(value) != fields or value['target_policy'] != POLICY:
        raise ValueError('Persistent association requires an explicit reviewed request')
    if value['operation'] not in ('create', 'patch', 'unlink'):
        raise ValueError('Only create, scalar patch and complete unlink are supported')
    if 'face_style' in value:
        from .face_style_batch_review import recipe,check_selection,selection as named_selection
        if value['operation'] not in ('create','patch'):raise ValueError('Unlink accepts no named recipe application')
        recipe(value['face_style']);check_selection(value['face_style'],value.get('selection'))
        if modules!=list(named_selection(value['face_style'])):raise ValueError('Named cohort needs its exact lexical ten-operation scope')
    S.token(value['association_id']); S.check_ref(value['source_ref'])
    source = I.check_proof(value['source'])
    targets = value['targets']
    if type(targets) is not list or not 1 <= len(targets) <= 15:
        raise ValueError('Persistent association requires two to sixteen independent documents')
    seen = {source['document']['document_id']}
    for item in targets:
        if type(item) is not dict or set(item) != {'target', 'target_refs'}:
            raise ValueError('Each association member requires owner proof and one exact FaceRef')
        proof = I.check_proof(item['target']); refs = item['target_refs']
        if type(refs) is not list or len(refs) != 1:
            raise ValueError('This reviewed association supports one selected face per document')
        S.check_ref(refs[0])
        document = proof['document']
        if document['document_id'] in seen or document['epoch'] != source['document']['epoch']:
            raise ValueError('Association documents must be distinct in one workspace')
        seen.add(document['document_id'])
    selection = value['selection']; defaults = A.defaults()
    if type(selection) is not dict or type(modules) is not list or len(modules) != len(set(modules)) or set(modules) != set(selection):
        raise ValueError('Association modules must exactly name selected scalar leaves')
    if value['operation'] == 'unlink':
        if selection: raise ValueError('Complete unlink accepts no new parameter selection')
    elif not selection:
        raise ValueError('Select scalar parameters explicitly; face edits are not implicitly shared')
    for op, paths in selection.items():
        if op not in defaults or type(paths) is not list or not paths or len(paths) != len(set(paths)):
            raise ValueError('Select unique supported scalar parameter leaves')
        if any(path not in defaults[op] for path in paths):
            raise ValueError('Association may inherit only supported scalar leaves')
    return deepcopy(value)


def _capsule(graph, association_id):
    matches = [(key, person['cross_owner']) for key, person in graph['persons'].items()
               if person.get('cross_owner', {}).get('association_id') == association_id]
    if len(matches) > 1: raise ValueError('Duplicate association projection in one owner')
    return matches[0] if matches else (None, None)


def _endpoint(engine, rows, proof, ref, *, reviewed_only=False):
    proof = I.check_proof(proof); ref = S.check_ref(ref)
    found = engine._document_versions().find(rows, proof['document']['document_id'])
    if found is None: raise ValueError('Association member is unavailable; restore and review every member')
    index, row = found
    if row.get('trashed'): raise ValueError('Association member is in project trash')
    if reviewed_only and (row.get('_people_new_import') or V.peek_graph(engine,row) is None):
        raise ValueError('Named cohort requires an already reviewed member owner; open and inspect each member first')
    graph = V.row_snapshot(engine, row)
    I.verify(engine, row, graph, proof); SOURCE.verify_row(row, proof['source_proof'])
    scope = V.scope(row)
    if sum(V.scope(other) == scope for other in rows) != 1:
        raise ValueError('Persistent association currently requires one retained document per independent portrait owner')
    asset = proof['source_proof']['asset_sha256']
    assets = {face['asset_sha256'] for face in graph['faces'].values()} | set(graph['analysis_runs'])
    assets |= {leaf['target_id'] for leaf in graph['overrides'] if leaf['scope'] == 'all_people'}
    if scope == V.PROJECT and assets != {asset}:
        raise ValueError('Shared project portrait owner has dormant sources; use an independent copy owner')
    face = graph['faces'].get(ref['face_instance_id'])
    if (face is None or S.face_ref(face) != ref or ref['asset_sha256'] != asset
            or not face['enabled'] or face['evidence']['status'] != 'verified'):
        raise ValueError('Every association face requires current independently verified source analysis')
    return {'index': index, 'row': row, 'before': graph, 'proof': proof, 'ref': ref,
            'member': {'document_id': proof['document']['document_id'], 'scope_id': scope,
                       'original_sha256': proof['source_proof']['original_sha256'], 'ref': ref}}


def _selected(graph, ref, selection):
    values = resolve(graph, ref['face_instance_id'], A.defaults()); result = []
    for op, paths in sorted(selection.items()):
        for path in sorted(paths):
            if any(item['operation_id'] == op and item['parameter_path'] == path for item in values['conflicts']):
                raise ValueError('Resolve source group precedence before sharing intent')
            leaf = values['operations'].get(op, {}).get(path)
            if leaf is None: raise ValueError('Selected source scalar is unavailable')
            result.append({'op': op, 'path': path, 'value': deepcopy(leaf['value'])})
    return result


def prepare(engine, selected, *, validate=True):
    """Rebuild the entire atomic cohort from exact current reviewed endpoints."""
    rows = engine._batch_controller().documents.rows()
    named='face_style' in selected
    endpoints = [_endpoint(engine, rows, selected['source'], selected['source_ref'],reviewed_only=named)]
    endpoints.extend(_endpoint(engine, rows, item['target'], item['target_refs'][0],reviewed_only=named) for item in selected['targets'])
    members = sorted((item['member'] for item in endpoints), key=lambda item: item['document_id'])
    if len({item['scope_id'] for item in members}) != len(members):
        raise ValueError('Persistent association requires independently owned portrait graphs')
    operation = selected['operation']; association_id = selected['association_id']; prior = None
    selected_documents = {member['document_id'] for member in members}
    for row in rows:
        if engine._document_versions().version(row).document_id in selected_documents: continue
        other = V.peek_graph(engine, row)
        if other is not None and _capsule(other, association_id)[1] is not None:
            raise ValueError('An unreviewed retained owner also contains this association identifier')
    for item in endpoints:
        person_id, capsule = _capsule(item['before'], association_id)
        if operation == 'create':
            if capsule is not None or association_id in item['before']['persons']:
                raise ValueError('Association identifier already exists; review its current membership')
            person_id = association_id
        else:
            if capsule is None or capsule['members'] != members or capsule['local_document_id'] != item['member']['document_id']:
                raise ValueError('Every exact saved association member must be current and reviewed')
            if prior is not None and (capsule['generation'] != prior['generation'] or capsule['intent'] != prior['intent']):
                raise ValueError('Association projections disagree; no member was changed')
            prior = capsule
        item['person_id'] = person_id
    intent = [] if prior is None else deepcopy(prior['intent'])
    if operation != 'unlink':
        merged = {(leaf['op'], leaf['path']): leaf for leaf in intent}
        if named:
            from .face_style_batch_review import parameters
            leaves=[{'op':leaf['operation_id'],'path':leaf['parameter_path'],'value':leaf['value']} for leaf in parameters(selected['face_style'])]
        else:leaves=_selected(endpoints[0]['before'],selected['source_ref'],selected['selection'])
        merged.update({(leaf['op'],leaf['path']):leaf for leaf in leaves})
        intent = [merged[key] for key in sorted(merged)]
    if operation == 'patch' and canonical(intent) == canonical(prior['intent']):
        raise ValueError('Selected named recipe does not change shared person intent' if named else 'Selected source values do not change shared person intent')
    for item in endpoints:
        capsule = C.descriptor(association_id, item['member']['document_id'], members, intent)
        if operation == 'create': candidate = C.create(item['before'], item['person_id'], capsule)
        elif operation == 'patch': candidate = C.update(item['before'], item['person_id'], capsule)
        else: candidate = C.unlink(item['before'], item['person_id'])
        # Metadata/general cohort review is not the dedicated ridge-support
        # image proof. Recheck every endpoint on both preflight and replay;
        # unlink can reveal inherited active intent just as create/patch can.
        from .eye_bag_preserve_project import require_unreviewed_transition
        require_unreviewed_transition(item['before'], candidate)
        if named:
            from .face_style_recipes import validate_compatibility
            validate_compatibility(A.recipes(resolve(candidate,item['ref']['face_instance_id'],A.defaults())))
        item['candidate'] = candidate
        item['candidate_sha256'] = I.graph_digest(candidate)
        if validate:
            from .people_candidate_render import validate as render
            render(engine, item['row'], candidate)
    # Full-resolution rendering may be expensive. It cannot bless newer owners.
    for item in endpoints:
        I.verify(engine, item['row'], V.row_snapshot(engine, item['row']), item['proof'])
        SOURCE.verify_row(item['row'], item['proof']['source_proof'])
    review = {'version': 1, 'operation': operation, 'association_id': association_id,
              'generation': capsule['generation'], 'members': members, 'intent': intent}
    return endpoints, review


def _public(item, *, live=False):
    document = item['proof']['document']
    return {'index': item['index'], 'path': item['row']['path'], 'live': live,
            'document_id': document['document_id'], 'revision': str(document['revision']),
            'blocked': None, 'before': {}, 'association': {'owner': item['proof'], 'ref': item['ref'],
            'candidate_sha256': item['candidate_sha256'], 'person_id': item['person_id'], **CLAVICLE.evidence(item), **PORTRAIT.evidence(item)}}


def preflight(engine, controller, p):
    if set(p) - {'cmd', 'action', 'request_id', 'docs', 'module_scope', 'conflict_policy', 'people_transfer'}:
        raise ValueError('Persistent association cannot be mixed with other batch options')
    if p.get('conflict_policy', 'recheck') != 'recheck':
        raise ValueError('Persistent association is atomic and requires recheck policy')
    selected = options(p.get('people_transfer'), p.get('module_scope'))
    docs = p.get('docs')
    if type(docs) is not list or len(docs) != len(set(docs)) or set(docs) != {item['target']['document']['document_id'] for item in selected['targets']}:
        raise ValueError('Requested documents must exactly match reviewed association targets')
    if 'face_style' in selected:
        from .people_preset_plan import require_active_owner
        require_active_owner(engine)
        if V.current_row(engine).get('_people_new_import'):raise ValueError('Open and review the named cohort source owner first')
    else:engine._people_bind()
    batch = engine._batch_controller(); batch.documents.remember_current()
    current = V.current_row(engine)
    if current is None or batch.versions.version(current).document_id != selected['source']['document']['document_id']:
        raise ValueError('Association source must be the current reviewed document')
    endpoints, review = prepare(engine, selected)
    visual_required = CLAVICLE.required(endpoints, selected, review)
    displays = CLAVICLE.prepare(engine, endpoints) if visual_required else None
    portrait_required=PORTRAIT.required(endpoints,selected,review)
    portrait_displays=PORTRAIT.prepare(engine,endpoints,selected,review,existing_displays=displays) if portrait_required else None
    for item in endpoints:
        I.verify(engine, item['row'], V.row_snapshot(engine, item['row']), item['proof'])
        SOURCE.verify_row(item['row'], item['proof']['source_proof'])
    source = endpoints[0]; document = source['proof']['document']
    frozen = [FrozenTarget(item['proof']['document']['document_id'], item['proof']['document']['revision'],
              item['index'], item['row']['path'], None, canonical(item['proof']),
              people_json=canonical({'ref': item['ref'], 'person_id': item['person_id'],
                                     'candidate_sha256': item['candidate_sha256'], **CLAVICLE.evidence(item), **PORTRAIT.evidence(item,private=True)})) for item in endpoints]
    params = {MARKER: {'mode': POLICY, 'options': selected, 'review': review,
                       'collarbone_visual_required': visual_required,'portrait_cohort_required':portrait_required}}
    plan = controller.store.create(batch.versions.workspace, document['document_id'], document['revision'],
        source['row']['path'], p['module_scope'], params, 'recheck', frozen, [])
    body = {'event': 'batch_preflight', 'success': True, 'module_scope': list(plan.modules), 'source': 'current',
            'source_snapshot': controller._source(plan), 'applies': selected, 'policy': 'recheck',
            'targets': [_public(item) for item in endpoints[1:]], 'association_source': _public(source, live=True),
            'persistent_association': review, 'people_transfer': True, 'rejected_docs': [],
            'ok': len(endpoints) - 1, 'blocked': 0, 'preflight_token': plan.token,
            'workspace_generation': plan.workspace, 'expires_ns': str(plan.expires_ns)}
    if visual_required:body['collarbone_cohort']=True
    if portrait_required:body['portrait_cohort']=True
    if visual_required or portrait_required:
        try:
            canonical(body,7*1024*1024)
            if visual_required:
                from .collarbone_visual_store import attach
                attach(controller.store,plan,displays)
            if portrait_required:
                from .portrait_cohort_store import attach
                attach(controller.store,plan,portrait_displays)
        except Exception:
            controller.store.pending.pop(plan.token,None)
            from .collarbone_visual_store import prune
            prune(controller.store)
            from .portrait_cohort_store import prune
            prune(controller.store)
            raise
    controller.emit(body); controller.emit_result(p, body)


def commit(engine, controller, p, plan):
    if set(p) - {'cmd','action','request_id','preflight_token','collarbone_review_ack','portrait_cohort_ack','module_scope'}:
        raise ValueError('Association commit accepts only its immutable reviewed token')
    import json
    params = plan.params()[MARKER]; selected = options(params['options'], list(plan.modules))
    visual_required = params.get('collarbone_visual_required') is True
    portrait_required=params.get('portrait_cohort_required') is True
    portrait_ack=None
    if portrait_required:
        if p.get('module_scope')!=list(plan.modules):raise ValueError('Cohort confirmation must retain exact frozen operation scope')
        portrait_ack=PORTRAIT.acknowledgments(p.get('portrait_cohort_ack'),[json.loads(t.people_json)['portrait_visual'] for t in plan.targets])
    elif 'portrait_cohort_ack' in p or 'module_scope' in p:raise ValueError('Portrait-cohort confirmation cannot authorize another operation')
    visual_ack = None
    if visual_required:
        visual_ack = CLAVICLE.R.acknowledgments(p.get('collarbone_review_ack'),
            [json.loads(target.people_json).get('collarbone_visual') for target in plan.targets])
    elif 'collarbone_review_ack' in p:
        raise ValueError('Collarbone acknowledgment cannot authorize a cohort without its own frozen image review')
    batch = engine._batch_controller(); batch.documents.remember_current()
    endpoints, review = prepare(engine, selected, validate=False)
    if (review != params['review'] or len(endpoints) != len(plan.targets)
            or CLAVICLE.required(endpoints, selected, review) != visual_required
            or PORTRAIT.required(endpoints,selected,review)!=portrait_required):
        raise ValueError('Reviewed association content changed')
    plans = {}
    for item, frozen in zip(endpoints, plan.targets):
        frozen_payload = json.loads(frozen.people_json)
        expected_payload = {'ref': item['ref'], 'person_id': item['person_id'], 'candidate_sha256': item['candidate_sha256']}
        if visual_required:
            expected_payload.update(CLAVICLE.evidence(frozen_payload))
            CLAVICLE.verify(engine, item, frozen_payload)
        if portrait_required:
            expected_payload.update(PORTRAIT.evidence(frozen_payload,private=True))
            PORTRAIT.verify(engine,item,frozen_payload,PORTRAIT.digest(selected,review))
        if (item['proof'] != json.loads(frozen.before_json) or item['row']['path'] != frozen.path
                or item['proof']['document']['document_id'] != frozen.document_id
                or expected_payload != frozen_payload):
            raise ValueError('Association endpoint or selected intent changed after review')
        plans[item['member']['scope_id']] = {'row': item['row'], 'before': item['before'],
            'candidate': item['candidate'], 'reviewed_face_refs': [item['ref']]}
    from .people_batch_ledger import _targets, prepare_scoped, _verify, commit_scoped
    targets = _targets(batch, engine, plans)
    if ({target['document_id'] for target in targets.values()}
            != {item['member']['document_id'] for item in endpoints}):
        raise ValueError('Association affected document set differs from its reviewed cohort')
    # The ordinary scoped preparer stages the live preview rather than a full
    # export for the active owner. Persistent consent includes that source
    # member too, so verify its full-resolution candidate at commit as well.
    from .people_candidate_render import validate as render
    current = V.current_row(engine)
    for item in endpoints:
        if item['row'] is current:
            render(engine, item['row'], item['candidate'])
    prepare_scoped(engine, plans, targets); _verify(batch, engine, plans, targets)
    for item in endpoints:
        I.verify(engine, item['row'], V.row_snapshot(engine, item['row']), item['proof'])
        SOURCE.verify_row(item['row'], item['proof']['source_proof'])
    if visual_required:
        for item, frozen in zip(endpoints, plan.targets):
            CLAVICLE.verify(engine, item, json.loads(frozen.people_json))
        from .collarbone_visual_store import verify_available
        verify_available(controller.store, plan)
    if portrait_required:
        for item,frozen in zip(endpoints,plan.targets):PORTRAIT.verify(engine,item,json.loads(frozen.people_json),PORTRAIT.digest(selected,review))
        from .portrait_cohort_store import verify_available
        verify_available(controller.store,plan)
    controller.store.claim(plan,collarbone_review_ack=visual_ack,portrait_cohort_ack=portrait_ack,request_id=p.get('request_id'))
    try:
        result = commit_scoped(batch, engine, plans, request_id=p.get('request_id'), prepare=False, prepared_targets=targets)
        bid, frame = (None, None) if result is None else result
        outcomes = [{'index': item['index'], 'path': item['row']['path'], 'document_id': item['member']['document_id'],
                     'expected_revision': str(item['proof']['document']['revision']),
                     'result_revision': str(batch.versions.version(item['row']).revision), 'outcome': 'applied', 'blocked': None}
                    for item in endpoints]
        body = {'event': 'batch_committed', 'success': True, 'batch_id': bid, 'module_scope': list(plan.modules),
                'applied': [item['index'] for item in endpoints], 'skipped': [], 'target_outcomes': outcomes[1:],
                'source_outcome': outcomes[0], 'source_snapshot': controller._source(plan),
                'persistent_association': review, 'people_transfer': True, 'source_changed_since_preflight': False,
                'source_missing': False, 'preflight_token': plan.token, 'workspace_generation': plan.workspace}
        if visual_required:
            body.update(collarbone_cohort=True, collarbone_review_ack=deepcopy(visual_ack))
        if portrait_required:body.update(portrait_cohort=True,portrait_cohort_ack=deepcopy(portrait_ack),outcome_unknown=False)
        controller.emit(body)
        if frame is not None: controller.emit(frame)
    except Exception as error:
        body = {'success': False, 'outcome_unknown': True, 'error': str(error)[:2000],
                'preflight_token': plan.token, 'workspace_generation': plan.workspace, 'requires_preflight': True}
    if visual_required:
        body.update(collarbone_cohort=True, collarbone_review_ack=deepcopy(visual_ack), module_scope=list(plan.modules))
    if portrait_required:body.update(portrait_cohort=True,portrait_cohort_ack=deepcopy(portrait_ack),module_scope=list(plan.modules))
    controller.emit_result(p, controller.store.finish(plan, body))
