"""Portrait transactions in the existing batch ledger, partitioned by document.

Original photos still share their established graph. Virtual copies retain an
independent owner; one reviewed batch can stage and publish several such owners
without changing source identity, support evidence, or accepted associations.
"""
from copy import deepcopy
from .people_graph_patch import between
from .people_graph_owner import affected_assets
from . import virtual_copy_people as V, creative_derived_source as SOURCE, people_state as S

OP='lnx.people_graph.v1'


def reviewed_refs(record):
    """New transfer history pins exact analysis; legacy originals stay explicit."""
    if 'reviewed_face_refs' not in record:
        if (record.get('source_proof') or {}).get('creative_source') is not None:
            raise ValueError('Derived portrait history is missing reviewed face analysis references')
        return None
    refs=record['reviewed_face_refs']
    if type(refs) is not list or not 1<=len(refs)<=128:
        raise ValueError('Reviewed portrait history requires bounded exact face references')
    checked=[];seen=set()
    for ref in refs:
        ref=S.check_ref(ref)
        if ref['asset_sha256']!=record['asset_sha256'] or ref['face_instance_id'] in seen:
            raise ValueError('Reviewed portrait history face is duplicated or belongs to another source')
        seen.add(ref['face_instance_id']);checked.append(ref)
    return checked


def verify_reviewed_refs(engine,row,record):
    refs=reviewed_refs(record)
    if refs is None:return
    state=V.row_snapshot(engine,row)
    for ref in refs:
        face=state['faces'].get(ref['face_instance_id'])
        if face is None or S.face_ref(face)!=ref:
            raise ValueError('Reviewed portrait face analysis changed; protected batch history refused')


def _targets(owner,engine,plans):
    targets={}
    for identity,plan in plans.items():
        assets=affected_assets(plan['before'],plan['candidate'])
        for index,row in enumerate(owner.documents.rows()):
            if V.scope(row)!=identity:continue
            proof=SOURCE.row_proof(row)
            asset=proof['asset_sha256']
            if asset not in assets:continue
            version=owner.versions.check_advance(row)
            targets[str(index)]={'path':row['path'],'document_id':version.document_id,
                'revision':version.revision,'asset_sha256':asset,'people_scope':identity,'source_proof':proof}
            if 'reviewed_face_refs' in plan:
                targets[str(index)]['reviewed_face_refs']=[deepcopy(ref) for ref in plan['reviewed_face_refs'] if ref['asset_sha256']==asset]
            reviewed_refs(targets[str(index)])
    return targets


def _verify(owner,engine,plans,targets):
    for plan in plans.values():
        if V.row_owner(engine,plan['row']).snapshot()!=plan['before']:
            raise ValueError('Portrait graph changed during scoped batch preparation')
    for target in targets.values():
        found=owner.versions.find(owner.documents.rows(),target['document_id'])
        if (found is None or found[1]['path']!=target['path']
                or owner.versions.version(found[1]).revision!=target['revision']
                or V.scope(found[1])!=target['people_scope']):
            raise ValueError('People batch target changed during preparation')
        SOURCE.verify_row_target(found[1],target)
        verify_reviewed_refs(engine,found[1],target)


def prepare_scoped(engine,plans,targets):
    from .people_candidate_render import validate
    current=V.current_row(engine);current_scope=V.scope(current)
    for identity,plan in plans.items():
        rows=[row for row in engine._docs if any(target['document_id']==row['document_id']
              and target['people_scope']==identity for target in targets.values())]
        if identity==current_scope and current is not None:
            assets=affected_assets(plan['before'],plan['candidate'])
            engine._people_prepare_graph(plan['candidate'],assets)
        else:
            for row in rows:validate(engine,row,plan['candidate'])


def _publish(owner,engine,plans,targets):
    from .people_cross_owner_ledger import validate_plans
    validate_plans(plans,targets)
    _verify(owner,engine,plans,targets)
    committed=[]
    try:
        for plan in plans.values():
            graph_owner=V.row_owner(engine,plan['row'])
            graph_owner.commit(plan['candidate'],expected_fence=graph_owner.fence)
            committed.append((graph_owner,plan['before']))
        for target in targets.values():
            found=owner.versions.find(owner.documents.rows(),target['document_id'])
            owner.versions.advance(found[1])
        engine._people_analysis_key=None
        current=V.current_row(engine)
        frame=None
        if current is not None and V.scope(current) in plans:
            engine._people_sync(strict=True)
            frame=engine._write_current_frame('people');frame['doc_state']=engine.doc_state()
        # Rendering the active owner may be expensive. Recheck every parked
        # target's actual effective bytes/provenance before returning success;
        # failure stays inside the existing all-owner graph rollback boundary.
        for target in targets.values():
            found=owner.versions.find(owner.documents.rows(),target['document_id'])
            if found is None or V.scope(found[1])!=target['people_scope']:
                raise ValueError('Portrait target owner changed during publication')
            SOURCE.verify_row_target(found[1],target)
            verify_reviewed_refs(engine,found[1],target)
        V.remember(engine)
        engine._project_dirty=True
        return frame
    except Exception:
        for graph_owner,before in reversed(committed):
            prior=deepcopy(before);prior['association_revision']=graph_owner.association_fence
            graph_owner.commit(prior,expected_fence=graph_owner.fence)
        engine._people_analysis_key=None
        try:engine._people_sync(strict=True)
        except Exception:engine._vram=None
        raise
    finally:engine._people_staged=None


