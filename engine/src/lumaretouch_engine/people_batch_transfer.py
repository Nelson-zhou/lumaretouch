"""Confirmed-face parameter adapter for the existing frozen batch owner.

Uses FrozenBatchController.store, its receipts and BatchSyncController.ledger.
There is no independent transaction queue, token service or undo stack here.
"""
from copy import deepcopy
import json
from . import people_state as S, people_algorithms as A, people_transfer_adapter as T
from .people_confirmed_transfer import prepare_confirmed
from .batch_preflight import FrozenTarget,canonical
from . import creative_derived_source as SOURCE, virtual_copy_people as V
from . import people_transfer_inventory as I

MARKER='_people_transfer'


def document(engine,row):
    version=engine._document_versions().version(row)
    return {'document_id':version.document_id,'epoch':engine._document_versions().workspace,'revision':version.revision}


def options(value,modules,source_asset):
    if type(value) is not dict:
        raise ValueError('People transfer requires an explicit request object')
    policy=value.get('target_policy')
    fields={'source_ref','selection','target_policy'}|({'source','targets'} if policy=='explicit_face_map' else set())
    if set(value)!=fields:
        raise ValueError('People transfer requires an explicit source, parameter selection and target policy')
    if policy not in ('confirmed_person_only','explicit_face_map'):
        raise ValueError('Only confirmed same-owner people or an explicit reviewed face map may select targets')
    ref=S.check_ref(value['source_ref'])
    if ref['asset_sha256']!=source_asset:raise ValueError('The source face belongs to another photo')
    selection=value['selection'];defaults=A.defaults()
    if type(selection) is not dict or not selection:raise ValueError('Select parameter leaves to transfer')
    if type(modules) is not list or len(modules)!=len(set(modules)) or set(modules)!=set(selection):
        raise ValueError('Module selection must exactly match the reviewed parameter leaves')
    for op,paths in selection.items():
        if op not in defaults or type(paths) is not list or not paths or len(paths)!=len(set(paths)):
            raise ValueError('Invalid people module or leaf selection')
        if any(path not in defaults[op] for path in paths):raise ValueError('Only supported scalar parameter leaves are transferable')
    if policy=='explicit_face_map':
        source=I.check_proof(value['source'])
        if source['source_proof']['asset_sha256']!=source_asset:
            raise ValueError('Explicit source proof belongs to another effective image')
        targets=value['targets']
        if type(targets) is not list or not 1<=len(targets)<=I.MAX_TARGETS:
            raise ValueError('Explicit face map needs one to sixteen reviewed target documents')
        seen=set()
        for item in targets:
            if type(item) is not dict or set(item)!={'target','target_refs'}:
                raise ValueError('Each explicit target needs its exact owner proof and selected FaceRefs')
            target=I.check_proof(item['target']);identity=target['document']['document_id']
            if identity in seen or identity==source['document']['document_id']:
                raise ValueError('Explicit transfer target is duplicated or is its source document')
            if target['document']['epoch']!=source['document']['epoch']:
                raise ValueError('Explicit transfer endpoints belong to different workspaces')
            seen.add(identity);refs=item['target_refs']
            if type(refs) is not list or not 1<=len(refs)<=I.MAX_FACES:
                raise ValueError('Select at least one exact face on each reviewed target')
            ids=set()
            for ref in refs:
                ref=S.check_ref(ref)
                if ref['asset_sha256']!=target['source_proof']['asset_sha256'] or ref['face_instance_id'] in ids:
                    raise ValueError('Explicit target face is duplicated or belongs to another effective source')
                ids.add(ref['face_instance_id'])
    return deepcopy(value)


