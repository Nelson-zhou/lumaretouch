# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen capture → explicit analyze → review → owned-field commit.

No ordinary slider starts inference. Cancel/close invalidates only the pending
proposal. Parameter/mask edits affect this group only and retain unrelated edits.
"""
from copy import deepcopy
import base64
import io
import json
import uuid
from . import semantic_colour_state as S, semantic_colour_runtime as R, semantic_colour_masks as M, semantic_colour_assets as MA


def png(array):
    from PIL import Image
    data=io.BytesIO();Image.fromarray(array).save(data,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(data.getvalue()).decode('ascii')

class SemanticColourController:
    def __init__(self,engine,emit):
        self.engine=engine;self.emit=emit;self.session=None;self.job=None;self.review=None;self.write_started=False

    def context(self):
        e=self.engine
        if not e._image_loaded or not 0<=e._doc_index<len(e._docs):return None
        v=e._document_versions().version(e._docs[e._doc_index])
        return {'document_id':v.document_id,'revision':str(v.revision)}

    def close(self):
        if self.job is not None and self.job.state=='running':self.job.cancel()
        self.job=None;self.review=None;self.session=None

    def shutdown(self):
        self.close()
        workflow=getattr(self,'workflow',None)
        if workflow is not None:workflow.close()

    def tick(self):
        workflow=getattr(self,'workflow',None)
        if workflow is not None:workflow.tick()
        if self.session is not None and self.session["context"]!=self.context():self.close()
        if self.job is not None and self.job.state=="running":self.job.poll()

    def _guard(self,expected):
        e=self.engine;reason=e._guard_editable('AI 语义追色')
        if reason:raise ValueError(reason)
        if expected!=self.context():raise ValueError('照片或编辑版本已变化，请刷新；未写入旧结果')

    def capture(self,reference,expected,token,*,cancelled=lambda:False):
        self._guard(expected);S.identifier(token)
        if cancelled():raise InterruptedError("AI 追色冻结已取消")
        if len(token)!=32:raise ValueError('冻结请求身份无效')
        self.close()
        from .semantic_colour_canvas import from_reference
        from .semantic_colour_capture import render,candidate_key
        from .render_snapshot import own_render_inputs
        from .semantic_colour_analysis import view
        from . import local_mask_state as LM
        e=self.engine;row=e._docs[e._doc_index]
        # Reference is opened first so the target renderer's admission includes
        # that retained full-float allocation rather than double-spending RAM.
        from . import reference_color_assets as A
        current=S.check(getattr(e,S.KEY,None))
        if current['reference']==reference:A.hydrate(reference,getattr(e,'_semantic_colour_bundle',None))
        ref=from_reference(reference)
        if cancelled():raise InterruptedError('AI 追色冻结已取消')
        from .semantic_colour_host import OWNED
        state=own_render_inputs({k:v for k,v in e._capture_state().items() if k not in OWNED},max_asset_bytes=512*1024*1024).value
        target=render(e,row,state,expected['document_id'],expected['revision'],cancelled=cancelled)
        self._guard(expected)
        self.session={'token':token,'reference':deepcopy(reference),'target':target,'reference_frame':ref,
            'context':deepcopy(expected),'row':row,'source_stamp':LM.file_stamp(row['path'])}
        rimage,_=view(ref);timage,_=view(target)
        return {'session_id':token,'context':expected,'target':{'binding':target.binding,'image':png(timage)},
                'reference':{'binding':ref.binding,'image':png(rimage)},
                'target_selection':M.create('target_selection','目标选区',target.binding),
                'reference_selection':M.create('reference_selection','样片选区',ref.binding),
                'notice':'双图已按完整渲染冻结；这里是选择蒙版用的分析预览，最终输出不会降采样。'}

    def _session(self,token):
        s=self.session
        if s is None or s['token']!=token:raise ValueError('AI 追色双图会话已关闭或被新请求替代')
        self._guard(s['context'])
        from . import local_mask_state as LM
        if self.engine._docs[self.engine._doc_index] is not s['row'] or LM.file_stamp(s['row']['path'])!=s['source_stamp']:
            raise ValueError('AI 追色源文件或文档已变化，请重新冻结')
        return s

    def start(self,token,mode,strengths,reference_selection,target_selection):
        s=self._session(token)
        if self.job is not None and self.job.state=='running':raise ValueError('已有 AI 追色任务进行中，请取消或等待')
        from .semantic_colour_job import SemanticColourJob
        self.review=None;self.job=SemanticColourJob(s['reference_frame'],s['target'],reference_asset=s['reference'],
            mode=mode,strengths=strengths,reference_selection=reference_selection,target_selection=target_selection)
        return {'state':'running','session_id':token}

    def poll(self,token):
        self._session(token)
        if self.job is None:return {'state':'captured','session_id':token}
        self.job.poll()
        out={'state':self.job.state,'session_id':token,'error':self.job.error}
        if self.job.state=='ready':
            from .semantic_colour_review import public
            self.review=self.job.result;out['review']=public(self.review)
            if 'preview' not in self.session:
                import numpy as np
                from .semantic_colour_stage import SemanticColourStage
                from .semantic_colour_analysis import view
                _,samples=view(self.session['target'])
                after=SemanticColourStage(self.review['recipe'],binding=self.session['target'].binding).apply_np(samples)
                self.session['preview']={'before':png(np.rint(np.clip(samples,0,1)*255).astype(np.uint8)),
                    'after':png(np.rint(np.clip(after,0,1)*255).astype(np.uint8)),
                    'notice':'全精度原画布的空间采样检查预览；非整幅摄影质量验收。'}
            out['preview']=self.session['preview']
        return out

    def commit(self,token,proof,reviewed):
        s=self._session(token)
        if reviewed is not True or self.review is None or self.review['proof']!=proof:raise ValueError('请检查冻结前后图及诊断，并明确确认应用此结果')
        from .semantic_colour_review import verify,saved_review
        from . import reference_color_assets as A
        path=A.cache_root()/(s['reference']['asset_id']+'.npz')
        if path.is_symlink() or A._hash(path)!=s['reference']['asset_id']:raise ValueError('审核后样片资源发生变化')
        recipe=verify(self.review,target_binding=s['target'].binding,reference=s['reference'])
        recipe['last_review']=saved_review(self.review)
        from .semantic_colour_canvas import reference_admission
        reference_admission(s['reference'],include_bundle=True)
        bundle=A.bundle(s['reference'])
        result=self._install(recipe,bundle,label='AI 语义追色应用',expected=s['context'])
        self.close();return result

    def _install(self,recipe,bundle,*,label,expected):
        e=self.engine;self._guard(expected);recipe=S.check(recipe)
        recipe,mask_assets=MA.retain(recipe,getattr(e,MA.KEY,{}))
        before=e._history_capture();old=S.check(getattr(e,S.KEY,None));old_bundle=getattr(e,'_semantic_colour_bundle',None);old_masks=getattr(e,MA.KEY,{})
        e._document_versions().check_advance(e._docs[e._doc_index])
        self.write_started=True
        try:
            setattr(e,S.KEY,recipe);e._semantic_colour_bundle=bundle;setattr(e,MA.KEY,mask_assets)
            R.sync(e,strict=True);frame=e._write_current_frame('semantic_colour')
        except BaseException:
            setattr(e,S.KEY,old);e._semantic_colour_bundle=old_bundle;setattr(e,MA.KEY,old_masks);R.sync(e)
            raise
        e._document_versions().advance(e._docs[e._doc_index]);e._remember_current()
        e._history_record(label,before,coalesce=False);e._project_dirty=True
        self.emit({**frame,'doc_state':e.doc_state()})
        return {'state':'applied','context':self.context(),'report':R.report(e)}

    def edit(self,operation,payload,expected):
        self._guard(expected);recipe=S.check(getattr(self.engine,S.KEY,None));bundle=getattr(self.engine,'_semantic_colour_bundle',None)
        if operation=='reset':recipe=S.empty();bundle=None
        elif operation=='strengths':
            if type(payload) is not list or len(payload)!=3:raise ValueError('需要三个独立程度')
            recipe['strengths']=[S.number(v,0,200) for v in payload]
        elif operation=='enabled':
            if type(payload) is not bool:raise ValueError('AI 追色开关无效')
            recipe['enabled']=payload
        elif operation in ('group_parameters','group_enabled','group_reset','group_delete'):
            if type(payload) is not dict or 'id' not in payload:raise ValueError('AI 追色组操作缺少身份')
            group=next((g for g in recipe['groups'] if g['id']==payload['id']),None)
            if group is None:raise ValueError('AI 追色组已不存在')
            if operation=='group_parameters':group['parameters']=S.parameters(payload['parameters'])
            elif operation=='group_enabled':
                if type(payload['enabled']) is not bool:raise ValueError('分组开关无效')
                group['enabled']=payload['enabled']
            elif operation=='group_reset':group['parameters']=deepcopy(group['baseline'])
            else:
                if group['id']=='global':raise ValueError('全图基础组可关闭或归零，不能伪装为可删除局部蒙版')
                recipe['groups']=[g for g in recipe['groups'] if g['id']!=group['id']]
                recipe['masks']=[m for m in recipe['masks'] if m['id']!=group['mask_id']]
                if not recipe['groups']:recipe=S.empty();bundle=None
        elif operation=='mask_objects':
            if type(payload) is not dict or set(payload)!={'id','objects'}:raise ValueError('蒙版编辑字段无效')
            mask=next((m for m in recipe['masks'] if m['id']==payload['id']),None)
            if mask is None:raise ValueError('蒙版已删除')
            mask['objects']=deepcopy(payload['objects']);M.check(mask)
        else:raise ValueError('未知 AI 追色编辑操作')
        result=self._install(recipe,bundle,label='AI 追色 '+operation,expected=expected)
        self.close();return result

    def mask_overlay(self,ident,objects=None):
        import numpy as np
        recipe=S.check(getattr(self.engine,S.KEY,None))
        mask=next((m for m in recipe['masks'] if m['id']==ident),None)
        if mask is None:raise ValueError('AI 追色蒙版已不存在')
        mask=deepcopy(mask)
        if objects is not None:mask['objects']=objects
        mask=M.check(mask);b=mask['binding'];scale=min(1.,512/max(b['width'],b['height']))
        h,w=max(1,round(b['height']*scale)),max(1,round(b['width']*scale))
        compiled=M.TileMask(mask,(h,w));success=False
        try:field=compiled.tile(0,0,w,h);success=True
        finally:compiled.close(success)
        rgba=np.empty((h,w,4),np.uint8);rgba[...,:3]=[50,220,190];rgba[...,3]=np.rint(field*170).astype(np.uint8)
        return {'image':png(rgba),'mask_id':ident,'domain':S.DOMAIN,'binding':b}

    def execute(self,command,*,cancelled=lambda:False):
        self.write_started=False
        if type(command) is not dict or len(json.dumps(command,allow_nan=False).encode())>2*1024*1024:
            raise ValueError('AI 追色命令大小或格式无效')
        action=command.get('action')
        from .semantic_colour_workflow import ACTIONS,dispatch
        if action in ACTIONS:return dispatch(self,command,cancelled=cancelled)
        fields={'state':{'action'},'capture':{'action','reference','context','session_id'},
            'start':{'action','session_id','mode','strengths','reference_selection','target_selection'},
            'poll':{'action','session_id'},'commit':{'action','session_id','proof','reviewed'},
            'mask_overlay':{'action','mask_id','objects'},'edit':{'action','operation','payload','context'},
            'cancel':{'action','session_id'}}
        if action not in fields or set(command)!=fields[action]:raise ValueError('未知 AI 追色操作或字段')
        if cancelled():raise InterruptedError('AI 追色操作已取消，未开始写入')
        if action=='state':return {'context':self.context(),'report':R.report(self.engine)}
        if action=='capture':return self.capture(command['reference'],command['context'],command['session_id'],cancelled=cancelled)
        if action=='start':return self.start(command['session_id'],command['mode'],command['strengths'],command['reference_selection'],command['target_selection'])
        if action=='poll':return self.poll(command['session_id'])
        if action=='commit':return self.commit(command['session_id'],command['proof'],command['reviewed'])
        if action=='mask_overlay':return self.mask_overlay(command['mask_id'],command['objects'])
        if action=='edit':return self.edit(command['operation'],command['payload'],command['context'])
        if self.session is not None and command['session_id']==self.session['token']:self.close()
        return {'state':'cancelled'}

def controller(engine,emit):
    owner=getattr(engine,'_semantic_colour_owner',None)
    if owner is None:owner=engine._semantic_colour_owner=SemanticColourController(engine,emit)
    return owner
