"""Persist existing document stacks and people entries of the existing batch ledger."""
from copy import deepcopy
from . import project as P,local_mask_state as SOURCE,people_state as S


def asset_for(row):
    return (row.get('fingerprint') or {}).get('sha256') or SOURCE.source_digest(row['path'])


def history_key(row):
    identity=row.get('document_id')
    if not identity:
        from .virtual_copy_host import initialize
        initialize(row);identity=row['document_id']
    return 'document:'+identity


def save(engine,project):
    # Keep unavailable-photo histories from the loaded project unchanged. A
    # missing original is not permission to discard its unresolved edit history.
    from .body_pose_document_history import assets as body_assets
    histories=deepcopy((engine._project or {}).get('people_document_history',{}));dropped=[]
    for row in engine._docs:
        key=history_key(row)
        stacks={name:row.get(name,[]) for name in ('undo','redo')}
        retained=any(snap.get('_people_history') is not None or body_assets(snap) for stack in stacks.values() for snap in stack)
        cleared=row.get('_history_owned') and not any(stacks.values())
        # Migrate only after this original has a replacement stack or an
        # explicitly cleared history. Unavailable originals retain old data.
        if retained or cleared:
            for old_key,old in list(histories.items()):
                if not row.get('copy_number',0) and 'document_id' not in old and old.get('path')==row['path']:
                    histories.pop(old_key,None)
        if row.get('_history_owned') and not any(stacks.values()):
            # An explicitly cleared current document is not an unavailable-photo
            # history to resurrect from the last project save.
            histories.pop(key,None)
        if not retained:continue
        # The physical original still anchors relocation/admission. Each
        # creative history frame proves its own immutable content independently.
        asset=asset_for(row)
        for stack in stacks.values():
            for snap in stack:
                from .creative_derived_source import binding
                expected=binding(snap)['sha256'] if snap.get('_creative_base') is not None else asset
                ref=snap.get('_people_history')
                if ref is not None and ref['asset_sha256']!=expected:
                    raise ValueError('Portrait history does not own its frame source')
                if body_assets(snap)-{expected}:
                    raise ValueError('Body history does not own its frame source')
        histories[key]={'document_id':row['document_id'],'asset_sha256':asset,'path':row['path'],
                        'stacks':P.encode(stacks,project['assets'],dropped,'people_history.'+key)}
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
    batches={key:deepcopy(value) for key,value in (batch.ledger.items() if batch else []) if 'people_changes' in value}
    from .face_style_alias_history import check as check_alias_history
    from .eye_bag_batch_history import check as check_eye_history
    from .face_decoration_batch_history import check as check_decoration_history
    from .face_decoration_alias_history import check as check_da
    from .face_decoration_cohort_history import check as check_dc
    from .eye_bag_cohort_history import check as check_cohort_history
    from .eye_bag_alias_history import check as check_eye_alias_history
    from .eye_bag_recovery_alias_history import validate_project_assets as validate_recovery_history
    for entry in batches.values():
        validate_recovery_history(entry,project)
        check_da(entry);check_dc(entry);check_decoration_history(entry);check_alias_history(entry);check_eye_history(entry);check_cohort_history(entry);check_eye_alias_history(entry)
    from .eye_bag_preset_alias_history import encode_states
    project['people_batch_history']={key:encode_states(entry,project['assets']) for key,entry in batches.items()}