def preflight(engine,controller,p):
    if set(p)-{'cmd','action','request_id','docs','module_scope','conflict_policy','people_transfer'}:
        raise ValueError('People transfer cannot be mixed with other batch options')
    policy=p.get('conflict_policy','skip_and_report')
    if policy not in ('skip_and_report','recheck'):raise ValueError('Unknown conflict policy')
    engine._people_bind();owner=engine._people_owner();before=owner.snapshot();fence=owner.fence
    batch=engine._batch_controller();batch.documents.remember_current()
    rows=batch.documents.rows();source_row=rows[batch.documents.current_index()]
    source_proof=SOURCE.row_proof(source_row);source_asset=source_proof['asset_sha256'];source_document=document(engine,source_row)
    selected=options(p.get('people_transfer'),p.get('module_scope'),source_asset)
    source_owner=I.proof(engine,source_row,before)
    explicit=selected['target_policy']=='explicit_face_map'
    if explicit:
        I.verify(engine,source_row,before,selected['source'])
        requested=p.get('docs')
        if (type(requested) is not list or len(requested)!=len(set(requested))
                or set(requested)!={item['target']['document']['document_id'] for item in selected['targets']}):
            raise ValueError('Selected target documents must exactly match the reviewed explicit face map')
    indices,rejected=batch.target_indices(p.get('docs'));targets=[];public=[];seen_documents=set()
    if explicit and policy=='recheck' and rejected:
        raise ValueError('An explicit target document is no longer available; review the complete face map again')
    for index in indices:
        row=rows[index];target_document=document(engine,row)
        blocked=None;payload=None;target_proof=None
        try:
            if row.get('trashed'):raise ValueError('Target photo is in the project trash')
            if target_document['document_id']==source_document['document_id']:raise ValueError('The source document is not a transfer target')
            if target_document['document_id'] in seen_documents:raise ValueError('The same document was already selected as a target')
            seen_documents.add(target_document['document_id'])
            target_proof=SOURCE.row_proof(row);asset=target_proof['asset_sha256']
            target_graph=V.row_snapshot(engine,row)
            target_owner=I.proof(engine,row,target_graph)
            if explicit:
                mapping=next(item for item in selected['targets'] if item['target']['document']['document_id']==target_document['document_id'])
                I.verify(engine,row,target_graph,mapping['target'])
                payload=T.prepare(before,target_graph,selected['source_ref'],mapping['target_refs'],selected['selection'],A.defaults(),
                    source_document=source_document,target_document=target_document,source_owner=source_owner,target_owner=target_owner)
                payload['target_policy']='explicit_face_map'
            else:
                payload=prepare_confirmed(before,target_graph,selected['source_ref'],asset,selected['selection'],A.defaults(),
                    source_document=source_document,target_document=target_document,source_owner=source_owner,target_owner=target_owner)
            staged=T.candidate(payload,before,target_graph,source_document=source_document,target_document=target_document,
                               source_owner=source_owner,target_owner=target_owner)
            from .people_candidate_render import validate
            validate(engine,row,staged)
            from .skin_colour_transfer_review import for_target as skin_coverage
            coverage=skin_coverage(engine,row,staged,payload)
            if coverage is not None:payload['skin_colour_coverage']=coverage
            finish_coverage=skin_coverage(engine,row,staged,payload,family='skin_finish')
            if finish_coverage is not None:payload['skin_finish_coverage']=finish_coverage
            body_evenness_coverage=skin_coverage(engine,row,staged,payload,family='body_skin_evenness')
            if body_evenness_coverage is not None:payload['body_skin_evenness_coverage']=body_evenness_coverage
            body_face_match_coverage=skin_coverage(engine,row,staged,payload,family='body_face_match')
            if body_face_match_coverage is not None:payload['body_face_match_coverage']=body_face_match_coverage
            SOURCE.verify_row(row,target_proof)
            if owner.fence!=fence or V.row_snapshot(engine,row)!=target_graph or document(engine,row)!=target_document:
                raise ValueError('Target or graph changed during preparation')
        except Exception as error:blocked=str(error)[:2000];payload=None
        public.append({'index':index,'path':row['path'],'live':False,'document_id':target_document['document_id'],
            'revision':str(target_document['revision']),'blocked':blocked,'before':{},'people_transfer':payload})
        targets.append(FrozenTarget(target_document['document_id'],target_document['revision'],index,row['path'],blocked,
            canonical({'source_proof':target_proof}),people_json=None if payload is None else canonical(payload)))
    SOURCE.verify_row(source_row,source_proof)
    if owner.fence!=fence or document(engine,source_row)!=source_document:
        raise ValueError('Source or associations changed during preparation; review again')
    I.verify(engine,source_row,before,source_owner)
    frozen={MARKER:{'options':selected,'source_asset':source_asset,'source_proof':source_proof,'state_revision':before['revision'],
                    'association_revision':before['association_revision'],'source_owner':source_owner}}
    plan=controller.store.create(batch.versions.workspace,source_document['document_id'],source_document['revision'],
        source_row['path'],p['module_scope'],frozen,policy,targets,rejected)
    body={'event':'batch_preflight','success':True,'module_scope':list(plan.modules),'source':'current',
        'source_snapshot':controller._source(plan),'applies':selected,'policy':policy,'targets':public,
        'rejected_docs':rejected,'ok':sum(not x['blocked'] for x in public),'blocked':sum(bool(x['blocked']) for x in public),
        'preflight_token':plan.token,'workspace_generation':plan.workspace,'expires_ns':str(plan.expires_ns),
        'people_transfer':True}
    controller.emit(body);controller.emit_result(p,body)


