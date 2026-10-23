"""Latest-wins preparation with a frozen source locator and real output review.

Only a fully shown exact candidate is redeemable. Source PNG authorizes brush
coordinates, output PNG is review only, neither is the export pixel source.
Preparation runs off sequence; production rendering and mutations stay on it.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import base64
import io
import json
import re
import threading
import numpy as np
from . import sky_replacement_state as S, sky_replacement_runtime as R, sky_replacement_assets as A, local_mask_state as B
from .sky_replacement_stage import SkyReplacementStage
from .effect_recovery_preview import image, MAX_REVIEW_BYTES


def ident(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{32}',value) or int(value,16) == 0:
        raise ValueError('天空会话或预览身份无效')
    return value


def context(engine):
    return engine._source_patch_controller().capture._context()


def _recipe_key(value):
    return json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))


def _array_key(value):
    if value is None:return None
    if (type(value) is not np.ndarray or value.dtype not in (np.float32,np.uint8,np.uint16)
            or not np.isfinite(value).all()):
        raise ValueError('天空预览输入或准备场不是有效像素数据')
    digest=sha256()
    for row in value:digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return tuple(value.shape),str(value.dtype),digest.hexdigest()


def capture_inputs(engine):
    """Prove actual source bytes, independently of a repairable linked asset.

    The physical original remains provenance for a returned creative source;
    its hash is never used to bind the manual source-domain vectors.
    """
    from . import creative_derived_source as D
    pipe=engine._vram;derived=D.record(engine) is not None
    if derived:
        from . import creative_derived_sky as C
        _,pixels,key=C.preview(engine,S.empty());binding=D.binding(engine)
    else:
        row=engine._docs[engine._doc_index]
        if row.get('_local_source_stamp')!=B.file_stamp(row['path']):
            raise ValueError('天空定位源照片自解码后变化')
        binding=B.bind_source(engine);key=R.stage_key(engine,S.empty())
        pixels=pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy()
    pixels=np.array(pixels,copy=True)
    if pixels.dtype!=np.float32 or pixels.shape!=(pipe.h,pipe.w,3):
        raise ValueError('天空定位像素与实际源图管线不一致')
    proof={'derived':derived,'source':deepcopy(binding),'runtime_key':key,'pixels':_array_key(pixels)}
    after=C.key(engine,S.empty()) if derived else R.stage_key(engine,S.empty())
    if after!=key:raise ValueError('天空定位来源在捕获期间变化')
    pixels.setflags(write=False)
    return proof,pixels


def validate_draft(engine,raw,binding):
    """Validate manual intent without resolving a new asset choice on sequence."""
    from . import creative_derived_source as D
    if type(raw) is not dict or set(raw)!=set(S.editable(S.empty())):
        raise ValueError('天空草稿字段无效')
    # Validate the original chooser envelope too, before neutralizing the link.
    path=raw['asset_path'];choice=raw['asset_choice']
    if path is not None:
        import os
        if type(path) is not str or not os.path.isabs(path) or '\x00' in path or len(path)>4096:
            raise ValueError('天空素材必须为明确选择的本地绝对路径')
    if choice is not None:ident(choice)
    neutral={**deepcopy(raw),'enabled':False,'asset_path':None,'asset_choice':None}
    value=S.from_editable(neutral,binding,None)
    if D.record(engine) is not None:
        from .creative_derived_sky import validate
        validate(value,binding)


def _asset_key(asset):
    return None if asset is None else (_recipe_key(asset.binding),tuple(asset.stamp),_array_key(asset.pixels))


def _immutable_key(packet):
    if packet is None:return None
    from .sky_semantic.immutable_input import key
    return key(packet)


def _semantic_stamp():
    """Missing installations invalidate effects, not the disable/remove UI."""
    from .sky_semantic.manifest import installation_stamp
    try:
        return installation_stamp(),None
    except Exception as error:
        return None,(type(error).__name__,str(error)[:2000])


def _capture_semantic(engine,binding):
    """Freeze canonical inference bytes, not the unwarped display locator.

    An unavailable canonical input is retained as an explicit repair-only
    error. Neither that error nor a disabled draft permits original-file ML.
    """
    from .creative_derived_sky import semantic_input
    from .sky_semantic.immutable_input import check
    try:
        return check(semantic_input(engine),binding),None
    except Exception as error:
        return None,str(error)[:2000] or '不可变天空语义输入无法验证'


def _semantic_transport(job):
    """Enforce the source choice even if work() bypasses UI admission."""
    packet=job.get('immutable_input');error=job.get('immutable_error')
    if not job['source_proof']['derived']:
        if packet is not None or error is not None:
            raise ValueError('原照片天空任务不能携带其他不可变来源')
        return
    if job['source_path'] is not None:
        raise ValueError('不可变天空任务禁止使用原照片路径执行自动选区')
    descriptor=job['raw'].get('semantic')
    if descriptor is None:
        if packet is not None or error is not None:
            raise ValueError('手动天空任务不能保留其他自动选区输入')
        return
    from .sky_semantic.state import check as check_descriptor
    descriptor=check_descriptor(descriptor)
    if descriptor['source']!=job['binding']:
        raise ValueError('天空自动选区属于另一份不可变来源')
    if packet is not None:
        from .sky_semantic.immutable_input import check
        check(packet,job['binding'])
        if error is not None:
            raise ValueError('不可变天空输入不能同时成功与失败')
    elif type(error) is not str or not 1<=len(error)<=2000:
        raise ValueError('不可变天空任务缺少已捕获的输入证明或明确失败原因')


def _job_key(job):
    return (_recipe_key(job['raw']),_recipe_key(job['binding']),_recipe_key(job['expected']),
            _recipe_key(job['asset_choices']),_asset_key(job['asset']),job['source_path'],
            _recipe_key(job['source_proof']),_immutable_key(job.get('immutable_input')),
            _recipe_key(job.get('immutable_error')),_recipe_key(job.get('semantic_stamp')))


def _semantic_result(job,value,prepared):
    if not job['source_proof']['derived']:
        return
    if value['semantic']!=job['raw'].get('semantic'):
        raise ValueError('天空准备结果改变了已捕获的自动选区审核身份')
    if not value['enabled'] or value['semantic'] is None:
        return
    from .sky_semantic.resolver import validate_input
    validate_input(value['semantic'],job.get('immutable_input'))
    if job.get('immutable_error') is not None or prepared.get('semantic_suspended') is not None:
        raise ValueError('已启用的天空预览不能接受暂停的自动选区')


def _prepared_key(prepared,value,shape):
    basic={'value','shape','raw_fields','fields','semantic_suspended'}
    expected=basic|({'asset','reflection','tint','cover','asset_stamp'} if value['enabled'] else set())
    if (type(prepared) is not dict or set(prepared)!=expected or prepared['value']!=value
            or tuple(prepared['shape'])!=tuple(shape)):
        raise ValueError('天空准备效果不属于本次完整配方与源图')
    targets={*S.REGIONS,'recovery'}
    if type(prepared['raw_fields']) is not dict or set(prepared['raw_fields'])!=targets:
        raise ValueError('天空定位蒙版缺少明确区域')
    for field in prepared['raw_fields'].values():
        if type(field) is not np.ndarray or field.dtype!=np.uint8 or field.shape!=tuple(shape):
            raise ValueError('天空定位蒙版不是当前源图网格')
    groups=[('raw_fields',tuple((name,_array_key(field)) for name,field in sorted(prepared['raw_fields'].items())))]
    if not value['enabled']:
        if prepared['fields'] is not None:raise ValueError('停用天空配方不能携带隐藏效果场')
    else:
        if type(prepared['fields']) is not dict or set(prepared['fields'])!=targets:
            raise ValueError('天空效果场缺少明确区域')
        for field in prepared['fields'].values():
            if (type(field) is not np.ndarray or field.dtype!=np.float32 or field.shape!=tuple(shape)
                    or not np.isfinite(field).all() or np.any((field<0)|(field>1))):
                raise ValueError('天空效果场与源图坐标或范围不一致')
        groups.append(('fields',tuple((name,_array_key(field)) for name,field in sorted(prepared['fields'].items()))))
        for name in ('asset','reflection','tint'):
            field=prepared[name]
            target=(3,) if name=='tint' else (value['asset']['height'],value['asset']['width'],3)
            if type(field) is not np.ndarray or field.dtype!=np.float32 or field.shape!=target:
                raise ValueError('天空素材准备像素与已确认原件不一致')
            groups.append((name,_array_key(field)))
        if type(prepared['cover']) not in (int,float) or not np.isfinite(prepared['cover']) or prepared['cover']<=0:
            raise ValueError('天空素材覆盖范围无效')
    return (_recipe_key(value),tuple(shape),tuple(groups),_recipe_key(prepared['semantic_suspended']),
            prepared.get('cover'),tuple(prepared['asset_stamp']) if value['enabled'] else None)


def _freeze_prepared(prepared):
    for name in ('raw_fields','fields'):
        for value in (prepared[name] or {}).values():value.setflags(write=False)
    for name in ('asset','reflection','tint'):
        if name in prepared:prepared[name].setflags(write=False)


def _stage_key(stage):
    def signature(tensor):
        return None if tensor is None else (id(tensor),tensor.data_ptr(),int(tensor._version),
            tuple(tensor.shape),str(tensor.dtype),str(tensor.device))
    return (id(stage),tuple(stage.shape),_recipe_key(stage.value),stage.suspended,stage.asset_stamp,
        tuple((name,signature(tensor)) for name,tensor in sorted(stage.fields.items())),
        tuple((name,signature(getattr(stage,name))) for name in
            ('sky','reflection','tint','horizon_weight','sky_valid','reflection_valid')))


def _work_owned(job,shape,stop):
    if _job_key(job)!=job['input_key']:raise ValueError('天空工作输入已不属于捕获的草稿')
    _semantic_transport(job)
    value,prepared,asset,issue,choice=SkyPreview.work(job,shape,stop)
    if _job_key(job)!=job['input_key']:raise ValueError('天空计算修改了其捕获输入')
    if job['source_proof']['derived']:
        from .creative_derived_sky import validate
        validate(value,job['binding'])
    _semantic_result(job,value,prepared)
    prepared_key=_prepared_key(prepared,value,shape);_freeze_prepared(prepared)
    return {'input_key':job['input_key'],'value':value,'prepared':prepared,'prepared_key':prepared_key,
            'asset':asset,'asset_key':_asset_key(asset),'issue':issue,'accepted_choice':choice}


def background_conflict(engine):
    pipe = engine._vram
    if pipe and pipe.has_background():
        return '换天空与换背景不能同时启用；请先关闭当前换背景，避免后层覆盖天空'
    return None


def overlay(fields, target, dimensions):
    from PIL import Image
    color = {'sky':(67,170,255), 'person':(255,180,40), 'water':(40,230,200), 'recovery':(245,80,170)}[target]
    alpha = fields[target]
    rgba = np.empty((*alpha.shape,4),np.uint8)
    rgba[...,:3] = color
    rgba[...,3] = (alpha.astype(np.uint16)*150//255).astype(np.uint8)
    picture = Image.fromarray(rgba,'RGBA').resize(dimensions,Image.Resampling.BILINEAR)
    buffer = io.BytesIO(); picture.save(buffer,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')


def render(engine, stage, source_image, fields, target):
    from .fabric_controller import sync as fabric
    from .local_mask_state import sync as masks
    from .local_grade_runtime import sync as grades
    from .effect_recovery_runtime import sync as recovery
    from .manual_liquify_runtime import sync as manual
    from .studio_background_runtime import sync as studio
    from .optics_runtime import sync as optics
    fabric(engine); studio(engine,strict=True); masks(engine,strict=True); grades(engine,strict=True); recovery(engine,strict=True); manual(engine,strict=True); optics(engine,strict=True)
    pipe = engine._vram
    original = getattr(pipe,'sky_replacement',SkyReplacementStage(pipe.device,(pipe.h,pipe.w)))
    presentation = engine._frame_presentation()
    strength,channel = engine._retouch_render_args()
    try:
        pipe.sky_replacement = stage
        after,dimensions = image(pipe.retouch(strength,channel=channel,**engine._params),presentation)
    finally:
        pipe.sky_replacement = original
    source,source_dimensions = source_image
    marked = overlay(fields,target,source_dimensions)
    if len(source)+len(after)+len(marked) > MAX_REVIEW_BYTES:
        raise ValueError('换天空定位与效果预览超过 6 MiB')
    from .creative_derived_source import record
    source_label='当前不可变来源' if record(engine) is not None else '原照片'
    return {'source':source,'after':after,'overlay':marked,'width':dimensions[0],'height':dimensions[1],
            'source_width':source_dimensions[0],'source_height':source_dimensions[1],
            'domain':'source-normalized','output_domain':'production-output','quality':'proxy-render-srgb8',
            'target':target,'automatic_detection':stage.value.get('semantic') is not None,
            'note':f'左侧是未变形/未裁剪的{source_label}定位；右侧是真实当前输出。导出重放完整尺寸区域与原件，不放大此预览'}


class SkyPreview:
    def __init__(self,engine,emit):
        self.engine,self.emit = engine,emit
        self.session = self.record = self.job = self.latest = None
        self.pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='sky-replacement')

    def cancel(self):
        if self.job:
            self.job['stop'].set()
        self.session = self.record = self.latest = None

    def close(self):
        self.cancel()
        self.pool.shutdown(wait=True,cancel_futures=True)
        self.job = None

    def event(self,p,**values):
        return {'event':'sky_replacement_preview','protocol':1,
                **{k:p.get(k) for k in ('preview_id','session_id','document_id')},**values}

    def matching(self,p):
        session = self.session;metadata,spec=context(self.engine)
        if (not session or session['id'] != p.get('session_id') or session['metadata'] != metadata or session['spec'] != spec
                or p.get('document_id') != session['metadata']['document_id']):
            raise ValueError('天空源图或编辑版本已变化，请重新进入')
        actual,_=capture_inputs(self.engine)
        if actual!=session['source_proof']:
            raise ValueError('天空定位实际来源、修补输入或变形已变化，请重新进入')
        return session

    def verify_inputs(self,job):
        actual,_=capture_inputs(self.engine)
        if actual!=job['source_proof'] or _job_key(job)!=job['input_key']:
            raise ValueError('天空来源、已冻结草稿或素材选择身份变化，旧结果不可提交')
        _semantic_transport(job)
        if job['raw'].get('semantic') is not None:
            if _semantic_stamp()!=job['semantic_stamp']:
                raise ValueError('天空语义模型安装在审核期间变化，请重新预览')
            if job['source_proof']['derived']:
                packet,error=_capture_semantic(self.engine,job['binding'])
                if _immutable_key(packet)!=_immutable_key(job.get('immutable_input')) or error!=job.get('immutable_error'):
                    raise ValueError('天空自动选区的完整不可变来源或固定输入已变化')

    def verify_record(self,p):
        self.matching(p);record=self.record
        if (record is None or record['request']['preview_id']!=p.get('preview_id') or self.job or self.latest):
            raise ValueError('天空预览已经被新内容替代')
        self.verify_inputs(record)
        _semantic_result(record,record['value'],record['prepared'])
        if (_prepared_key(record['prepared'],record['value'],(self.engine._vram.h,self.engine._vram.w))!=record['prepared_key']
                or _stage_key(record['stage'])!=record['stage_key']
                or _asset_key(record['resolved_asset'])!=record['resolved_asset_key']):
            raise ValueError('天空已显示效果场或原件像素发生变化，请重新预览')
        if record['issue'] is None:
            value=R.verified_value(self.engine,record['value'])
            if R.stage_key(self.engine,value)!=record['runtime_key']:
                raise ValueError('天空最终预览的来源、区域或素材身份已变化')
            if value['enabled'] and (B.file_stamp(value['asset']['path'])!=record['prepared']['asset_stamp']
                    or record['stage'].asset_stamp!=record['prepared']['asset_stamp']):
                raise ValueError('天空原件在最终效果显示后变化')
        return record

    def handle(self,p):
        try:
            action = p.get('action')
            fields = {'cmd','action','preview_id','session_id','document_id'} | ({'mutation'} if action == 'preview' else set())
            if set(p) != fields or p['cmd'] != 'sky_replacement_preview' or action not in ('preview','presented','cancel'):
                raise ValueError('天空预览命令字段无效')
            ident(p['preview_id']); ident(p['session_id'])
            if action == 'cancel':
                if self.session and self.session['id'] == p['session_id']:
                    self.cancel()
                self.emit(self.event(p,state='cancelled',success=True)); return
            if action == 'presented':
                record=self.verify_record(p)
                record['presented'] = True
                self.session['shown'] = True
                self.emit(self.event(p,state='presented',success=True)); return
            if len(json.dumps(p,allow_nan=False).encode()) > 256*1024:
                raise ValueError('天空预览草稿超过 256 KiB')
            mutation = p['mutation']
            if type(mutation) is not dict:
                raise ValueError('天空修改必须是对象')
            viewing = mutation.get('action') == 'view'
            allowed = {'action','target'} if viewing else {'action','target','draft'}
            if set(mutation) != allowed or mutation.get('action') not in ('view','replace') or mutation['target'] not in (*S.REGIONS,'recovery'):
                raise ValueError('天空修改或标记目标无效')
            if not self.session or self.session['id'] != p['session_id']:
                if not viewing:
                    raise ValueError('请先显示原始源图定位画面')
                self.cancel()
                metadata,spec = context(self.engine)
                if metadata['document_id'] != p['document_id']:
                    raise ValueError('当前照片已经改变')
                row = self.engine._docs[self.engine._doc_index]
                source_proof,_=capture_inputs(self.engine)
                pipe = self.engine._vram
                source_image = image(pipe.src_f32,SimpleNamespace(width=pipe.w,height=pipe.h))
                if capture_inputs(self.engine)[0]!=source_proof:
                    raise ValueError('准备天空源图定位时实际来源变化')
                self.session = {'id':p['session_id'],'metadata':metadata,'spec':spec,'path':row['path'],
                                'binding':deepcopy(source_proof['source']),'source_proof':source_proof,
                                'source_image':source_image,'shown':False,'asset':None,'asset_choices':{}}
            session = self.matching(p)
            if not viewing and not session['shown']:
                raise ValueError('原始源图定位尚未确认显示，不能接收区域笔迹')
            current = S.check(getattr(self.engine,'_sky_replacement',None))
            if current['source'] is not None and current['source'] != session['binding']:
                raise ValueError('换天空区域属于另一张照片，不能重新绑定')
            if session['source_proof']['derived']:
                from .creative_derived_sky import validate
                validate(current,session['binding'])
            raw = S.editable(current) if viewing else deepcopy(mutation['draft'])
            validate_draft(self.engine,raw,session['binding'])
            packet=immutable_error=semantic_stamp=None
            if raw.get('semantic') is not None:
                semantic_stamp=_semantic_stamp()
                if session['source_proof']['derived']:
                    packet,immutable_error=_capture_semantic(self.engine,session['binding'])
            if self.job:
                self.job['stop'].set()
            self.record = None
            self.latest = {'request':deepcopy(p),'raw':raw,'viewing':viewing,
                           'binding':deepcopy(session['binding']),'asset':session['asset'],
                           'source_path':None if session['source_proof']['derived'] else session['path'],
                           'immutable_input':packet,'immutable_error':immutable_error,'semantic_stamp':semantic_stamp,
                           'expected':deepcopy(current['asset']),
                           'asset_choices':deepcopy(session['asset_choices']),'source_image':session['source_image'],
                           'source_proof':deepcopy(session['source_proof'])}
            self.latest['input_key']=_job_key(self.latest)
            self.tick()
        except Exception as error:
            self.cancel()
            self.emit(self.event(p,state='failed',success=False,error=str(error)[:2000]))

    @staticmethod
    def work(job,shape,stop):
        _semantic_transport(job)
        raw,asset = job['raw'],job['asset']
        semantic_inputs={'source_path':job['source_path'],'immutable_input':job.get('immutable_input'),
                         'immutable_error':job.get('immutable_error')}
        path = raw.get('asset_path')
        choice = raw.get('asset_choice')
        if choice is not None:
            ident(choice)
        known_choice = job['asset_choices'].get(choice)
        explicitly_chosen = choice is not None and known_choice is None
        accepted_choice = None
        issue = None
        try:
            if explicitly_chosen and len(job['asset_choices']) >= 128:
                raise ValueError('本次会话已选择 128 份素材，请应用或取消后重新进入；不会忘记旧素材身份')
            if known_choice is not None and known_choice['path'] != path:
                raise ValueError('同一素材选择身份不能用于另一个文件')
            expected = (known_choice if known_choice is not None else None if explicitly_chosen else
                        job['expected'] if job['expected'] and job['expected']['path'] == path else
                        asset.binding if asset is not None and asset.binding['path'] == path else None)
            if path is None:
                asset = None
            elif not raw.get('enabled') and not explicitly_chosen and expected is not None:
                # Disabling a broken linked effect must remain possible without
                # deleting its source-bound intent or replacing the missing asset.
                value = S.from_editable(raw,job['binding'],expected)
                return value,R.prepare(value,shape,**semantic_inputs,cancelled=stop.is_set),asset,None,accepted_choice
            elif not explicitly_chosen and expected is None:
                raise ValueError('新素材需要明确选择，不能悄悄替换路径')
            elif explicitly_chosen or asset is None or asset.binding != expected or B.file_stamp(path) != asset.stamp:
                asset = A.read(path,expected=expected,cancelled=stop.is_set)
                if explicitly_chosen:
                    accepted_choice = (choice,deepcopy(asset.binding))
            value = S.from_editable(raw,job['binding'],asset.binding if asset else None)
            prepared = R.prepare(value,shape,asset=asset,**semantic_inputs,cancelled=stop.is_set)
        except InterruptedError:
            raise
        except Exception as error:
            # Keep the source locator and editable intent available for repair.
            # This disabled draft is NEVER commit eligible while the error is set.
            issue = str(error)[:2000]
            fallback = deepcopy(raw)
            fallback['enabled'] = False
            fallback['asset_path'] = None
            value = S.from_editable(fallback,job['binding'],None)
            prepared = R.prepare(value,shape,**semantic_inputs,cancelled=stop.is_set)
        return value,prepared,asset,issue,accepted_choice

    def tick(self):
        if self.job and self.job['future'].done():
            job,self.job = self.job,None
            if not job['stop'].is_set() and self.session and self.latest is None:
                p = job['request']
                try:
                    session = self.matching(p)
                    self.verify_inputs(job)
                    outcome=job['future'].result()
                    if outcome['input_key']!=job['input_key']:
                        raise ValueError('天空计算返回了其他草稿的输入证明')
                    value,prepared,asset,issue,accepted_choice=(outcome[name] for name in
                        ('value','prepared','asset','issue','accepted_choice'))
                    _semantic_result(job,value,prepared)
                    prepared_key=outcome['prepared_key']
                    if (_prepared_key(prepared,value,(self.engine._vram.h,self.engine._vram.w))!=prepared_key
                            or _asset_key(asset)!=outcome['asset_key']):
                        raise ValueError('天空准备场或原件像素在计算完成前变化')
                    if value['enabled'] and B.file_stamp(value['asset']['path']) != prepared['asset_stamp']:
                        raise ValueError('素材在异步准备之后变化，请重新预览')
                    pipe = self.engine._vram
                    if value['enabled'] and background_conflict(self.engine):
                        issue = background_conflict(self.engine)
                    stage = SkyReplacementStage(pipe.device,(pipe.h,pipe.w))
                    try:
                        stage.set(S.empty() if issue else value, None if issue else prepared)
                    except Exception as error:
                        issue=str(error)[:2000]
                        stage=SkyReplacementStage(pipe.device,(pipe.h,pipe.w))
                    stage_key=_stage_key(stage)
                    try:
                        result = render(self.engine,stage,job['source_image'],prepared['raw_fields'],p['mutation']['target'])
                    except Exception as error:
                        issue = str(error)[:2000]
                        stage = SkyReplacementStage(pipe.device,(pipe.h,pipe.w))
                        stage_key=_stage_key(stage)
                        result = render(self.engine,stage,job['source_image'],prepared['raw_fields'],p['mutation']['target'])
                    result['semantic_suspended'] = prepared.get('semantic_suspended')
                    result['automatic_detection'] = value['semantic'] is not None and not prepared.get('semantic_suspended')
                    self.matching(p);self.verify_inputs(job)
                    if (_stage_key(stage)!=stage_key or _prepared_key(prepared,value,(pipe.h,pipe.w))!=prepared_key
                            or _asset_key(asset)!=outcome['asset_key']):
                        raise ValueError('天空准备效果在最终画面显示过程中变化')
                    if value['enabled'] and B.file_stamp(value['asset']['path']) != prepared['asset_stamp']:
                        raise ValueError('素材在预览渲染期间变化，请重新选择')
                    runtime_key=None
                    if issue is None:
                        R.verified_value(self.engine,value)
                        runtime_key=R.stage_key(self.engine,value)
                    self.matching(p);self.verify_inputs(job)
                    session['asset'] = asset
                    if accepted_choice is not None:
                        session['asset_choices'][accepted_choice[0]] = accepted_choice[1]
                    self.record = {**{key:item for key,item in job.items() if key!='future'},
                        'value':value,'prepared':prepared,'prepared_key':prepared_key,
                        'stage':stage,'stage_key':stage_key,'runtime_key':runtime_key,
                        'resolved_asset':asset,'resolved_asset_key':outcome['asset_key'],'presented':False,'issue':issue}
                    self.verify_record(p)
                    self.emit(self.event(p,state='ready',success=True,result=result,editable=job['raw'],
                        committable=not job['viewing'] and issue is None,validation_error=issue,
                        recipe_document_id=session['metadata']['recipe_document_id'],recipe_revision=session['metadata']['recipe_revision']))
                except Exception as error:
                    self.cancel()
                    self.emit(self.event(p,state='failed',success=False,error=str(error)[:2000]))
        if self.job is None and self.latest is not None:
            job,self.latest = self.latest,None
            stop = threading.Event()
            shape = (self.engine._vram.h,self.engine._vram.w)
            try:
                self.matching(job['request']);self.verify_inputs(job)
                job.update(stop=stop,future=self.pool.submit(_work_owned,job,shape,stop))
                self.job = job
            except Exception as error:
                self.cancel()
                self.emit(self.event(job['request'],state='failed',success=False,error=str(error)[:2000]))

    def prepare(self,p):
        record = self.verify_record(p)
        if (not record['presented'] or record['viewing'] or record['issue']):
            raise ValueError('当前天空草稿未显示、存在错误或已被替代；不能提交')
        value = R.verified_value(self.engine,record['value'])
        if value['enabled'] and background_conflict(self.engine):
            raise ValueError(background_conflict(self.engine))
        return deepcopy(value),record['stage']


def controller(engine,emit):
    owner = engine.__dict__.get('_sky_replacement_preview_owner')
    if owner is None:
        owner = engine._sky_replacement_preview_owner = SkyPreview(engine,emit)
    return owner
