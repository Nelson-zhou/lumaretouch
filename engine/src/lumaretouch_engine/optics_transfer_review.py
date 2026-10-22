"""Bounded frozen optical preparation, source/version/DB guards, and exact undo.

Frozen batch/preset controllers own the prepared review data,
never accepted as portable preset modules or recalculated during commit.
"""
from copy import deepcopy
from hashlib import sha256
import json
import numpy as np
from . import optics_state as S, optics_auto_scope as A, optics_runtime as R, local_mask_state as M
from .optics_stage import OpticsStage
from .optics_transfer_input import TargetInput
from .optics_candidate_identity import fingerprint

MAX_RECORD=128*1024


def canonical(value):
    text=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
    if len(text.encode())>MAX_RECORD:raise ValueError('自动镜头/透视预检记录超限')
    return text


def runtime(request):
    import importlib
    return {'solver':'robust-lines-v1','numpy':np.__version__,'opencv':str(importlib.import_module('cv2').__version__) if request['auto_mode']!='off' else None,'optics_abi':1,'ml_model':None}


def digest(value):return sha256(canonical(value).encode()).hexdigest()


def _thumb(rgb):
    from PIL import Image
    from base64 import b64encode
    from io import BytesIO
    image=Image.fromarray(np.clip(np.rint(rgb*255),0,255).astype(np.uint8),'RGB')
    image.thumbnail((320,320),Image.Resampling.LANCZOS)
    data=BytesIO();image.save(data,format='PNG')
    return 'data:image/png;base64,'+b64encode(data.getvalue()).decode(),list(image.size)


def prepare(params,target,*,before_state,preview=False,cancelled=lambda:False):
    if not isinstance(target,TargetInput) or target.domain!=S.DOMAIN:raise ValueError('自动分析缺少真实目标编辑阶段输入')
    request=A.check_params(params)['request'];pixels=target.pixels
    if not isinstance(pixels,np.ndarray) or pixels.dtype!=np.float32 or pixels.ndim!=3 or pixels.shape[2]!=3 or not pixels.flags.c_contiguous or not np.isfinite(pixels).all():raise ValueError('自动分析需要有限、连续浮点 RGB')
    if pixels.shape[:2]!=(target.source['height'],target.source['width']):raise ValueError('自动预检必须来自完整目标编辑画布，不能拿源图定位代理冒充')
    if target.stamp!=M.file_stamp(target.path):raise ValueError('自动分析目标源图变化')
    M.verify_source({'source':target.source},target.path)
    if cancelled():raise InterruptedError('自动镜头/透视预检取消')
    recipe=R.transfer(request,metadata=target.metadata,source_binding=target.source,input_rgb=pixels)
    stage=OpticsStage(recipe,pixels.shape[:2]);result=stage.apply_np(pixels,cancelled=cancelled)
    if target.stamp!=M.file_stamp(target.path):raise ValueError('自动分析过程中目标源图变化')
    record={'version':1,'document_id':target.document_id,'revision':target.revision,'path':target.path,'stamp':list(target.stamp),
            'source':target.source,'request':request,'recipe':recipe,'input_shape':list(pixels.shape[:2]),'domain':S.DOMAIN,
            'input_sha256':sha256(memoryview(pixels).cast('B')).hexdigest(),'before_key':A.undo_key(before_state),'crop_zoom':stage.zoom,'candidate_key':target.candidate_key,'runtime':runtime(request)}
    record=json.loads(canonical(record));record['proof']=digest(record)
    report={'version':1,'document_id':target.document_id,'revision':target.revision,'success':True,
            'proof':record['proof'],'candidate_key':record['candidate_key'],'auto_mode':request['auto_mode'],'lens_auto':request['lens_auto'],
            'method':(recipe['perspective']['analysis'] or {}).get('method','manual-only'),
            'analysis':recipe['perspective']['analysis'],'lens':recipe['lens']['profile'],'crop_zoom':stage.zoom,
            'note':'目标自身完整编辑画布的重新匹配/解算；不是复制源照片配置或矩阵'}
    if preview:
        before,size=_thumb(pixels);after,after_size=_thumb(result)
        if size!=after_size or len(before)+len(after)>1024*1024:raise ValueError('自动预检比较图超过预算')
        report['comparison']={'before':before,'after':after,'width':size[0],'height':size[1],'domain':S.DOMAIN}
    return record,report


def verify(record,*,path,document_id,revision,state,params,candidate_state):
    if type(record) is not dict:raise ValueError('自动镜头/透视预检缺失')
    expected={'version','document_id','revision','path','stamp','source','request','recipe','input_shape','domain','input_sha256','before_key','crop_zoom','proof','candidate_key','runtime'}
    if set(record)!=expected or type(record['version']) is not int or record['version']!=1 or record['domain']!=S.DOMAIN:raise ValueError('自动预检协议无效')
    if digest({k:v for k,v in record.items() if k!='proof'})!=record['proof']:raise ValueError('自动预检记录已改变')
    if (record['path'],record['document_id'],record['revision'])!=(path,document_id,str(revision)):raise ValueError('目标照片或编辑版本与自动预检不同')
    if A.undo_key(state)!=record['before_key'] or A.check_params(params)['request']!=record['request']:raise ValueError('目标参数或自动请求已变化，请重新预检')
    if list(M.file_stamp(path))!=record['stamp']:raise ValueError('自动预检后的源图已变化')
    if fingerprint(candidate_state)!=record['candidate_key']:raise ValueError('完整目标候选或保留的模型/蒙版数据已变化，请重新预检')
    if runtime(record['request'])!=record['runtime']:raise ValueError('自动透视求解运行库与预检不同')
    source=S.binding(record['source']);M.verify_source({'source':source},path)
    recipe=S.check(record['recipe'])
    if S.source_bound(recipe) and recipe['source']!=source:raise ValueError('自动预检的目标身份不一致')
    # Rebuild calibration and geometric admission, not the solver. A changed DB
    # or library is rejected, never silently substituted by another profile.
    shape=record['input_shape']
    if type(shape) is not list or len(shape)!=2 or any(type(v) is not int or v<1 for v in shape):raise ValueError('自动预检画布尺寸无效')
    if shape!=[source['height'],source['width']]:raise ValueError('自动预检画布与完整目标身份不同')
    stage=OpticsStage(recipe,tuple(shape))
    if abs(stage.zoom-float(record['crop_zoom']))>1e-10:raise ValueError('自动预检裁剪映射与当前实现不同')
    if list(M.file_stamp(path))!=record['stamp']:raise ValueError('自动预检验证期间源图变化')
    return recipe


def install_verified(state,record,**identity):
    recipe=verify(record,state=state,**identity)
    updated=dict(state);updated['_optics']=deepcopy(recipe)
    return updated