def commit(engine,controller,p,plan):
    if set(p)-{'cmd','action','request_id','preflight_token'}:raise ValueError('Commit accepts only the frozen token')
    batch=engine._batch_controller();batch.documents.remember_current()
    params=plan.params()[MARKER];source=batch.versions.find(batch.documents.rows(),plan.source_id)
    if source is None or source[1]['path']!=plan.source_path or batch.versions.version(source[1]).revision!=plan.source_revision:
        raise ValueError('People source changed after review')
    graph=V.row_snapshot(engine,source[1])
    source_proof=SOURCE.verify_row(source[1],params['source_proof'])
    if source_proof['asset_sha256']!=params['source_asset'] or graph['revision']!=params['state_revision'] or graph['association_revision']!=params['association_revision']:
        raise ValueError('Source bytes or people associations changed after review')
    source_document=document(engine,source[1]);resolved=[];plans={};eligible=0
    source_owner=I.verify(engine,source[1],graph,params['source_owner'])
    for target in plan.targets:
        found=batch.versions.find(batch.documents.rows(),target.document_id);blocked=target.blocked;payload=None
        try:
            if blocked:raise ValueError(blocked)
            if found is None:raise ValueError('Target photo was removed')
            index,row=found
            if row.get('trashed') or row['path']!=target.path or batch.versions.version(row).revision!=target.revision:
                raise ValueError('Target photo changed after review')
            target_proof=SOURCE.verify_row(row,json.loads(target.before_json)['source_proof'])
            payload=json.loads(target.people_json)
            target_graph=V.row_snapshot(engine,row)
            target_owner=I.proof(engine,row,target_graph)
            T.verify(payload,graph,target_graph,source_document=source_document,target_document=document(engine,row),
                     source_owner=source_owner,target_owner=target_owner)
            if payload['target_policy']=='confirmed_person_only' and source_owner['people_scope']!=target_owner['people_scope']:
                raise ValueError('Confirmed person IDs do not authorize transfer between independent owners')
            if any(ref['asset_sha256']!=target_proof['asset_sha256'] for ref in payload['target_refs']):
                raise ValueError('Reviewed target faces belong to another effective source')
            identity=V.scope(row)
            scoped=plans.get(identity)
            if scoped is not None and scoped['before']!=target_graph:raise ValueError('Target scope changed during preparation')
            candidate=S.check(target_graph if scoped is None else scoped['candidate'])
            # Every payload verifies its own logical document and owner. Same
            # source bytes are valid across independent copies, never merged
            # just because the digest or inherited face reference matches.
            for ref in payload['target_refs']:
                for leaf in payload['parameters']:
                    candidate=S.set_override(candidate,'face',ref['face_instance_id'],leaf['operation_id'],leaf['parameter_path'],leaf['value'])
            from .body_skin_evenness_state import OP as BODY_SKIN_EVENNESS
            from .body_face_match_state import OP as BODY_FACE_MATCH
            body_families=[family for operation,family in ((BODY_SKIN_EVENNESS,'body_skin_evenness'),
                (BODY_FACE_MATCH,'body_face_match')) if any(leaf['operation_id']==operation for leaf in payload['parameters'])]
            if body_families:
                # Frozen scalar leaves do not authorize another body review.
                # Validate the actual target again, then compare its exact local
                # review receipt before this candidate enters a publishable plan.
                from .people_candidate_render import validate
                from .skin_colour_transfer_review import for_target as skin_coverage
                validate(engine,row,candidate)
                for family in body_families:
                    coverage=skin_coverage(engine,row,candidate,payload,family=family)
                    if coverage!=payload.get(family+'_coverage'):
                        raise ValueError('Body-skin target coverage or own-face reference changed after review')
            # A per-target validation/budget failure must not leave a partial
            # candidate that skip_and_report could accidentally publish.
            plans[identity]={'row':row if scoped is None else scoped['row'],
                             'before':target_graph,'candidate':candidate,
                             'reviewed_face_refs':list({(ref['asset_sha256'],ref['face_instance_id'],ref['analysis_revision']):ref
                                 for ref in (([] if scoped is None else scoped.get('reviewed_face_refs',[]))+payload['target_refs'])}.values())}
            eligible+=1
        except Exception as error:blocked=str(error)[:2000]
        resolved.append({'index':None if found is None else found[0],'path':target.path,'document_id':target.document_id,
            'blocked':blocked,'expected_revision':str(target.revision),
            'current_revision':None if found is None else str(batch.versions.version(found[1]).revision),
            'target_refs':[] if payload is None else payload['target_refs']})
    if plan.policy=='recheck' and any(x['blocked'] for x in resolved):raise ValueError('A target changed; no people parameters were applied')
    if not eligible:raise ValueError('No confirmed target remains eligible')
    from .people_batch_ledger import prepare_scoped,_targets,_verify
    targets=_targets(batch,engine,plans)
    prepare_scoped(engine,plans,targets)
    # Full aggregate preparation may acquire fresher target observations. Do
    # not publish a previously frozen face-reference receipt against those new
    # observations, even when the document/graph counters did not change.
    for result in resolved:
        if result['blocked']:continue
        frozen=next(item for item in plan.targets if item.document_id==result['document_id'] and not item.blocked)
        payload=json.loads(frozen.people_json)
        from .body_face_match_state import OP as BODY_FACE_MATCH
        if not any(leaf['operation_id']==BODY_FACE_MATCH for leaf in payload['parameters']):continue
        found=batch.versions.find(batch.documents.rows(),result['document_id'])
        if found is None:raise ValueError('Body/face target disappeared during final preparation')
        row=found[1];scoped=plans.get(V.scope(row))
        if scoped is None:raise ValueError('Body/face target owner changed during final preparation')
        from .skin_colour_transfer_review import for_target as skin_coverage
        if skin_coverage(engine,row,scoped['candidate'],payload,family='body_face_match')!=payload.get('body_face_match_coverage'):
            raise ValueError('Body/face target review or own-face reference changed during final preparation; no graph was published')
    _verify(batch,engine,plans,targets)
    # Expensive effective-source preparation cannot authorize a newer graph.
    if V.row_snapshot(engine,source[1])!=graph:raise ValueError('People graph changed during final preparation')
    SOURCE.verify_row(source[1],source_proof)
    I.verify(engine,source[1],graph,source_owner)
    if document(engine,source[1])!=source_document:
        raise ValueError('People source changed during final preparation')
    for result in resolved:
        if result['blocked']:continue
        found=batch.versions.find(batch.documents.rows(),result['document_id'])
        if found is None or found[1]['path']!=result['path'] or str(batch.versions.version(found[1]).revision)!=result['expected_revision']:
            raise ValueError('People target changed during final preparation; no graph was published')
        target=next(item for item in plan.targets if item.document_id==result['document_id'] and not item.blocked)
        proof=SOURCE.verify_row(found[1],json.loads(target.before_json)['source_proof'])
        if any(ref['asset_sha256']!=proof['asset_sha256'] for ref in result['target_refs']):
            raise ValueError('People target source changed during final preparation; no graph was published')
    controller.store.claim(plan)
    try:
        from .people_batch_ledger import commit_scoped as publish
        result=publish(batch,engine,plans,request_id=p.get('request_id'),prepare=False,prepared_targets=targets)
        bid,frame=(None,None) if result is None else result
        body={'event':'batch_committed','success':True,'batch_id':bid,'module_scope':list(plan.modules),
            'applied':[x['index'] for x in resolved if not x['blocked']],
            'skipped':[x for x in resolved if x['blocked']], 'source_snapshot':controller._source(plan),
            'target_outcomes':[{**x,'result_revision':None if x['index'] is None else str(batch.versions.version(batch.documents.rows()[x['index']]).revision),
                'outcome':'skipped' if x['blocked'] else 'applied'} for x in resolved],
            'preflight_token':plan.token,'workspace_generation':plan.workspace,'people_transfer':True,
            'source_changed_since_preflight':False,'source_missing':False}
        controller.emit(body)
        if frame is not None:controller.emit(frame)
    except Exception as error:
        body={'success':False,'outcome_unknown':True,'error':str(error)[:2000],'preflight_token':plan.token,
              'workspace_generation':plan.workspace,'requires_preflight':True}
    controller.emit_result(p,controller.store.finish(plan,body))


def handle(engine,controller,p,plan):
    if plan is None and p.get('action')=='people_targets':return I.inventory(engine,controller,p)
    selected=p.get('people_transfer')
    if ((plan is None and type(selected) is dict and selected.get('target_policy')=='persistent_association')
            or (plan is not None and plan.params()[MARKER].get('mode')=='persistent_association')):
        from . import people_cross_owner_workflow as associations
        return associations.preflight(engine,controller,p) if plan is None else associations.commit(engine,controller,p,plan)
    return preflight(engine,controller,p) if plan is None else commit(engine,controller,p,plan)
