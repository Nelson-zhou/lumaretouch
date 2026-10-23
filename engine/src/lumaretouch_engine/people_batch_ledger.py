"""Portrait transactions in the existing batch ledger, partitioned by document.

Original photos still share their established graph. Virtual copies retain an
independent owner; one reviewed batch can stage and publish several such owners
without changing source identity, support evidence, or accepted associations.
"""
from copy import deepcopy
from .people_graph_patch import between
from .people_graph_owner import affected_assets
from . import virtual_copy_people as V

OP='lnx.people_graph.v1'


def _targets(owner,engine,plans):
    from .local_mask_state import source_digest
    targets={}
    for identity,plan in plans.items():
        assets=affected_assets(plan['before'],plan['candidate'])
        for index,row in enumerate(owner.documents.rows()):
            if V.scope(row)!=identity:continue
            asset=source_digest(row['path'])
            if asset not in assets:continue
            version=owner.versions.check_advance(row)
            targets[str(index)]={'path':row['path'],'document_id':version.document_id,
                'revision':version.revision,'asset_sha256':asset,'people_scope':identity}
    return targets


def _verify(owner,engine,plans,targets):
    from .local_mask_state import source_digest
    for plan in plans.values():
        if V.row_owner(engine,plan['row']).snapshot()!=plan['before']:
            raise ValueError('Portrait graph changed during scoped batch preparation')
    for target in targets.values():
        found=owner.versions.find(owner.documents.rows(),target['document_id'])
        if (found is None or found[1]['path']!=target['path']
                or owner.versions.version(found[1]).revision!=target['revision']
                or V.scope(found[1])!=target['people_scope']
                or source_digest(found[1]['path'])!=target['asset_sha256']):
            raise ValueError('People batch target changed during preparation')


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


def commit_scoped(owner,engine,plans,*,request_id,prepare=True):
    plans={identity:plan for identity,plan in plans.items() if between(plan['before'],plan['candidate'])}
    if not plans:return None
    owner.documents.remember_current()
    targets=_targets(owner,engine,plans)
    if not targets:raise ValueError('No retained portrait document can receive this batch')
    if prepare:prepare_scoped(engine,plans,targets)
    _verify(owner,engine,plans,targets)
    owner.sequence+=1;bid=f'batch-{owner.sequence:03d}-{int(owner.clock()*1000)}'
    scoped=[{'scope':identity,'document_id':plan['row']['document_id'],
             'changes':between(plan['before'],plan['candidate'])} for identity,plan in plans.items()]
    entry={'ops':[OP],'targets':targets,'at_ns':owner.monotonic(),'undone':False,
        'policy':'protected_scoped_graph','people_changes':[],
        'people_scoped_changes':scoped,'request_id':request_id}
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
    from .local_mask_state import source_digest
    from .source_relocation_history import matches as source_path_matches
    owner=engine._batch_controller();plans={}
    for record in batch['targets'].values():
        found=owner.versions.find(engine._docs,record['document_id'])
        if (found is None or not source_path_matches(found[1],record['path'])
                or source_digest(found[1]['path'])!=record['asset_sha256']
                or V.scope(found[1])!=record.get('people_scope')):
            raise ValueError('A scoped portrait batch target changed or was removed')
    for record in batch['people_scoped_changes']:
        found=owner.versions.find(engine._docs,record['document_id'])
        if found is None or V.scope(found[1])!=record['scope']:
            raise ValueError('Portrait batch graph owner is no longer available')
        row=found[1];before=V.row_snapshot(engine,row)
        plans[record['scope']]={'row':row,'before':before,
                               'candidate':apply(before,record['changes'],redo=redo)}
    targets=_targets(owner,engine,plans)
    # Recompute runtime paths/fences only after exact historical document/source
    # verification; a duplicate path never grants a replacement identity.
    prepare_scoped(engine,plans,targets)
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
