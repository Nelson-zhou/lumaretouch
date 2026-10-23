"""Bounded producer-rendered common replacement review; no bitmap parameters."""
from copy import deepcopy
import json
import math
from . import common_background_source as S,common_background_preview_source as P
from .studio_background_preview import ident
from .creative_derived_id_background import _deformation_key,_activity_key

FIELDS={'cmd','action','preview_id','session_id','document_id'}


def mutation(value):
    if type(value) is not dict:raise ValueError('Invalid common background mutation')
    if value=={'action':'clear'}:return deepcopy(value)
    if set(value)!={'action','bg','tol','softness'} or value['action']!='set':raise ValueError('Common replacement accepts deterministic key set/clear only')
    bg=value['bg']
    if type(bg) is not list or len(bg)!=3 or any(type(v) is not int or not 0<=v<=255 for v in bg):raise ValueError('Invalid background RGB color')
    for key,lo in (('tol',0.),('softness',.001)):
        v=value[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=1:raise ValueError('Invalid common key parameter')
    return deepcopy(value)


def candidate(engine,value):
    m=mutation(value)
    if m['action']=='clear':
        retained=S.check(engine._bg)
        if retained is not None:return {**deepcopy(engine._bg),'active':False,'matte':None}
        return dict(active=False,matte=None,bg=None,backend=None,tol=None,softness=None)
    from . import id_background_state as ID,studio_background_state as ST,sky_replacement_state as SKY
    if ID.active(engine._id_background) or ST.active(engine._studio_background) or SKY.check(engine._sky_replacement)['enabled']:
        raise ValueError('Close ID replacement, studio background and sky replacement before common replacement')
    key=S.capture(engine,engine._src_rgb,tol=m['tol'],softness=m['softness'])
    bg={'active':True,'matte':None,'bg':[v/255. for v in m['bg']],'backend':'color_key',
        'tol':m['tol'],'softness':m['softness'],'key_recipe':key}
    S.check(bg);return bg


def proof(engine):
    metadata,projection=engine._source_patch_controller().capture._context()
    return {'metadata':metadata,'projection':projection,'consumer':S.consumer_proof(engine),
        'geometry':_deformation_key(engine._vram),'activity':_activity_key(engine)}


def render(engine,value):
    from .effect_recovery_preview import render_current,sync_review_pipeline
    # Synchronize every actual existing effect using its established review path;
    # then temporarily replace only the common operator, never source RGB.
    pipe=engine._vram
    P.verify_live(engine)
    before,dimensions=render_current(engine)
    baseline=proof(engine)
    bg=engine._bg
    saved={key:getattr(pipe,key,None) for key in ('bg_active','bg_matte','bg_ref','_common_background_source_key',
        '_common_background_field_proof','_common_background_preserve','effect_recovery','_effect_recovery_key')}
    try:
        engine._bg=deepcopy(value);P.install(engine)
        after,after_dimensions=render_current(engine)
        if after_dimensions!=dimensions:raise ValueError('Common review framing changed')
    finally:
        engine._bg=bg
        for key,item in saved.items():setattr(pipe,key,item)
        sync_review_pipeline(engine)
    image={'before':before,'after':after,'width':dimensions[0],'height':dimensions[1],
        'domain':'production-output','quality':'proxy-render-srgb8',
        'note':'实际完整效果代理对比；完整导出在各自真实源像素上重算色键，不放大代理蒙版。复杂背景、发丝精细分割不是色键算法保证。'}
    if any(len(image[k])>4*1024*1024 for k in ('before','after')):raise ValueError('Common review exceeds image budget')
    return image,baseline


class Preview:
    def __init__(self,engine,emit):self.engine,self.emit=engine,emit;self.record=None;self.seen=set()
    def cancel(self):self.record=None
    def close(self):self.cancel()
    def event(self,p,**value):return {'event':'common_background_preview','protocol':1,**{k:p.get(k) for k in ('preview_id','session_id','document_id')},**value}
    def matching(self,p):
        r=self.record
        if r is None or any(r['request'][k]!=p.get(k) for k in ('preview_id','session_id','document_id')):
            raise ValueError('Common review identity expired')
        if proof(self.engine)!=r['proof']:raise ValueError('Common review source, fields or document changed')
        return r
    def handle(self,p):
        try:
            action=p.get('action');fields=FIELDS|({'mutation'} if action=='preview' else set())
            if set(p)!=fields or p['cmd']!='common_background_preview' or action not in ('preview','presented','cancel'):raise ValueError('Invalid common review envelope')
            ident(p['preview_id']);ident(p['session_id'])
            if p['document_id']!=self.engine._load_id:raise ValueError('Common review document changed')
            if action=='cancel':
                if self.record and self.record['request']['preview_id']==p['preview_id']:self.cancel()
                self.emit(self.event(p,state='cancelled',success=True));return
            if action=='preview':
                if p['preview_id'] in self.seen:raise ValueError('Common preview ID cannot be reused')
                if len(self.seen)>=4096:raise ValueError('Common review identity capacity reached; save and restart')
                self.seen.add(p['preview_id']);self.cancel()
                value=candidate(self.engine,p['mutation'])
                image,before=render(self.engine,value)
                if proof(self.engine)!=before:raise ValueError('Common review context changed during rendering')
                self.record={'request':deepcopy(p),'proof':before,'value':value,'presented':False,'image':image}
                self.emit(self.event(p,state='ready',success=True,image=image,
                    recipe_document_id=before['metadata']['recipe_document_id'],recipe_revision=before['metadata']['recipe_revision']))
            else:
                record=self.matching(p);record['presented']=True
                self.emit(self.event(p,state='presented',success=True,
                    recipe_document_id=record['proof']['metadata']['recipe_document_id'],recipe_revision=record['proof']['metadata']['recipe_revision']))
        except Exception as error:
            self.cancel();self.emit(self.event(p,state='failed',success=False,error=str(error)[:2000]))
    def prepare(self,p):
        r=self.matching(p)
        if not r['presented']:raise ValueError('View the exact common before/after before applying')
        return deepcopy(r['value'])


def controller(engine,emit):
    owner=engine.__dict__.get('_common_background_preview_owner')
    if owner is None:owner=engine._common_background_preview_owner=Preview(engine,emit)
    return owner
