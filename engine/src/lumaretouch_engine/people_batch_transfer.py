"""Confirmed-face parameter adapter for the existing frozen batch owner.

Uses FrozenBatchController.store, its receipts and BatchSyncController.ledger.
There is no independent transaction queue, token service or undo stack here.
"""
from copy import deepcopy
import json
from dataclasses import replace
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
    if 'face_style' in value:
        from .face_style_batch_review import recipe,check_selection
        if policy!='explicit_face_map':raise ValueError('Named face styles require an explicit target-owned face map')
        recipe(value['face_style']);check_selection(value['face_style'],value.get('selection'))
        fields.add('face_style')
    if 'eye_bag' in value:
        from .eye_bag_batch_review import options as eye_options
        eye_options(value['eye_bag'],value);fields.add('eye_bag')
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



def _collarbone_visuals(engine, rows, targets, public):
    """Render the final aggregate shared-owner graph, including all mixed leaves.

    Original photos share one owner. Independent per-row previews would omit
    other selected updates and could not authorize the actual committed graph.
    """
    from . import collarbone_transfer_review as review
    from .skin_colour_transfer_review import for_target
    if len(targets) > review.MAX_TARGETS:
        raise ValueError('Collarbone visual review supports at most sixteen targets; no target was omitted')
    plans = {}
    for target in targets:
        if target.blocked: continue
        row = rows[target.index]; payload = json.loads(target.people_json)
        identity = V.scope(row); graph = V.row_snapshot(engine, row)
        staged = plans.get(identity)
        if staged is not None and staged['before'] != graph:
            raise ValueError('Collarbone target owner changed during aggregate preparation')
        candidate = S.check(graph if staged is None else staged['candidate'])
        from .eye_bag_batch_plan import ADMISSION
        candidate = T.stage(payload, candidate, eye_bag_review=ADMISSION if 'eye_bag' in payload else None)
        plans[identity] = {'before': graph, 'candidate': candidate}
    from .people_graph_owner import affected_assets
    reviewed = {target.document_id for target in targets if not target.blocked}
    for row in rows:
        staged = plans.get(V.scope(row))
        if staged is not None and SOURCE.row_proof(row)['asset_sha256'] in affected_assets(staged['before'], staged['candidate']):
            if document(engine,row)['document_id'] not in reviewed:
                raise ValueError('Collarbone changes also affect an unreviewed shared-source document; include that document or use an independent virtual copy')
    total = 0; frozen = []; displays = {}
    for target, visible in zip(targets, public):
        if target.blocked:
            frozen.append(target); continue
        row = rows[target.index]; payload = json.loads(target.people_json); staged = plans[V.scope(row)]
        coverage = for_target(engine, row, staged['candidate'], payload, family='collarbone')
        if coverage != payload.get('collarbone_coverage'):
            raise ValueError('Collarbone target coverage changed during aggregate review')
        record, display = review.prepare(engine, row, staged['before'], staged['candidate'],
            target.document_id, str(target.revision), coverage)
        total += len(display['before']['base64']) + len(display['after']['base64'])
        if total > review.MAX_TOTAL_BASE64:
            raise ValueError('Collarbone review response exceeds its display budget; select fewer targets, no target was silently omitted')
        payload['collarbone_visual'] = record
        frozen.append(replace(target, people_json=canonical(payload)))
        visible['people_transfer'] = deepcopy(payload)
        displays[target.document_id] = {'revision': str(target.revision), 'before': display['before'], 'after': display['after']}
    # No view may become obsolete while another target is being rendered.
    for target in frozen:
        if target.blocked: continue
        row = rows[target.index]; payload = json.loads(target.people_json); staged = plans[V.scope(row)]
        if V.row_snapshot(engine, row) != staged['before']:
            raise ValueError('Collarbone target graph changed while reviewing other targets')
        coverage = for_target(engine, row, staged['candidate'], payload, family='collarbone')
        review.verify(engine, row, staged['before'], staged['candidate'], target.document_id,
            str(target.revision), coverage, payload['collarbone_visual'])
    return frozen, displays


