"""All-or-none scoped group undo/redo, preserving unrelated subsequent edits."""
from . import scope as SC, optics_auto_scope as OA, reference_color_scope as RC
from . import reference_color_state as RS, reference_color_runtime as RR
from .source_relocation_history import matches as source_path_matches
from . import white_balance_recipe as WB, id_background_scope as ID_BACKGROUND
from . import creative_derived_source as SOURCE, creative_derived_transfer as TRANSFER
from .body_scalar_transfer_review import select as body_family


def restore_group(owner,request):
    bid=str(request.get('batch_id') or '');batch=owner.ledger.get(bid)
    redo=request.get('action')=='redo'
    if batch is None or bool(batch['undone'])!=redo:raise SC.ScopeError('批次不存在，或不在可撤销/重做状态')
    ops=batch['ops'];family=body_family(ops)
    identity=None if family is None else getattr(owner.editor,family.port_name+'_history_identity')
    owner.documents.remember_current();planned=[];conflicts=[];proofs={};scalar_identities={}
    for rec in batch['targets'].values():
        found=owner.versions.find(owner.documents.rows(),rec['document_id'])
        if found is None:conflicts.append({'path':rec['path'],'reason':'目标已移除'});continue
        index,row=found;current=row['state']
        try:
            expected=OA.before_params(rec['before'],ops) if redo else rec['applied']
            if not source_path_matches(row, rec['path']) or OA.before_params(current,ops)!=expected:
                conflicts.append({'path':rec['path'],'reason':'作用域已另行编辑，不覆盖后续修改'});continue
            previous=rec['after'] if redo else rec['before']
            from .batch_sync import verify_history_source
            verify_history_source(row,rec,ops,previous)
            restored=SC.restore_modules(current,previous,ops)
            if rec.get('source_proof') is not None:
                TRANSFER.require_restoration(current,previous,restored,ops,rec['source_proof'])
                SOURCE.verify_row({**row,'state':restored},rec['source_proof'])
            if SC.SPILL_REMOVAL.OP in ops:SC.SPILL_REMOVAL.validate_target(restored,row['path'],(row['src_h'],row['src_w']))
            if SC.ORIGINAL_SHADOW.OP in ops:SC.ORIGINAL_SHADOW.validate_target(restored,row['path'],(row['src_h'],row['src_w']))
            if family is not None:
                family.scope.validate_target(restored,row['path'],(row['src_h'],row['src_w']))
                if identity is None:
                    raise ValueError('Body-scalar history requires current target body and face review verification')
                version=owner.versions.version(row)
                scalar_identities[index]={
                    'row':row,'path':row['path'],'document_id':version.document_id,'revision':version.revision,
                    'body_keys':(family.scope.undo_key(current),family.scope.undo_key(restored)),
                    'before':identity(row,current,version.document_id,str(version.revision)),
                    'after':identity(row,restored,version.document_id,str(version.revision))}
                reviewed=rec[family.private_key]
                if (reviewed['before_people_sha256']!=reviewed['candidate_people_sha256']
                        or any(scalar_identities[index][side]['people_sha256']!=reviewed['candidate_people_sha256']
                               for side in ('before','after'))):
                    raise ValueError('Body-scalar history people context changed after its full-target safety review')
            if SC.FRINGE_REPAIR.OP in ops:SC.FRINGE_REPAIR.validate_target(restored,row['path'],(row['src_h'],row['src_w']))
            if RC.OP in ops:
                value=RS.check(restored.get(RS.KEY));RR.verify_export({'reference_color':value},row['path'],(row['src_h'],row['src_w']))
            if OA.OP in ops:OA.validate_restoration(restored,row)
            if ID_BACKGROUND.OP in ops:ID_BACKGROUND.validate_target(restored,row["path"],(row["src_h"],row["src_w"]))
            WB.prepare_state(restored);owner.versions.check_advance(row)
            if not isinstance(row.get('undo'),list) or not isinstance(row.get('redo'),list):raise ValueError('历史不可用')
            planned.append((index,row,current,restored))
            proofs[index]=rec.get('source_proof')
        except Exception as error:conflicts.append({'path':rec['path'],'reason':str(error)[:500]})
    if conflicts:raise SC.ScopeError('整组未修改：'+str(conflicts))
    def verify_scalar_replay(index,state,side,revision):
        if index not in scalar_identities:return
        frozen=scalar_identities[index];row=frozen['row']
        if (index>=len(owner.documents.rows()) or owner.documents.rows()[index] is not row
                or row['path']!=frozen['path'] or owner.versions.version(row).document_id!=frozen['document_id']
                or owner.versions.version(row).revision!=revision):
            raise ValueError('Body-scalar history target changed during replay')
        if proofs[index] is None:raise ValueError('Body-scalar history lacks its target source proof')
        SOURCE.verify_row({**row,'state':state},proofs[index])
        actual=identity(row,state,frozen['document_id'],str(revision))
        expected={**frozen[side],'revision':str(revision)}
        if actual!=expected:
            raise ValueError('Body-scalar history source, full state, body support or current face graph changed')
    for index,row,current,restored in planned:
        if proofs[index] is not None:SOURCE.verify_row(row,proofs[index])
        if index in scalar_identities:
            verify_scalar_replay(index,current,'before',scalar_identities[index]['revision'])
            verify_scalar_replay(index,restored,'after',scalar_identities[index]['revision'])
    live=owner.documents.current_index();frame=None
    active=next((item for item in planned if item[0]==live),None)
    if active:
        _,row,before,after=active
        shadow_history=SC.ORIGINAL_SHADOW.OP in ops
        if shadow_history:
            from .optics_candidate_identity import fingerprint
            frozen_identity=(owner.documents.current_index(),row['path'],owner.versions.version(row).document_id)
            frozen_before=fingerprint(before);frozen_after=fingerprint(after)
            if owner.editor.history_identity is None:raise ValueError('Original-shadow history identity port unavailable')
            reviewed_version=owner.versions.version(row)
            identities={frozen_before:owner.editor.history_identity(row,before,reviewed_version.document_id,str(reviewed_version.revision)),
                        frozen_after:owner.editor.history_identity(row,after,reviewed_version.document_id,str(reviewed_version.revision))}
        owner.versions.advance(row)
        frozen_revision=owner.versions.version(row).revision
        def require_scalar_target():
            if family is not None:
                frozen=scalar_identities[live];current_rows=owner.documents.rows()
                if (owner.documents.current_index()!=live or live>=len(current_rows)
                        or current_rows[live] is not frozen['row'] or row is not frozen['row']
                        or row['path']!=frozen['path']
                        or owner.versions.version(row).document_id!=frozen['document_id']
                        or owner.versions.version(row).revision!=frozen_revision):
                    raise ValueError('Body-scalar history replay target or revision changed; no write or rollback is allowed')
                if proofs[live] is None:raise ValueError('Body-scalar history replay lacks its frozen source proof')
                SOURCE.verify_row({**row,'state':owner.editor.capture()},proofs[live])
        scalar_write_started=False
        def replay_target(state,*,rollback=False,**kwargs):
            nonlocal scalar_write_started
            require_scalar_target()
            if family is not None:
                from .optics_candidate_identity import fingerprint
                if rollback and not scalar_write_started:
                    raise ValueError('Body-scalar history forward write never started; no rollback is allowed')
                frozen=scalar_identities[live];actual=owner.editor.capture();actual_hash=fingerprint(actual)
                wanted={**frozen['before'],'revision':str(frozen_revision)}
                if rollback:
                    if family.scope.undo_key(actual) not in frozen['body_keys']:
                        raise ValueError('Body-scalar history body dependencies changed before rollback')
                    wanted['candidate_sha256']=actual_hash
                current_identity=identity(row,actual,frozen['document_id'],str(frozen_revision))
                if current_identity!=wanted or current_identity['candidate_sha256']!=actual_hash:
                    raise ValueError('Body-scalar history full state, body review or people changed before replay')
                require_scalar_target()
                latest=owner.editor.capture()
                if (fingerprint(latest)!=actual_hash
                        or identity(row,latest,frozen['document_id'],str(frozen_revision))!=current_identity):
                    raise ValueError('Body-scalar history state or people changed during pre-write verification')
                require_scalar_target()
                if fingerprint(owner.editor.capture())!=actual_hash:
                    raise ValueError('Body-scalar history pre-write callback changed the full target state')
                kwargs['strict_local']=True
                if not rollback:scalar_write_started=True
            result=owner.editor.replay(state,**kwargs)
            require_scalar_target()
            return result
        def verify_shadow_replay(expected_state,expected_fingerprint):
            if not shadow_history:return
            if (owner.documents.current_index(),row['path'],owner.versions.version(row).document_id)!=frozen_identity or owner.documents.rows()[frozen_identity[0]] is not row:
                raise ValueError('Original-shadow history target changed during replay')
            if owner.versions.version(row).revision!=frozen_revision:
                raise ValueError('Original-shadow history revision changed during replay')
            actual=owner.editor.capture()
            if fingerprint(actual)!=expected_fingerprint or SC.ORIGINAL_SHADOW.undo_key(actual)!=SC.ORIGINAL_SHADOW.undo_key(expected_state):
                raise ValueError('Original-shadow history did not retain the frozen full state')
            if proofs[frozen_identity[0]] is None:raise ValueError('Original-shadow history lacks source proof')
            SOURCE.verify_row({**row,'state':actual},proofs[frozen_identity[0]])
            expected={**identities[expected_fingerprint],'revision':str(frozen_revision)}
            if owner.editor.history_identity(row,actual,frozen_identity[2],str(frozen_revision))!=expected:
                raise ValueError('Original-shadow history source, full state or people graph changed')
        try:
            frame=replay_target(after,mode='batch',replayed_for=f'batch_group:{bid}',strict_local=True)
            if shadow_history:verify_shadow_replay(after,frozen_after)
            if SC.SPILL_REMOVAL.OP in ops and SC.SPILL_REMOVAL.undo_key(owner.editor.capture()) != SC.SPILL_REMOVAL.undo_key(after):
                raise ValueError('祛反光目标依赖在组历史重放期间变化')
            if SC.ORIGINAL_SHADOW.OP in ops and SC.ORIGINAL_SHADOW.undo_key(owner.editor.capture()) != SC.ORIGINAL_SHADOW.undo_key(after):
                raise ValueError('原图阴影目标依赖在组历史重放期间变化')
            if family is not None:
                if owner.documents.current_index()!=live:
                    raise ValueError('Body-scalar active history target changed during replay')
                if family.scope.undo_key(owner.editor.capture())!=family.scope.undo_key(after):
                    raise ValueError('Body-scalar target body dependencies changed during history replay')
                verify_scalar_replay(live,owner.editor.capture(),'after',frozen_revision)
            for index,target,_,candidate in planned:
                if proofs[index] is not None:
                    SOURCE.verify_row({**target,'state':owner.editor.capture() if index==live else target['state']},proofs[index])
                if index in scalar_identities and index!=live:
                    verify_scalar_replay(index,target['state'],'before',scalar_identities[index]['revision'])
                    verify_scalar_replay(index,candidate,'after',scalar_identities[index]['revision'])
        except Exception:
            try:
                replay_target(before,rollback=True,mode='batch',replayed_for=f'batch_group_rollback:{bid}',**({'strict_local':True} if shadow_history or family is not None else {}))
                if shadow_history:verify_shadow_replay(before,frozen_before)
                if family is not None:
                    if owner.documents.current_index()!=live:
                        raise ValueError('Body-scalar active history target changed during rollback')
                    verify_scalar_replay(live,owner.editor.capture(),'before',frozen_revision)
            except Exception:owner.editor.invalidate()
            raise
    for index,row,before,after in planned:
        if index in scalar_identities:
            if index==live:
                require_scalar_target()
                verify_scalar_replay(index,owner.editor.capture(),'after',frozen_revision)
            else:
                verify_scalar_replay(index,row['state'],'before',scalar_identities[index]['revision'])
                verify_scalar_replay(index,after,'after',scalar_identities[index]['revision'])
        if index!=live:
            owner.versions.advance(row);row['undo'].append(before)
            if len(row['undo'])>owner.history_limit:del row['undo'][0]
            row['redo'].clear()
        row['state']=after
    owner.editor.mark_dirty();batch['undone']=not redo
    body={'event':'batch_redone' if redo else 'batch_undone','batch_id':bid,'module_scope':ops,
          'restored':[r[0] for r in planned],'conflicts':[],'doc_state':owner.editor.status()}
    owner.last_result={'kind':'redo' if redo else 'undo','batch_id':bid,'restored':body['restored'],'conflicts':[]}
    owner.emit(body)
    if frame is not None:owner.emit(frame)
    return body
