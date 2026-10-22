"""Document lifecycle, honest RAW defaults, snapshot/export and transfer hooks."""
from copy import deepcopy
import json
from . import optics_state as S, local_mask_state as M
from .optics_stage import OpticsStage
from . import optics_lensfun as L


def verify(engine, value):
    value = S.check(value)
    row = engine._docs[engine._doc_index]
    before = M.file_stamp(row['path'])
    if row.get('_local_source_stamp') != before: raise ValueError('照片自解码后已变化，请重新打开')
    if S.source_bound(value): M.verify_source(value,row['path'],(row['src_h'],row['src_w']))
    if M.file_stamp(row['path']) != before: raise ValueError('镜头/透视源图验证期间发生变化')
    return value


def prepare_stage(engine, value):
    value = verify(engine,value); pipe = engine._vram
    return OpticsStage(value,(pipe.h,pipe.w))


def stage_key(engine, value):
    row = engine._docs[engine._doc_index]
    return json.dumps(value,sort_keys=True,allow_nan=False),M.file_stamp(row['path']),id(engine._vram.src_f32)


def sync(engine, *, strict=False):
    pipe = engine._vram
    if pipe is None: return
    value = S.check(getattr(engine,'_optics',None)); key = stage_key(engine,value)
    if getattr(pipe,'_optics_key',None)==key:
        if strict and pipe.optics.suspended: raise ValueError(pipe.optics.suspended)
        return
    try: stage = prepare_stage(engine,value) if S.active(value) else OpticsStage(value,(pipe.h,pipe.w))
    except Exception as error:
        stage = OpticsStage(); stage.value = value; stage.shape = (pipe.h,pipe.w); stage.suspended = str(error)
        pipe.optics,pipe._optics_key = stage,key
        if strict: raise
    else: pipe.optics,pipe._optics_key = stage,key


def import_default(engine, decoded):
    """Call ONLY for a brand-new photo, never restored projects/history."""
    value = S.empty(); meta = L.metadata(decoded,engine._docs[engine._doc_index]['path'])
    engine._optics_metadata = meta
    reason = '非 RAW 默认关闭自动镜头矫正，可使用手动调整'
    if meta['is_raw']:
        try:
            if (getattr(decoded,'raw',None) or {}).get('used_preview'): raise ValueError('内嵌预览可能已矫正，须完整解码再判断')
            if not meta['lens_model']: raise ValueError('RAW 没有完整镜头型号，不能自动猜配；'+meta.get('note',''))
            options = L.candidates(meta)
            if len(options)!=1: raise ValueError('RAW 镜头配置缺失或不唯一，需要手动选择')
            value['lens']['profile'] = L.resolve(options[0],meta,(engine._vram.h,engine._vram.w))
            value['lens']['enabled'] = True; value['source'] = M.bind_source(engine)
            prepare_stage(engine,value)
            reason = 'RAW 已匹配真实 Lensfun 配置并启用可用校正：'+', '.join(value['lens']['profile']['flags'])
        except Exception as error:
            value = S.empty(); reason = 'RAW 自动镜头矫正未启用：'+str(error)+'；手动调整仍可用'
    engine._optics,engine._optics_import_note = value,reason
    return value


def report(engine):
    value = S.check(getattr(engine,'_optics',None)); stage = getattr(engine._vram,'optics',None)
    return {'version':1,'recipe':value,'metadata':deepcopy(getattr(engine,'_optics_metadata',None) or L.metadata(None)),
            'note':getattr(engine,'_optics_import_note','旧项目保留原链序，新增镜头/透视默认中性'),
            'suspended':getattr(stage,'suspended',None),'crop_zoom':getattr(stage,'zoom',1.),
            'resident_bytes':stage.resident_bytes() if stage else 0,
            'boundaries':['镜头/透视在全部旧效果与最终手动液化之后、裁剪旋转之前；不会改写旧配方顺序',
                          '自动透视使用 OpenCV 线段分析与置信度筛选，不是 AI 模型；无可信证据则不改图',
                          '镜头库/依赖需显式安装，没有隐藏下载；缺配置时手动畸变和暗角可用',
                          '预设/批量只复制手动数值；镜头配置和自动模式需在各目标重新选择/分析，镜头身份和引导线不跨图复制']}


