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


def commit_scoped(owner,engine,plans,*,request_id,prepare=True,prepared_targets=None,alias_history=None,eye_bag_history=None,eye_bag_cohort_history=None,eye_bag_alias_history=None,eye_bag_preset_alias_history=None,preset_alias_verify=None,eye_bag_recovery_alias_history=None,recovery_alias_assets=None,recovery_alias_verify=None):
    composite=eye_bag_preset_alias_history is not None
    recovery=eye_bag_recovery_alias_history is not None
    if composite and recovery:raise ValueError('Mixed preset and recovery alias authority cannot be combined')
    plans={identity:plan for identity,plan in plans.items() if composite or between(plan['before'],plan['candidate'])}
    if not plans:return None
    if not composite and not recovery:owner.documents.remember_current()
    # Transfer callers retain the proof actually rendered. Re-freezing here
    # could authorize changed source bytes after expensive target preparation.
    targets=_targets(owner,engine,plans) if prepared_targets is None else deepcopy(prepared_targets)
    if not targets:raise ValueError('No retained portrait document can receive this batch')
    if prepare and not composite and not recovery:prepare_scoped(engine,plans,targets)
    if not composite and not recovery:_verify(owner,engine,plans,targets)
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
    if eye_bag_history is not None:
        from .eye_bag_batch_history import KEY as EYE_KEY, check as check_eye_history
        entry[EYE_KEY]=deepcopy(eye_bag_history)
        check_eye_history(entry)
    if eye_bag_cohort_history is not None:
        from .eye_bag_cohort_history import KEY as COHORT_KEY, check as check_cohort_history
        entry[COHORT_KEY]=deepcopy(eye_bag_cohort_history)
        check_cohort_history(entry)
    if eye_bag_alias_history is not None:
        from .eye_bag_alias_history import KEY as EYE_ALIAS_KEY, check as check_eye_alias_history
        entry[EYE_ALIAS_KEY]=deepcopy(eye_bag_alias_history)
        check_eye_alias_history(entry)
    if composite:
        from . import eye_bag_preset_alias_history as MIXED, eye_bag_preset_alias_transaction as TRANSACTION
        entry[MIXED.KEY]=deepcopy(eye_bag_preset_alias_history);MIXED.check(entry)
        if prepare:TRANSACTION.prepare(engine,plans,targets,entry,redo=True)
    if recovery:
        from . import eye_bag_recovery_alias_history as RECOVERY, eye_bag_recovery_alias_transaction as RECOVERY_TRANSACTION
        entry[RECOVERY.KEY]=deepcopy(eye_bag_recovery_alias_history);RECOVERY.check(entry)
        if prepare:RECOVERY_TRANSACTION.prepare(engine,plans,targets,entry,redo=True,assets=recovery_alias_assets)
    result={'kind':'commit','batch_id':bid,'applied':[int(k) for k in targets],'skipped':[]}
    frame=(TRANSACTION.publish(owner,engine,plans,targets,entry,redo=True,verify_before=preset_alias_verify)
           if composite else RECOVERY_TRANSACTION.publish(owner,engine,plans,targets,entry,redo=True,
               assets=recovery_alias_assets,verify_before=recovery_alias_verify) if recovery else _publish(owner,engine,plans,targets))
    owner.ledger[bid]=entry;owner.last_result=result
    engine._people_shared_mutation=True
    try:owner.editor.mark_dirty()
    except Exception as error:
        if composite or recovery:error.side_effects_started=True;error.batch_id=bid
        if recovery:error.rolled_back=False;error.requires_reload=True
        raise
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
    from .eye_bag_batch_history import check as check_eye_history, verify_restore as verify_eye_restore
    eye_history=check_eye_history(batch)
    from .eye_bag_cohort_history import check as check_cohort_history, verify_restore as verify_cohort_restore
    cohort_history=check_cohort_history(batch)
    from .eye_bag_alias_history import check as check_eye_alias_history, verify_restore as verify_eye_alias_restore
    eye_alias_history=check_eye_alias_history(batch)
    from . import eye_bag_preset_alias_history as MIXED, eye_bag_preset_alias_transaction as TRANSACTION
    mixed_history=MIXED.check(batch)
    from . import eye_bag_recovery_alias_history as RECOVERY, eye_bag_recovery_alias_transaction as RECOVERY_TRANSACTION
    recovery_history=RECOVERY.check(batch)
    owner=engine._batch_controller();plans={};reviewed={}
    if eye_history is not None or cohort_history is not None or eye_alias_history is not None or mixed_history is not None or recovery_history is not None:
        # The scoped restore route bypasses the legacy undo() wrapper. Capture
        # the current document so unsaved repair/crop edits cannot hide behind
        # a parked row's older dependency digest.
        owner.documents.remember_current()
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
    targets=(MIXED.targets(engine,mixed_history,plans['project']['before']) if mixed_history is not None else
             RECOVERY.targets(engine,recovery_history,plans['project']['before']) if recovery_history is not None else _targets(owner,engine,plans))
    if recovery_history is not None:
        assets=RECOVERY_TRANSACTION.bank(engine)
        RECOVERY_TRANSACTION.prepare(engine,plans,targets,batch,redo=redo,assets=assets)
        return RECOVERY_TRANSACTION.publish(owner,engine,plans,targets,batch,redo=redo,assets=assets)
    if mixed_history is not None:
        TRANSACTION.prepare(engine,plans,targets,batch,redo=redo)
        return TRANSACTION.publish(owner,engine,plans,targets,batch,redo=redo)
    if alias_history is not None:verify_alias_restore(engine,batch,plans,targets)
    if eye_history is not None:verify_eye_restore(engine,batch,plans,targets)
    if cohort_history is not None:verify_cohort_restore(engine,batch,plans,targets,redo=redo)
    if eye_alias_history is not None:verify_eye_alias_restore(engine,batch,plans,targets,redo=redo)
    # Recompute runtime paths/fences only after exact historical document/source
    # verification; a duplicate path never grants a replacement identity.
    prepare_scoped(engine,plans,targets)
    if alias_history is not None:
        # Preparation must not expand an explicitly reviewed alias cohort.
        # Legacy scoped batches retain their established restoration behavior.
        verify_alias_restore(engine,batch,plans,_targets(owner,engine,plans))
    if eye_history is not None:verify_eye_restore(engine,batch,plans,_targets(owner,engine,plans))
    if cohort_history is not None:verify_cohort_restore(engine,batch,plans,_targets(owner,engine,plans),redo=redo)
    if eye_alias_history is not None:verify_eye_alias_restore(engine,batch,plans,_targets(owner,engine,plans),redo=redo)
    return _publish(owner,engine,plans,targets)


