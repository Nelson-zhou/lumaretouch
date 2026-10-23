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
    if snap.get('creative_base') is not None or snap.get('creative_id_background_context') is not None:
        from .creative_derived_id_background import verify_snapshot as derived_verify
        return derived_verify(snap,path,shape)
    value=S.check(snap.get('id_background'))
    if value['source'] is not None:M.verify_source(value,path,shape)
    if value['background']['kind']=='asset':
        bundle=A.check_bundle(snap.get('id_background_bundle'))
        if bundle is None or bundle['binding']!=value['background']['asset']:raise ValueError('背景素材身份不匹配')

def check_export_decode(snap,path,before,shape):
    value=S.check(snap.get('id_background'))
    if value['source'] is None and snap.get('creative_id_background_context') is None:return
    if before is None or M.file_stamp(path)!=before:raise ValueError('证件照换背景源图在解码期间变化')
    verify_snapshot(snap,path,None if snap.get('creative_base') is not None else shape)
    if M.file_stamp(path)!=before:raise ValueError('证件照换背景源图验证期间变化')
    snap['id_background_path']=path;snap['id_background_stamp']=list(before)

def configure_export(spec,snap,shape,*,for_document):
    spec.id_background=S.check(snap.get('id_background'))
    spec.id_background_bundle=snap.get('id_background_bundle')
    spec.id_background_path=snap.get('id_background_path')
    spec.id_background_stamp=snap.get('id_background_stamp')
    if (S.active(spec.id_background) or snap.get('creative_id_background_context') is not None) and not for_document:
        raise ValueError('证件照保留范围不能移植到另一张照片')
    if snap.get('creative_base') is not None:
        from copy import deepcopy
        from .creative_derived_id_background import verify_snapshot as derived_verify
        derived_verify(snap,spec.id_background_path,shape)
        spec.creative_id_background_context=deepcopy(snap.get('creative_id_background_context'))

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

def prepare(value,bundle,path,source,*,full_source=False,effective_source=None,source_input=None,
            source_pixels=None,force_prompted=False,cancelled=lambda:False):
    from . import id_background_support as U,id_background_native as N
    value=S.check(value);h,w=source.shape[:2]
    if h*w>MAX_PIXELS:raise ValueError('证件照完整场超过 3200 万像素预算；不会降级为放大代理蒙版')
    from .cpu_memory_budget import available_estimate
    asset=value['background'].get('asset');asset_pixels=asset['width']*asset['height'] if asset and value['background']['kind']=='asset' else 0
    scale=min(w/value['source']['width'],h/value['source']['height'])
    if N.memory_estimate((h,w),value,render_scale=scale)+asset_pixels*48+64*1024**2>available_estimate():raise MemoryError('背景完整场与素材超过可用内存，不会降低源图质量')
    binding=value['support'][value['selected_support']]
    if binding is None:raise ValueError('请先独立确认此保留范围')
    alpha=U.raster(binding,path,source,full_source=full_source,cancelled=cancelled,
        effective_source=effective_source,source_input=source_input,source_pixels=source_pixels,
        force_prompted=force_prompted)
    bg=background(value,bundle,(h,w),cancelled)
    scale=min(w/value['source']['width'],h/value['source']['height'])
    return N.prepare(alpha,bg,value,render_scale=scale,cancelled=cancelled)

def _stage_proof(stage):
    from hashlib import sha256
    field=stage.fields
    if field is None:return stage.required,stage.suspended,None
    # A writable CPU/numpy alias can bypass a tensor version increment. Bind
    # actual packed coverage/background content as well as allocation identity.
    digest=sha256()
    if tuple(field.shape)!=(1,4,*stage.shape):
        raise ValueError('ID background installed field extent changed')
    for y in range(0,stage.shape[0],64):
        block=field[:,:,y:y+64].detach().cpu().numpy()
        if block.dtype!=np.float32 or not np.isfinite(block).all():
            raise ValueError('ID background installed fields changed type or finite contract')
        digest.update(memoryview(np.ascontiguousarray(block)).cast('B'))
    return (stage.required,stage.suspended,
        (id(field),field.data_ptr(),int(field._version),tuple(field.shape),str(field.dtype),str(field.device),digest.hexdigest()))


def _live_input(engine,value):
    """Return actual source pixels and an exclusive inference input route."""
    from . import prompted_mask_resolver as P
    pipe=engine._vram;row=engine._docs[engine._doc_index]
    support=value['support'][value['selected_support']]
    prompted=bool(S.active(value) and support and P.active(support['mask']['recipe']))
    if getattr(engine,'_creative_base',None) is not None:
        from . import creative_derived_id_background as C,creative_derived_source as D
        _,pixels,key=C.preview(engine,value)
        source=D.binding(engine)
        packet=None
        if prompted:
            from .creative_derived_prompted import capture,cache_identity
            packet=capture(engine)
            key=(key,cache_identity(packet,source),P.dependency_stamp())
        return key,None,pixels,source,packet
    dependency=P.dependency_stamp() if prompted else None
    key=(json.dumps(value,sort_keys=True),M.file_stamp(row['path']),id(pipe.src_f32),dependency)
    pixels=pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy() if S.active(value) else None
    return key,row['path'],pixels,None,None


