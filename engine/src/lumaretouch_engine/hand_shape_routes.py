# SPDX-License-Identifier: GPL-3.0-or-later
"""Serialized current-document commands; existing history owns publication."""
from copy import deepcopy
from . import hand_shape_state as S
from .hand_shape_host import Review,tag
from .optics_candidate_identity import fingerprint
ACTIONS={'reference','propose','preview','confirm','clear','status'}
READS={'reference','propose','preview','status'}


def check(p):
    if type(p) is not dict or set(p)!={'cmd','protocol','request_id','action','document_id','revision','payload'} or p['cmd']!='hand_shape' or type(p['protocol']) is not int or p['protocol']!=1 or p['action'] not in ACTIONS or type(p['payload']) is not dict:raise ValueError('手部美型命令格式无效')
    S.token(p['request_id']);S.token(p['document_id'])
    if type(p['revision']) is not str or not p['revision'].isdigit() or len(p['revision'])>16 or int(p['revision'])>9007199254740991:raise ValueError('手部美型需要准确文档版本')
    return p


def read_only(p):
    try:return check(p)['action'] in READS
    except (ValueError,TypeError,KeyError):return False


def _row(engine,p):
    from .virtual_copy_people import current_row
    row=current_row(engine)
    if row is None or p['document_id']!=engine._load_id or p['revision']!=str(engine._document_versions().version(row).revision):raise ValueError('照片或版本已改变，请重新获取手部范围')
    return row


def _result(p,**values):
    return {'event':'hand_shape_result',**tag(),'request_id':p.get('request_id'),'action':p.get('action'),
        'document_id':p.get('document_id'),'revision':p.get('revision'),'hand_shape_request':deepcopy(p),**values}


def owner(engine):
    value=engine.__dict__.get('_hand_shape_review')
    if value is None:value=engine._hand_shape_review=Review(engine)
    return value


def handle(engine,p,emit):
    records=engine.__dict__.setdefault('_hand_shape_receipts',{})
    started=False;published=False;review=None
    try:
        check(p)
        if p['action']=='status':
            if set(p['payload'])!={'original_request_id'}:raise ValueError('查询必须指向原请求 ID')
            S.token(p['payload']['original_request_id']);old=records.get(p['payload']['original_request_id'])
            emit(deepcopy(old['result']) if old is not None else _result(p,success=True,outcome_unknown=False,found=False));return
        previous=records.get(p['request_id'])
        if previous is not None:
            if previous['request']!=p:raise ValueError('Hand request ID was reused for different content')
            emit(deepcopy(previous['result']));return
        _row(engine,p)
        why=engine._guard_editable('hand_shape')
        if why:raise ValueError(why)
        from .sample_library_capture import heavy_reason
        why=heavy_reason(engine)
        if why:raise ValueError(why)
        review=owner(engine);action=p['action']
        if action in ('reference','propose','preview'):
            payload=getattr(review,action)(p['payload']);_row(engine,p)
            emit(_result(p,success=True,outcome_unknown=False,payload=payload));return
        # Keep all admitted mutation identities in this process. Never evict an
        # uncertain write and make a retry look like a new command.
        if len(records)>=256:raise ValueError('Hand mutation receipt budget exhausted; reopen document/session before more changes')
        if action=='clear':
            if p['payload']!={}:raise ValueError('Clear accepts no replacement geometry')
            candidate=None
        else:candidate=review.confirm(p['payload'])
        _row(engine,p)
        before=engine._history_capture();old=deepcopy(getattr(engine,'_hand_shape',None));undo,redo=list(engine._undo),list(engine._redo)
        old_prepared=getattr(engine._vram,'people_prepared',None);old_key=getattr(engine._vram,'people_key',None);old_suspended=getattr(engine._vram,'people_suspended',None)
        pending=_result(p,success=False,outcome_unknown=True,error='Hand publication pending; query this exact request, do not replay')
        records[p['request_id']]={'request':deepcopy(p),'result':pending}
        try:
            started=True;engine._hand_shape=candidate
            # Rebuild/install actual common map before publishing, including an
            # empty face/body bank for a standalone hand photograph.
            engine._people_sync(strict=True)
            frame=engine._write_current_frame('hand_shape')
            engine._history_record('hand_shape',before,coalesce=False);engine._remember_current();published=True
            frame['doc_state']=engine.doc_state();emit(frame)
        except Exception:
            if not published:
                engine._hand_shape=old;engine._undo,engine._redo=undo,redo
                from .people_pipeline import install,clear
                if engine._vram is not None:
                    if old_prepared is None:clear(engine._vram)
                    else:install(engine._vram,old_prepared)
                    engine._vram.people_key=old_key;engine._vram.people_suspended=old_suspended
                engine._remember_current()
                # Frame publication may have begun. A fresh canonical old frame
                # is necessary before claiming a known rollback.
                restored=engine._write_current_frame('hand_shape_rollback');restored['doc_state']=engine.doc_state();emit(restored)
                started=False
            raise
        review.invalidate()
        payload={**tag(),'active':S.active(candidate),'candidate_sha256':fingerprint(candidate)}
        result=_result(p,success=True,outcome_unknown=False,payload=payload,doc_state=engine.doc_state())
        records[p['request_id']]['result']=deepcopy(result);emit(result)
    except Exception as error:
        result=_result(p,success=False,outcome_unknown=bool(published or started),no_write=not(published or started),error=str(error))
        if type(p) is dict and type(p.get('request_id')) is str and p.get('action') in ('confirm','clear'):
            existing=records.get(p['request_id'])
            if existing is not None and existing['request']==p:existing['result']=deepcopy(result)
        emit(result)


def rejected(engine,p,error,started,emit):
    known=engine.__dict__.get('_hand_shape_receipts',{}).get(p.get('request_id'))
    if known and known['request']==p:emit(deepcopy(known['result']));return
    emit(_result(p,success=False,outcome_unknown=bool(started),no_write=not started,error=str(error)))