def restore(owner,request):
    batch=owner.ledger[str(request.get('batch_id') or '')];redo=request.get('action')=='redo'
    from .eye_bag_preset_alias_history import KEY as MIXED_KEY, status_summary as mixed_summary
    marker=mixed_summary(batch);published=False
    from .eye_bag_recovery_alias_history import KEY as RECOVERY_KEY, status_summary as recovery_summary
    recovery_marker=recovery_summary(batch)
    try:
        if marker is not None:
            from .eye_bag_preset_alias_transaction import require_history_request
            require_history_request(owner,request,batch)
        if recovery_marker is not None:
            from .eye_bag_recovery_alias_transaction import require_history_request as require_recovery_request
            require_recovery_request(owner,request,batch)
        if bool(batch['undone'])!=redo:raise ValueError('People group is not in the requested undo/redo state')
        if owner.editor.people_restore is None:raise ValueError('People group restore adapter is unavailable')
        frame=owner.editor.people_restore(batch,redo);published=True
        batch['undone']=not redo;owner.editor.mark_dirty()
        body={'event':'batch_redone' if redo else 'batch_undone','batch_id':request['batch_id'],
              'module_scope':batch['ops'],'restored':[int(k) for k in batch['targets']], 'conflicts':[], 'doc_state':owner.editor.status()}
        owner.last_result={'kind':'redo' if redo else 'undo','batch_id':request['batch_id'],'restored':body['restored'],'conflicts':[]}
        if marker is not None:body[MIXED_KEY]=marker
        if recovery_marker is not None:body[RECOVERY_KEY]=recovery_marker
        owner.emit(body)
        if frame is not None:owner.emit(frame)
        return body
    except Exception as error:
        if marker is not None:
            error.eye_bag_preset_alias_history_no_write=not getattr(error,'side_effects_started',published)
        if recovery_marker is not None:
            started=bool(getattr(error,'side_effects_started',published))
            error.eye_bag_recovery_alias_history_no_write=not started
            error.eye_bag_recovery_alias_history_rolled_back=started and bool(getattr(error,'rolled_back',False))
        raise
