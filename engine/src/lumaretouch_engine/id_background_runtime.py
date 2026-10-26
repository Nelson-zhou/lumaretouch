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
    from .common_background_source import verify_snapshot as verify_common
    verify_common(snap,path,shape)
    if snap.get('creative_base') is not None or snap.get('creative_id_background_context') is not None:
        from .creative_derived_id_background import verify_snapshot as derived_verify
        return derived_verify(snap,path,shape)
    value=S.check(snap.get('id_background'))
    if value['source'] is not None:M.verify_source(value,path,shape)
    if value['background']['kind']=='asset':
        bundle=A.check_bundle(snap.get('id_background_bundle'))
        if bundle is None or bundle['binding']!=value['background']['asset']:raise ValueError('背景素材身份不匹配')

def check_export_decode(snap,path,before,shape):
    from .common_background_source import check_export_decode as check_common
    check_common(snap,path,before,shape)
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
            source_pixels=None,force_prompted=False,original_shadow_pixels=None,cancelled=lambda:False):
    from . import id_background_support as U,id_background_native as N
    from . import spill_removal_render as SP,original_shadow_render as OS
    value=S.check(value);h,w=source.shape[:2]
    if cancelled():raise InterruptedError('证件照完整场准备已取消')
    if h*w>MAX_PIXELS:raise ValueError('证件照完整场超过 3200 万像素预算；不会降级为放大代理蒙版')
    from .cpu_memory_budget import available_estimate
    asset=value['background'].get('asset');asset_pixels=asset['width']*asset['height'] if asset and value['background']['kind']=='asset' else 0
    scale=min(w/value['source']['width'],h/value['source']['height'])
    if N.memory_estimate((h,w),value,render_scale=scale)+SP.memory_estimate((h,w),value)+OS.memory_estimate((h,w),value)+asset_pixels*48+64*1024**2>available_estimate():raise MemoryError('背景、祛染色、原阴影完整场与素材超过可用内存，不会降低源图质量')
    binding=value['support'][value['selected_support']]
    if binding is None:raise ValueError('请先独立确认此保留范围')
    spill_input=SP.source_identity(source,value['source'],full_source=full_source,cancelled=cancelled) if SP.active(value) else None
    alpha=U.raster(binding,path,source,full_source=full_source,cancelled=cancelled,
        effective_source=effective_source,source_input=source_input,source_pixels=source_pixels,
        force_prompted=force_prompted)
    # Estimate from the independently reviewed source alpha, before ID edge,
    # opacity or shadow processing. The matte itself is never altered by spill.
    spill=SP.prepare(value,source,alpha,full_source=full_source,render_scale=scale,cancelled=cancelled)
    if spill_input is not None and spill_input!={key:spill['spill_source'][key] for key in spill_input}:
        raise ValueError('Spill source changed while resolving reviewed foreground support')
    bg=background(value,bundle,(h,w),cancelled)
    original_shadow_proof=None
    if OS.active(value):
        display_background=bg
        if full_source:
            if original_shadow_pixels is not None:
                raise ValueError('原阴影完整导出不能混用第二份源图输入')
            original_pixels,original_alpha=source,alpha
        else:
            # The locator above may be RGB8-derived. It never supplies original
            # shadow evidence: replay the reviewed matte on actual full pixels.
            original_pixels=original_shadow_pixels
            OS.source_identity(original_pixels,value['source'],cancelled=cancelled)
            original_alpha=U.raster(binding,path,original_pixels,full_source=True,cancelled=cancelled,
                effective_source=effective_source,source_input=None,
                source_pixels=original_pixels if effective_source is not None else None)
        if not full_source:
            # Shade the actual full background before reducing completed RGB.
            # Opacity multiplication / Soft Light do not commute with resizing.
            bg=background(value,bundle,original_pixels.shape[:2],cancelled)
        bg,original_shadow_proof=OS.prepare(value,original_pixels,original_alpha,bg,
            render_shape=(h,w),display_background=display_background,cancelled=cancelled)
    scale=min(w/value['source']['width'],h/value['source']['height'])
    prepared=N.prepare(alpha,bg,value,render_scale=scale,cancelled=cancelled)
    if original_shadow_proof is not None:
        if OS._hash(prepared['background'],cancelled)!=original_shadow_proof['background_sha256']:
            raise ValueError('原阴影背景场被另一投影改变；不能叠加重复阴影')
        prepared['original_shadow_source']=original_shadow_proof
        for field in prepared.values():
            if isinstance(field,np.ndarray):field.setflags(write=False)
    if cancelled():raise InterruptedError('证件照完整场准备已取消')
    return {**prepared,**spill} if spill else prepared

