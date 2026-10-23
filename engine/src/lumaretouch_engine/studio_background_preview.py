"""Source locator plus real production before/after. Latest-wins prepare jobs.

Displayed PNGs are never parameters. The source canvas is deliberately uncropped,
unwarped and labelled; normalized strokes cannot accidentally follow final warp.
An exact ready preview must be delivered and acknowledged before one commit.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import base64
import io
import json
import re
import threading
import numpy as np
from . import studio_background_state as S,studio_background_runtime as R
from .ops.studio_background import prepare
from .effect_recovery_preview import image
MAX_REVIEW_BYTES=10*1024*1024


def ident(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{32}',value) or int(value,16)==0:
        raise ValueError('背景预览或会话身份无效')
    return value


def context(engine):
    return engine._source_patch_controller().capture._context()


def _array_key(value):
    if value is None:return None
    if type(value) is not np.ndarray or value.dtype!=np.float32 or not np.isfinite(value).all():
        raise ValueError('背景预览输入或准备场不是有效 float32 数据')
    digest=sha256()
    for row in value:digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return (tuple(value.shape),str(value.dtype),digest.hexdigest())


def _recipe_key(value):
    return json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))


def capture_inputs(engine,value):
    """Freeze exactly the pre-repair bytes measured by the existing solver.

    Document revisions alone cannot detect a replaced composite or in-place
    semantic field mutation. These internal proofs never come from the UI.
    """
    from .creative_derived_source import record
    value=S.check(value)
    derived=record(engine) is not None
    if derived:
        from .creative_derived_studio import preview
        owned,source,before=preview(engine,value)
        background=None if owned is None else owned['mask']
    else:
        value=R.verify(engine,value);before=R.key(engine,value)
        source=engine._vram.src_f32[0].permute(1,2,0).detach().cpu().numpy()
        background=R.semantic(engine,value)
    source=np.array(source,copy=True)
    if background is not None:background=np.array(background,copy=True)
    proof={'derived':derived,'runtime_key':before,'recipe':_recipe_key(value),
           'source_pixels':_array_key(source),'background_pixels':_array_key(background)}
    if source.shape!=(engine._vram.h,engine._vram.w,3):
        raise ValueError('背景预览源图尺寸与实际管线不一致')
    if background is not None and (background.shape!=source.shape[:2] or np.any((background<0)|(background>1))):
        raise ValueError('背景预览语义范围与实际源图不一致')
    if R.key(engine,value)!=before:raise ValueError('背景预览源图或分析在捕获时变化')
    source.setflags(write=False)
    if background is not None:background.setflags(write=False)
    return proof,source,background


def _prepared_key(prepared,shape):
    from .studio_background_stage import check_prepared
    check_prepared(prepared,shape)
    if set(prepared['masks'])!={'background','floor','protect','intrusion','blemish'}:
        raise ValueError('背景定位蒙版缺失或包含未知目标')
    for mask in prepared['masks'].values():
        if (type(mask) is not np.ndarray or mask.dtype!=np.float32 or mask.shape!=tuple(shape)
                or not np.isfinite(mask).all() or np.any((mask<0)|(mask>1))):
            raise ValueError('背景定位蒙版与准备来源不一致')
    return (tuple((group,tuple((name,_array_key(value)) for name,value in sorted(prepared[group].items())))
                  for group in ('fields','recovery','masks')),
            _recipe_key({'analysis':prepared['analysis'],'method':prepared['method']}))


def _prepare_owned(source,value,background,proof,stop):
    if (_array_key(source)!=proof['source_pixels'] or _array_key(background)!=proof['background_pixels']
            or _recipe_key(value)!=proof['recipe']):
        raise ValueError('背景工作输入已不属于捕获的预览')
    prepared=prepare(source,value,semantic_background=background,cancelled=stop.is_set)
    if (_array_key(source)!=proof['source_pixels'] or _array_key(background)!=proof['background_pixels']
            or _recipe_key(value)!=proof['recipe']):
        raise ValueError('背景计算修改了其捕获输入')
    prepared_key=_prepared_key(prepared,source.shape[:2])
    for group in ('fields','recovery','masks'):
        for value in prepared[group].values():value.setflags(write=False)
    return {'input_proof':deepcopy(proof),'prepared':prepared,'prepared_key':prepared_key}


def _stage_key(stage):
    def signature(tensor):
        return (id(tensor),tensor.data_ptr(),int(tensor._version),tuple(tensor.shape),
                str(tensor.dtype),str(tensor.device))
    return (id(stage),tuple(stage.shape),stage.required,stage.suspended,
            tuple((group,tuple((name,signature(value)) for name,value in sorted(getattr(stage,group).items())))
                  for group in ('fields','recovery')),_recipe_key(stage.analysis))


def png(a,dimensions):
    from PIL import Image
    picture=Image.fromarray(a,'RGBA' if a.shape[2]==4 else 'RGB').resize(dimensions,Image.Resampling.BILINEAR)
    buffer=io.BytesIO();picture.save(buffer,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')


def render(engine,stage,prepared,target):
    from .fabric_controller import sync as fabric
    from .local_mask_state import sync as masks
    from .local_grade_runtime import sync as grades
    from .effect_recovery_runtime import sync as recovery
    from .manual_liquify_runtime import sync as manual
    fabric(engine);masks(engine,strict=True);grades(engine,strict=True);recovery(engine,strict=True);manual(engine,strict=True);R.sync(engine,strict=False)
    from .sky_replacement_runtime import sync as sky
    sky(engine,strict=True)
    from .optics_runtime import sync as optics
    optics(engine,strict=True)
    pipe=engine._vram;old=pipe.studio_background
    paused=bool(old.required and old.suspended)
    if paused:
        from .studio_background_stage import StudioBackgroundStage
        pipe.studio_background=StudioBackgroundStage(pipe.device,(pipe.h,pipe.w))
    strength,channel=engine._retouch_render_args();presentation=engine._frame_presentation()
    try:
        before,dimensions=image(pipe.retouch(strength,channel=channel,**engine._params),presentation)
        pipe.studio_background=stage
        after,other=image(pipe.retouch(strength,channel=channel,**engine._params),presentation)
        if other!=dimensions:raise ValueError('背景效果构图在预览中变化')
    finally:pipe.studio_background=old
    from .quant import quantize_t
    raw=quantize_t(pipe.src_f32[0].permute(1,2,0)).cpu().numpy()
    scale=min(1.,800/max(pipe.h,pipe.w));source_size=(max(1,round(pipe.w*scale)),max(1,round(pipe.h*scale)))
    if target.startswith('recover_'):weight=prepared['recovery'][target[len('recover_'):]]
    else:weight=prepared['masks'][target]
    rgba=np.zeros((pipe.h,pipe.w,4),np.uint8);rgba[...,0]=255;rgba[...,1]=80;rgba[...,3]=np.round(np.clip(weight,0,1)*150).astype(np.uint8)
    result={'before':before,'after':after,'source':png(raw,source_size),'mask':png(rgba,source_size),
            'width':dimensions[0],'height':dimensions[1],'source_width':source_size[0],'source_height':source_size[1],
            'domain':'source-normalized','review_domain':'production-output','quality':'proxy-render-srgb8',
            'target':target,'analysis':prepared['analysis'],
            'note':('原有背景效果已暂停；调整前画面仅供修复对比，不可作为省略效果的导出。' if paused else '')+'左侧为未裁剪、未液化原图定位与蒙版；右侧为真实全效果输出。全尺寸导出重新分析原始像素。'}
    if len(json.dumps(result))>MAX_REVIEW_BYTES:raise ValueError('背景照片预览超过 10 MiB')
    return result


class StudioPreview:
    def __init__(self,engine,emit):
        self.engine,self.emit=engine,emit;self.session=None;self.record=None;self.job=None;self.latest=None
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='studio-background')
    def cancel(self):
        if self.job:self.job['stop'].set()
        self.session=self.record=self.latest=None
    def close(self):
        self.cancel();self.pool.shutdown(wait=True,cancel_futures=True);self.job=None
    def matching(self,p):
        metadata,spec=context(self.engine);s=self.session
        if s is None or s['id']!=p.get('session_id') or s['metadata']!=metadata or s['spec']!=spec or metadata['document_id']!=p.get('document_id'):
            raise ValueError('背景定位源图或编辑版本变化，请重新进入')
        source_proof,_,_=capture_inputs(self.engine,S.empty())
        if s['source_proof']!=source_proof:
            raise ValueError('背景定位的实际像素来源或修补输入已变化，请重新进入')
        return s
    def verify_inputs(self,record):
        actual,_,_=capture_inputs(self.engine,record['value'])
        if actual!=record['input_proof']:
            raise ValueError('背景预览的来源、参数或语义范围已变化，旧计算结果不可提交')
    def verify_record(self,p):
        self.matching(p);record=self.record
        if record is None or record['request']['preview_id']!=p.get('preview_id') or self.job or self.latest:
            raise ValueError('背景预览已被替代')
        self.verify_inputs(record)
        if (_prepared_key(record['prepared'],(self.engine._vram.h,self.engine._vram.w))!=record['prepared_key']
                or _stage_key(record['stage'])!=record['stage_key']
                or record['stage'].verified_source_key!=record['input_proof']['runtime_key']):
            raise ValueError('背景已显示效果场发生变化，请重新预览')
        return record
    def event(self,p,**values):
        return {'event':'studio_background_preview','protocol':1,**{k:p.get(k) for k in ('preview_id','session_id','document_id')},**values}
    def handle(self,p):
        try:
            action=p.get('action');fields={'cmd','action','preview_id','session_id','document_id'}|({'mutation'} if action=='preview' else set())
            if set(p)!=fields or p['cmd']!='studio_background_preview' or action not in ('preview','presented','cancel'):
                raise ValueError('背景预览命令字段无效')
            ident(p['preview_id']);ident(p['session_id'])
            if action=='cancel':
                if self.session and self.session['id']==p['session_id']:self.cancel()
                self.emit(self.event(p,state='cancelled',success=True));return
            if action=='preview':
                if len(json.dumps(p,allow_nan=False))>512*1024:raise ValueError('背景配方请求超过 512 KiB')
                m=p['mutation'];viewing=type(m) is dict and m.get('action')=='view'
                if type(m) is not dict or set(m)!=({'action','target'} if viewing else {'action','target','proposal'}) or m.get('action') not in ('view','replace') or m['target'] not in S.TARGETS:
                    raise ValueError('背景预览修改字段无效')
                if self.session is None or self.session['id']!=p['session_id']:
                    if not viewing:raise ValueError('请先显示当前原图定位与真实效果')
                    self.cancel();metadata,spec=context(self.engine)
                    if metadata['document_id']!=p['document_id']:raise ValueError('背景照片已切换')
                    source_proof,_,_=capture_inputs(self.engine,S.empty())
                    self.session={'id':p['session_id'],'metadata':metadata,'spec':spec,'shown':False,'source_proof':source_proof}
                session=self.matching(p)
                if not viewing and not session['shown']:raise ValueError('原图定位画面尚未确认显示')
                value=S.check(getattr(self.engine,'_studio_background',None)) if viewing else S.bind_proposal(self.engine,m['proposal'])
                input_proof,source,background=capture_inputs(self.engine,value)
                if self.job:self.job['stop'].set()
                self.record=None;self.latest={'request':deepcopy(p),'value':deepcopy(value),'committable':not viewing,
                    'input_proof':input_proof,'source':source,'background':background}
                self.tick()
            else:
                record=self.verify_record(p)
                record['presented']=True;self.session['shown']=True
                self.emit(self.event(p,state='presented',success=True))
        except Exception as error:
            self.cancel();self.emit(self.event(p,state='failed',success=False,error=str(error)[:2000]))
    def tick(self):
        if self.job and self.job['future'].done():
            job,self.job=self.job,None
            if not job['stop'].is_set() and self.session is not None and self.latest is None:
                p=job['request']
                try:
                    self.matching(p);self.verify_inputs(job);outcome=job['future'].result()
                    if outcome['input_proof']!=job['input_proof']:
                        raise ValueError('背景计算返回了其他预览的输入证明')
                    prepared=outcome['prepared'];prepared_key=outcome['prepared_key']
                    if _prepared_key(prepared,(self.engine._vram.h,self.engine._vram.w))!=prepared_key:
                        raise ValueError('背景准备场在完成前变化')
                    stage=R.prepare_stage(self.engine,job['value'],prepared=prepared)
                    if stage.verified_source_key!=job['input_proof']['runtime_key']:
                        raise ValueError('背景准备场不能重新绑定到变化后的来源')
                    stage_key=_stage_key(stage)
                    result=render(self.engine,stage,prepared,p['mutation']['target'])
                    self.matching(p);self.verify_inputs(job)
                    if (_stage_key(stage)!=stage_key
                            or _prepared_key(prepared,(self.engine._vram.h,self.engine._vram.w))!=prepared_key):
                        raise ValueError('背景准备场在显示过程中变化')
                    self.record={**{k:v for k,v in job.items() if k not in ('future','source','background')},
                        'stage':stage,'stage_key':stage_key,'prepared':prepared,'prepared_key':prepared_key,'presented':False}
                    self.emit(self.event(p,state='ready',success=True,result=result,
                        recipe_document_id=self.session['metadata']['recipe_document_id'],recipe_revision=self.session['metadata']['recipe_revision']))
                except Exception as error:
                    self.cancel();self.emit(self.event(p,state='failed',success=False,error=str(error)[:2000]))
        if self.job is None and self.latest is not None:
            job,self.latest=self.latest,None;stop=threading.Event()
            try:
                self.matching(job['request']);self.verify_inputs(job)
                job.update(stop=stop,future=self.pool.submit(_prepare_owned,job['source'],deepcopy(job['value']),
                    job['background'],deepcopy(job['input_proof']),stop));self.job=job
            except Exception as error:
                self.cancel();self.emit(self.event(job['request'],state='failed',success=False,error=str(error)[:2000]))
    def prepare(self,p):
        record=self.verify_record(p)
        if not record['presented'] or not record['committable']:
            raise ValueError('请先更新并查看本次背景效果，再确定；旧预览不能提交')
        value=R.verify(self.engine,record['value'])
        if record['stage'].verified_source_key!=R.key(self.engine,value):raise ValueError('背景准备效果的来源已变化')
        return deepcopy(value),record['stage']


def controller(engine,emit):
    owner=engine.__dict__.get('_studio_background_preview_owner')
    if owner is None:owner=engine._studio_background_preview_owner=StudioPreview(engine,emit)
    return owner