def preflight(engine,controller,p):
    if set(p)-{'cmd','action','request_id','docs','module_scope','conflict_policy','people_transfer'}:
        raise ValueError('People transfer cannot be mixed with other batch options')
    policy=p.get('conflict_policy','skip_and_report')
    if policy not in ('skip_and_report','recheck'):raise ValueError('Unknown conflict policy')
    named=type(p.get('people_transfer')) is dict and 'face_style' in p['people_transfer']
    eye=type(p.get('people_transfer')) is dict and 'eye_bag' in p['people_transfer']
    if named or eye:
        from .people_preset_plan import require_active_owner
        owner=require_active_owner(engine)
        if V.current_row(engine).get('_people_new_import'):
            raise ValueError('Open and review the context photograph before named-style batch preparation')
    else:
        engine._people_bind();owner=engine._people_owner()
    before=owner.snapshot();fence=owner.fence
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
    if explicit and (policy=='recheck' or eye) and rejected:
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
            if (named or eye) and (row.get('_people_new_import') or V.peek_graph(engine,row) is None):
                raise ValueError('Named style requires an already reviewed target portrait owner; open and inspect it first')
            target_graph=V.row_snapshot(engine,row)
            target_owner=I.proof(engine,row,target_graph)
            if explicit:
                mapping=next(item for item in selected['targets'] if item['target']['document']['document_id']==target_document['document_id'])
                I.verify(engine,row,target_graph,mapping['target'])
                from .eye_bag_batch_plan import ADMISSION
                from .eye_bag_batch_review import for_document
                payload=T.prepare(before,target_graph,selected['source_ref'],mapping['target_refs'],selected['selection'],A.defaults(),
                    source_document=source_document,target_document=target_document,source_owner=source_owner,target_owner=target_owner,
                    face_style=selected.get('face_style'),
                    eye_bag=for_document(selected,target_document['document_id']) if eye else None,
                    eye_bag_review=ADMISSION if eye else None)
                payload['target_policy']='explicit_face_map'
            else:
                payload=prepare_confirmed(before,target_graph,selected['source_ref'],asset,selected['selection'],A.defaults(),
                    source_document=source_document,target_document=target_document,source_owner=source_owner,target_owner=target_owner)
            staged=T.candidate(payload,before,target_graph,source_document=source_document,target_document=target_document,
                               source_owner=source_owner,target_owner=target_owner,
                               eye_bag_review=ADMISSION if eye else None)
            if 'face_style' in payload:
                from .face_style_batch_plan import validate as validate_style
                validate_style(staged,payload['target_refs'])
            from .people_candidate_render import validate
            validate(engine,row,staged)
            from .skin_colour_transfer_review import for_target as skin_coverage
            coverage=skin_coverage(engine,row,staged,payload)
            if coverage is not None:payload['skin_colour_coverage']=coverage
            finish_coverage=skin_coverage(engine,row,staged,payload,family='skin_finish')
            if finish_coverage is not None:payload['skin_finish_coverage']=finish_coverage
            clavicle_coverage=skin_coverage(engine,row,staged,payload,family='collarbone')
            if clavicle_coverage is not None:payload['collarbone_coverage']=clavicle_coverage
            body_evenness_coverage=skin_coverage(engine,row,staged,payload,family='body_skin_evenness')
            if body_evenness_coverage is not None:payload['body_skin_evenness_coverage']=body_evenness_coverage
            body_face_match_coverage=skin_coverage(engine,row,staged,payload,family='body_face_match')
            if body_face_match_coverage is not None:payload['body_face_match_coverage']=body_face_match_coverage
            if eye:
                from .eye_bag_batch_plan import coverage as eye_coverage
                payload['eye_bag_coverage']=eye_coverage(engine,row,staged,payload)
            SOURCE.verify_row(row,target_proof)
            if owner.fence!=fence or V.row_snapshot(engine,row)!=target_graph or document(engine,row)!=target_document:
                raise ValueError('Target or graph changed during preparation')
        except Exception as error:blocked=str(error)[:2000];payload=None
        public.append({'index':index,'path':row['path'],'live':False,'document_id':target_document['document_id'],
            'revision':str(target_document['revision']),'blocked':blocked,'before':{},'people_transfer':payload})
        targets.append(FrozenTarget(target_document['document_id'],target_document['revision'],index,row['path'],blocked,
            canonical({'source_proof':target_proof}),people_json=None if payload is None else canonical(payload)))
    from .collarbone_state import OP as COLLARBONE
    displays = None
    if 'face_style' in selected:
        from .face_style_batch_plan import visuals
        targets,displays=visuals(engine,rows,targets,public)
    elif COLLARBONE in selected['selection']:
        targets,displays=_collarbone_visuals(engine,rows,targets,public)
    eye_displays=None
    if eye:
        from .eye_bag_batch_plan import visuals
        targets,eye_displays=visuals(engine,rows,targets,public)
    SOURCE.verify_row(source_row,source_proof)
    if owner.fence!=fence or document(engine,source_row)!=source_document:
        raise ValueError('Source or associations changed during preparation; review again')
    I.verify(engine,source_row,before,source_owner)
    frozen={MARKER:{'options':selected,'source_asset':source_asset,'source_proof':source_proof,'state_revision':before['revision'],
                    'association_revision':before['association_revision'],'source_owner':source_owner}}
    body={'event':'batch_preflight','success':True,'module_scope':list(p['module_scope']),'source':'current',
        'source_snapshot':{'document_id':source_document['document_id'],'revision':str(source_document['revision']),'path':source_row['path']},
        'applies':selected,'policy':policy,'targets':public,
        'rejected_docs':rejected,'ok':sum(not x['blocked'] for x in public),'blocked':sum(bool(x['blocked']) for x in public),
        # Conservative envelope placeholders checked BEFORE retaining a token.
        'preflight_token':'x'*256,'workspace_generation':batch.versions.workspace,'expires_ns':'9'*128,
        'people_transfer':True}
    if (eye or 'face_style' in selected or COLLARBONE in selected['selection']) and len(json.dumps(body,ensure_ascii=True,allow_nan=False).encode('utf-8'))>7*1024*1024:
        raise ValueError('Collarbone visual response exceeds transport budget; select fewer targets and review again')
    plan=controller.store.create(batch.versions.workspace,source_document['document_id'],source_document['revision'],
        source_row['path'],p['module_scope'],frozen,policy,targets,rejected)
    if displays is not None:
        if 'face_style' in selected:
            from .face_style_batch_store import attach,prune
        else:
            from .collarbone_visual_store import attach,prune
        try:
            attach(controller.store,plan,displays)
        except Exception:
            controller.store.pending.pop(plan.token,None)
            prune(controller.store)
            raise
    if eye_displays is not None:
        from .eye_bag_batch_store import attach,prune
        try:attach(controller.store,plan,eye_displays)
        except Exception:
            controller.store.pending.pop(plan.token,None)
            prune(controller.store)
            from .collarbone_visual_store import prune as prune_collarbone
            prune_collarbone(controller.store)
            raise
    body.update(module_scope=list(plan.modules),source_snapshot=controller._source(plan),
                preflight_token=plan.token,workspace_generation=plan.workspace,expires_ns=str(plan.expires_ns))
    controller.emit(body);controller.emit_result(p,body)


