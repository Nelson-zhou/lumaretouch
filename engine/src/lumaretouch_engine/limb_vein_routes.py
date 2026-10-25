# SPDX-License-Identifier: GPL-3.0-or-later
"""Current-photo adapter using the existing document/history owner. UNRUN."""
from collections import OrderedDict
from copy import deepcopy
from . import limb_vein_runtime as R, limb_vein_state as S
from .limb_vein_host import Review, Ports, Rendered
from .optics_candidate_identity import fingerprint

ACTIONS = {'reference','preview','confirm','clear','status'}
READS = {'reference','preview','status'}


def check(p):
    if (type(p) is not dict or set(p) != {'cmd','protocol','request_id','action','document_id','revision','payload'}
            or p['cmd'] != 'limb_vein' or type(p['protocol']) is not int or p['protocol'] != 1
            or p['action'] not in ACTIONS or type(p['payload']) is not dict):
        raise ValueError('肢体青筋命令格式无效')
    from .people_state import token
    token(p['request_id']); token(p['document_id'])
    if type(p['revision']) is not str or not p['revision'].isdigit() or len(p['revision']) > 20:
        raise ValueError('肢体青筋需要当前文档版本')
    return p


def read_only(p):
    try: return check(p)['action'] in READS
    except (ValueError,TypeError,KeyError): return False


def _row(engine,p):
    from .virtual_copy_people import current_row
    row = current_row(engine)
    if row is None or p['document_id'] != engine._load_id or p['revision'] != str(engine._document_versions().version(row).revision):
        raise ValueError('照片或版本已改变，请重新加载肢体参考')
    return row


class Adapter:
    def __init__(self,engine):
        self.engine = engine
        self.cached = None
        self.review = Review(Ports(self.capture,self.render,R.budget))
    def capture(self):
        e = self.engine
        from .creative_derived_source import binding
        from .creative_derived_repairs import stack_digest
        state_key = fingerprint(e._capture_state())
        row = e._docs[e._doc_index]
        key = (e._load_id,str(e._document_versions().version(row).revision),state_key,
               fingerprint(binding(e)),stack_digest(e))
        if self.cached is None or self.cached[0] != key:
            self.cached = (key,R.capture(e))
        return self.cached[1]
    def render(self,recipe):
        e = self.engine; captured = self.capture(); row = e._docs[e._doc_index]
        state = e._capture_state(); state['_limb_vein'] = S.check(recipe)
        version = e._document_versions().version(row)
        from .full_candidate_render import render
        pixels,_ = render(e,row,state,version.document_id,str(version.revision))
        return Rendered(pixels,captured.source,captured.input_sha256,captured.repair_sha256,fingerprint(recipe))


def adapter(engine):
    result = engine.__dict__.get('_limb_vein_adapter')
    if result is None:
        result = Adapter(engine); engine._limb_vein_adapter = result
    return result


def _result(p,**values):
    return {'event':'limb_vein_result','protocol':1,'family':'limb_vein',
        'request_id':p.get('request_id'),'action':p.get('action'),
        'document_id':p.get('document_id'),'revision':p.get('revision'),
        'limb_vein_request':deepcopy(p),**values}


def handle(engine,p,emit):
    records = engine.__dict__.setdefault('_limb_vein_receipts',OrderedDict())
    owner = adapter(engine); owner.cached = None
    published = False
    try:
        check(p)
        if p['action'] == 'status':
            if set(p['payload']) != {'original_request_id'}: raise ValueError('查询必须使用原请求 ID')
            old = records.get(p['payload']['original_request_id'])
            emit(deepcopy(old['result']) if old else _result(p,success=True,outcome_unknown=False,found=False))
            return
        previous = records.get(p['request_id'])
        if previous:
            if previous['request'] != p: raise ValueError('肢体青筋请求 ID 已用于另一内容')
            emit(deepcopy(previous['result'])); return
        _row(engine,p)
        why = engine._guard_editable('limb_vein')
        if why: raise ValueError(why)
        from .sample_library_capture import heavy_reason
        why = heavy_reason(engine)
        if why: raise ValueError(why)
        action = p['action']
        if action in ('reference','preview'):
            payload = getattr(owner.review,action)(p['payload'])
            result = _result(p,success=True,outcome_unknown=False,payload=payload)
        else:
            edit = getattr(owner.review,action)(p['payload'])
            _row(engine,p)
            candidate = owner.review.assert_publishable(edit)
            before = engine._history_capture()
            old_recipe = deepcopy(getattr(engine,'_limb_vein',None))
            undo,redo = list(engine._undo),list(engine._redo)
            try:
                engine._limb_vein = candidate
                frame = engine._write_current_frame('limb_vein')
                engine._history_record('limb_vein',before,coalesce=False)
                engine._remember_current()
                published = True
                frame['doc_state'] = engine.doc_state(); emit(frame)
            except Exception:
                if not published:
                    engine._limb_vein = old_recipe; engine._undo,engine._redo = undo,redo
                    if engine._vram is not None and hasattr(engine._vram,'limb_vein'):
                        engine._vram.limb_vein.clear()
                    engine._remember_current()
                raise
            owner.review.invalidate()
            result = _result(p,success=True,outcome_unknown=False,payload=edit.payload,doc_state=engine.doc_state())
        import json
        if len(json.dumps(result,separators=(',',':'),ensure_ascii=False).encode()) > 8*1024**2:
            raise ValueError('肢体青筋审核图片超过回执预算')
        records[p['request_id']] = {'request':deepcopy(p),'result':deepcopy(result)}
        while len(records)>256: records.popitem(last=False)
        emit(result)
    except Exception as error:
        result = _result(p,success=False,outcome_unknown=published,error=str(error),no_write=not published)
        if type(p.get('request_id')) is str and p['request_id'] not in records:
            records[p['request_id']] = {'request':deepcopy(p),'result':deepcopy(result)}
        emit(result)
    finally:
        owner.cached = None


def rejected(engine,p,error,started,emit):
    # A pre-dispatch refusal has not entered this serialized adapter.
    records = engine.__dict__.get('_limb_vein_receipts',{})
    known = records.get(p.get('request_id'))
    if known and known['request'] == p: emit(deepcopy(known['result'])); return
    emit(_result(p,success=False,outcome_unknown=bool(started),no_write=not started,error=str(error)))
