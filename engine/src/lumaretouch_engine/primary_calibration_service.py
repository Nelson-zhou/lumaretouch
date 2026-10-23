"""Reader ingress cancellation + last-intent fence immediately before shm write."""
import json
import threading
from .primary_calibration_native import native
from .primary_calibration_controller import PrimaryCalibrationController
from .primary_calibration_host import PrimaryCalibrationHost
from . import primary_calibration_adapters as A

class Service:
    def __init__(self):
        self.lock=threading.RLock();self.events={};self.active=None;self.published=False;self.owner=None
    def ingress(self,line):
        if len(line)>65536:return False
        try:p=json.loads(line)
        except Exception:return False
        if not isinstance(p,dict):return False
        cmd=p.get('cmd');action=p.get('action');rid=p.get('request_id');invalidate=False;consumed=False
        with self.lock:
            if cmd=='primary_calibration_abort':
                event=self.events.get(rid) if isinstance(rid,str) else None
                if event is not None and not (rid==self.active and self.published):event.set()
                invalidate=self.owner is not None and self.owner.ticket is not None and self.owner.ticket.request==rid
                consumed=True
            elif cmd=='primary_calibration' and action in ('preview','commit','cancel') and isinstance(rid,str) and 0<len(rid)<=128:
                if rid not in self.events and len(self.events)<64:self.events[rid]=threading.Event()
                if action in ('preview','cancel'):
                    for key,event in self.events.items():
                        if key!=rid and not (key==self.active and self.published):event.set()
                    invalidate=True
            elif cmd not in ('hello','photo_grain_state','colour_grading_state','selective_colour_state','primary_calibration','primary_calibration_state','color_scopes','photo_detail_state','photo_detail_receipt','extended_tone_state','extended_tone_receipt') and action not in ('state','status','list','get','preflight','validate'):
                for key,event in self.events.items():
                    if not (key==self.active and self.published):event.set()
                invalidate=True
        # Never acquire controller lock under publication lock: commit uses reverse.
        if invalidate and self.owner is not None:self.owner.invalidate()
        return consumed
    def cancelled(self):
        with self.lock:
            event=self.events.get(self.active)
            return event is None or event.is_set()
    def publish(self,callback):
        with self.lock:
            if self.cancelled():raise InterruptedError('RGB 原色校准已被取消或新操作替代')
            result=callback();self.published=True;return result
    def execute(self,engine,p,emit):
        if self.owner is None:self.owner=PrimaryCalibrationController(PrimaryCalibrationHost(engine))
        rid=p.get('request_id');action=p.get('action')
        if action=='status':
            emit(self.owner.handle(p));return
        with self.lock:
            if rid not in self.events:
                emit({'event':'primary_calibration_result','request_id':rid,'document_id':p.get('document_id'),'status':'failed','error':'请求未登记或队列已满'});return
            self.active=rid;self.published=False
        try:
            engine._primary_calibration_publication=self
            engine._primary_calibration_cancelled=self.cancelled
            result=self.owner.handle(p)
            if result.get('status')=='applied':result={**result,'doc_state':engine.doc_state()}
            emit(result)
        except Exception as error:
            emit({'event':'primary_calibration_result','request_id':rid,'document_id':p.get('document_id'),
                  'status':'cancelled' if isinstance(error,InterruptedError) else 'failed',
                  'error':str(error)[:1000],'requires_reload':self.owner.host.requires_reload})
        finally:
            engine._primary_calibration_publication=None;engine._primary_calibration_cancelled=lambda:False
            if engine._vram is not None:engine._vram.primary_calibration.cancelled=lambda:False
            with self.lock:self.events.pop(rid,None);self.active=None;self.published=False
    @staticmethod
    def available():
        try:
            native()  # Verifies ABI; never compiles or falls back.
            return True
        except (OSError, RuntimeError, AttributeError):
            return False
    def readback(self,engine):
        from .extended_tone_host import revision
        return {'document_id':str(engine._load_id),'revision':revision(engine),
                **A.report(engine),'requires_reload':bool(self.owner is not None and self.owner.host.requires_reload and self.owner.host.failure_document==str(engine._load_id)),'available':self.available()}
    def stop(self):
        with self.lock:
            for event in self.events.values():event.set()
        if self.owner is not None:self.owner.invalidate()
