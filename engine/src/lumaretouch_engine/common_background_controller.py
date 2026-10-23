"""One reviewed common-background mutation, one existing history owner."""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
from . import common_background_preview_source as P
from .common_background_review import controller as preview,ident
from .history_policy import state_signature


class Controller:
    def __init__(self,engine,emit):self.engine,self.emit=engine,emit;self.cache=OrderedDict()
    def handle(self,p):
        e=self.engine;rid=p.get('request_id');digest=None;before=None;ledger=None;frame=None;row=None
        result={'event':'common_background_result','protocol':1,'action':'apply',
            **{k:p.get(k) for k in ('request_id','preview_id','session_id','document_id')},
            'success':False,'outcome_unknown':False,'requires_reload':False,'no_change':False,'history':None}
        try:
            if set(p)!={'cmd','action','request_id','preview_id','session_id','document_id'} or p['cmd']!='common_background' or p['action']!='apply':raise ValueError('Invalid common apply envelope')
            if type(rid) is not str or not 1<=len(rid)<=128:raise ValueError('Invalid common request identity')
            ident(p['preview_id']);ident(p['session_id'])
            digest=sha256(json.dumps(p,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if rid in self.cache:
                old,cached=self.cache[rid]
                if old!=digest:raise ValueError('Common request ID reused with different content')
                result={**deepcopy(cached),'replayed':True};return
            why=e._guard_editable('common background')
            if why:raise ValueError(why)
            value=preview(e,self.emit).prepare(p)
            before=e._history_capture();previous=state_signature(before)
            history=e._history_controller()
            ledger=(list(history.undo),list(history.redo),history.group,history.group_ns)
            dirty=e._project_dirty
            index=getattr(e,'_doc_index',-1);rows=getattr(e,'_docs',())
            if 0<=index<len(rows):row=rows[index];edit_time=row.get('_library_edit_time_ns')
            e._fence_current_document();e._cancel_snapshot('common background');preview(e,self.emit).cancel()
            e._bg=value;P.install(e)
            frame=e._write_current_frame('common_background')
            no_change=previous==state_signature(e._history_capture())
            e._history_record('common_background:'+rid,before,coalesce=False)
            state=e.doc_state()
            result.update(success=True,no_change=no_change,history={k:state['history'][k] for k in ('undo_steps','redo_steps')})
            frame['doc_state']=state;before=None
        except Exception as error:
            result['success']=False
            result['error']=str(error)[:2000]
            if before is not None:
                try:
                    e._history_apply(before);P.install(e)
                    if ledger is not None:
                        history.undo,history.redo,history.group,history.group_ns=ledger
                        e._project_dirty=dirty
                        if row is not None:
                            if edit_time is None:row.pop('_library_edit_time_ns',None)
                            else:row['_library_edit_time_ns']=edit_time
                    frame=e._write_current_frame('common_background_rollback');frame['doc_state']=e.doc_state();self.emit(frame)
                except Exception:
                    result.update(outcome_unknown=True,requires_reload=True);e._vram=None
        finally:
            if result['success'] and frame is not None:
                try:self.emit(frame)
                except Exception:result['frame_delivery_unknown']=True
            if rid and digest and rid not in self.cache:
                self.cache[rid]=(digest,deepcopy(result))
                while len(self.cache)>64:self.cache.popitem(last=False)
            self.emit(result)


def controller(engine,emit):
    owner=engine.__dict__.get('_common_background_owner')
    if owner is None:owner=engine._common_background_owner=Controller(engine,emit)
    return owner
