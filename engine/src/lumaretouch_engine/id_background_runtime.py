"""One source-bound ID replacement path for preview, inspection and export."""
import json
import numpy as np
from . import id_background_state as S, id_background_assets as A, local_mask_state as M
from .id_background_stage import IDBackgroundStage

MAX_PIXELS=32_000_000

def available():
    from . import id_background_native as N
    return N.available()

def verify_snapshot(snap,path,shape=None):
    value=S.check(snap.get('id_background'))
    if value['source'] is not None:M.verify_source(value,path,shape)
    if value['background']['kind']=='asset':
        bundle=A.check_bundle(snap.get('id_background_bundle'))
        if bundle is None or bundle['binding']!=value['background']['asset']:raise ValueError('背景素材身份不匹配')

def check_export_decode(snap,path,before,shape):
    value=S.check(snap.get('id_background'))
    if value['source'] is None:return
    if before is None or M.file_stamp(path)!=before:raise ValueError('证件照换背景源图在解码期间变化')
    verify_snapshot(snap,path,shape)
    if M.file_stamp(path)!=before:raise ValueError('证件照换背景源图验证期间变化')
    snap['id_background_path']=path;snap['id_background_stamp']=list(before)

def configure_export(spec,snap,shape,*,for_document):
    spec.id_background=S.check(snap.get('id_background'))
    spec.id_background_bundle=snap.get('id_background_bundle')
    spec.id_background_path=snap.get('id_background_path')
    spec.id_background_stamp=snap.get('id_background_stamp')
    if S.active(spec.id_background) and not for_document:raise ValueError('证件照保留范围不能移植到另一张照片')

def _linear(rgb):
    x=np.asarray(rgb,dtype=np.float32)
    return np.where(x<=0.04045,x/12.92,((x+0.055)/1.055)**2.4).astype(np.float32)

def background(value,bundle,shape,cancelled):
    h,w=shape;b=value['background']
    if b['kind']=='solid':return np.broadcast_to(_linear(np.array(b['color'])/255.0),(h,w,3)).copy()
    asset=A.unpack(bundle,cancelled=cancelled)
    if asset.binding!=b['asset']:raise ValueError('背景素材与配方身份不匹配')
    pixels=A.flatten(asset,b['color']);ah,aw=pixels.shape[:2]
    # Bounded row sampling; uncovered centered-image pixels use the explicit
    # selected solid base, never a smeared edge or unspecified black fill.
    out=np.empty((h,w,3),np.float32)
    scale=max(w/aw,h/ah)*b['scale'] if b['fit']=='center' else None
    for y in range(h):
        if cancelled():raise InterruptedError('背景采样已取消')
        if scale is None:xs=(np.arange(w)+0.5)*aw/w-0.5;sy=(y+0.5)*ah/h-0.5
        else:xs=(np.arange(w)+0.5-w*(0.5+b['x']))/scale+aw/2-0.5;sy=(y+0.5-h*(0.5+b['y']))/scale+ah/2-0.5
        valid=(xs>=-0.5)&(xs<=aw-0.5)&(sy>=-0.5)&(sy<=ah-0.5)
        xs=np.clip(xs,0,aw-1);sy=np.clip(sy,0,ah-1);x0=np.floor(xs).astype(int);x1=np.minimum(x0+1,aw-1);y0=int(sy);y1=min(y0+1,ah-1);fx=(xs-x0)[:,None];fy=sy-y0
        out[y]=(pixels[y0,x0]*(1-fx)+pixels[y0,x1]*fx)*(1-fy)+(pixels[y1,x0]*(1-fx)+pixels[y1,x1]*fx)*fy
        out[y,~valid]=_linear(np.array(b["color"])/255.0)
    return out

def prepare(value,bundle,path,source,*,full_source=False,cancelled=lambda:False):
    from . import id_background_support as U,id_background_native as N
    value=S.check(value);h,w=source.shape[:2]
    if h*w>MAX_PIXELS:raise ValueError('证件照完整场超过 3200 万像素预算；不会降级为放大代理蒙版')
    from .cpu_memory_budget import available_estimate
    asset=value['background'].get('asset');asset_pixels=asset['width']*asset['height'] if asset and value['background']['kind']=='asset' else 0
    scale=min(w/value['source']['width'],h/value['source']['height'])
    if N.memory_estimate((h,w),value,render_scale=scale)+asset_pixels*48+64*1024**2>available_estimate():raise MemoryError('背景完整场与素材超过可用内存，不会降低源图质量')
    binding=value['support'][value['selected_support']]
    if binding is None:raise ValueError('请先独立确认此保留范围')
    alpha=U.raster(binding,path,source,full_source=full_source,cancelled=cancelled)
    bg=background(value,bundle,(h,w),cancelled)
    scale=min(w/value['source']['width'],h/value['source']['height'])
    return N.prepare(alpha,bg,value,render_scale=scale,cancelled=cancelled)