def _stage_proof(stage):
    from hashlib import sha256
    field=stage.fields
    if field is None:return stage.required,stage.suspended,None
    # A writable CPU/numpy alias can bypass a tensor version increment. Bind
    # actual packed coverage/background content as well as allocation identity.
    digest=sha256()
    spill=getattr(stage,'spill_source',None)
    original_shadow=getattr(stage,'original_shadow_source',None)
    if tuple(field.shape)!=(1,8 if spill is not None else 4,*stage.shape):
        raise ValueError('ID background installed field extent changed')
    if spill is not None:
        from .spill_removal_render import check_source_proof
        digest.update(check_source_proof(spill,tuple(spill.get('shape',[])[:2])).encode('utf-8'))
        digest.update(json.dumps(getattr(stage,'spill_window',None),allow_nan=False).encode('utf-8'))
    if original_shadow is not None:
        from .original_shadow_render import check_source_proof
        digest.update(check_source_proof(original_shadow,tuple(original_shadow.get('render_shape',[])[:2])).encode('utf-8'))
        digest.update(json.dumps(getattr(stage,'original_shadow_window',None),allow_nan=False).encode('utf-8'))
    for y in range(0,stage.shape[0],64):
        block=field[:,:,y:y+64].detach().cpu().numpy()
        if block.dtype!=np.float32 or not np.isfinite(block).all():
            raise ValueError('ID background installed fields changed type or finite contract')
        digest.update(memoryview(np.ascontiguousarray(block)).cast('B'))
    return (stage.required,stage.suspended,
        (id(field),field.data_ptr(),int(field._version),tuple(field.shape),str(field.dtype),str(field.device),digest.hexdigest()))


def _install(stage,prepared,window=None):
    """Carry compact full-source proof, not extra compositor tensor channels."""
    from copy import deepcopy
    from . import original_shadow_render as OS
    proof=prepared.get('original_shadow_source')
    if proof is not None:
        OS.check_source_proof(proof,prepared['alpha'].shape)
        # Export owns one frozen full-field proof at preparation and rechecks
        # before publication. Do not rehash a whole image for every small tile.
        if window is None and OS._hash(prepared['background'])!=proof['background_sha256']:
            raise ValueError('原阴影背景场与审核源图证明不匹配')
    stage.install(prepared,window)
    stage.original_shadow_source=deepcopy(proof)
    stage.original_shadow_window=None if proof is None or window is None else tuple(window)


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
        from . import original_shadow_render as OS
        if OS.active(value):key=(key,OS.live_source_key(engine,value))
        return key,None,pixels,source,packet
    dependency=P.dependency_stamp() if prompted else None
    automatic=None
    if S.active(value) and support and any(o['kind']=='automatic_foreground' and o['enabled'] for o in support['mask']['recipe']['objects']):
        from .automatic_foreground import dependency_stamp
        automatic=dependency_stamp()
    key=(json.dumps(value,sort_keys=True),M.file_stamp(row['path']),id(pipe.src_f32),dependency,automatic)
    pixels=pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy() if S.active(value) else None
    from . import spill_removal_render as SP
    if SP.active(value):
        # A writable alias of src_f32 does not change object identity. Spill
        # estimation must bind actual bytes before accepting a cached field.
        key=(*key,json.dumps(SP.source_identity(pixels,value['source']),sort_keys=True))
    from . import original_shadow_render as OS
    if OS.active(value):key=(*key,OS.live_source_key(engine,value),OS._hash(pixels))
    return key,row['path'],pixels,None,None


def sync(engine,*,strict=False):
    pipe=engine._vram
    if pipe is None:return
    from .common_background_source import verify_live
    verify_live(engine)
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
                effective_source=effective,source_input=packet,force_prompted=strict,
                original_shadow_pixels=_original_shadow_live_pixels(engine,value))
            if _live_input(engine,value)[0]!=stamp:
                raise ValueError('ID background source, support, asset or model changed during preparation')
            _install(stage,prepared)
        pipe.id_background=stage;pipe._id_background_key=stamp
        pipe._id_background_field_proof=_stage_proof(stage)
    except Exception as error:
        stage=IDBackgroundStage(pipe.device,(pipe.h,pipe.w));stage.required=S.active(value);stage.suspended=str(error) if stage.required else None
        pipe.id_background=stage;pipe._id_background_key=stamp
        pipe._id_background_field_proof=_stage_proof(stage)
        if strict:raise


def _original_shadow_live_pixels(engine,value):
    from . import original_shadow_render as OS
    return OS.full_source(engine,value) if OS.active(value) else None


