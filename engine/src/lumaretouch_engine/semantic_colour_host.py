# SPDX-License-Identifier: GPL-3.0-or-later
"""Small native receipts, no replay after uncertainty, cancellation-only ingress.

The reader owns Event metadata only. Editor state, rendering and commits remain
on the command thread. Cancellation is checked before a write, not called rollback.
"""
from collections import OrderedDict
from hashlib import sha256
import json
import re
import threading
from . import semantic_colour_state as S, semantic_colour_runtime as R, semantic_colour_assets as MA
from .semantic_colour_project import BUNDLE

MAX_REQUEST=2*1024*1024
MAX_RESULT=8*1024*1024
MAX_RETAINED=16*1024*1024
OWNED=(S.KEY,BUNDLE,MA.KEY)

def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def identity(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value):raise ValueError('AI 追色请求身份无效')
    return value

class SemanticColourHost:
    def __init__(self):
        self.lock=threading.Lock();self.events={};self.early=set();self.seen={};self.results=OrderedDict();self.bytes=0;self.stopped=False;self.overflow=False
    def register(self,ident):
        ident=identity(ident)
        with self.lock:
            if ident not in self.events:
                if len(self.events)>=128:raise ValueError('AI 追色请求队列已满')
                event=threading.Event()
                if self.stopped or self.overflow or ident in self.early:event.set()
                self.early.discard(ident);self.events[ident]=event
            return self.events[ident]
    def cancel(self,ident):
        ident=identity(ident)
        with self.lock:
            if ident in self.events:self.events[ident].set()
            elif ident not in self.seen:
                if len(self.early)<128:self.early.add(ident)
                else:
                    self.overflow=True
                    for event in self.events.values():event.set()
    def stop(self):
        with self.lock:
            self.stopped=True
            for event in self.events.values():event.set()
    def observe_line(self,line):
        if type(line) is not str or 'semantic_colour' not in line:return False
        try:
            if len(line.encode())>MAX_REQUEST:return False
            message=json.loads(line)
            if type(message) is not dict:return False
            if message.get('cmd')=='semantic_colour_cancel' and set(message)=={'cmd','request_id'}:
                self.cancel(message['request_id']);return True
            if message.get('cmd')=='semantic_colour':self.register(message.get('request_id'))
        except (ValueError,TypeError,UnicodeError):pass
        return False
    def handle(self,engine,message,emit):
        from .semantic_colour_controller import controller
        owner=controller(engine,emit);ident=message.get('request_id');signature=None;owner.write_started=False
        terminal={'event':'semantic_colour_result','protocol':1,'action':'request','request_id':ident if type(ident) is str and len(ident)<=128 else None}
        try:
            ident=identity(ident)
            if set(message)!={'cmd','request_id','action','request'} or message['action']!='request':raise ValueError('AI 追色传输字段无效')
            raw=encoded(message)
            if len(raw)>MAX_REQUEST:raise ValueError('AI 追色请求超过 2 MiB 预算')
            signature=sha256(raw).hexdigest()
            with self.lock:
                previous=self.seen.get(ident);receipt=self.results.get(ident)
                if previous is None:
                    if len(self.seen)>=65536:raise ValueError('AI 追色请求身份预算已满，请重启应用')
                    self.seen[ident]=signature
            if previous is not None:
                signature=None
                if previous!=sha256(raw).hexdigest():raise ValueError('AI 追色请求身份不能绑定不同内容')
                if receipt is not None:
                    with self.lock:self.events.pop(ident,None)
                    emit(receipt[0]);return
                terminal.update(success=False,outcome_unknown=True,committed=None,error='旧回执已释放，禁止重放操作；请核对当前配方')
            else:
                stop=self.register(ident)
                if message['request'].get('action') in ('commit','edit','batch_apply','batch_restore') and not stop.is_set():
                    engine._cancel_snapshot('semantic_colour')
                    engine._close_owned_previews()
                    for key in ('_color_capture_owner','_white_balance_owner','_source_patch_owner','_color_picker_owner'):
                        other=engine.__dict__.get(key)
                        if other is not None:
                            capture=getattr(other,'capture',other)
                            if hasattr(capture,'invalidate'):capture.invalidate()
                out=owner.execute(message['request'],cancelled=stop.is_set)
                # Batch publication may return an uncertain receipt instead of
                # raising after token claim. Preserve its small evidence, but
                # never turn that nested failure into a successful mutation.
                if isinstance(out,dict) and out.get('outcome_unknown') is True:
                    terminal.update(success=False,outcome_unknown=True,committed=None,result=out,
                        error=str(out.get('error') or '写入结果需要逐目标核对')[:2000],error_code='outcome_unknown')
                else:terminal.update(success=True,outcome_unknown=False,committed=owner.write_started,result=out)
                if len(encoded(terminal))>MAX_RESULT:raise ValueError('AI 追色回执超出 8 MiB 限额，请核对当前配方')
        except Exception as error:
            terminal.pop('result',None)
            terminal.update(success=False,outcome_unknown=owner.write_started,committed=None if owner.write_started else False,
                            error=str(error)[:2000],error_code='outcome_unknown' if owner.write_started else 'rejected')
        size=len(encoded(terminal))
        with self.lock:
            if type(ident) is str:self.events.pop(ident,None)
            if signature is not None:
                while self.results and (len(self.results)>=128 or self.bytes+size>MAX_RETAINED):
                    _,(_,old_size)=self.results.popitem(last=False);self.bytes-=old_size
                self.results[ident]=(terminal,size);self.bytes+=size
        emit(terminal)

