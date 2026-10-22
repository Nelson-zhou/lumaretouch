"""Prepared, atomic targeted color transactions with terminal post-history receipts."""
from collections import OrderedDict
from copy import deepcopy
from .white_balance_controller import identity, error_text, WhiteBalanceController
from .color_picker_capture import ColorPickerCapture, PROOF_KEYS
from .color_picker_math import selection
from .ops import levels as L, curves as C, hsl as H

class ColorPickerController:
    def __init__(self,engine,emit):
        self.engine=engine;self.emit=emit;self.capture=ColorPickerCapture(engine,emit)
        self.pending=None;self.prepared=None;self.cache=OrderedDict()
    def prepare(self,p):
        self.prepared=None
        result={'event':'color_picker_result','protocol':1,'request_id':identity(p.get('request_id'),128),
                'document_id':identity(p.get('document_id'),64),'action':identity(p.get('action'),32),'channel':identity(p.get('channel'),32),
                **{k:identity(p.get(k),128) for k in PROOF_KEYS},'success':False,'outcome_unknown':False,'requires_reload':False}
        self.pending=(None,result)
        try:
            fingerprint=WhiteBalanceController.fingerprint(p);self.pending=(fingerprint,result)
            if set(p)!={'cmd','request_id','document_id','action','channel','region','delta',*PROOF_KEYS} or p['cmd']!='color_picker':raise ValueError('Invalid targeted color action fields')
            selection(p.get('action'),p.get('channel'))
            if not result['request_id'] or not result['document_id'] or any(result[k] is None for k in PROOF_KEYS):raise ValueError('Invalid targeted color action identity')
            if p['request_id'] in self.cache:
                old,cached=self.cache[p['request_id']]
                if old!=fingerprint:raise ValueError('Color picker request ID reused with different data')
                self.pending=(fingerprint,{**deepcopy(cached),'replayed':True});return False
            if p['document_id']!=self.engine._load_id:raise ValueError('Color picker photo changed')
            why=self.engine._guard_editable('color picker')
            if why:raise ValueError(why)
            proof=self.capture.prepare_apply(p)
            if any(proof.get(k)!=p[k] for k in ('document_id',*PROOF_KEYS)):raise ValueError('Color picker prepared proof does not match')
            self.prepared=(fingerprint,proof);return True
        except Exception as error:
            result['error']=error_text(error);self.emit({'event':'error','error':result['error']});return False
    def handle(self,p):
        result=self.pending[1] if self.pending else None
        try:
            prepared,self.prepared=self.prepared,None
            if result is None or prepared is None or prepared[0]!=WhiteBalanceController.fingerprint(p):raise ValueError('Color picker must be prepared before the mutation fence')
            e=self.engine;action=p['action'];before=self.capture.recipe(action);recipe=prepared[1]['recipe'];no_change=before==recipe
            result.update(before=deepcopy(before),sample=prepared[1]['sample'],no_change=no_change)
            if not no_change:
                try:
                    self.install(action,recipe)
                    frame=e._write_current_frame('color_picker');frame['doc_state']=e.doc_state();self.emit(frame)
                except Exception:
                    try:
                        self.install(action,before);self.emit(e._write_current_frame('color_picker_rollback'))
                    except Exception as rollback:
                        result.update(outcome_unknown=True,requires_reload=True)
                        self.emit({'event':'engine_warn','warn':'Color picker rollback failed; reopen photo: '+error_text(rollback)})
                    raise
            result['success']=True
        except Exception as error:
            if result is not None:result['error']=error_text(error)
            self.emit({'event':'error','error':error_text(error)})
    def install(self,action,recipe):
        e=self.engine
        if action.startswith('levels_'):
            recipe=L.check_levels(recipe);e._vram.set_levels(recipe);e._levels=recipe
        elif action=='curve':
            recipe=C.check_curves(recipe);e._vram.set_curves(recipe);e._curves=recipe
        else:
            recipe=H.check_hsl(recipe);e._vram.set_hsl(recipe);e._hsl=tuple(recipe)
    def finish(self,p,dispatch_error=None):
        pending,self.pending=self.pending,None;self.prepared=None
        if pending is None:
            result={'event':'color_picker_result','protocol':1,'request_id':identity(p.get('request_id'),128),'document_id':identity(p.get('document_id'),64),
                'action':identity(p.get('action'),32),'channel':identity(p.get('channel'),32),**{k:identity(p.get(k),128) for k in PROOF_KEYS},
                'success':False,'outcome_unknown':True,'requires_reload':False,'error':'Color action produced no outcome'}
            fingerprint=None
        else:fingerprint,result=pending
        if dispatch_error:result.update(success=False,outcome_unknown=True,error=error_text(dispatch_error))
        if result.get('success') and not result.get('replayed'):
            try:
                status=self.engine.doc_state()
                if status['document_id']!=result['document_id']:raise ValueError('Photo changed before color action receipt')
                result['after']=self.capture.recipe(result['action'])
                result['history']={k:status['history'][k] for k in ('undo_steps','redo_steps')}
            except Exception as error:result.update(success=False,outcome_unknown=True,error=error_text(error))
        rid=result.get('request_id')
        if fingerprint is not None and identity(rid,128) and rid not in self.cache:
            self.cache[rid]=(fingerprint,deepcopy(result))
            while len(self.cache)>64:self.cache.popitem(last=False)
        self.emit(result)

def controller(engine,emit):
    owner=engine.__dict__.get('_color_picker_owner')
    if owner is None:owner=ColorPickerController(engine,emit);engine._color_picker_owner=owner
    return owner
