"""Latest-wins preparation with a frozen source locator and real output review.

Only a fully shown exact candidate is redeemable. Source PNG authorizes brush
coordinates, output PNG is review only, neither is the export pixel source.
Preparation runs off sequence; production rendering and mutations stay on it.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
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
    metadata, _ = engine._source_patch_controller().capture._context()
    return metadata


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
    return {'source':source,'after':after,'overlay':marked,'width':dimensions[0],'height':dimensions[1],
            'source_width':source_dimensions[0],'source_height':source_dimensions[1],
            'domain':'source-normalized','output_domain':'production-output','quality':'proxy-render-srgb8',
            'target':target,'automatic_detection':stage.value.get('semantic') is not None,
            'note':'左侧是未变形/未裁剪的原照片定位；右侧是真实当前输出。导出重放原始尺寸区域与原件，不放大此预览'}


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
        session = self.session
        if (not session or session['id'] != p.get('session_id') or session['metadata'] != context(self.engine)
                or p.get('document_id') != session['metadata']['document_id']):
            raise ValueError('天空源图或编辑版本已变化，请重新进入')
        row = self.engine._docs[self.engine._doc_index]
        if (row['path'] != session['path'] or B.file_stamp(row['path']) != session['stamp']
                or row.get('_local_source_stamp') != session['stamp'] or id(self.engine._vram.src_f32) != session['pixels']):
            raise ValueError('天空定位源图已过期，请重新打开照片')
        return session

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
                session = self.matching(p)
                if not self.record or self.record['request']['preview_id'] != p['preview_id']:
                    raise ValueError('天空预览已经被新内容替代')
                self.record['presented'] = True
                session['shown'] = True
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
                metadata = context(self.engine)
                if metadata['document_id'] != p['document_id']:
                    raise ValueError('当前照片已经改变')
                row = self.engine._docs[self.engine._doc_index]
                stamp = B.file_stamp(row['path'])
                binding = B.bind_source(self.engine)
                pipe = self.engine._vram
                source_image = image(pipe.src_f32,SimpleNamespace(width=pipe.w,height=pipe.h))
                if B.file_stamp(row['path']) != stamp:
                    raise ValueError('准备天空源图定位时源文件变化')
                self.session = {'id':p['session_id'],'metadata':metadata,'path':row['path'],'stamp':stamp,
                                'binding':binding,'source_image':source_image,'shown':False,'asset':None,'asset_choices':{},'pixels':id(pipe.src_f32)}
            session = self.matching(p)
            if not viewing and not session['shown']:
                raise ValueError('原始源图定位尚未确认显示，不能接收区域笔迹')
            current = S.check(getattr(self.engine,'_sky_replacement',None))
            if current['source'] is not None and current['source'] != session['binding']:
                raise ValueError('换天空区域属于另一张照片，不能重新绑定')
            raw = S.editable(current) if viewing else deepcopy(mutation['draft'])
            if self.job:
                self.job['stop'].set()
            self.record = None
            self.latest = {'request':deepcopy(p),'raw':raw,'viewing':viewing,
                           'binding':deepcopy(session['binding']),'asset':session['asset'],
                           'source_path':session['path'],'expected':current['asset'],'asset_choices':deepcopy(session['asset_choices']),'source_image':session['source_image']}
            self.tick()
        except Exception as error:
            self.emit(self.event(p,state='failed',success=False,error=str(error)[:2000]))

    @staticmethod
    def work(job,shape,stop):
        raw,asset = job['raw'],job['asset']
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
                return value,R.prepare(value,shape,source_path=job['source_path'],cancelled=stop.is_set),asset,None,accepted_choice
            elif not explicitly_chosen and expected is None:
                raise ValueError('新素材需要明确选择，不能悄悄替换路径')
            elif explicitly_chosen or asset is None or asset.binding != expected or B.file_stamp(path) != asset.stamp:
                asset = A.read(path,expected=expected,cancelled=stop.is_set)
                if explicitly_chosen:
                    accepted_choice = (choice,deepcopy(asset.binding))
            value = S.from_editable(raw,job['binding'],asset.binding if asset else None)
            prepared = R.prepare(value,shape,asset=asset,source_path=job['source_path'],cancelled=stop.is_set)
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
            prepared = R.prepare(value,shape,source_path=job['source_path'],cancelled=stop.is_set)
        return value,prepared,asset,issue,accepted_choice

    def tick(self):
        if self.job and self.job['future'].done():
            job,self.job = self.job,None
            if not job['stop'].is_set() and self.session and self.latest is None:
                p = job['request']
                try:
                    session = self.matching(p)
                    value,prepared,asset,issue,accepted_choice = job['future'].result()
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
                    try:
                        result = render(self.engine,stage,job['source_image'],prepared['raw_fields'],p['mutation']['target'])
                    except Exception as error:
                        issue = str(error)[:2000]
                        stage = SkyReplacementStage(pipe.device,(pipe.h,pipe.w))
                        result = render(self.engine,stage,job['source_image'],prepared['raw_fields'],p['mutation']['target'])
                    result['semantic_suspended'] = prepared.get('semantic_suspended')
                    result['automatic_detection'] = value['semantic'] is not None and not prepared.get('semantic_suspended')
                    self.matching(p)
                    if value['enabled'] and B.file_stamp(value['asset']['path']) != prepared['asset_stamp']:
                        raise ValueError('素材在预览渲染期间变化，请重新选择')
                    session['asset'] = asset
                    if accepted_choice is not None:
                        session['asset_choices'][accepted_choice[0]] = accepted_choice[1]
                    self.record = {**job,'value':value,'stage':stage,'presented':False,'issue':issue}
                    self.emit(self.event(p,state='ready',success=True,result=result,editable=job['raw'],
                        committable=not job['viewing'] and issue is None,validation_error=issue,
                        recipe_document_id=session['metadata']['recipe_document_id'],recipe_revision=session['metadata']['recipe_revision']))
                except Exception as error:
                    self.emit(self.event(p,state='failed',success=False,error=str(error)[:2000]))
        if self.job is None and self.latest is not None:
            job,self.latest = self.latest,None
            stop = threading.Event()
            shape = (self.engine._vram.h,self.engine._vram.w)
            job.update(stop=stop,future=self.pool.submit(self.work,job,shape,stop))
            self.job = job

    def prepare(self,p):
        self.matching(p)
        record = self.record
        if (not record or record['request']['preview_id'] != p.get('preview_id') or not record['presented']
                or record['viewing'] or record['issue'] or self.job or self.latest):
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
