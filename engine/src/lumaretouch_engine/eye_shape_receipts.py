"""Correlated, bounded eye receipts published only after dispatcher history."""
from collections import OrderedDict
from . import eye_shape_state as S, eye_shape_runtime as R


def _text(v): return type(v) is str and 0<len(v)<=128


def apply(engine,p,emit):
    expected={'cmd','recipe','base','document_id','control','request_id','gesture_id','face_id'}
    if type(p) is not dict or set(p)!=expected or any(not _text(p[k]) for k in ('request_id','gesture_id','face_id','document_id')):
        raise ValueError('眼形请求身份或字段无效')
    records=engine.__dict__.setdefault('_eye_receipts',OrderedDict())
    if p['request_id'] in records: raise ValueError('眼形请求已经提交；只能查询原请求，不得重发')
    pc=engine._precompute
    selected=R.identity(pc.landmarks) if pc is not None else 'none'
    if p['face_id']!=selected: raise ValueError('选中人物已变化，未应用排队眼形调整')
    from .eye_shape_command import apply as edit
    edit(engine,{k:v for k,v in p.items() if k not in ('request_id','gesture_id','face_id')},emit)
    # Actual frame publication succeeded. The dispatcher still owns history.
    records[p['request_id']]={'frame_emitted':True}
    while len(records)>32: records.popitem(last=False)


def finish(engine,p,error,emit):
    if not all(_text(p.get(k)) for k in ('request_id','gesture_id','face_id','document_id')): return
    records=engine.__dict__.setdefault('_eye_receipts',OrderedDict())
    old=records.get(p['request_id'],{})
    if 'result' in old:
        emit(old['result']);return
    success=not error and bool(old.get('frame_emitted'))
    unknown=engine._vram is None or (not error and not success)
    result={'event':'eye_shape_result','protocol':1,'action':'edit','request_id':p['request_id'],
        'gesture_id':p['gesture_id'],'face_id':p['face_id'],'document_id':p['document_id'],
        'control':p.get('control'),'success':success,'outcome_unknown':unknown,'error':error,
        'frame_emitted':bool(old.get('frame_emitted'))}
    if not unknown and engine._load_id==p['document_id']:
        result['doc_state']=engine.doc_state()  # AFTER dispatch history bookkeeping
        status=result['doc_state']['eye_shape']
        if status['selected_face_id']==p['face_id']:
            result['recipe']=S.check(engine._eye_shape)
            result['revision']=status['revision']
            result['controls']=status['controls']
    records[p['request_id']]={'result':result}
    while len(records)>32: records.popitem(last=False)
    emit(result)
