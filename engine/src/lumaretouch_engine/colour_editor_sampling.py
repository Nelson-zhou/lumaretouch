"""Verified displayed operator-input capture using current picker proof contract."""
import os
import uuid
from copy import deepcopy
import numpy as np
from .color_picker_capture import ColorPickerCapture, PROOF_KEYS
from .source_patch_capture import write_capture, _hex, _uint, MAX_U64
from .color_action_sampling import gather_region, _region, admit, available_memory
from .cpu_memory_budget import available_estimate
from .quant import quantize_t
from .colour_editor_native import FullDomain
from . import colour_editor_state as S
class ColourEditorCapture(ColorPickerCapture):
    def handle(self, p):
        action = p.get('action')
        allowed = {'cmd','action','request_id','capture_id','ticket','document_id'}
        allowed |= {'epoch'} if action == 'arm' else {'generation'}
        if set(p) != allowed or p.get('cmd') != 'colour_editor_capture' or action not in ('arm','presented','cancel'): raise ValueError('Invalid colour editor capture request')
        if not isinstance(p['request_id'],str) or not 1 <= len(p['request_id']) <= 128: raise ValueError('Invalid capture request identity')
        if not _hex(p['capture_id']) or not _uint(p['ticket']) or not _uint(p['document_id']): raise ValueError('Invalid capture identity')
        if action == 'cancel':
            if self.capture and all(self.capture['descriptor'][k] == p[k] for k in ('capture_id','ticket','document_id','generation')): self.invalidate()
            return {'event':'colour_editor_capture','request_id':p['request_id'],'action':action,'success':True}
        if action == 'presented':
            c = self.capture
            if c is None or any(c['descriptor'][k] != p[k] for k in ('capture_id','ticket','document_id','generation')): raise ValueError('Input display proof expired')
            context,spec = self._context()
            if spec != c['spec'] or any(c['descriptor'][k] != v for k,v in context.items()): raise ValueError('Input changed before display')
            c['eligible'] = True
            return {'event':'colour_editor_capture','request_id':p['request_id'],'action':action,'success':True}
        self.invalidate()
        if not _hex(p['epoch']): raise ValueError('Invalid epoch')
        context,spec = self._context()
        if context['document_id'] != p['document_id']: raise ValueError('Document changed')
        if self.generation == MAX_U64: raise ValueError('Capture generation exhausted')
        required = spec.width*spec.height*32 + 16*1024**2
        if required > max(0, available_estimate()-256*1024**2)*65//100: raise MemoryError('Input capture exceeds host budget')
        pipeline=self.engine._vram;admit(spec,available_memory(pipeline.device))
        strength,scope=self.engine._retouch_render_args()
        # Shared integration must implement this exact pre-consumer stage. No
        # fallback to final render, displayed RGBA, HSL input or inverse grading.
        pixels=pipeline.retouch(strength,channel=scope,render_stage='colour-editor-input',**self.engine._params)
        import torch
        coverage=self.engine.__dict__.pop('_colour_editor_input_coverage',None)
        if coverage is None or tuple(coverage.shape)!=(1,1,spec.height,spec.width):raise ValueError('Verified source coverage missing')
        coverage=coverage.detach().clone()
        # This stage is already original-source geometry projected and resized.
        # Applying Projection again would crop/rotate twice.
        pixels=pixels.detach().clone()
        if tuple(pixels.shape)!=(1,3,spec.height,spec.width): raise ValueError('Input geometry mismatch')
        context_now,spec_now=self._context()
        if context_now != context or spec_now != spec: raise ValueError('Input changed during capture')
        rgb=quantize_t(pixels[0].permute(1,2,0)).contiguous().cpu().numpy()
        rgba=np.empty((spec.height,spec.width,4),np.uint8);rgba[...,:3]=rgb;rgba[...,3]=255
        self.generation+=1
        d={**context,'version':1,'domain':'color-action-input','quality':'proxy-float-input','profile':'working-srgb','epoch':p['epoch'],
           'shm_instance':uuid.uuid4().hex,'seq':'1','generation':str(self.generation),'capture_id':p['capture_id'],'ticket':p['ticket'],
           'width':spec.width,'height':spec.height,'projection':spec.descriptor(),'picker_action':'colour_editor','picker_channel':'master','source_stage':'colour-editor-input'}
        root=os.environ.get('LRT_INSPECTION_ROOT')
        if not root: raise ValueError('Private capture root unavailable')
        self.path=write_capture(root,d,rgba,purpose='color-picker')
        self.capture={'descriptor':d,'spec':spec,'eligible':False,'pixels':pixels,'coverage':coverage}
        return {'event':'colour_editor_capture','request_id':p['request_id'],'action':'arm','success':True,'descriptor':d}
    def probe(self,p):
        if set(p)!={'cmd','request_id','document_id','region',*PROOF_KEYS} or p['cmd']!='colour_editor_sample': raise ValueError('Invalid colour editor sample request')
        if not isinstance(p['request_id'],str) or not 1 <= len(p['request_id']) <= 128: raise ValueError('Invalid sample request identity')
        c=self.matching(p)
        if not c['eligible']: raise ValueError('Operator input has not been displayed')
        _region(p['region'],c['spec'])
        rows=gather_region(c['pixels'],p['region'],c['spec'])
        cover=gather_region(c['coverage'],p['region'],c['spec'])
        rows=[row for row,m in zip(rows,cover) if m[0] >= .999]
        if not rows: raise ValueError('Sample outside valid source coverage')
        a=np.asarray(rows,dtype=np.float32).reshape(1,-1,3)
        if a.shape[1] > 121: raise ValueError('Sample exceeds 121-pixel budget')
        recipe=S.neutral();recipe['selection']['half_width']=.5
        stats=FullDomain().apply(a,recipe,prepare_only=True)['stats']
        import math
        h=(math.atan2(stats[2],stats[1])/(2*math.pi))%1 if abs(stats[1])+abs(stats[2])>1e-12 else 0.0
        if stats[0] <= 0: raise ValueError('No covered sample pixels')
        self.matching(p)
        return {'event':'colour_editor_sample','request_id':p['request_id'],'success':True,'sample':{'proof':{k:p[k] for k in ('document_id',*PROOF_KEYS)},'source_stage':'colour-editor-input','hsl':[h,float(stats[3]/stats[0]),float(stats[4]/stats[0])]}}