def sync(engine,*,strict=False):
    pipe=engine._vram
    if pipe is None:return
    value=S.check(getattr(engine,'_id_background',None));stamp=None
    try:
        row=engine._docs[engine._doc_index]
        stamp,path,src,effective,packet=_live_input(engine,value)
        if getattr(pipe,'_id_background_key',None)==stamp:
            if _stage_proof(pipe.id_background)!=getattr(pipe,'_id_background_field_proof',None):
                raise ValueError('ID background prepared fields changed after installation')
            if strict and pipe.id_background.suspended:raise ValueError(pipe.id_background.suspended)
            if not strict or not S.active(value):return
        stage=IDBackgroundStage(pipe.device,(pipe.h,pipe.w))
        if S.active(value):
            if engine._bg.get('active') or engine._sky_replacement['enabled'] or any(engine._studio_background['parameters'][k] for k in ('intrusions','blemish_background','blemish_floor','uniformity','banding','enhancement')):
                raise ValueError('证件照换背景与旧换底、换天空、影棚背景调整互斥')
            if effective is None:
                if row.get('_local_source_stamp')!=M.file_stamp(row['path']):raise ValueError('原图已改变，请重新打开')
                M.verify_source(value,row['path'],(row['src_h'],row['src_w']))
            prepared=prepare(value,getattr(engine,'_id_background_bundle',None),path,src,
                effective_source=effective,source_input=packet,force_prompted=strict)
            if _live_input(engine,value)[0]!=stamp:
                raise ValueError('ID background source, support, asset or model changed during preparation')
            stage.install(prepared)
        pipe.id_background=stage;pipe._id_background_key=stamp
        pipe._id_background_field_proof=_stage_proof(stage)
    except Exception as error:
        stage=IDBackgroundStage(pipe.device,(pipe.h,pipe.w));stage.required=S.active(value);stage.suspended=str(error) if stage.required else None
        pipe.id_background=stage;pipe._id_background_key=stamp
        pipe._id_background_field_proof=_stage_proof(stage)
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
                '证件照恢复使用独立目标，只减弱当前换背景贡献并保留上游编辑；祛染色、原阴影提取仍未实现',
                '当前源图、真实选定参考与审核主体关联三种吸管均读取经验证的代理浮点输入',
                '原尺寸检查与导出共用完整场；超过预算明确拒绝，不静默降质']}

def export_prepare(spec,source,*,cancelled=lambda:False):
    # A reused export specification cannot retain an earlier consumer stamp.
    spec._id_recovery_consumer=None
    spec.id_background_prepared=None
    spec._id_background_prepared_proof=None
    if not S.active(spec.id_background):return
    path=spec.id_background_path
    if not path or list(M.file_stamp(path))!=spec.id_background_stamp:raise ValueError('证件照换背景导出源图身份缺失或变化')
    derived=getattr(spec,'creative_base',None) is not None
    effective=None
    if derived:
        from .creative_derived_id_background import verify_export
        effective=verify_export(spec,source)['source']
    else:M.verify_source(spec.id_background,path,source.shape[:2])
    prepared=prepare(spec.id_background,spec.id_background_bundle,None if derived else path,source,
        full_source=True,effective_source=effective,source_pixels=source if derived else None,cancelled=cancelled)
    if derived:
        verify_export(spec,source)
        spec._id_background_prepared_proof=_prepared_proof(spec,prepared)
        prepared['alpha'].setflags(write=False);prepared['background'].setflags(write=False)
    spec.id_background_prepared=prepared
    finish_export(spec)


def _prepared_proof(spec,prepared):
    from hashlib import sha256
    value=S.check(spec.id_background);source=value['source']
    if type(prepared) is not dict or set(prepared)!={'alpha','background','encoding','render_scale'}:
        raise ValueError('ID background full fields lack their exact preparation contract')
    if prepared['encoding']!='linear-srgb-d65' or prepared['render_scale']!=1.:
        raise ValueError('ID background export cannot substitute proxy-scale or encoded fields')
    hashes=[]
    for key,shape in (('alpha',(source['height'],source['width'])),
                      ('background',(source['height'],source['width'],3))):
        pixels=prepared[key]
        if (type(pixels) is not np.ndarray or pixels.dtype!=np.float32 or pixels.shape!=shape
                or not np.isfinite(pixels).all() or np.any(pixels<0) or np.any(pixels>1)):
            raise ValueError('ID background export fields are not complete finite SDR coverage/linear pixels')
        digest=sha256()
        for row in pixels:digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
        hashes.append(digest.hexdigest())
    return json.dumps(value,sort_keys=True),tuple(hashes)

def attach_tile(pipe,spec,window):
    stage=IDBackgroundStage(pipe.device,(pipe.h,pipe.w))
    if S.active(spec.id_background):
        if spec.id_background_prepared is None:raise ValueError('缺少证件照完整背景场')
        stage.install(spec.id_background_prepared,window)
    pipe.id_background=stage

def finish_export(spec):
    if S.active(spec.id_background) and list(M.file_stamp(spec.id_background_path))!=spec.id_background_stamp:raise ValueError('证件照换背景导出期间源图变化')
    if S.active(spec.id_background) and getattr(spec,'creative_base',None) is not None:
        from .creative_derived_id_background import verify_snapshot
        verify_snapshot({'creative_base':spec.creative_base,'id_background':spec.id_background,
            'id_background_bundle':spec.id_background_bundle,
            'creative_id_background_context':spec.creative_id_background_context},spec.id_background_path)
        if _prepared_proof(spec,spec.id_background_prepared)!=getattr(spec,'_id_background_prepared_proof',None):
            raise ValueError('ID background source-bound fields changed during export')
    # Initial ID preparation precedes recovery preparation. Once that consumer
    # proof exists, every finalization also checks the actual full ID fields.
    if getattr(spec,'_id_recovery_consumer',None) is not None:
        from .id_background_recovery import verify_export
        verify_export(spec)

def resident_bytes(spec):
    return sum(v.nbytes for v in (spec.id_background_prepared or {}).values() if isinstance(v,np.ndarray))