def check_export_decode(snap, path, before, shape):
    value = S.check(snap.get('optics'))
    if S.source_bound(value):
        if before is None or M.file_stamp(path)!=before: raise ValueError('镜头/透视源图在解码时变化')
        M.verify_source(value,path,shape)
        if M.file_stamp(path)!=before: raise ValueError('镜头/透视源图在身份验证时变化')
        snap['optics_path'],snap['optics_stamp'] = path,list(before)


def configure_export(spec, snap, shape, *, for_document):
    value = S.check(snap.get('optics'))
    if S.source_bound(value) and not for_document: raise ValueError('镜头/自动透视需逐图匹配和重算，不允许复制另一张图的解算结果')
    spec.optics = value; spec.optics_path = snap.get('optics_path'); spec.optics_stamp = snap.get('optics_stamp')
    if S.source_bound(value):
        if not spec.optics_path or spec.optics_stamp is None: raise ValueError('镜头/透视全尺寸出片缺少已验证源图')
        M.verify_source(value,spec.optics_path,shape)


def apply_export(pixels, spec, *, cancelled=lambda:False):
    """After upstream tiles are stitched, BEFORE upscale/sharpen/geometry.

    A full float editing raster is required for both RGB8 and RGB16. Do not call
    this on already quantized 8-bit tiles, nor on separately transformed tiles.
    """
    import numpy as np
    value = S.check(getattr(spec,'optics',None))
    if not S.active(value): return pixels,{'applied':False}
    if not np.issubdtype(pixels.dtype,np.floating): raise ValueError('镜头/透视必须在最终量化前运行；不接受已量化的导出拼块')
    if S.source_bound(value):
        if list(M.file_stamp(spec.optics_path))!=spec.optics_stamp: raise ValueError('镜头/透视出片源图发生变化')
        M.verify_source(value,spec.optics_path,pixels.shape[:2])
    stage = OpticsStage(value,pixels.shape[:2]); result = stage.apply_np(pixels,cancelled=cancelled)
    if S.source_bound(value) and list(M.file_stamp(spec.optics_path))!=spec.optics_stamp: raise ValueError('镜头/透视渲染期间源图变化')
    return result,{'applied':True,'ms':stage.last_ms,'crop_zoom':stage.zoom,'algorithm':'rust-f64-composed-remap-v1','profile':value['lens']['profile']}


def transfer(packet, *, metadata, source_binding, input_rgb):
    """For an explicitly selected preset/batch target. Never mutate target here."""
    from .optics_perspective import automatic
    if type(packet) is not dict or set(packet)!={'version','manual','auto_mode','lens_auto','excluded'} or packet['version']!=1:
        raise ValueError('镜头/透视预设不兼容')
    if type(packet['lens_auto']) is not bool or packet['auto_mode'] not in ('off','smart','horizontal','vertical'): raise ValueError('镜头/透视自动模式无效')
    value = S.check(packet['manual'])
    if S.source_bound(value): raise ValueError('可移植镜头/透视预设不能携带源图身份或引导线')
    if packet['lens_auto']:
        options = L.candidates(metadata)
        if len(options)!=1: raise ValueError('目标图片没有唯一镜头配置，批量未应用此项')
        value['lens']['profile'] = L.resolve(options[0],metadata,input_rgb.shape[:2]); value['lens']['enabled'] = True
    if packet['auto_mode']!='off':
        value['source'] = source_binding
        lens_only = deepcopy(value); lens_only['perspective'] = S.empty()['perspective']; lens_only['lens']['crop_lock'] = False
        lens_input = OpticsStage(lens_only,input_rgb.shape[:2]).apply_np(input_rgb)
        solved,analysis = automatic(lens_input,packet['auto_mode'])
        value['perspective'].update(mode=packet['auto_mode'],matrix=solved,analysis=analysis)
    value['source'] = source_binding if S.source_bound(value) else None
    return S.check(value)


def verify_snapshot(snap,path,shape=None):
    value=S.check(snap.get('optics'))
    if S.source_bound(value): M.verify_source(value,path,shape)


def import_metadata(engine,decoded,*,new=False):
    engine._optics_metadata=L.metadata(decoded,engine._docs[engine._doc_index]['path'])
    engine._optics_import_note=engine._optics_metadata.get('note','') or '已保留该照片的镜头/透视配方；没有重新套用 RAW 默认值'
    if new: import_default(engine,decoded)
