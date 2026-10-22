"""Persist existing document stacks and people entries of the existing batch ledger."""
from copy import deepcopy
from . import project as P,local_mask_state as SOURCE,people_state as S


def asset_for(row):
    return (row.get('fingerprint') or {}).get('sha256') or SOURCE.source_digest(row['path'])


def save(engine,project):
    # Keep unavailable-photo histories from the loaded project unchanged. A
    # missing original is not permission to discard its unresolved edit history.
    histories=deepcopy((engine._project or {}).get('people_document_history',{}));dropped=[]
    for row in engine._docs:
        stacks={name:row.get(name,[]) for name in ('undo','redo')}
        if not any(snap.get('_people_history') is not None for stack in stacks.values() for snap in stack):continue
        refs={snap['_people_history']['asset_sha256'] for stack in stacks.values() for snap in stack if snap.get('_people_history') is not None}
        if len(refs)!=1:raise ValueError('Document stack mixes source assets')
        asset=next(iter(refs))
        histories[asset]={'path':row['path'],'stacks':P.encode(stacks,project['assets'],dropped,'people_history.'+asset)}
    if dropped:raise ValueError('People history cannot be saved lossily: '+str(dropped))
    # The enclosing project rebuilds its asset table. Carry only assets still
    # referenced by preserved encoded histories, not an unbounded old table.
    def retain_assets(value):
        if isinstance(value,dict):
            key=value.get('__asset__')
            if key is not None and key not in project['assets']:
                old=(engine._project or {}).get('assets',{}).get(key)
                if old is None:raise ValueError('Retained history asset is missing')
                project['assets'][key]=deepcopy(old)
            for child in value.values():retain_assets(child)
        elif isinstance(value,list):
            for child in value:retain_assets(child)
    retain_assets(histories)
    project['people_document_history']=histories
    batch=getattr(engine,'_batch_sync',None)
    project['people_batch_history']={key:deepcopy(value) for key,value in (batch.ledger.items() if batch else []) if 'people_changes' in value}


def prepare(project,rows,limit):
    """Decode/validate BEFORE replacing any live documents or canonical graph."""
    from .repair_record import RepairOp
    from .vram import LightOp
    histories=project.get('people_document_history',{});saved=project.get('people_batch_history',{})
    if type(histories) is not dict or len(histories)>10000 or type(saved) is not dict or len(saved)>10000:
        raise ValueError('Invalid saved people history budget')
    staged={}
    for asset,record in histories.items():
        S.digest(asset)
        if type(record) is not dict or set(record)!={'path','stacks'} or type(record['path']) is not str:
            raise ValueError('Invalid saved people history record')
        dropped=[];stacks=P.decode(record['stacks'],project['assets'],dropped,'people_history.'+asset,dc_types={'RepairOp':RepairOp,'LightOp':LightOp})
        if dropped or type(stacks) is not dict or set(stacks)!={'undo','redo'}:raise ValueError('Saved people history cannot be restored lossily')
        for stack in stacks.values():
            if type(stack) is not list or len(stack)>limit:raise ValueError('Saved people history exceeds its retained budget')
            for snapshot in stack:
                if type(snapshot) is not dict:raise ValueError('Invalid document history snapshot')
                ref=snapshot.get('_people_history')
                if ref is not None:
                    required={'asset_sha256','faces','overrides','unresolved_legacy','analysis_run','association_revision','asset_fence','association_fence'}
                    if type(ref) is not dict or set(ref)!=required or ref['asset_sha256']!=asset:
                        raise ValueError('Saved document history names another source or incomplete scope')
                    for field in ('association_revision','association_fence','asset_fence'):S.revision(ref[field])
        matches=[i for i,row in enumerate(rows) if row['path']==record['path']]
        if len(matches)>1:raise ValueError('Saved document history is ambiguous')
        if matches:
            row=rows[matches[0]]
            try:actual=asset_for(row)
            except OSError:continue # Retain unavailable source history in project data.
            if actual==asset:staged[matches[0]]=stacks
    entries={}
    for key,value in saved.items():
        if type(value) is not dict or not {'ops','targets','at_ns','undone','people_changes'}<=set(value):
            raise ValueError('Malformed people batch history')
        if value['ops']!=['lnx.people_graph.v1'] or type(value['targets']) is not dict or type(value['undone']) is not bool or type(value['people_changes']) is not list:
            raise ValueError('Invalid people batch history contract')
        entry=deepcopy(value)
        for rec in entry['targets'].values():
            if type(rec) is not dict or not {'path','document_id','revision','asset_sha256'}<=set(rec):raise ValueError('Invalid saved batch target')
            S.digest(rec['asset_sha256']);S.revision(rec['revision'])
        entries[str(key)]=entry
    return staged,entries


def restore(engine,project,prepared=None):
    staged,entries=prepare(project,engine._docs,engine.HISTORY_MAX) if prepared is None else prepared
    for index,stacks in staged.items():
        for name,stack in stacks.items():engine._docs[index][name]=stack
    if entries:
        owner=engine._batch_controller()
        for key,entry in entries.items():
            for rec in entry['targets'].values():
                matches=[row for row in engine._docs if row['path']==rec['path']]
                # Keep missing/replaced source entries, but never give them a new
                # runtime identity; protected restore will explicitly refuse.
                if len(matches)==1:
                    try:matches=matches if asset_for(matches[0])==rec['asset_sha256'] else []
                    except OSError:matches=[]
                if len(matches)==1:rec['document_id']=owner.versions.version(matches[0]).document_id
            owner.ledger['people-restored-'+key]=entry
