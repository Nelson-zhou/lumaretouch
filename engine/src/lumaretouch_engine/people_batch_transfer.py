"""Confirmed-face parameter adapter for the existing frozen batch owner.

Uses FrozenBatchController.store, its receipts and BatchSyncController.ledger.
There is no independent transaction queue, token service or undo stack here.
"""
from copy import deepcopy
import json
from . import people_state as S, people_algorithms as A, people_transfer_adapter as T
from .people_confirmed_transfer import prepare_confirmed
from .batch_preflight import FrozenTarget,canonical
from . import local_mask_state as SOURCE

MARKER='_people_transfer'


def document(engine,row):
    version=engine._document_versions().version(row)
    return {'document_id':version.document_id,'epoch':engine._document_versions().workspace,'revision':version.revision}


def options(value,modules,source_asset):
    if type(value) is not dict or set(value)!={'source_ref','selection','target_policy'}:
        raise ValueError('People transfer requires an explicit source, parameter selection and target policy')
    if value['target_policy']!='confirmed_person_only':raise ValueError('Only explicitly confirmed anonymous associations may select people targets')
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
    return deepcopy(value)


def preflight(engine,controller,p):
    if set(p)-{'cmd','action','request_id','docs','module_scope','conflict_policy','people_transfer'}:
        raise ValueError('People transfer cannot be mixed with other batch options')
    policy=p.get('conflict_policy','skip_and_report')
    if policy not in ('skip_and_report','recheck'):raise ValueError('Unknown conflict policy')
    engine._people_bind();owner=engine._people_owner();before=owner.snapshot();fence=owner.fence
    batch=engine._batch_controller();batch.documents.remember_current()
    rows=batch.documents.rows();source_row=rows[batch.documents.current_index()]
    source_asset=SOURCE.source_digest(source_row['path']);source_document=document(engine,source_row)
    selected=options(p.get('people_transfer'),p.get('module_scope'),source_asset)
    indices,rejected=batch.target_indices(p.get('docs'));targets=[];public=[];seen_assets=set()
    for index in indices:
        row=rows[index];target_document=document(engine,row);asset=SOURCE.source_digest(row['path'])
        blocked=None;payload=None
        try:
            if row.get('trashed'):raise ValueError('Target photo is in the project trash')
            if asset==source_asset:raise ValueError('The source photo is not a transfer target')
            if asset in seen_assets:raise ValueError('The same source asset was already selected as a target')
            seen_assets.add(asset)
            payload=prepare_confirmed(before,before,selected['source_ref'],asset,selected['selection'],A.defaults(),
                source_document=source_document,target_document=target_document)
            staged=T.candidate(payload,before,before,source_document=source_document,target_document=target_document)
            engine._people_prepare_graph(staged,{asset})
            if owner.fence!=fence or document(engine,row)!=target_document or SOURCE.source_digest(row['path'])!=asset:
                raise ValueError('Target or graph changed during preparation')
        except Exception as error:blocked=str(error)[:2000];payload=None
        public.append({'index':index,'path':row['path'],'live':False,'document_id':target_document['document_id'],
            'revision':str(target_document['revision']),'blocked':blocked,'before':{},'people_transfer':payload})
        targets.append(FrozenTarget(target_document['document_id'],target_document['revision'],index,row['path'],blocked,
            canonical({'asset_sha256':asset}),people_json=None if payload is None else canonical(payload)))
    if owner.fence!=fence or document(engine,source_row)!=source_document or SOURCE.source_digest(source_row['path'])!=source_asset:
        raise ValueError('Source or associations changed during preparation; review again')
    frozen={MARKER:{'options':selected,'source_asset':source_asset,'state_revision':before['revision'],
                    'association_revision':before['association_revision']}}
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
    batch=engine._batch_controller();batch.documents.remember_current();graph=engine._people_owner().snapshot()
    params=plan.params()[MARKER];source=batch.versions.find(batch.documents.rows(),plan.source_id)
    if source is None or source[1]['path']!=plan.source_path or batch.versions.version(source[1]).revision!=plan.source_revision:
        raise ValueError('People source changed after review')
    if SOURCE.source_digest(source[1]['path'])!=params['source_asset'] or graph['revision']!=params['state_revision'] or graph['association_revision']!=params['association_revision']:
        raise ValueError('Source bytes or people associations changed after review')
    source_document=document(engine,source[1]);resolved=[];candidate=S.check(graph);assets=set()
    for target in plan.targets:
        found=batch.versions.find(batch.documents.rows(),target.document_id);blocked=target.blocked;payload=None
        try:
            if blocked:raise ValueError(blocked)
            if found is None:raise ValueError('Target photo was removed')
            index,row=found
            if row.get('trashed') or row['path']!=target.path or batch.versions.version(row).revision!=target.revision:
                raise ValueError('Target photo changed after review')
            asset=json.loads(target.before_json)['asset_sha256']
            if SOURCE.source_digest(row['path'])!=asset:raise ValueError('Target source bytes changed after review')
            payload=json.loads(target.people_json)
            T.verify(payload,graph,graph,source_document=source_document,target_document=document(engine,row))
            # All frozen payloads are verified against the same original graph;
            # merge sparse leaves only, without replaying strength or masks.
            for ref in payload['target_refs']:
                for leaf in payload['parameters']:
                    candidate=S.set_override(candidate,'face',ref['face_instance_id'],leaf['operation_id'],leaf['parameter_path'],leaf['value'])
            assets.add(asset)
        except Exception as error:blocked=str(error)[:2000]
        resolved.append({'index':None if found is None else found[0],'path':target.path,'document_id':target.document_id,
            'blocked':blocked,'expected_revision':str(target.revision),
            'current_revision':None if found is None else str(batch.versions.version(found[1]).revision),
            'target_refs':[] if payload is None else payload['target_refs']})
    if plan.policy=='recheck' and any(x['blocked'] for x in resolved):raise ValueError('A target changed; no people parameters were applied')
    if not assets:raise ValueError('No confirmed target remains eligible')
    engine._people_prepare_graph(candidate,assets|{params['source_asset']})
    # Expensive original-source preparation cannot authorize a newer graph.
    if engine._people_owner().snapshot()!=graph:raise ValueError('People graph changed during final preparation')
    if document(engine,source[1])!=source_document or SOURCE.source_digest(source[1]['path'])!=params['source_asset']:
        raise ValueError('People source changed during final preparation')
    for result in resolved:
        if result['blocked']:continue
        found=batch.versions.find(batch.documents.rows(),result['document_id'])
        if found is None or found[1]['path']!=result['path'] or str(batch.versions.version(found[1]).revision)!=result['expected_revision'] or SOURCE.source_digest(found[1]['path'])!=result['target_refs'][0]['asset_sha256']:
            raise ValueError('People target changed during final preparation; no graph was published')
    controller.store.claim(plan)
    try:
        from .people_batch_ledger import commit as publish
        result=publish(batch,engine,graph,candidate,request_id=p.get('request_id'),prepare=False)
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
    return preflight(engine,controller,p) if plan is None else commit(engine,controller,p,plan)