def report(engine):
    from . import spill_removal_native as SP,original_shadow_native as OS
    stage=getattr(engine._vram,'id_background',None)
    version=engine._document_versions().version(engine._docs[engine._doc_index]) if 0<=engine._doc_index<len(engine._docs) else None
    return {'recipe':S.check(getattr(engine,'_id_background',None)), 'available':available(),
            'spill_protocol':1,'spill_available':SP.available(),
            'original_shadow_protocol':1,'original_shadow_available':OS.available(),
            'recipe_document_id':version.document_id if version else '', 'recipe_revision':str(version.revision) if version else '',
            'suspended':getattr(stage,'suspended',None),'boundaries':[
                '三种范围逐类手动审核；不自动判断接触关系，不提供自动发丝抠像',
                '源图手工矢量按目标尺寸重放，使用现有 8 位覆盖度；提示模型使用其固有低分辨率候选，不宣称发丝或原生全尺寸 alpha',
                '自动前景由固定六类模型在有界 RGB8 分析副本上产生，仅合并头发、皮肤与衣物，排除 others；全图类别不证明单人、遮挡完整性或证件照合规，原照片仍保留完整精度',
                '新阴影为线性 sRGB 二维设计投影，不是物理三维光照或原阴影提取',
                '证件照恢复使用独立目标，只减弱当前换背景、原阴影及祛染色贡献并保留上游编辑',
                '原阴影为源数据估计的黑色标量图层，不是 AI、三维光照恢复或原地面像素粘贴；需要分别审核同材质明亮地面与阴影范围',
                '原阴影主体范围只接受完整源图手工矢量重放；提示模型代理 alpha 不作为原阴影提取证据',
                '原阴影只适用于已确认的均匀漫反射地面；深色、纹理、反射、彩色照明与主体本色可能无法区分，不能保证提取',
                '不一致、过暗、过亮或接近噪声的选中像素保持零阴影；主体边缘和接触阴影可能被保守排除，不保证完整保留',
                '原阴影普通与正片叠底对黑色图层数学等价；柔光是不同的艺术性调暗，不能同时开启新投影阴影',
                '原阴影始终从实际完整原图或派生浮点源提取；预览只缩小完成阴影混合的背景，不使用 RGB8 代理作为证据',
                '实时素材背景预览用完整阴影/背景的缩小透射比维持零强度中性；与最终全尺寸采样可有差异，以完整前后审核与导出为准',
                '祛染色从审核源图估计有证据的颜色方向，只作用于当前 SDR 像素；HDR 编辑像素原样旁路，不裁切或压平',
                '祛染色前后景联合颜色估计使用最长 1024 像素引导层，并在完整源图逐像素细化；不是原尺寸联合 F/B 求解或自动发丝蒙版',
                '接近不透明边缘的反射染色使用独立门控启发式；深层不透明染色与主体本色可能无法区分',
                '强烈非线性上游改色后，源图估计的祛染色方向可能不再合适，需重新检查并减弱或关闭',
                '当前源图、真实选定参考与审核主体关联三种吸管均读取经验证的代理浮点输入',
                '原尺寸检查与导出共用完整场；超过预算明确拒绝，不静默降质']}

def export_prepare(spec,source,*,cancelled=lambda:False):
    # A reused export specification cannot retain an earlier consumer stamp.
    spec._id_recovery_consumer=None
    spec.id_background_prepared=None
    spec._id_background_prepared_proof=None
    spec._spill_source_input=None
    spec._original_shadow_source_input=None
    spec._id_background_cancelled=cancelled
    if not S.active(spec.id_background):return
    path=spec.id_background_path
    if not path or list(M.file_stamp(path))!=spec.id_background_stamp:raise ValueError('证件照换背景导出源图身份缺失或变化')
    derived=getattr(spec,'creative_base',None) is not None
    effective=None
    if derived:
        from .creative_derived_id_background import verify_export
        effective=verify_export(spec,source)['source']
    else:
        M.verify_source(spec.id_background,path,source.shape[:2])
        from . import original_shadow_render as OS
        if OS.active(spec.id_background):
            bits=OS.verify_original_format(path)
            if bits==16 and source.dtype!=np.uint16:
                raise ValueError('Original-shadow export requires genuine full-precision RGB16, not an RGB8 surrogate')
    prepared=prepare(spec.id_background,spec.id_background_bundle,None if derived else path,source,
        full_source=True,effective_source=effective,source_pixels=source if derived else None,cancelled=cancelled)
    from . import spill_removal_render as SP,original_shadow_render as OS
    spill_active=SP.active(spec.id_background)
    original_shadow_active=OS.active(spec.id_background)
    if spill_active:spec._spill_source_input=source
    if original_shadow_active:spec._original_shadow_source_input=source
    if derived:
        verify_export(spec,source)
    if derived or spill_active or original_shadow_active:
        spec._id_background_prepared_proof=_prepared_proof(spec,prepared)
        for field in prepared.values():
            if isinstance(field,np.ndarray):field.setflags(write=False)
    spec.id_background_prepared=prepared
    finish_export(spec)


