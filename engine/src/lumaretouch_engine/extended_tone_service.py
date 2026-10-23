"""Reader-side latest intent/cancel and publication fence; serial Engine owns history."""
import json
import threading
from . import extended_tone_state as S
from .extended_tone_host import controller, preview_scale

class Service:
    def __init__(self):
        self.lock=threading.RLock();self.events={};self.active=None;self.published=False
    def ingress(self,line):
        if len(line)>65536:return False
        try:p=json.loads(line)
        except Exception:return False
        if not isinstance(p,dict):return False
        cmd=p.get('cmd');rid=p.get('request_id')
        with self.lock:
            if cmd=='extended_tone_cancel':
                event=self.events.get(rid)
                if event and not (rid==self.active and self.published):event.set()
                return True
            if cmd=='extended_tone' and isinstance(rid,str) and 0<len(rid)<=128:
                if rid not in self.events and len(self.events)<64:self.events[rid]=threading.Event()
                for key,event in self.events.items():
                    if key!=rid and not (key==self.active and self.published):event.set()
            elif cmd not in ('hello','extended_tone_state','extended_tone_receipt','color_scopes') and p.get('action') not in ('state','status','list','get','preflight','validate'):
                for key,event in self.events.items():
                    if not (key==self.active and self.published):event.set()
        return False
    def cancelled(self):
        with self.lock:
            event=self.events.get(self.active)
            return event is None or event.is_set()
    def publish(self,callback):
        with self.lock:
            if self.cancelled():raise InterruptedError('扩展影调已取消或被新操作替代')
            result=callback();self.published=True;return result
    def execute(self,engine,p,emit):
        def deliver(result):
            if result.get('success'):result={**result,'doc_state':engine.doc_state()}
            emit(result)
        owner=controller(engine,deliver,preview_scale=lambda:preview_scale(engine),monochrome=lambda:S.check(getattr(engine,S.KEY,None))['monochrome'])
        rid=p.get('request_id')
        if rid in owner.receipts:return owner.handle(p)
        with self.lock:
            event=self.events.get(rid)
            if event is None:
                emit({'event':'extended_tone_result','protocol':1,'request_id':rid,'document_id':p.get('document_id'),'success':False,'outcome_unknown':False,'requires_reload':False,'error':'请求未登记或有界队列已满'})
                return
            self.active=rid;self.published=False
        try:
            engine._extended_tone_publication=self
            engine._extended_tone_cancelled=self.cancelled
            return owner.handle(p)
        finally:
            engine._extended_tone_publication=None
            engine._extended_tone_cancelled=lambda:False
            if engine._vram is not None:engine._vram.extended_tone.cancelled=lambda:False
            with self.lock:self.events.pop(rid,None);self.active=None;self.published=False
    def stop(self):
        with self.lock:
            for event in self.events.values():event.set()