class SemanticColourHostMixin:
    def _semantic_colour_host(self):
        owner=self.__dict__.get('_semantic_colour_protocol')
        if owner is None:owner=self._semantic_colour_protocol=SemanticColourHost()
        return owner
    def cmd_semantic_colour(self,message):
        from .server import emit
        self._semantic_colour_host().handle(self,message,emit)
    def cmd_semantic_colour_cancel(self,message):
        if set(message)!={'cmd','request_id'}:raise ValueError('AI 追色取消字段无效')
        self._semantic_colour_host().cancel(message['request_id'])
    def _semantic_init(self):
        self._semantic_colour=S.empty();self._semantic_colour_bundle=None;self._semantic_colour_mask_assets={}
    @staticmethod
    def _semantic_fields(state=None):
        state=state or {};recipe=S.check(state.get(S.KEY));assets=MA.check(recipe,state.get(MA.KEY,{}))
        return {S.KEY:recipe,BUNDLE:state.get(BUNDLE),MA.KEY:assets}
    @staticmethod
    def _semantic_restore(state):
        from .semantic_colour_project import validate_decoded
        return validate_decoded(state)
    def _semantic_capture(self):return self._semantic_fields({key:getattr(self,key,None) for key in OWNED})
    def _semantic_snapshot(self,snap,state,source_path=None):
        from . import local_mask_state as LM
        recipe=S.check(state.get(S.KEY));source=None;path=None
        if recipe['target'] is not None:
            path=source_path or self._docs[self._doc_index]['path']
            source={**recipe['target']['source'],'sha256':LM.source_digest(path)}
        snap.update(semantic_colour=recipe,semantic_colour_mask_assets=state.get(MA.KEY,{}),semantic_colour_source_path=path,
            semantic_colour_binding=R.export_binding(state,snap.get('people'),source,recipe))
        return snap
    def _semantic_shutdown(self):
        self._semantic_colour_host().stop()
        owner=self.__dict__.get('_semantic_colour_owner')
        if owner is not None:owner.shutdown()
    def _semantic_workspace_reset(self):
        owner=self.__dict__.get('_semantic_colour_owner')
        if owner is not None:owner.shutdown()
        batch=self.__dict__.get('_batch_sync')
        if batch is not None:batch.semantic_colour_inspection=None
    def _owned_command_ingress(self,line):
        return self._sample_library_host().observe_line(line) or self._semantic_colour_host().observe_line(line)
    def _owned_reader_stop(self):
        self._sample_library_host().stop();self._semantic_colour_host().stop()
