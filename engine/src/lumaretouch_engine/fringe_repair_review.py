"""Source-owned, full-source-rendered dehalo review; drafts never change history."""
from copy import deepcopy
import base64
import io
import json
from . import fringe_repair_state as S, creative_derived_source as D
from .studio_background_preview import ident
from .history_policy import state_signature

FIELDS={'cmd','action','preview_id','session_id','document_id'}


def proof(engine):
    from .local_mask_state import file_stamp
    if engine._vram is None or not engine._doc_path:raise ValueError('Fringe review requires the actual loaded source')
    row=engine._docs[engine._doc_index]
    version=engine._document_versions().version(row)
    stamp=file_stamp(engine._doc_path)
    if row.get('_local_source_stamp')!=stamp:raise ValueError('Fringe source changed after decode')
    return {'document_id':engine._load_id,'recipe_document_id':version.document_id,'recipe_revision':str(version.revision),
        'source':D.binding(engine),'stamp':stamp,'state':state_signature(engine._history_capture())}


def image_mask(value,dimensions):
    import numpy as np
    from PIL import Image
    if value is None:raise ValueError('Fringe preview lacks actual coverage evidence')
    if hasattr(value,'detach'):value=value.detach().cpu().numpy()
    value=np.asarray(value)
    if value.ndim==4 and value.shape[:2]==(1,1):value=value[0,0]
    if value.ndim!=2 or not np.isfinite(value).all():raise ValueError('Invalid fringe review coverage')
    alpha=np.rint(np.clip(value,0,1)*120).astype(np.uint8)
    rgba=np.zeros((*alpha.shape,4),np.uint8);rgba[...,0]=255;rgba[...,3]=alpha
    picture=Image.fromarray(rgba,'RGBA').resize(dimensions,Image.Resampling.BILINEAR)
    out=io.BytesIO();picture.save(out,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode('ascii')


def render(engine,baseline,candidate):
    from .photo_grain_runtime import render_preview
    from .effect_recovery_preview import image
    before_proof=proof(engine)
    old_override=engine.__dict__.get('_fringe_repair_render_override')
    old_capture=engine.__dict__.get('_fringe_repair_capture_coverage',False)
    try:
        engine._fringe_repair_capture_coverage=True
        engine._fringe_repair_render_override=baseline
        before,size=image(render_preview(engine,pack=False),engine._frame_presentation())
        engine._fringe_repair_render_override=candidate
        engine._fringe_repair_capture_coverage=True
        engine._fringe_repair_review_coverage=None
        after,after_size=image(render_preview(engine,pack=False),engine._frame_presentation())
        if size!=after_size:raise ValueError('Fringe review framing changed')
        coverage=image_mask(engine._fringe_repair_review_coverage,size)
    finally:
        if old_override is None:engine.__dict__.pop('_fringe_repair_render_override',None)
        else:engine._fringe_repair_render_override=old_override
        engine._fringe_repair_capture_coverage=old_capture
        engine.__dict__.pop('_fringe_repair_review_coverage',None)
    if proof(engine)!=before_proof:raise ValueError('Fringe source or edits changed during review')
    pictures={'before':before,'after':after,'coverage':coverage}
    if any(len(v)>4*1024**2 for v in pictures.values()):raise ValueError('Fringe review image exceeds 4 MiB')
    return {**pictures,'width':size[0],'height':size[1],'domain':'production-output',
        'quality':'full-source-render-downsampled-srgb8',
        'note':'真实全源渲染后缩小的审核图，不是 100% 细节。添加恢复处理范围，擦除排除范围；仅修正有源图证据的新生黑白边，不保证修复已烘焙边缘。'},before_proof


class Preview:
    def __init__(self,engine,emit):self.engine,self.emit=engine,emit;self.record=None;self.session=None;self.seen=set()
    def cancel(self):self.record=None;self.session=None
    def close(self):self.cancel()
    def event(self,p,**value):return {'event':'fringe_repair_preview','protocol':1,**{k:p.get(k) for k in ('preview_id','session_id','document_id')},**value}
    def matching(self,p):
        r=self.record
        if r is None or any(r['request'][k]!=p.get(k) for k in ('preview_id','session_id','document_id')):raise ValueError('Fringe review identity expired')
        if proof(self.engine)!=r['proof']:raise ValueError('Fringe review source or upstream edits changed')
        return r
    def candidate(self,p):
        m=p['mutation'];e=self.engine
        if type(m) is not dict:raise ValueError('Invalid fringe mutation')
        if m=={'action':'enter'}:
            baseline=S.check(getattr(e,S.KEY,None));bound=proof(e)
            if baseline['source'] is not None and baseline['source']!=bound['source']:raise ValueError('Fringe coverage belongs to another source')
            self.session={'id':p['session_id'],'baseline':baseline,'proof':bound}
            return {**deepcopy(baseline),'enabled':True}
        if (set(m)!={'action','enabled','strength','reset_coverage','strokes'} or m['action']!='set'
                or type(m['reset_coverage']) is not bool):raise ValueError('Invalid fringe set fields')
        session=self.session
        if session is None or session['id']!=p['session_id'] or session['proof']!=proof(e):raise ValueError('Enter the current fringe review before editing coverage')
        from .fringe_repair_geometry import inverse_strokes
        binding=session['proof']['source'];base=deepcopy(session['baseline'])
        if m['reset_coverage']:base['coverage']['strokes']=[]
        geometry=(tuple(e._crop_rect),float(e._crop_rotation))
        strokes=inverse_strokes((binding['width'],binding['height']),geometry,m['strokes'])
        base['coverage']['strokes']+=strokes
        base.update(enabled=m['enabled'],strength=m['strength'],source=binding if base['coverage']['strokes'] else None)
        return S.check(base)
    def handle(self,p):
        try:
            action=p.get('action');fields=FIELDS|({'mutation'} if action=='preview' else set())
            if set(p)!=fields or p['cmd']!='fringe_repair_preview' or action not in ('preview','presented','cancel'):raise ValueError('Invalid fringe review envelope')
            ident(p['preview_id']);ident(p['session_id'])
            if p['document_id']!=self.engine._load_id:raise ValueError('Fringe document changed')
            if action=='cancel':
                if self.session and self.session['id']==p['session_id']:self.cancel()
                self.emit(self.event(p,state='cancelled',success=True));return
            if action=='preview':
                if p['preview_id'] in self.seen or len(self.seen)>=4096:raise ValueError('Fringe preview identity reused or capacity reached')
                if len(json.dumps(p,allow_nan=False).encode())>512*1024:raise ValueError('Fringe preview request exceeds 512 KiB')
                why=self.engine._guard_editable('fringe repair')
                if why:raise ValueError(why)
                self.seen.add(p['preview_id']);self.record=None
                value=self.candidate(p);baseline=self.session['baseline']
                rendered,context=render(self.engine,baseline,value)
                self.record={'request':deepcopy(p),'proof':context,'value':value,'presented':False}
                self.emit(self.event(p,state='ready',success=True,image=rendered,recipe=value,source=context['source'],
                    defaults={'strength':50,'min_strength':0,'max_strength':100},
                    recipe_document_id=context['recipe_document_id'],recipe_revision=context['recipe_revision']))
            else:
                record=self.matching(p);record['presented']=True
                self.emit(self.event(p,state='presented',success=True,
                    recipe_document_id=record['proof']['recipe_document_id'],recipe_revision=record['proof']['recipe_revision']))
        except Exception as error:
            self.record=None;self.emit(self.event(p,state='failed',success=False,error=str(error)[:2000]))
    def prepare(self,p):
        r=self.matching(p)
        if not r['presented']:raise ValueError('View the actual fringe result before applying')
        return deepcopy(r['value'])


def controller(engine,emit):
    owner=engine.__dict__.get('_fringe_repair_preview_owner')
    if owner is None:owner=engine._fringe_repair_preview_owner=Preview(engine,emit)
    return owner
