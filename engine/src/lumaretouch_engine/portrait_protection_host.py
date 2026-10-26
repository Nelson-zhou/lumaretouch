"""Exact document/revision owner with retained terminal outcomes, never retry-on-timeout."""
from copy import deepcopy
from . import portrait_protection_state as S
from . import portrait_protection_runtime as R


def _available(engine):
    try:
        if type(engine._load_id) is not str or not engine._load_id:return False
        from .creative_derived_source import binding, record
        from .local_mask_state import file_stamp
        if record(engine) is not None:return False # new P0 entry remains original-source only
        if not 0<=engine._doc_index<len(engine._docs):return False
        row=engine._docs[engine._doc_index]
        if row.get('_local_source_stamp')!=file_stamp(engine._doc_path):return False
        old=S.check(getattr(engine,S.KEY,None))
        if old['source'] is not None and old['source']==binding(engine):
            R.owner_check(engine,old)
            return True
        R.owner_check(engine)
        pc=engine._precompute
        return bool(pc is not None and pc.backend=='mediapipe' and pc.num_faces==1
                    and not pc.detection_limit_reached and len(pc.all_landmarks or [pc.landmarks])==1
                    and pc.semantic_model_sha256 and pc.detector_model_sha256 and 'face_skin' in pc.masks)
    except (ValueError,AttributeError,IndexError,OSError,TypeError):return False


def report(engine):
    from .extended_tone_host import revision
    value=S.check(getattr(engine,S.KEY,None)); available=_available(engine)
    return {'controls':value['controls'],'document_id':str(engine._load_id),
            'revision':str(revision(engine)),'active':S.active(value),
            'analysis_available':available,
            'reason':getattr(engine,'_portrait_protection_suspended',None) or (None if available else '需要有效当前原照片的启用单脸分析；人工禁用/补脸或归属不明时不处理')}


def _commit(engine,request,emit):
    from .extended_tone_host import revision
    from .optics_candidate_identity import fingerprint
    if set(request)!={'cmd','request_id','document_id','revision','controls'} or request['cmd']!='portrait_protection':
        raise ValueError('Portrait command needs exact request/document/revision/controls')
    if type(engine._load_id) is not str or not engine._load_id:
        raise ValueError('No valid current loaded document token; reload before portrait editing')
    desired=S.controls(request['controls']); rev=revision(engine); document=engine._load_id
    if type(request['document_id']) is not str or type(request['revision']) is not str or (request['document_id'],request['revision'])!=(document,str(rev)):
        raise ValueError('Portrait request document/revision changed; refresh before editing')
    guard=engine._guard_editable('portrait_protection')
    if guard:raise ValueError(guard)
    if engine.__dict__.get('_portrait_protection_reload')==document:raise ValueError('Portrait rollback unconfirmed; reload required')
    previous=S.check(getattr(engine,S.KEY,None))
    resetting=desired==S.controls()
    if previous['controls']==desired and (not resetting or previous==S.neutral()):
        return {'phase':'no_change','spec':desired,'result_revision':str(rev)}
    # Explicit neutral reset discards old evidence; a later activation can
    # capture the current verified owner after deliberate reanalysis.
    proposed=S.neutral() if resetting else {**previous,'controls':desired}
    if S.needs_analysis(proposed):
        if not _available(engine):raise ValueError(report(engine)['reason'])
        from .creative_derived_source import binding
        source=binding(engine)
        if previous['source']!=source:proposed=S.capture(engine._precompute,source,desired,face_instance_id=R.owner_check(engine))
        R.owner_check(engine,proposed)
    proposed=S.check(proposed)
    engine._cancel_snapshot('portrait_protection');engine._close_owned_previews()
    before=engine._history_capture()
    if S.KEY not in before:raise ValueError('Portrait protection missing from canonical history integration')
    history=engine._history_controller();ledger=(list(history.undo),list(history.redo),history.group,history.group_ns)
    proof=fingerprint((before,ledger));dirty=engine._project_dirty
    row=engine._docs[engine._doc_index]
    edit_time=('_library_edit_time_ns' in row,row.get('_library_edit_time_ns'))
    engine._portrait_protection_outcome='unknown'
    try:
        setattr(engine,S.KEY,proposed)
        R.sync(engine)
        frame=engine._write_current_frame('portrait_protection')
        engine._history_record('portrait_protection',before,coalesce=False)
        if not history.undo or S.check(history.undo[-1].get(S.KEY))!=previous or history.redo:
            raise RuntimeError('Portrait history did not retain exact previous recipe')
        engine._fence_current_document()
        if str(engine._load_id)!=document or revision(engine)!=rev+1 or S.check(engine._history_capture().get(S.KEY))!=proposed:
            raise RuntimeError('Portrait post-commit source/revision/state proof mismatch')
    except Exception as error:
        try:
            setattr(engine,S.KEY,previous)
            history.undo,history.redo,history.group,history.group_ns=ledger
            engine._project_dirty=dirty
            if edit_time[0]:row['_library_edit_time_ns']=edit_time[1]
            else:row.pop('_library_edit_time_ns',None)
            R.sync(engine)
            back=engine._write_current_frame('portrait_protection_rollback')
            if fingerprint((engine._history_capture(),(list(history.undo),list(history.redo),history.group,history.group_ns)))!=proof or revision(engine)!=rev:
                raise RuntimeError('Portrait rollback proof mismatch')
        except Exception as rollback:
            engine._portrait_protection_reload=document
            failure=RuntimeError(f'Portrait commit failed ({error}); rollback unconfirmed ({rollback})')
            failure.outcome_unknown=True
            raise failure from error
        engine._portrait_protection_outcome='rolled_back'
        try:emit(back)
        except Exception:pass
        failure=RuntimeError(f'Portrait edit rolled back: {error}');failure.rolled_back=True
        raise failure from error
    engine._portrait_protection_outcome='applied'
    result={'phase':'applied','spec':desired,'result_revision':str(rev+1)}
    try:
        frame['doc_state']=engine.doc_state();emit(frame);engine.emit_session_state()
    except Exception:result['frame_delivery_unknown']=True
    return result