def prepare(project,rows,limit):
    """Decode/validate BEFORE replacing any live documents or canonical graph."""
    from .repair_record import RepairOp
    from .vram import LightOp
    histories=project.get('people_document_history',{});saved=project.get('people_batch_history',{})
    if type(histories) is not dict or len(histories)>10000 or type(saved) is not dict or len(saved)>10000:
        raise ValueError('Invalid saved people history budget')
    staged={}
    for key,record in histories.items():
        if type(record) is not dict or type(record.get('path')) is not str:
            raise ValueError('Invalid saved people history record')
        legacy=set(record)=={'path','stacks'}
        if legacy:asset=S.digest(key)
        else:
            if set(record)!={'document_id','asset_sha256','path','stacks'}:
                raise ValueError('Invalid document-scoped portrait history')
            S.token(record['document_id']);asset=S.digest(record['asset_sha256'])
            if key!='document:'+record['document_id']:raise ValueError('Portrait history document identity mismatch')
        dropped=[];stacks=P.decode(record['stacks'],project['assets'],dropped,'people_history.'+key,dc_types={'RepairOp':RepairOp,'LightOp':LightOp})
        if dropped or type(stacks) is not dict or set(stacks)!={'undo','redo'}:raise ValueError('Saved people history cannot be restored lossily')
        for stack in stacks.values():
            if type(stack) is not list or len(stack)>limit:raise ValueError('Saved people history exceeds its retained budget')
            for snapshot in stack:
                if type(snapshot) is not dict:raise ValueError('Invalid document history snapshot')
                from .body_pose_project import validate_records as validate_body
                validate_body(snapshot)
                from .body_pose_document_history import assets as body_assets
                from .creative_derived_source import binding
                expected=binding(snapshot)['sha256'] if snapshot.get('_creative_base') is not None else asset
                if body_assets(snapshot)-{expected}:raise ValueError('Saved body history names another source')
                ref=snapshot.get('_people_history')
                if ref is not None:
                    required={'asset_sha256','faces','overrides','unresolved_legacy','analysis_run','association_revision','asset_fence','association_fence'}
                    if type(ref) is not dict or set(ref) not in (required,required|{'source_context_sha256'}) or ref['asset_sha256']!=expected:
                        raise ValueError('Saved document history names another source or incomplete scope')
                    for field in ('association_revision','association_fence','asset_fence'):S.revision(ref[field])
                    if 'source_context_sha256' in ref:S.digest(ref['source_context_sha256'])
        if legacy:
            matches=[i for i,row in enumerate(rows) if not row.get('copy_number',0) and row['path']==record['path']]
        else:
            matches=[i for i,row in enumerate(rows) if row.get('document_id')==record['document_id']]
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
        from .eye_bag_preset_alias_history import decode_states
        entry=decode_states(deepcopy(value),project['assets'])
        scopes=entry.get('people_scoped_changes')
        if scopes is not None:
            if type(scopes) is not list or not scopes or len(scopes)>10000 or entry['people_changes']:
                raise ValueError('Invalid scoped portrait batch history')
            seen=set()
            for scope in scopes:
                if type(scope) is not dict or set(scope)!={'scope','document_id','changes'} or type(scope['changes']) is not list:
                    raise ValueError('Invalid saved portrait graph scope')
                S.token(scope['scope']);S.token(scope['document_id'])
                if scope['scope'] in seen:raise ValueError('Duplicate saved portrait graph scope')
                seen.add(scope['scope'])
                if scope['scope']!='project' and scope['scope']!=scope['document_id']:
                    raise ValueError('Copy history belongs to another document scope')
        for rec in entry['targets'].values():
            if type(rec) is not dict or not {'path','document_id','revision','asset_sha256'}<=set(rec):raise ValueError('Invalid saved batch target')
            S.digest(rec['asset_sha256']);S.revision(rec['revision'])
            if 'source_proof' in rec:
                from .creative_derived_source import check_row_proof
                proof=check_row_proof(rec['source_proof'])
                if proof['asset_sha256']!=rec['asset_sha256']:
                    raise ValueError('Saved portrait target has conflicting source evidence')
            if scopes is not None and rec.get('people_scope') not in seen:
                raise ValueError('Saved portrait target has no graph scope')
            from .people_batch_ledger import reviewed_refs
            reviewed_refs(rec)
        from .face_style_alias_history import check as check_alias_history
        check_alias_history(entry)
        from .eye_bag_batch_history import check as check_eye_history
        check_eye_history(entry)
        from .face_decoration_batch_history import check as check_decoration_history
        check_decoration_history(entry)
        from .face_decoration_alias_history import check as check_da
        from .face_decoration_cohort_history import check as check_dc
        check_da(entry);check_dc(entry)
        from .eye_bag_cohort_history import check as check_cohort_history
        check_cohort_history(entry)
        from .eye_bag_alias_history import check as check_eye_alias_history
        check_eye_alias_history(entry)
        from .eye_bag_recovery_alias_history import validate_project_assets as validate_recovery_history
        validate_recovery_history(entry,project)
        entries[str(key)]=entry
    return staged,entries


def restore(engine,project,prepared=None):
    staged,entries=prepare(project,engine._docs,engine.HISTORY_MAX) if prepared is None else prepared
    for index,stacks in staged.items():
        for name,stack in stacks.items():engine._docs[index][name]=stack
        engine._docs[index]['_history_owned']=True
    if entries:
        owner=engine._batch_controller()
        for key,entry in entries.items():
            for rec in entry['targets'].values():
                matches=[row for row in engine._docs if row.get('document_id')==rec['document_id']]
                if not matches and 'people_scoped_changes' not in entry:
                    matches=[row for row in engine._docs if not row.get('copy_number',0) and row['path']==rec['path']]
                # Keep missing/replaced source entries, but never give them a new
                # runtime identity; protected restore will explicitly refuse.
                if len(matches)==1:
                    try:
                        if 'people_scoped_changes' in entry:
                            from .creative_derived_source import verify_row_target
                            verify_row_target(matches[0],rec)
                        else:
                            from .creative_derived_source import record
                            if record(matches[0].get('state') or {}) is not None or asset_for(matches[0])!=rec['asset_sha256']:
                                matches=[]
                    except (OSError,ValueError):matches=[]
                if len(matches)==1:rec['document_id']=owner.versions.version(matches[0]).document_id
            owner.ledger['people-restored-'+key]=entry
