"""People graph transactions inside the existing BatchSyncController ledger.

No separate history stack, document owner, receipt service or batch scheduler.
The engine callback prepares all affected sources and publishes one graph.
"""
from .people_graph_patch import between
from .people_graph_owner import affected_assets

OP='lnx.people_graph.v1'


def commit(owner,engine,before,candidate,*,request_id,prepare=True):
    changes=between(before,candidate)
    if not changes:return None
    owner.documents.remember_current();assets=affected_assets(before,candidate)
    assets.add(engine._people_source()['sha256'])
    targets={}
    for index,row in enumerate(owner.documents.rows()):
        from .local_mask_state import source_digest
        if source_digest(row['path']) not in assets:continue
        version=owner.versions.check_advance(row)
        targets[str(index)]={'path':row['path'],'document_id':version.document_id,'revision':version.revision,'asset_sha256':source_digest(row['path'])}
    if prepare:engine._people_prepare_graph(candidate,assets)
    # Re-check the exact rows/source identities after potentially expensive preparation.
    for target in targets.values():
        found=owner.versions.find(owner.documents.rows(),target['document_id'])
        if found is None or found[1]['path']!=target['path'] or owner.versions.version(found[1]).revision!=target['revision']:
            raise ValueError('People batch target changed during preparation')
    # Perform fallible clock/result preparation before publishing any graph.
    # A failed publication may leave a sequence gap; IDs must not rewind/reuse.
    owner.sequence+=1;bid=f'batch-{owner.sequence:03d}-{int(owner.clock()*1000)}'
    entry={'ops':[OP],'targets':targets,'at_ns':owner.monotonic(),'undone':False,
        'policy':'protected_scoped_graph','people_changes':changes,'request_id':request_id}
    result={'kind':'commit','batch_id':bid,'applied':[int(k) for k in targets],'skipped':[]}
    frame=engine._people_publish_graph(candidate,assets)
    owner.ledger[bid]=entry;owner.last_result=result
    # Keep protected group history even if the final dirty notification fails.
    engine._people_shared_mutation=True;owner.editor.mark_dirty()
    return bid,frame


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