def _prepared_proof(spec,prepared):
    from hashlib import sha256
    from . import spill_removal_render as SP,original_shadow_render as OS
    value=S.check(spec.id_background);source=value['source']
    spill_active=SP.active(value)
    original_shadow_active=OS.active(value)
    expected={'alpha','background','encoding','render_scale'} | (set(SP.FIELD_KEYS) if spill_active else set()) | (set(OS.FIELD_KEYS) if original_shadow_active else set())
    if type(prepared) is not dict or set(prepared)!=expected:
        raise ValueError('ID background full fields lack their exact preparation contract')
    if prepared['encoding']!='linear-srgb-d65' or prepared['render_scale']!=1.:
        raise ValueError('ID background export cannot substitute proxy-scale or encoded fields')
    hashes=[]
    fields=[('alpha',(source['height'],source['width'])),
            ('background',(source['height'],source['width'],3))]
    if spill_active:fields.extend((('spill_delta',(source['height'],source['width'],3)),
                                   ('spill_confidence',(source['height'],source['width']))))
    cancelled=getattr(spec,'_id_background_cancelled',lambda:False)
    for key,shape in fields:
        pixels=prepared[key]
        if (type(pixels) is not np.ndarray or pixels.dtype!=np.float32 or pixels.shape!=shape
                or not np.isfinite(pixels).all()
                or key!='spill_delta' and (np.any(pixels<0) or np.any(pixels>1))):
            raise ValueError('ID background export fields are not complete finite SDR coverage/linear pixels')
        digest=sha256()
        for row in pixels:
            if cancelled():raise InterruptedError('证件照完整场验证已取消')
            digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
        hashes.append(digest.hexdigest())
    if spill_active:
        proof=prepared['spill_source']
        checked=SP.check_source_proof(proof,(source['height'],source['width']),source)
        actual=SP.source_identity(getattr(spec,'_spill_source_input',None),source,
                                  full_source=True,cancelled=cancelled)
        if actual!={key:proof[key] for key in actual}:
            raise ValueError('Spill estimator source pixels changed during export')
        hashes.append(sha256(checked.encode('utf-8')).hexdigest())
    if original_shadow_active:
        proof=prepared['original_shadow_source']
        checked=OS.check_source_proof(proof,(source['height'],source['width']),source,value)
        actual=OS.source_identity(getattr(spec,'_original_shadow_source_input',None),source,
                                  cancelled=cancelled)
        if actual!={key:proof[key] for key in actual} or hashes[1]!=proof['background_sha256']:
            raise ValueError('Original-shadow actual source pixels or prepared background changed during export')
        hashes.append(sha256(checked.encode('utf-8')).hexdigest())
    return json.dumps(value,sort_keys=True),tuple(hashes)

def attach_tile(pipe,spec,window):
    stage=IDBackgroundStage(pipe.device,(pipe.h,pipe.w))
    if S.active(spec.id_background):
        if spec.id_background_prepared is None:raise ValueError('缺少证件照完整背景场')
        _install(stage,spec.id_background_prepared,window)
    pipe.id_background=stage

def finish_export(spec):
    from . import spill_removal_render as SP,original_shadow_render as OS
    if S.active(spec.id_background) and list(M.file_stamp(spec.id_background_path))!=spec.id_background_stamp:raise ValueError('证件照换背景导出期间源图变化')
    if S.active(spec.id_background) and getattr(spec,'creative_base',None) is not None:
        from .creative_derived_id_background import verify_snapshot
        verify_snapshot({'creative_base':spec.creative_base,'id_background':spec.id_background,
            'id_background_bundle':spec.id_background_bundle,
            'creative_id_background_context':spec.creative_id_background_context},spec.id_background_path)
    if S.active(spec.id_background) and (getattr(spec,'creative_base',None) is not None or SP.active(spec.id_background) or OS.active(spec.id_background)):
        if _prepared_proof(spec,spec.id_background_prepared)!=getattr(spec,'_id_background_prepared_proof',None):
            raise ValueError('ID background source-bound fields changed during export')
    # Initial ID preparation precedes recovery preparation. Once that consumer
    # proof exists, every finalization also checks the actual full ID fields.
    if getattr(spec,'_id_recovery_consumer',None) is not None:
        from .id_background_recovery import verify_export
        verify_export(spec)

def resident_bytes(spec):
    return sum(v.nbytes for v in (spec.id_background_prepared or {}).values() if isinstance(v,np.ndarray))
