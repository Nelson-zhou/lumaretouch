"""Frozen stage capture, bounded proposal and pre-fence one-shot preparation."""
import os
import uuid
from copy import deepcopy
import numpy as np
from .source_patch_capture import MAX_U64, _hex, _uint, write_capture
from .color_action_sampling import Projection, admit, available_memory
from .color_picker_sampling import projected, sample, stage_name
from .color_picker_math import calculate, selection
from .white_balance_controller import identity, error_text
from .cpu_memory_budget import available_estimate
from .quant import quantize_t
from .color_picker_preview import freeze, render as preview_render

PROOF_KEYS=('capture_id','ticket','generation','recipe_document_id','recipe_revision')

class ColorPickerCapture:
    def __init__(self,engine,emit):
        self.engine=engine;self.emit=emit;self.capture=None;self.path=None;self.generation=0
    def invalidate(self):
        self.capture=None
        path,self.path=self.path,None
        if path is not None:
            try:(path/'capture.lrcp').unlink(missing_ok=True)
            except OSError:pass
            try:path.rmdir()
            except OSError:pass
    def _context(self):
        from .final_canvas_flip_state import require_processing_capture
        require_processing_capture(self.engine)
        e=self.engine;why=e._guard_editable('color picker')
        if why:raise ValueError(why)
        inspection=e._inspection_controller()
        if any(v is not None for v in (inspection.tx,inspection.result,inspection.job)):raise ValueError('Release full-resolution inspection before targeted color sampling')
        if not 0<=e._doc_index<len(e._docs):raise ValueError('No active document')
        row=e._docs[e._doc_index];version=e._document_versions().version(row);spec=Projection.from_pipeline(e._vram)
        presentation=e._frame_presentation()
        return {'document_id':str(e._load_id),'recipe_document_id':version.document_id,'recipe_revision':str(version.revision),
                'full_source':[int(row.get('src_w') or spec.width),int(row.get('src_h') or spec.height)],
                'presentation_width':presentation.width,'presentation_height':presentation.height},spec
    def matching(self,p):
        c=self.capture
        if c is None:raise ValueError('Color picker capture expired; sample again')
        if any(p.get(k)!=c['descriptor'][k] for k in ('document_id',*PROOF_KEYS)):raise ValueError('Color picker input proof changed')
        context,spec=self._context()
        if spec!=c['spec'] or any(c['descriptor'][k]!=v for k,v in context.items()):raise ValueError('Color picker document/recipe changed')
        return c
    def recipe(self,action):
        e=self.engine
        return deepcopy(e._levels if action.startswith('levels_') else e._curves if action=='curve' else list(e._hsl))
    def proposal(self,p):
        c=self.matching(p)
        if not c['eligible']:raise ValueError('Color picker input has not been presented')
        d=c['descriptor'];action,channel=selection(p.get('action'),p.get('channel'))
        if (action,channel)!=(d['picker_action'],d['picker_channel']):raise ValueError('Color picker target changed')
        e=self.engine;strength,scope=e._retouch_render_args()
        # Keep at most one bounded 121-pixel selection, never a full float raster.
        region=p.get('region')
        if c.get('region')!=region:
            rows=sample(e._vram,c['spec'],strength,scope,e._params,action,channel,region)
            self.matching(p);c['region']=deepcopy(region);c['rows']=rows
        recipe,report=calculate(c['rows'],action,channel,p.get('delta'),self.recipe(action))
        self.matching(p)
        return recipe,{**report,'region':deepcopy(region),'source_stage':d['source_stage']}
    def prepare_apply(self,p):
        recipe,report=self.proposal(p)
        proof={k:self.capture['descriptor'][k] for k in ('document_id',*PROOF_KEYS)}
        self.invalidate()
        return {**proof,'recipe':recipe,'sample':report}
    def handle(self,p):
        action=p.get('action');event={'event':'color_picker_capture','action':identity(action,32),'capture_id':identity(p.get('capture_id'),32),'ticket':identity(p.get('ticket'),20),'success':False}
        try:
            allowed={'cmd','action','capture_id','ticket','document_id'}
            allowed|={'epoch','picker_action','picker_channel'} if action=='arm' else {'generation'}
            if set(p)-allowed or action not in ('arm','presented','cancel'):raise ValueError('Invalid color picker capture command')
            if not _hex(p.get('capture_id')) or not _uint(p.get('ticket')) or not _uint(p.get('document_id')):raise ValueError('Invalid color picker identity')
            if action=='cancel':
                if self.capture and all(self.capture['descriptor'][k]==p[k] for k in ('capture_id','ticket','document_id')):self.invalidate()
            elif action=='presented':
                c=self.capture
                if c is None or any(p.get(k)!=c['descriptor'][k] for k in ('capture_id','ticket','document_id','generation')):raise ValueError('Color picker presentation proof changed')
                context,spec=self._context()
                if c['spec']!=spec or any(c['descriptor'][k]!=v for k,v in context.items()):raise ValueError('Color picker changed before presentation')
                c['eligible']=True
            else:
                self.invalidate();selection(p.get('picker_action'),p.get('picker_channel'))
                if not _hex(p.get('epoch')):raise ValueError('Invalid color picker epoch')
                context,spec=self._context()
                if context['document_id']!=p['document_id']:raise ValueError('Color picker photo changed')
                if self.generation==MAX_U64:raise ValueError('Color picker generation exhausted')
                self.generation+=1;pipeline=self.engine._vram;admit(spec,available_memory(pipeline.device))
                required=spec.width*spec.height*32+16*1024**2
                if required>max(0,available_estimate()-256*1024**2)*65//100:raise ValueError('Insufficient host memory for targeted input capture')
                strength,scope=self.engine._retouch_render_args()
                pixels=projected(pipeline,spec,strength,scope,self.engine._params,p['picker_action'],p['picker_channel'])
                rgb=quantize_t(pixels[0].permute(1,2,0)).contiguous().cpu().numpy();rgba=np.empty((spec.height,spec.width,4),np.uint8)
                rgba[...,:3]=rgb;rgba[...,3]=255
                d={**context,'version':1,'domain':'color-action-input','quality':'proxy-float-input','profile':'working-srgb',
                   'epoch':p['epoch'],'shm_instance':uuid.uuid4().hex,'seq':'1','generation':str(self.generation),
                   'capture_id':p['capture_id'],'ticket':p['ticket'],'width':spec.width,'height':spec.height,'projection':spec.descriptor(),
                   'picker_action':p['picker_action'],'picker_channel':p['picker_channel'],'source_stage':stage_name(p['picker_action'],p['picker_channel'])}
                current,current_spec=self._context()
                if current!=context or current_spec!=spec:raise ValueError('Color picker changed while freezing input')
                root=os.environ.get('LRT_INSPECTION_ROOT')
                if not root:raise ValueError('Private color picker capture root unavailable')
                self.path=write_capture(root,d,rgba,purpose='color-picker');self.capture={'descriptor':d,'spec':spec,'eligible':False,'preview':freeze(pixels)}
                event['descriptor']=d
            event['success']=True
        except Exception as error:
            if action=='arm':self.invalidate()
            event['error']=error_text(error)
        self.emit(event)
    def probe(self,p):
        event={'event':'color_picker_probe_result','protocol':1,'request_id':identity(p.get('request_id'),128),'document_id':identity(p.get('document_id'),64),
               **{k:identity(p.get(k),128) for k in PROOF_KEYS},'action':identity(p.get('action'),32),'channel':identity(p.get('channel'),32),'success':False,'outcome_unknown':False}
        try:
            if set(p)!={'cmd','request_id','document_id','action','channel','region','delta',*PROOF_KEYS}:raise ValueError('Invalid color picker probe fields')
            if type(p['request_id']) is not str or not 1<=len(p['request_id'])<=128:raise ValueError('Invalid probe request ID')
            recipe,event['sample']=self.proposal(p)
            event['preview']=preview_render(self.capture['preview'],p['action'],p['channel'],recipe)
            self.matching(p);event['success']=True
        except Exception as error:event['error']=error_text(error)
        self.emit(event)