def sync(engine,*,strict=False):
    pipe=engine._vram
    if pipe is None:return
    value=S.check(getattr(engine,'_id_background',None))
    stamp=None
    try:
        row=engine._docs[engine._doc_index]
        from . import prompted_mask_resolver as P
        support=value['support'][value['selected_support']]
        dependency=P.dependency_stamp() if S.active(value) and support and P.active(support['mask']['recipe']) else None
        stamp=(json.dumps(value,sort_keys=True),M.file_stamp(row['path']),id(pipe.src_f32),dependency)
        if getattr(pipe,'_id_background_key',None)==stamp:
            if strict and pipe.id_background.suspended:raise ValueError(pipe.id_background.suspended)
            return
        stage=IDBackgroundStage(pipe.device,(pipe.h,pipe.w))
        if S.active(value):
            if engine._bg.get('active') or engine._sky_replacement['enabled'] or any(engine._studio_background['parameters'][k] for k in ('intrusions','blemish_background','blemish_floor','uniformity','banding','enhancement')):
                raise ValueError('证件照换背景与旧换底、换天空、影棚背景调整互斥')
            if row.get('_local_source_stamp')!=M.file_stamp(row['path']):raise ValueError('原图已改变，请重新打开')
            M.verify_source(value,row['path'],(row['src_h'],row['src_w']))
            src=pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy()
            stage.install(prepare(value,getattr(engine,'_id_background_bundle',None),row['path'],src))
        pipe.id_background=stage;pipe._id_background_key=stamp
    except Exception as error:
        stage=IDBackgroundStage(pipe.device,(pipe.h,pipe.w));stage.required=S.active(value);stage.suspended=str(error) if stage.required else None
        pipe.id_background=stage;pipe._id_background_key=stamp
        if strict:raise

def report(engine):
    stage=getattr(engine._vram,'id_background',None)
    version=engine._document_versions().version(engine._docs[engine._doc_index]) if 0<=engine._doc_index<len(engine._docs) else None
    return {'recipe':S.check(getattr(engine,'_id_background',None)), 'available':available(),
            'recipe_document_id':version.document_id if version else '', 'recipe_revision':str(version.revision) if version else '',
            'suspended':getattr(stage,'suspended',None),'boundaries':[
                '三种范围逐类手动审核；不自动判断接触关系，不提供自动发丝抠像',
                '源图手工矢量按目标尺寸重放，使用现有 8 位覆盖度；提示模型使用其固有低分辨率候选，不宣称发丝或原生全尺寸 alpha',
                '新阴影为线性 sRGB 二维设计投影，不是物理三维光照或原阴影提取',
                '祛染色与原阴影提取尚未实现；原图、真实选定参考与审核主体关联三种吸管均读取经验证的代理浮点输入',
                '原尺寸检查与导出共用完整场；超过预算明确拒绝，不静默降质']}

def export_prepare(spec,source,*,cancelled=lambda:False):
    spec.id_background_prepared=None
    if not S.active(spec.id_background):return
    path=spec.id_background_path
    if not path or list(M.file_stamp(path))!=spec.id_background_stamp:raise ValueError('证件照换背景导出源图身份缺失或变化')
    M.verify_source(spec.id_background,path,source.shape[:2])
    spec.id_background_prepared=prepare(spec.id_background,spec.id_background_bundle,path,source,full_source=True,cancelled=cancelled)
    finish_export(spec)

def attach_tile(pipe,spec,window):
    stage=IDBackgroundStage(pipe.device,(pipe.h,pipe.w))
    if S.active(spec.id_background):
        if spec.id_background_prepared is None:raise ValueError('缺少证件照完整背景场')
        stage.install(spec.id_background_prepared,window)
    pipe.id_background=stage

def finish_export(spec):
    if S.active(spec.id_background) and list(M.file_stamp(spec.id_background_path))!=spec.id_background_stamp:raise ValueError('证件照换背景导出期间源图变化')

def resident_bytes(spec):
    return sum(v.nbytes for v in (spec.id_background_prepared or {}).values() if isinstance(v,np.ndarray))