def commit(engine,controller,p,plan):
    if set(p)-{'cmd','action','request_id','preflight_token','collarbone_review_ack','face_style_review_ack','eye_bag_review_ack'}:raise ValueError('Commit accepts only the frozen token and its collarbone image acknowledgments')
    from .collarbone_state import OP as COLLARBONE
    from . import collarbone_transfer_review as visual_review
    visual_selected=COLLARBONE in plan.modules
    from . import eye_bag_batch_review as eye_review
    from .eye_bag_batch_plan import ADMISSION
    eye_records=eye_review.records(plan);eye_selected=eye_records is not None;eye_ack=None
    if eye_selected:eye_ack=eye_review.acknowledgments(p.get('eye_bag_review_ack'),eye_records)
    elif 'eye_bag_review_ack' in p:raise ValueError('Eye-bag ACK cannot authorize another operation')
    from . import face_style_batch_review as style_review
    style_selected=style_review.required(plan);style_ack=None
    if style_selected:
        if 'collarbone_review_ack' in p:raise ValueError('Mixed acknowledgment families cannot authorize named styles')
        style_ack=style_review.acknowledgments(p.get('face_style_review_ack'),[json.loads(t.people_json)['face_style_visual'] for t in plan.targets if not t.blocked])
    elif 'face_style_review_ack' in p:raise ValueError('Face-style ACK cannot authorize another operation')
    visual_ack=None
    if visual_selected:
        records=[json.loads(target.people_json).get('collarbone_visual') for target in plan.targets if not target.blocked]
        visual_ack=visual_review.acknowledgments(p.get('collarbone_review_ack'),records)
    elif 'collarbone_review_ack' in p:
        raise ValueError('Collarbone acknowledgment cannot authorize another operation')
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
                     source_owner=source_owner,target_owner=target_owner,eye_bag_review=ADMISSION if eye_selected else None)
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
            candidate=T.stage(payload,candidate,eye_bag_review=ADMISSION if eye_selected else None)
            if eye_selected:
                from .eye_bag_batch_plan import coverage as eye_coverage
                if eye_coverage(engine,row,candidate,payload)!=payload.get('eye_bag_coverage'):
                    raise ValueError('Eye-bag target support changed after review')
            if style_selected:
                from .face_style_batch_plan import validate as validate_style
                validate_style(candidate,payload['target_refs'])
            from .collarbone_state import OP as COLLARBONE
            from .body_skin_evenness_state import OP as BODY_SKIN_EVENNESS
            from .body_face_match_state import OP as BODY_FACE_MATCH
            body_families=[family for operation,family in ((COLLARBONE,'collarbone'),(BODY_SKIN_EVENNESS,'body_skin_evenness'),
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
    if eye_selected:
        # A no-op first row cannot represent the changed scope in protected
        # history. Select a retained actually affected document before claim.
        for identity,scoped in plans.items():
            member=next((target for target in targets.values() if target['people_scope']==identity),None)
            if member is not None:
                found=batch.versions.find(batch.documents.rows(),member['document_id'])
                if found is None:raise ValueError('Eye-bag history representative disappeared')
                scoped['row']=found[1]
    if visual_selected or style_selected or eye_selected:
        reviewed={item['document_id'] for item in resolved if not item['blocked']}
        if any(target['document_id'] not in reviewed for target in targets.values()):
            raise ValueError('Collarbone publication would modify an unreviewed shared-source document; review the complete affected set')
    prepare_scoped(engine,plans,targets)
    # Full aggregate preparation may acquire fresher target observations. Do
    # not publish a previously frozen face-reference receipt against those new
    # observations, even when the document/graph counters did not change.
    for result in resolved:
        if result['blocked']:continue
        frozen=next(item for item in plan.targets if item.document_id==result['document_id'] and not item.blocked)
        payload=json.loads(frozen.people_json)
        from .body_face_match_state import OP as BODY_FACE_MATCH
        from .collarbone_state import OP as COLLARBONE
        families=[family for operation,family in ((BODY_FACE_MATCH,'body_face_match'),(COLLARBONE,'collarbone'))
                  if any(leaf['operation_id']==operation for leaf in payload['parameters'])]
        if not families:continue
        found=batch.versions.find(batch.documents.rows(),result['document_id'])
        if found is None:raise ValueError('Reviewed body target disappeared during final preparation')
        row=found[1];scoped=plans.get(V.scope(row))
        if scoped is None:raise ValueError('Reviewed body target owner changed during final preparation')
        from .skin_colour_transfer_review import for_target as skin_coverage
        for family in families:
            if skin_coverage(engine,row,scoped['candidate'],payload,family=family)!=payload.get(family+'_coverage'):
                raise ValueError('Target-local body review changed during final preparation; no graph was published')
    if visual_selected:
        # Verify the actual aggregate about to publish, not each isolated face
        # recipe. A newly skipped shared-owner target may change that aggregate;
        # require fresh visual review rather than silently weaken the receipt.
        for result in resolved:
            if result['blocked']:continue
            found=batch.versions.find(batch.documents.rows(),result['document_id'])
            if found is None:raise ValueError('Collarbone visual target disappeared')
            row=found[1];scoped=plans[V.scope(row)]
            frozen=next(target for target in plan.targets if target.document_id==result['document_id'])
            payload=json.loads(frozen.people_json)
            from .skin_colour_transfer_review import for_target as skin_coverage
            coverage=skin_coverage(engine,row,scoped['candidate'],payload,family='collarbone')
            visual_review.verify(engine,row,scoped['before'],scoped['candidate'],result['document_id'],
                result['expected_revision'],coverage,payload['collarbone_visual'])
    if style_selected:
        from .face_style_batch_plan import verify as verify_style
        for result in resolved:
            if result['blocked']:continue
            found=batch.versions.find(batch.documents.rows(),result['document_id'])
            if found is None:raise ValueError('Named-style target disappeared')
            row=found[1];frozen=next(t for t in plan.targets if t.document_id==result['document_id'])
            verify_style(engine,row,plans[V.scope(row)],frozen,json.loads(frozen.people_json))
    eye_history=None
    if eye_selected:
        from .eye_bag_batch_plan import verify as verify_eye,closure
        closure(engine,batch.documents.rows(),plans,{item['document_id'] for item in resolved if not item['blocked']})
        for result in resolved:
            if result['blocked']:continue
            found=batch.versions.find(batch.documents.rows(),result['document_id'])
            if found is None:raise ValueError('Eye-bag target disappeared during full preparation')
            row=found[1];frozen=next(t for t in plan.targets if t.document_id==result['document_id'])
            verify_eye(engine,row,plans[V.scope(row)],frozen,json.loads(frozen.people_json))
        from .eye_bag_batch_history import prepare as prepare_history
        eye_history=prepare_history(engine,plans,targets,eye_ack) if targets else None
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
    if visual_selected:
        from .collarbone_visual_store import verify_available
        verify_available(controller.store,plan)
    if style_selected:
        from .face_style_batch_store import verify_available
        verify_available(controller.store,plan)
    if eye_selected:
        from .eye_bag_batch_store import verify_available
        verify_available(controller.store,plan)
    controller.store.claim(plan,collarbone_review_ack=visual_ack,face_style_review_ack=style_ack,eye_bag_review_ack=eye_ack,request_id=p.get('request_id'))
    try:
        from .people_batch_ledger import commit_scoped as publish
        result=publish(batch,engine,plans,request_id=p.get('request_id'),prepare=False,prepared_targets=targets,eye_bag_history=eye_history)
        bid,frame=(None,None) if result is None else result
        body={'event':'batch_committed','success':True,'batch_id':bid,'module_scope':list(plan.modules),
            'applied':[x['index'] for x in resolved if not x['blocked']],
            'skipped':[x for x in resolved if x['blocked']], 'source_snapshot':controller._source(plan),
            'target_outcomes':[{**x,'result_revision':None if x['index'] is None else str(batch.versions.version(batch.documents.rows()[x['index']]).revision),
                'outcome':'skipped' if x['blocked'] else 'applied'} for x in resolved],
            'preflight_token':plan.token,'workspace_generation':plan.workspace,'people_transfer':True,
            'source_changed_since_preflight':False,'source_missing':False}
        if eye_selected:
            changed={target['document_id'] for target in targets.values()}
            body['applied']=[x['index'] for x in resolved if not x['blocked'] and x['document_id'] in changed]
            for item in body['target_outcomes']:
                if not item['blocked'] and item['document_id'] not in changed:item['outcome']='noop'
            body.update(eye_bag_review_ack=deepcopy(eye_ack),outcome_unknown=False)
        if visual_ack is not None:body['collarbone_review_ack']=deepcopy(visual_ack)
        if style_ack is not None:
            body['face_style_review_ack']=deepcopy(style_ack)
            body['outcome_unknown']=False
        controller.emit(body)
        if frame is not None:controller.emit(frame)
    except Exception as error:
        body={'success':False,'outcome_unknown':True,'error':str(error)[:2000],'preflight_token':plan.token,
              'workspace_generation':plan.workspace,'requires_preflight':True}
    if visual_ack is not None:
        body['collarbone_review_ack']=deepcopy(visual_ack)
        body['module_scope']=list(plan.modules)
    if style_ack is not None:
        body['face_style_review_ack']=deepcopy(style_ack)
        body['module_scope']=list(plan.modules)
    if eye_ack is not None:
        body['eye_bag_review_ack']=deepcopy(eye_ack)
        body['module_scope']=list(plan.modules)
    controller.emit_result(p,controller.store.finish(plan,body))


def handle(engine,controller,p,plan):
    if plan is None and p.get('action')=='people_targets':return I.inventory(engine,controller,p)
    selected=p.get('people_transfer')
    if ((plan is None and type(selected) is dict and selected.get('target_policy')=='persistent_association')
            or (plan is not None and plan.params()[MARKER].get('mode')=='persistent_association')):
        from . import people_cross_owner_workflow as associations
        return associations.preflight(engine,controller,p) if plan is None else associations.commit(engine,controller,p,plan)
    return preflight(engine,controller,p) if plan is None else commit(engine,controller,p,plan)
