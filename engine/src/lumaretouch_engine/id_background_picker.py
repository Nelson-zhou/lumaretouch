"""Identity-bound current-source, frozen-reference and contact float pickers.

Private native copy/presentation leases bind the actual displayed proxy. RGB
samples come from retained float pixels, never from canvas display bytes.
"""
import os
import uuid
import json
from hashlib import sha256
from copy import deepcopy
import numpy as np
from .color_picker_capture import ColorPickerCapture, PROOF_KEYS
from .source_patch_capture import write_capture, _hex, _uint, MAX_U64
from .color_action_sampling import Projection, _region, gather_region, admit, available_memory
from .cpu_memory_budget import available_estimate
from .quant import quantize_t

MODES={'id_background':('original','id-background-source'),'id_background_reference':('reference','id-background-reference'),'id_background_subject':('subject','id-background-subject')}


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _array_proof(value,channels):
    """Hash actual bounded float content, without converting a wrong dtype."""
    if (type(value) is not np.ndarray or value.dtype!=np.float32 or value.ndim!=3
            or value.shape[2]!=channels or min(value.shape[:2])<1):
        raise ValueError('取色输入必须是实际 float32 RGB 或覆盖度')
    digest=sha256()
    for row in value:
        if not np.isfinite(row).all() or np.any(row<0) or np.any(row>1):
            raise ValueError('取色仅支持已验证的不透明 SDR；不会静默剪裁 HDR 或无效覆盖度')
        digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return {'shape':list(value.shape),'sha256':digest.hexdigest()}


def _tensor_proof(value,spec,channels):
    import torch
    if value.dtype!=torch.float32 or tuple(value.shape)!=(1,channels,spec.height,spec.width):
        raise ValueError('取色画面的实际浮点尺寸或类型改变')
    return _array_proof(value[0].permute(1,2,0).detach().cpu().numpy(),channels)