def commit_scoped(owner,engine,plans,*,request_id,prepare=True,prepared_targets=None,alias_history=None):
    plans={identity:plan for identity,plan in plans.items() if between(plan['before'],plan['candidate'])}
    if not plans:return None
    owner.documents.remember_current()
    # Transfer callers retain the proof actually rendered. Re-freezing here
    # could authorize changed source bytes after expensive target preparation.
    targets=_targets(owner,engine,plans) if prepared_targets is None else deepcopy(prepared_targets)
    if not targets:raise ValueError('No retained portrait document can receive this batch')
    if prepare:prepare_scoped(engine,plans,targets)
    _verify(owner,engine,plans,targets)
    owner.sequence+=1;bid=f'batch-{owner.sequence:03d}-{int(owner.clock()*1000)}'
    scoped=[{'scope':identity,'document_id':plan['row']['document_id'],
             'changes':between(plan['before'],plan['candidate'])} for identity,plan in plans.items()]
    entry={'ops':[OP],'targets':targets,'at_ns':owner.monotonic(),'undone':False,
        'policy':'protected_scoped_graph','people_changes':[],
        'people_scoped_changes':scoped,'request_id':request_id}
    if alias_history is not None:
        # Validate before graph publication; no successful alias batch may be
        # left in the ledger without its exact-member restore protection.
        from .face_style_alias_history import KEY as ALIAS_KEY, check as check_alias_history
        entry[ALIAS_KEY]=deepcopy(alias_history)
        check_alias_history(entry)
    result={'kind':'commit','batch_id':bid,'applied':[int(k) for k in targets],'skipped':[]}
    frame=_publish(owner,engine,plans,targets)
    owner.ledger[bid]=entry;owner.last_result=result
    engine._people_shared_mutation=True;owner.editor.mark_dirty()
    return bid,frame


def commit(owner,engine,before,candidate,*,request_id,prepare=True):
    row=V.current_row(engine)
    if row is None:raise ValueError('Portrait transaction needs its current document')
    return commit_scoped(owner,engine,{V.scope(row):{'row':row,'before':before,'candidate':candidate}},
                         request_id=request_id,prepare=prepare)


def restore_scoped(engine,batch,redo):
    from .people_graph_patch import apply
    from .source_relocation_history import matches as source_path_matches
    from .face_style_alias_history import check as check_alias_history, verify_restore as verify_alias_restore
    alias_history=check_alias_history(batch)
    owner=engine._batch_controller();plans={};reviewed={}
    for record in batch['targets'].values():
        found=owner.versions.find(engine._docs,record['document_id'])
        if (found is None or not source_path_matches(found[1],record['path'])
                or V.scope(found[1])!=record.get('people_scope')):
            raise ValueError('A scoped portrait batch target changed or was removed')
        SOURCE.verify_row_target(found[1],record)
        verify_reviewed_refs(engine,found[1],record)
        refs=reviewed_refs(record)
        if refs is not None:reviewed.setdefault(record['people_scope'],[]).extend(refs)
    for record in batch['people_scoped_changes']:
        found=owner.versions.find(engine._docs,record['document_id'])
        if found is None or V.scope(found[1])!=record['scope']:
            raise ValueError('Portrait batch graph owner is no longer available')
        row=found[1];before=V.row_snapshot(engine,row)
        plans[record['scope']]={'row':row,'before':before,
                               'candidate':apply(before,record['changes'],redo=redo)}
        if record['scope'] in reviewed:
            plans[record['scope']]['reviewed_face_refs']=list({(ref['asset_sha256'],ref['face_instance_id'],ref['analysis_revision']):ref
                for ref in reviewed[record['scope']]}.values())
    targets=_targets(owner,engine,plans)
    if alias_history is not None:verify_alias_restore(engine,batch,plans,targets)
    # Recompute runtime paths/fences only after exact historical document/source
    # verification; a duplicate path never grants a replacement identity.
    prepare_scoped(engine,plans,targets)
    if alias_history is not None:
        # Preparation must not expand an explicitly reviewed alias cohort.
        # Legacy scoped batches retain their established restoration behavior.
        verify_alias_restore(engine,batch,plans,_targets(owner,engine,plans))
    return _publish(owner,engine,plans,targets)


def restore(owner,request):
    batch=owner.ledger[str(request.get('batch_id') or '')];redo=request.get('action')=='redo'
    if bool(batch['undone'])!=redo:raise ValueError('People group is not in the requested undo/redo state')
    if owner.editor.people_restore is None:raise ValueError('People group restore adapter is unavailable')
    frame=owner.editor.people_restore(batch,redo)
    batch['undone']=not redo;owner.editor.mark_dirty()
    body={'event':'batch_redone' if redo else 'batch_undone','batch_id':request['batch_id'],
          'module_scope':batch['ops'],'restored':[int(k) for k in batch['targets']], 'conflicts':[], 'doc_state':owner.editor.status()}
    owner.last_result={'kind':'redo' if redo else 'undo','batch_id':request['batch_id'],'restored':body['restored'],'conflicts':[]}
    owner.emit(body)
    if frame is not None:owner.emit(frame)
    return body
