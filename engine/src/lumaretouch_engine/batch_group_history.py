"""All-or-none scoped group undo/redo, preserving unrelated subsequent edits."""
from . import scope as SC, optics_auto_scope as OA, reference_color_scope as RC
from . import reference_color_state as RS, reference_color_runtime as RR
from .source_relocation_history import matches as source_path_matches
from . import white_balance_recipe as WB, id_background_scope as ID_BACKGROUND
from . import creative_derived_source as SOURCE, creative_derived_transfer as TRANSFER


def restore_group(owner,request):
    bid=str(request.get('batch_id') or '');batch=owner.ledger.get(bid)
    redo=request.get('action')=='redo'
    if batch is None or bool(batch['undone'])!=redo:raise SC.ScopeError('批次不存在，或不在可撤销/重做状态')
    ops=batch['ops'];owner.documents.remember_current();planned=[];conflicts=[];proofs={};torso_identities={}
    for rec in batch['targets'].values():
        found=owner.versions.find(owner.documents.rows(),rec['document_id'])
        if found is None:conflicts.append({'path':rec['path'],'reason':'目标已移除'});continue
        index,row=found;current=row['state']
        expected=OA.before_params(rec['before'],ops) if redo else rec['applied']
        if not source_path_matches(row, rec['path']) or OA.before_params(current,ops)!=expected:
            conflicts.append({'path':rec['path'],'reason':'作用域已另行编辑，不覆盖后续修改'});continue
        try:
            previous=rec['after'] if redo else rec['before']
            from .batch_sync import verify_history_source
            verify_history_source(row,rec,ops,previous)
            restored=SC.restore_modules(current,previous,ops)
            if rec.get('source_proof') is not None:
                TRANSFER.require_restoration(current,previous,restored,ops,rec['source_proof'])
                SOURCE.verify_row({**row,'state':restored},rec['source_proof'])
            if SC.SPILL_REMOVAL.OP in ops:SC.SPILL_REMOVAL.validate_target(restored,row['path'],(row['src_h'],row['src_w']))
            if SC.ORIGINAL_SHADOW.OP in ops:SC.ORIGINAL_SHADOW.validate_target(restored,row['path'],(row['src_h'],row['src_w']))
            if SC.TORSO_LENGTH.OP in ops:
                SC.TORSO_LENGTH.validate_target(restored,row['path'],(row['src_h'],row['src_w']))
                if owner.editor.torso_history_identity is None:
                    raise ValueError('Torso-length history requires current target body and face review verification')
                version=owner.versions.version(row)
                torso_identities[index]={
                    'row':row,'path':row['path'],'document_id':version.document_id,'revision':version.revision,
                    'before':owner.editor.torso_history_identity(row,current,version.document_id,str(version.revision)),
                    'after':owner.editor.torso_history_identity(row,restored,version.document_id,str(version.revision))}
                reviewed=rec['torso_review']
                if (reviewed['before_people_sha256']!=reviewed['candidate_people_sha256']
                        or any(torso_identities[index][side]['people_sha256']!=reviewed['candidate_people_sha256']
                               for side in ('before','after'))):
                    raise ValueError('Torso-length history people context changed after its full-target safety review')
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
    def verify_torso_replay(index,state,side,revision):
        if index not in torso_identities:return
        frozen=torso_identities[index];row=frozen['row']
        if (index>=len(owner.documents.rows()) or owner.documents.rows()[index] is not row
                or row['path']!=frozen['path'] or owner.versions.version(row).document_id!=frozen['document_id']
                or owner.versions.version(row).revision!=revision):
            raise ValueError('Torso-length history target changed during replay')
        if proofs[index] is None:raise ValueError('Torso-length history lacks its target source proof')
        SOURCE.verify_row({**row,'state':state},proofs[index])
        actual=owner.editor.torso_history_identity(row,state,frozen['document_id'],str(revision))
        expected={**frozen[side],'revision':str(revision)}
        if actual!=expected:
            raise ValueError('Torso-length history source, full state, body support or current face graph changed')
    for index,row,current,restored in planned:
        if proofs[index] is not None:SOURCE.verify_row(row,proofs[index])
        if index in torso_identities:
            verify_torso_replay(index,current,'before',torso_identities[index]['revision'])
            verify_torso_replay(index,restored,'after',torso_identities[index]['revision'])
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
        def require_torso_target():
            if SC.TORSO_LENGTH.OP in ops:
                frozen=torso_identities[live];current_rows=owner.documents.rows()
                if (owner.documents.current_index()!=live or live>=len(current_rows)
                        or current_rows[live] is not frozen['row'] or row is not frozen['row']
                        or row['path']!=frozen['path']
                        or owner.versions.version(row).document_id!=frozen['document_id']
                        or owner.versions.version(row).revision!=frozen_revision):
                    raise ValueError('Torso-length history replay target or revision changed; no write or rollback is allowed')
                if proofs[live] is None:raise ValueError('Torso-length history replay lacks its frozen source proof')
                SOURCE.verify_row({**row,'state':owner.editor.capture()},proofs[live])
        def replay_target(state,**kwargs):
            require_torso_target()
            if SC.TORSO_LENGTH.OP in ops:kwargs['strict_local']=True
            result=owner.editor.replay(state,**kwargs)
            require_torso_target()
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
            if SC.TORSO_LENGTH.OP in ops:
                if owner.documents.current_index()!=live:
                    raise ValueError('Torso-length active history target changed during replay')
                if SC.TORSO_LENGTH.undo_key(owner.editor.capture())!=SC.TORSO_LENGTH.undo_key(after):
                    raise ValueError('Torso-length target body dependencies changed during history replay')
                verify_torso_replay(live,owner.editor.capture(),'after',frozen_revision)
            for index,target,_,candidate in planned:
                if proofs[index] is not None:
                    SOURCE.verify_row({**target,'state':owner.editor.capture() if index==live else target['state']},proofs[index])
                if index in torso_identities and index!=live:
                    verify_torso_replay(index,target['state'],'before',torso_identities[index]['revision'])
                    verify_torso_replay(index,candidate,'after',torso_identities[index]['revision'])
        except Exception:
            try:
                replay_target(before,mode='batch',replayed_for=f'batch_group_rollback:{bid}',**({'strict_local':True} if shadow_history or SC.TORSO_LENGTH.OP in ops else {}))
                if shadow_history:verify_shadow_replay(before,frozen_before)
                if SC.TORSO_LENGTH.OP in ops:
                    if owner.documents.current_index()!=live:
                        raise ValueError('Torso-length active history target changed during rollback')
                    verify_torso_replay(live,owner.editor.capture(),'before',frozen_revision)
            except Exception:owner.editor.invalidate()
            raise
    for index,row,before,after in planned:
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