class IDBackgroundCapture(ColorPickerCapture):
    def _target(self,spec):
        """Current target proof is required even when sampling another image."""
        from . import local_mask_state as M,id_background_state as S
        from . import creative_derived_source as D
        value=S.check(getattr(self.engine,'_id_background',None));derived=D.record(self.engine) is not None
        source_tensor=self.engine._vram.src_f32
        actual=_tensor_proof(source_tensor,spec,3)
        if derived:
            from . import creative_derived_id_background as C
            _,rgb,key=C.preview(self.engine,value)
            source=D.binding(self.engine)
        else:
            source=M.bind_source(self.engine)
            if value['source'] is not None and value['source']!=source:
                raise ValueError('背景范围不属于当前取色源图')
            rgb=source_tensor[0].permute(1,2,0).detach().cpu().numpy()
            key=('original-id-picker-v1',source,M.file_stamp(self.engine._doc_path))
        if _array_proof(rgb,3)!=actual:
            raise ValueError('取色源图与实际管线浮点像素不一致')
        target={'source':deepcopy(source),'input':actual,'review_sha256':_digest(value),
                'context_sha256':_digest(key),'projection_sha256':_digest(spec.descriptor())}
        return target,rgb,derived,value

    def _binding_inputs(self,mode,spec,expected=None):
        from . import id_background_support as U
        target,rgb,derived,value=self._target(spec)
        source=target['source']
        if expected is not None and expected.get('target')!=target:
            raise ValueError('取色目标源图、审核配方或投影已改变')
        if mode=='reference':
            from . import reference_color_assets as A
            from .sample_library_controller import SampleLibrary
            selection=getattr(self,'reference_selection',None)
            if type(selection) is not dict or set(selection)!={'sample_id','source','render_sha256','asset_id'}:raise ValueError('请先在样片库选择参考图')
            reference={k:selection[k] for k in ('source','render_sha256','asset_id')}
            with SampleLibrary().store.read() as catalog:
                selected=next((row for row in catalog['samples'] if row['id']==selection['sample_id'] and row['deleted_at'] is None),None)
                if selected is None or selected['reference']!=reference:raise ValueError('选中的参考样片已变化、移除或尚未准备真实像素')
            path=A.cache_root()/(reference['asset_id']+'.npz')
            if path.is_symlink() or not path.is_file() or path.stat().st_size>A.MAX_BYTES or A._hash(path)!=reference['asset_id']:raise ValueError('参考图不可变资源缺失或改变')
            return {'reference':deepcopy(reference),'sample_id':selection['sample_id'],'target':target},None
        if mode=='original':return {'source':source,'target':target},None
        if mode!='subject':raise ValueError('未知证件照取色模式')
        support=value['support']['contact']
        if support is None:raise ValueError('请先独立审核“主体及关联物品”源图范围')
        support=U.check_binding(support,'contact')
        if support['mask']['source']!=source:raise ValueError('主体关联范围不属于当前源图')
        from . import prompted_mask_resolver as P
        packet=None;prompted=None;active_prompted=P.active(support['mask']['recipe'])
        if derived and any(obj['kind']=='prompted' for obj in support['mask']['recipe']['objects']):
            from . import creative_derived_prompted as Q
            packet=Q.capture(self.engine)
            prompted=(Q.cache_identity(packet,source),P.dependency_stamp() if active_prompted else None)
        elif active_prompted:prompted=P.dependency_stamp()
        binding={'source':source,'support_sha256':support['recipe_sha256'],'category':'contact',
                 'prompted_sha256':None if prompted is None else _digest(prompted),'target':target}
        if expected is not None and any(expected.get(key)!=item for key,item in binding.items()):
            raise ValueError('主体关联取色审核或模型输入已改变，请重新进入取色')
        # Re-rasterize from the exact current float source at every evidence
        # boundary. Cached prompted fields remain usable, but changed actual
        # coverage cannot hide behind unchanged recipe or model identifiers.
        if derived:
            alpha=U.raster(support,None,rgb,effective_source=source,source_input=packet)
        else:alpha=U.raster(support,self.engine._doc_path,rgb)
        if type(alpha) is not np.ndarray or alpha.shape!=rgb.shape[:2]:
            raise ValueError('主体关联范围覆盖度与当前源图尺寸不一致')
        coverage=_array_proof(alpha[...,None],1)
        return {**binding,'coverage':coverage},alpha

    def binding(self,mode,expected=None):
        return self._binding_inputs(mode,Projection.from_pipeline(self.engine._vram),expected)[0]

    def _capture_proof(self,c):
        return _digest({'descriptor':c['descriptor'],'context':c['context'],
            'document_projection':c['document_spec'].descriptor(),'projection':c['spec'].descriptor(),
            'pixels':_tensor_proof(c['pixels'],c['spec'],3),'coverage':_tensor_proof(c['coverage'],c['spec'],1)})

    def matching(self,p):
        c=self.capture
        if c is None:raise ValueError('取色画面已失效，请重新进入')
        d=c['descriptor']
        if any(p.get(k)!=d[k] for k in ('document_id',*PROOF_KEYS)):raise ValueError('取色画面身份改变')
        if self._capture_proof(c)!=c['capture_proof']:raise ValueError('取色画面的实际像素、覆盖度或投影已经改变')
        context,spec=self._context()
        if context!=c['context'] or spec!=c['document_spec'] or self.binding(d['picker_mode'],d['source_binding'])!=d['source_binding']:raise ValueError('照片、参考图或审核范围已变化')
        return c
    def handle(self,p):
        action=p.get('action');allowed={'cmd','action','capture_id','ticket','document_id'}
        allowed|={'epoch','picker_action','picker_channel','reference'} if action=='arm' else {'generation'}
        if set(p)-allowed or action not in ('arm','presented','cancel'):raise ValueError('Invalid ID background capture')
        if not _hex(p.get('capture_id')) or not _uint(p.get('ticket')) or not _uint(p.get('document_id')):raise ValueError('Invalid capture identity')
        event={'event':'color_picker_capture','action':action,'capture_id':p['capture_id'],'ticket':p['ticket'],'success':True}
        if action=='cancel':
            if self.capture and all(self.capture['descriptor'][k]==p.get(k) for k in ('capture_id','ticket','document_id')):self.invalidate()
            return event
        if action=='presented':
            c=self.capture
            if c is None or any(c['descriptor'][k]!=p.get(k) for k in ('capture_id','ticket','document_id','generation')):raise ValueError('Source display proof expired')
            self.matching({**p,**{k:c['descriptor'][k] for k in PROOF_KEYS}});c['eligible']=True
            return event
        self.invalidate();picker=p.get('picker_action')
        if picker not in MODES or p.get('picker_channel')!='master' or not _hex(p.get('epoch')):raise ValueError('Unsupported ID background picker')
        mode,stage=MODES[picker]
        if mode!='reference' and p.get('reference') is not None:raise ValueError('Only reference picker accepts a selected sample')
        self.reference_selection=deepcopy(p.get('reference')) if mode=='reference' else None
        context,document_spec=self._context()
        if context['document_id']!=p['document_id']:raise ValueError('Document changed')
        if self.generation==MAX_U64:raise ValueError('Capture generation exhausted')
        import torch
        pipeline=self.engine._vram
        admit(document_spec,available_memory(pipeline.device))
        if document_spec.width*document_spec.height*80+16*1024**2>max(0,available_estimate()-256*1024**2)*65//100:
            raise MemoryError('Source capture exceeds host budget')
        binding,alpha=self._binding_inputs(mode,document_spec)
        target_source=binding['target']['source']
        if context['full_source']!=[target_source['width'],target_source['height']]:
            raise ValueError('取色目标尺寸与当前不可变源图不一致')
        if mode=='reference':
            from . import reference_color_assets as A
            # load validates archive headers before NumPy allocation. Reserve its
            # documented maximum full RGB/authentic canvas plus proxy headroom.
            if A.MAX_RAW_BYTES*2+128*1024**2>max(0,available_estimate()-256*1024**2)*65//100:raise MemoryError('参考完整像素验证与取色代理超过可用内存预算')
            frame=A.load(A.cache_root(),binding['reference']);h,w=frame.rgb.shape[:2]
            # Reject HDR before interpolation can average an out-of-range
            # contributor back into SDR. Do not silently clip a selected render.
            _array_proof(frame.rgb,3)
            ratio=min(1.,1536/max(h,w));pw=max(1,round(w*ratio));ph=max(1,round(h*ratio))
            spec=Projection(pw,ph,(0.,0.,1.,1.),0.,(0,0,pw,ph),(pw,ph))
            admit(spec,available_estimate());source=torch.from_numpy(np.ascontiguousarray(frame.rgb.transpose(2,0,1)))[None]
            pixels=torch.nn.functional.interpolate(source,size=(ph,pw),mode='bilinear',align_corners=False).contiguous()
            # The immutable reference is an actual rendered canvas: edited
            # backgrounds are visible valid colours too. No scene-provenance
            # mask restriction is applied to reference-view sampling.
            coverage=torch.ones((1,1,ph,pw),dtype=torch.float32);full_source=[w,h]
            del source,frame
        else:
            spec=document_spec
            source=pipeline.src_f32
            if _tensor_proof(source,spec,3)!=binding['target']['input']:
                raise ValueError('实际源图浮点像素在取色期间改变')
            pixels=spec.apply(source).detach().clone();coverage=spec.apply(torch.ones_like(source[:,:1])).detach().clone();full_source=context['full_source']
            if mode=='subject':
                support=torch.as_tensor(alpha,device=source.device)[None,None]
                coverage=coverage*spec.apply(support);del alpha,support
        current,current_spec=self._context()
        if current!=context or current_spec!=document_spec or self.binding(mode,binding)!=binding:raise ValueError('Picker input changed during capture')
        _tensor_proof(pixels,spec,3);_tensor_proof(coverage,spec,1)
        rgb=quantize_t(pixels[0].permute(1,2,0)).contiguous().cpu().numpy()
        valid=(coverage[0,0]>=.999999).contiguous().cpu().numpy()
        # Dim uncovered/non-reviewed source areas for aiming only. Sampling uses
        # untouched float pixels and separately retained conservative coverage.
        rgb[~valid]=(rgb[~valid].astype(np.float32)*.2).astype(np.uint8)
        rgba=np.empty((spec.height,spec.width,4),np.uint8);rgba[...,:3]=rgb;rgba[...,3]=255
        self.generation+=1
        d={**context,'full_source':full_source,'version':1,'domain':'color-action-input','quality':'proxy-float-input','profile':'working-srgb','epoch':p['epoch'],
           'shm_instance':uuid.uuid4().hex,'seq':'1','generation':str(self.generation),'capture_id':p['capture_id'],'ticket':p['ticket'],
           'width':spec.width,'height':spec.height,'projection':spec.descriptor(),'picker_action':picker,'picker_channel':'master','source_stage':stage,
           'picker_mode':mode,'source_binding':binding}
        root=os.environ.get('LRT_INSPECTION_ROOT')
        if not root:raise ValueError('Private source capture root unavailable')
        captured={'descriptor':deepcopy(d),'context':deepcopy(context),'document_spec':document_spec,'spec':spec,'eligible':False,'pixels':pixels,'coverage':coverage}
        captured['capture_proof']=self._capture_proof(captured)
        self.path=write_capture(root,d,rgba,purpose='color-picker');self.capture=captured
        return {**event,'descriptor':deepcopy(d)}
    def sample(self,p):
        if set(p)!={'cmd','action','request_id','document_id','region','picker_mode','source_binding',*PROOF_KEYS} or p['cmd']!='background' or p['action']!='id_sample':raise ValueError('Invalid source sample request')
        c=self.matching(p);d=c['descriptor']
        if not c['eligible']:raise ValueError('Source capture has not been presented')
        if p['picker_mode']!=d['picker_mode'] or p['source_binding']!=d['source_binding']:raise ValueError('取色模式或像素来源身份不符')
        _region(p['region'],c['spec']);rows=gather_region(c['pixels'],p['region'],c['spec']);coverage=gather_region(c['coverage'],p['region'],c['spec'])
        valid=[row for row,cover in zip(rows,coverage) if cover[0]>=.999999]
        if not valid:raise ValueError('请选择亮显的真实像素；该位置不在已审核/真实来源范围内')
        a=np.asarray(valid,dtype=np.float32)
        if a.shape[0]>121 or not np.isfinite(a).all() or np.any(a<0) or np.any(a>1):raise ValueError('Invalid SDR source sample; clipping is not allowed')
        rgb=np.floor(a.mean(axis=0,dtype=np.float64)*255+.5).astype(np.uint8).tolist();self.matching(p)
        return {'rgb':rgb,'proof':{k:p[k] for k in ('document_id',*PROOF_KEYS)},'source_stage':d['source_stage'],'quality':'proxy-float-input','sample_pixels':len(valid),'picker_mode':d['picker_mode'],'source_binding':deepcopy(d['source_binding'])}

def owner(engine,emit):
    value=engine.__dict__.get('_id_background_capture_owner')
    if value is None:value=IDBackgroundCapture(engine,emit);engine._id_background_capture_owner=value
    return value

def route_capture(engine,p,emit):
    current=engine.__dict__.get('_id_background_capture_owner')
    belongs=p.get('picker_action') in MODES or (current is not None and current.capture is not None and current.capture['descriptor']['capture_id']==p.get('capture_id'))
    if not belongs:return False
    try:emit(owner(engine,emit).handle(p))
    except Exception as error:emit({'event':'color_picker_capture','action':p.get('action'),'capture_id':p.get('capture_id'),'ticket':p.get('ticket'),'success':False,'error':str(error)[:1000]})
    return True
