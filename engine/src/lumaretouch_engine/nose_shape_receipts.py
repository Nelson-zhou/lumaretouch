"""Correlated, bounded nose receipts published only after dispatcher history."""
from collections import OrderedDict
from . import nose_shape_state as S, nose_shape_runtime as R


def _text(v): return type(v) is str and 0<len(v)<=128


def apply(engine,p,emit):
    expected={'cmd','recipe','base','document_id','control','request_id','gesture_id','face_id'}
    if isinstance(p,dict) and 'people_context' in p:expected.add('people_context')
    if type(p) is not dict or set(p)!=expected or any(not _text(p[k]) for k in ('request_id','gesture_id','face_id','document_id')):
        raise ValueError('鼻形请求身份或字段无效')
    records=engine.__dict__.setdefault('_nose_receipts',OrderedDict())
    if p['request_id'] in records: raise ValueError('鼻形请求已经提交；只能查询原请求，不得重发')
    pc=engine._precompute
    selected=R.identity(pc.landmarks) if pc is not None else 'none'
    if p['face_id']!=selected: raise ValueError('选中人物已变化，未应用排队鼻形调整')
    from .nose_shape_command import apply as edit
    edit(engine,{k:v for k,v in p.items() if k not in ('request_id','gesture_id','face_id')},emit)
    # Actual frame publication succeeded. The dispatcher still owns history.
    records[p['request_id']]={'frame_emitted':True}
    while len(records)>32: records.popitem(last=False)


def finish(engine,p,error,emit):
    if not all(_text(p.get(k)) for k in ('request_id','gesture_id','face_id','document_id')): return
    records=engine.__dict__.setdefault('_nose_receipts',OrderedDict())
    old=records.get(p['request_id'],{})
    if 'result' in old:
        emit(old['result']);return
    success=not error and bool(old.get('frame_emitted'))
    unknown=engine._vram is None or (not error and not success)
    result={'event':'nose_shape_result','protocol':1,'action':'edit','request_id':p['request_id'],
        'gesture_id':p['gesture_id'],'face_id':p['face_id'],'document_id':p['document_id'],
        'control':p.get('control'),'success':success,'outcome_unknown':unknown,'error':error,
        'frame_emitted':bool(old.get('frame_emitted'))}
    if success:
        result['recipe']=S.check(engine._nose_shape)
        result['doc_state']=engine.doc_state()  # AFTER dispatch history bookkeeping
        result['revision']=result['doc_state']['nose_shape']['revision']
    records[p['request_id']]={'result':result}
    while len(records)>32: records.popitem(last=False)
    emit(result)
