"""Producer-owned true-pixel before/after and immutable pre-perspective guides."""
from copy import deepcopy
from types import SimpleNamespace
import json
from . import optics_state as S, optics_runtime as R, optics_lensfun as L, local_mask_state as M
from .optics_stage import OpticsStage
from .optics_perspective import automatic, solve_guides
from .effect_recovery_preview import image, MAX_REVIEW_BYTES
from .manual_liquify_preview import ident


def context(engine):
    return engine._source_patch_controller().capture._context()


def upstream(engine):
    from .studio_background_runtime import sync as studio
    from .fabric_controller import sync as fabric
    from .local_mask_state import sync as masks
    from .local_grade_runtime import sync as grades
    from .effect_recovery_runtime import sync as recovery
    from .manual_liquify_runtime import sync as liquify
    fabric(engine); masks(engine,strict=True); grades(engine,strict=True); recovery(engine,strict=True); liquify(engine,strict=True); studio(engine,strict=True)
    strength,channel = engine._retouch_render_args()
    return engine._vram.retouch(strength,channel=channel,render_stage='optics-input',**engine._params)


def guide_value(value):
    value = deepcopy(value); value['perspective'] = S.empty()['perspective']; value['lens']['crop_lock'] = False
    return S.check(value)


def mutate(engine, value, mutation, pixels, source_binding):
    if type(mutation) is not dict: raise ValueError('镜头/透视修改必须是对象')
    value = S.check(value); action = mutation.get('action'); shape = pixels.shape[-2:]
    fields = {'view':{'action'},'reset':{'action'},'set':{'action','section','key','value'},
              'auto':{'action','mode'},'guides':{'action','guides'},'profile':{'action','candidate','metadata'},'find_profile':{'action','metadata'}}
    if action not in fields or set(mutation)!=fields[action]: raise ValueError('镜头/透视修改字段无效')
    extra = {}
    if action=='reset': value = S.empty()
    elif action=='set':
        section,key = mutation['section'],mutation['key']
        allowed = {'lens':{'enabled','distortion','vignette','midpoint','crop_lock'},'perspective':{*S.MANUAL,'show_guides','crop_lock'}}
        if section not in allowed or key not in allowed[section]: raise ValueError('此镜头/透视字段不能直接修改')
        if section=='lens' and key in ('enabled','distortion') and value['perspective']['mode']!='off':
            raise ValueError('镜头几何改变前请先关闭自动/引导透视，再重新分析或放置引导线，避免改变原线条含义')
        value[section][key] = mutation['value']
    elif action=='profile':
        if value['perspective']['mode']!='off': raise ValueError('更换镜头前请先关闭自动/引导透视，之后重新分析')
        value['lens']['profile'] = L.resolve(mutation['candidate'],mutation['metadata'],shape)
        value['lens']['enabled'] = True
    elif action=='find_profile':
        extra['candidates'] = L.candidates(mutation['metadata'])
        extra['profile_metadata'] = mutation['metadata']
    elif action in ('auto','guides'):
        if action=='auto' and mutation['mode']=='off':
            value['perspective'].update(mode='off',matrix=S.IDENTITY.copy(),analysis=None,guides=[])
        else:
            value['source'] = source_binding
            lens_stage = OpticsStage(guide_value(value),shape)
            if action=='guides':
                guides = [S.guide(g) for g in mutation['guides']]
                if len(guides)>4: raise ValueError('最多 4 条引导线')
                import numpy as np
                for g in guides:
                    a,b = np.array(g['start']),np.array(g['end'])
                    lens_stage.inverse_points([a+(b-a)*t for t in np.linspace(0,1,17)])
                matrix,analysis = solve_guides(guides,shape)
                value['perspective'].update(mode='guided',matrix=matrix,analysis=analysis,guides=guides)
            else:
                rendered = lens_stage.apply(pixels)[0].permute(1,2,0).detach().cpu().numpy()
                matrix,analysis = automatic(rendered,mutation['mode'])
                value['perspective'].update(mode=mutation['mode'],matrix=matrix,analysis=analysis,guides=[])
    value['source'] = source_binding if S.source_bound(value) else None
    return S.check(value),extra


