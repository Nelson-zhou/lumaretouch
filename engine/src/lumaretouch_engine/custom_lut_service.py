"""Bounded local library and edit commands, reader-side cancel, durable receipts."""
import json
import os
from pathlib import Path
import threading
from .custom_lut_library import default_library
from .custom_lut_asset import CustomCube

class Service:
    def __init__(self):
        self.lock=threading.RLock(); self.events={}; self.seen=set(); self.active=None; self.published=False; self.library=None
    def store(self):
        return default_library()
    def ingress(self,line):
        if len(line)>65536:return False
        try:p=json.loads(line)
        except Exception:return False
        if not isinstance(p,dict):return False
        cmd=p.get('cmd');rid=p.get('request_id')
        with self.lock:
            if cmd=='custom_lut_cancel':
                event=self.events.get(rid)
                if event and not (self.active==rid and self.published):event.set()
                return True
            if cmd=='custom_lut':
                if not isinstance(rid,str) or not 1<=len(rid)<=128:return False
                if rid not in self.seen and len(self.events)<64 and len(self.seen)<65536:
                    self.seen.add(rid);self.events[rid]=threading.Event()
                    if p.get('action') in ('select','import','recover'):
                        for key,event in self.events.items():
                            if key!=rid and not (self.active==key and self.published):event.set()
            elif cmd in ('primary_calibration','selective_colour','colour_grading','extended_tone','set_strength','inpaint','source_patch','clone_stamp','local_masks','effect_recovery','manual_liquify','studio_background','optics','sky_replacement','light','deform','lut','grade','background','crop','exposure','white_balance','color_picker','hsl','curves','levels','preset','batch','face','enhance','people','hair_colour','fabric','history','load_image','session','project','set_device','shutdown','compare') and p.get('action') not in ('state','status','list','get','preflight','validate'):
                for key,event in self.events.items():
                    if not (self.active==key and self.published):event.set()
        return False
    def publish(self, callback):
        with self.lock:
            event=self.events.get(self.active)
            if event is None or event.is_set():raise InterruptedError('LUT 请求已取消或被更新替代')
            result=callback(); self.published=True; return result
    @staticmethod
    def snapshot(engine):
        index=getattr(engine,'_doc_index',-1)
        revision=engine._document_versions().version(engine._docs[index]).revision if 0<=index<len(engine._docs) else 0
        cube=engine._lut
        return dict(document_id=engine._load_id or '',revision=revision,asset_id=cube.asset_id if isinstance(cube,CustomCube) else None,amount=float(engine._lut_amount))
    def execute(self,engine,p,emit):
        rid=p.get('request_id');result=None;success=False;error=None;committed=False
        try:
            if set(p)-{'cmd','request_id','action','document_id','revision','path','id','name','amount'}:raise ValueError('未知 LUT 请求字段')
            with self.lock:
                event=self.events.get(rid)
                if event is None:raise ValueError('LUT 请求身份重复、未登记或已超过有界容量')
                self.active=rid;self.published=False
            action=p.get('action');lib=self.store()
            if event.is_set():raise InterruptedError('LUT 已取消')
            if action=='list':result=lib.list()
            elif action=='state':result=self.snapshot(engine)
            elif action in ('import','recover','select'):
                snap=self.snapshot(engine)
                if p.get('document_id')!=snap['document_id'] or type(p.get('revision')) is not int or p['revision']!=snap['revision']:raise ValueError('文档或编辑版本已改变；请刷新后重试')
                if action in ('import','recover'):
                    ident=lib.import_path(p['path'],event.is_set) if action=='import' else lib.recover(p['id'],p['path'],event.is_set)
                    committed=True;result=next(x for x in lib.list() if x['id']==ident)
                else:
                    ident=p.get('id');cube=None
                    if ident is not None:
                        if isinstance(engine._lut,CustomCube) and engine._lut.asset_id==ident and not lib.contains(ident):lib.import_bytes(engine._lut.content,engine._lut.title,event.is_set)
                        data=lib.content(ident)
                        name=next((x['name'] for x in lib.list() if x['id']==ident),'已保留 LUT')
                        cube=CustomCube(data,ident,name)
                    if event.is_set():raise InterruptedError('LUT 已取消')
                    engine._cancel_snapshot('custom_lut')
                    engine._close_owned_previews()
                    before=engine._history_capture()
                    engine._custom_lut_publication=self
                    engine._vram.custom_lut_cancelled=event.is_set
                    request={'action':'clear'} if cube is None else {'action':'set','_custom_cube':cube,'amount':p.get('amount',1.)}
                    try:
                        if engine.cmd_lut(request) is not True:raise RuntimeError('LUT 应用失败；原配方保留，详见引擎错误')
                        committed=True
                        engine._fence_current_document()
                        engine._history_record('custom_lut',before,coalesce=False)
                        result=self.snapshot(engine)
                    finally:
                        engine._custom_lut_publication=None
                        engine._vram.custom_lut_cancelled=lambda:False
            elif action in ('rename','remove','restore'):
                if action=='rename':lib.rename(p['id'],p['name'])
                elif action=='remove':lib.remove(p['id'])
                else:lib.undo_remove(p['id'])
                committed=True;result=lib.list()
            else:raise ValueError('未知自定义 LUT 操作')
            success=True
        except Exception as exc:error=str(exc)[:2000]
        finally:
            with self.lock:self.events.pop(rid,None);self.active=None;self.published=False
        receipt=dict(event='custom_lut_result',request_id=rid,success=success,committed=committed,result=result,error=error)
        if p.get('action')=='select' and committed: receipt['doc_state']=engine.doc_state()
        emit(receipt)
