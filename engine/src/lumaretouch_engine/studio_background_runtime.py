from . import id_background_state as ID
"""Studio recipe lifecycle and one full-domain preparation for tiled export."""
from copy import deepcopy
import json
import numpy as np
from . import studio_background_state as S,local_mask_state as M
from .studio_background_stage import StudioBackgroundStage,check_prepared
from .ops.studio_background import prepare


def key(engine,value):
    row=engine._docs[engine._doc_index]
    return (json.dumps(value,sort_keys=True),M.file_stamp(row['path']),id(engine._vram.src_f32),json.dumps(M.current_owner(engine),sort_keys=True))


def verify(engine,value):
    value=S.check(value);row=engine._docs[engine._doc_index];before=M.file_stamp(row['path'])
    if S.active(value) and (engine._vram.has_background() or ID.active(getattr(engine,'_id_background',None))): raise ValueError('完整换底会覆盖影棚背景调整，请先关闭换底')
    if row.get('_local_source_stamp')!=before: raise ValueError('解码后原照片变化，请重新打开')
    M.verify_source(value,row['path'],(row['src_h'],row['src_w']))
    if value['region_mode']=='semantic_background' and value['semantic_owner']!=M.current_owner(engine):
        raise ValueError('背景分析模型来源改变；蒙版已暂停，请重新确认背景范围')
    if M.file_stamp(row['path'])!=before: raise ValueError('验证背景源图时文件变化')
    return value


def semantic(engine,value):
    if value['region_mode']!='semantic_background': return None
    pc=engine._precompute
    if value['semantic_owner'] is None or value['semantic_owner']!=M.current_owner(engine):
        raise ValueError('无法验证背景语义来源')
    result=(getattr(pc,'masks',None) or {}).get('background')
    if result is None: raise ValueError('此模型没有背景通道；请手动标记，不会反推地面')
    return np.asarray(result,dtype=np.float32).copy()


def prepare_stage(engine,value,*,prepared=None):
    value=verify(engine,value);pipe=engine._vram;before=key(engine,value)
    stage=StudioBackgroundStage(pipe.device,(pipe.h,pipe.w))
    if prepared is None:
        source=pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy()
        prepared=prepare(source,value,semantic_background=semantic(engine,value))
    stage.install(prepared)
    if key(engine,value)!=before: raise ValueError('背景准备过程中源图或分析身份变化')
    stage.verified_source_key=before
    return stage


def sync(engine,*,strict=False):
    pipe=engine._vram
    if pipe is None:return
    value=S.check(getattr(engine,'_studio_background',None));stamp=None
    try:
        stamp=key(engine,value)
        if getattr(pipe,'_studio_background_key',None)==stamp:
            if strict and pipe.studio_background.suspended: raise ValueError(pipe.studio_background.suspended)
            return
        stage=prepare_stage(engine,value) if S.active(value) else StudioBackgroundStage(pipe.device,(pipe.h,pipe.w))
        pipe.studio_background,pipe._studio_background_key=stage,stamp
    except Exception as error:
        stage=StudioBackgroundStage(pipe.device,(pipe.h,pipe.w));stage.suspended=str(error);stage.required=S.active(value)
        pipe.studio_background,pipe._studio_background_key=stage,stamp
        if strict: raise


def report(engine):
    value=S.check(getattr(engine,'_studio_background',None));stage=getattr(engine._vram,'studio_background',None)
    owner=M.current_owner(engine);background=(getattr(engine._precompute,'masks',None) or {}).get('background')
    return {'version':S.VERSION,'domain':S.DOMAIN,'parameters':value['parameters'],'region_mode':value['region_mode'],
            'strokes':value['strokes'],'semantic_available':owner is not None and background is not None,
            'suspended':getattr(stage,'suspended',None),'analysis':getattr(stage,'analysis',[]),
            'bytes_fields':stage.resident_bytes() if stage else 0,
            'boundaries':['前四项只处理已确认的纯色背景；非纯色检测失败时暂停，不以模糊冒充祛穿帮',
                '地面来自显式手动标记；保护笔可排除主体、道具与接触阴影',
                '恢复只撤回选定背景算子，保留其他修补、自动美型、分组调色和最终手动液化',
                '预设/批量只复制强度；范围、保护与恢复笔迹属于各自照片',
                '背景清理先于自动塑形；换天空仅覆盖其标记区域，那里不会保留旧背景的清理效果；地面清理仍保留',
                '确定性开源处理，不宣称与官方专有 AI 算法等价；当前画面是代理预览']}


def verify_snapshot(snap,path,shape=None):
    value=S.check(snap.get('studio_background'))
    if value['source'] is None:return
    before=M.file_stamp(path);M.verify_source(value,path,shape)
    if shape is not None:S.validate_budget(value,shape)
    if M.file_stamp(path)!=before:raise ValueError('背景配方源图验证过程中变化')


def check_export_decode(snap,path,before,shape):
    value=S.check(snap.get('studio_background'))
    if value['source'] is None:return
    if before is None or M.file_stamp(path)!=before:raise ValueError('背景源图在全尺寸解码过程中变化')
    verify_snapshot(snap,path,shape)
    if M.file_stamp(path)!=before:raise ValueError('背景源图在身份验证过程中变化')
    snap['studio_background_path'],snap['studio_background_stamp']=path,list(before)


def configure_export(spec,snap,shape,*,for_document):
    value=S.check(snap.get('studio_background'))
    if value['source'] is not None and not for_document:raise ValueError('背景范围不可自动转移到其他照片，请使用其自己的准备状态')
    spec.studio_background=value;spec.studio_background_path=snap.get('studio_background_path');spec.studio_background_stamp=snap.get('studio_background_stamp')
    S.validate_budget(value,shape)
    if S.active(value):
        if not spec.studio_background_path:raise ValueError('背景全尺寸导出缺少已验证的源图路径')
        verify_snapshot(snap,spec.studio_background_path,shape)


def export_prepare(spec,source,*,semantic_background=None,semantic_owner=None,cancelled=lambda:False):
    value=S.check(spec.studio_background);spec.studio_background_prepared=None
    if not S.active(value):return
    path=spec.studio_background_path;before=M.file_stamp(path)
    if list(before)!=spec.studio_background_stamp:raise ValueError('全尺寸解码后背景源图变化')
    M.verify_source(value,path,source.shape[:2])
    if value['region_mode']=='semantic_background' and value['semantic_owner']!=semantic_owner:
        raise ValueError('全尺寸背景语义模型身份不匹配；不能用代理蒙版替代')
    spec.studio_background_prepared=prepare(source,value,semantic_background=semantic_background,cancelled=cancelled)
    if M.file_stamp(path)!=before:raise ValueError('全尺寸背景分析时原照片发生变化')


def attach_tile(pipe,spec,window):
    prepared=spec.studio_background_prepared
    stage=StudioBackgroundStage(pipe.device,(pipe.h,pipe.w))
    if prepared is None:
        if S.active(spec.studio_background):raise ValueError('背景全尺寸效果场缺失，停止导出')
    else:
        y0,x0,y1,x1=window
        tile={**prepared,'fields':{k:v[y0:y1,x0:x1] for k,v in prepared['fields'].items()},
              'recovery':{k:v[y0:y1,x0:x1] for k,v in prepared['recovery'].items()}}
        stage.install(tile)
    pipe.studio_background=stage


def preset_payload(value):return S.portable(value)


def apply_to_prepared_target(target,payload):
    """Preset/batch adapter. Keep that target's regions/protection/recovery intact."""
    return S.apply_portable(target,payload)