class OpticsPreview:
    def __init__(self, engine, emit): self.engine,self.emit,self.session,self.record = engine,emit,None,None
    def cancel(self): self.session = self.record = None
    def close(self): self.cancel()
    def matching(self,p):
        metadata,spec = context(self.engine); session = self.session
        if session is None or p.get('session_id')!=session['id'] or p.get('document_id')!=metadata['document_id'] or metadata!=session['metadata'] or spec!=session['spec']:
            raise ValueError('镜头/透视照片、画布或版本已变化，请重新进入')
        if M.file_stamp(session['path'])!=session['stamp']: raise ValueError('镜头/透视源图已变化')
        return session
    def event(self,p,**values):
        return {'event':'optics_preview','protocol':1,**{k:p.get(k) for k in ('preview_id','session_id','document_id')},**values}
    def handle(self,p):
        try:
            action = p.get('action'); fields = {'cmd','action','preview_id','session_id','document_id'}|({'mutation'} if action=='preview' else set())
            if set(p)!=fields or p['cmd']!='optics_preview' or action not in ('preview','presented','cancel'): raise ValueError('镜头/透视预览命令字段无效')
            ident(p['preview_id']); ident(p['session_id'])
            if action=='cancel':
                if self.session and self.session['id']==p['session_id']: self.cancel()
                self.emit(self.event(p,state='cancelled',success=True)); return
            if action=='presented':
                self.matching(p)
                if self.record is None or self.record['request']['preview_id']!=p['preview_id']: raise ValueError('镜头/透视预览已替换')
                self.record['presented'] = True; self.session['shown'] = True
                self.emit(self.event(p,state='presented',success=True)); return
            if len(json.dumps(p,allow_nan=False).encode())>64*1024: raise ValueError('镜头/透视参数超过预算')
            viewing = p['mutation']=={'action':'view'}
            resetting = p['mutation']=={'action':'reset'}
            if self.session is None or self.session['id']!=p['session_id']:
                if not viewing and not resetting: raise ValueError('必须先展示真实参考画面才能编辑')
                self.cancel(); metadata,spec = context(self.engine)
                if metadata['document_id']!=p['document_id']: raise ValueError('照片已切换')
                row = self.engine._docs[self.engine._doc_index]; stamp = M.file_stamp(row['path']); binding = M.bind_source(self.engine)
                if M.file_stamp(row['path'])!=stamp: raise ValueError('源图身份读取期间变化')
                self.session = {'id':p['session_id'],'metadata':metadata,'spec':spec,'path':row['path'],'stamp':stamp,'binding':binding,'shown':False}
            session = self.matching(p)
            if not viewing and not resetting and not session['shown']: raise ValueError('参考画面尚未展示完成')
            self.record = None
            pixels = upstream(self.engine)
            value,extra = mutate(self.engine,session.get('draft',getattr(self.engine,'_optics',None)),p['mutation'],pixels,session['binding'])
            stage = R.prepare_stage(self.engine,value)
            pipe = self.engine._vram; presentation = self.engine._frame_presentation()
            before,dimensions = image(pipe.apply_geometry(pixels),presentation)
            after,after_dimensions = image(pipe.apply_geometry(stage.apply(pixels)),presentation)
            if dimensions!=after_dimensions: raise ValueError('镜头/透视预览构图不一致')
            locator = OpticsStage(guide_value(value),(pipe.h,pipe.w))
            input_image,input_dimensions = image(locator.apply(pixels),SimpleNamespace(width=pipe.w,height=pipe.h))
            if len(before)+len(after)+len(input_image)>MAX_REVIEW_BYTES: raise ValueError('镜头/透视预览超过 6 MiB')
            self.matching(p)
            committable = value != S.check(getattr(self.engine,'_optics',None))
            result = {'committable':committable,'before':before,'after':after,'input':input_image,'width':dimensions[0],'height':dimensions[1],
                      'input_width':input_dimensions[0],'input_height':input_dimensions[1],'domain':S.DOMAIN,'quality':'proxy-render-srgb8',
                      'recipe':value,'crop_zoom':stage.zoom,'note':'右侧为真实全效果；引导线绘制在独立的镜头校正后、透视/裁剪之前画面，不从变形后的显示猜坐标',**extra}
            session['draft'] = deepcopy(value)
            self.record = {'request':deepcopy(p),'value':value,'stage':stage,'presented':False,'committable':committable}
            self.emit(self.event(p,state='ready',success=True,result=result,recipe_document_id=session['metadata']['recipe_document_id'],recipe_revision=session['metadata']['recipe_revision']))
        except Exception as error:
            self.record = None
            self.emit(self.event(p,state='failed',success=False,error=str(error)[:2000]))
    def prepare(self,p):
        self.matching(p); record = self.record
        if record is None or record['request']['preview_id']!=p.get('preview_id') or not record['presented'] or not record['committable']: raise ValueError('真实镜头/透视结果尚未展示或已过期')
        return R.verify(self.engine,record['value']),record['stage']


def controller(engine,emit):
    owner = engine.__dict__.get('_optics_preview_owner')
    if owner is None: owner = engine._optics_preview_owner = OpticsPreview(engine,emit)
    return owner