def _packet(request):
    return {'event':'portrait_protection_result','protocol':1,'request_id':request.get('request_id'),
            'original_request':deepcopy(request),'success':False,'outcome_unknown':False,
            'requires_reload':False,'phase':'rejected'}


def command(engine,request,emit):
    engine._portrait_protection_outcome='no_write'
    if type(request) is not dict:raise ValueError('Portrait request must be an object')
    rid=request.get('request_id')
    if type(rid) is not str or not 1<=len(rid)<=128:raise ValueError('Portrait request needs bounded identity')
    receipts=engine.__dict__.setdefault('_portrait_protection_receipts',{})
    if rid in receipts:
        original,packet=receipts[rid]
        if original!=request:raise ValueError('Portrait request identity conflict')
        emit(deepcopy(packet));return deepcopy(packet)
    if len(receipts)>=4096:raise ValueError('Portrait receipt capacity exhausted; save/restart')
    packet=_packet(request)
    try:packet.update(_commit(engine,request,emit),success=True)
    except Exception as error:
        unknown=bool(getattr(error,'outcome_unknown',False))
        packet.update(error=str(error)[:2000],outcome_unknown=unknown,requires_reload=unknown,
                      phase='unknown' if unknown else 'rolled_back' if getattr(error,'rolled_back',False) else 'rejected')
    receipts[rid]=(deepcopy(request),deepcopy(packet));emit(deepcopy(packet));return packet


def receipt(engine,request,emit):
    if type(request) is not dict or set(request)!={'cmd','request_id','original_request'} or request['cmd']!='portrait_protection_receipt':raise ValueError('Invalid portrait receipt query')
    original=request['original_request']
    if type(original) is not dict or original.get('request_id')!=request['request_id']:raise ValueError('Receipt identity mismatch')
    retained=engine.__dict__.get('_portrait_protection_receipts',{}).get(request['request_id'])
    if retained is not None and retained[0]==original:emit(deepcopy(retained[1]));return
    packet=_packet(original)
    packet.update(phase='unknown',error='No retained exact receipt in this engine session; do not retry edit',outcome_unknown=True,requires_reload=True)
    emit(packet)


def dispatch_rejected(engine,request,error,started,emit):
    retained=engine.__dict__.get('_portrait_protection_receipts',{}).get(request.get('request_id'))
    if retained is not None and retained[0]==request:emit(deepcopy(retained[1]));return
    unknown=bool(started) and engine.__dict__.get('_portrait_protection_outcome') not in ('no_write','rolled_back')
    packet=_packet(request);packet.update(error=str(error)[:2000],phase='unknown' if unknown else 'rejected',outcome_unknown=unknown,requires_reload=unknown)
    emit(packet)
