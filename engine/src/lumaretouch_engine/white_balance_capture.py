"""Frozen, labelled pre-WB input capture; only bounded linear samples reach Rust.

Reuse LRCP private publication and the existing geometry/resource admission.
No final display RGB, UI-supplied gain or persistent sampled raster is accepted.
"""
import os
import uuid
import numpy as np
from .source_patch_capture import MAX_U64, _hex, _uint, write_capture
from .color_action_sampling import Projection, available_memory, admit, preview, sample
from .cpu_memory_budget import available_estimate
from .quant import quantize_t
from .white_balance_recipe import check_options, compile_gains
from .white_balance_pick_math import calculate


class WhiteBalanceCapture:
    def __init__(self, engine, emit):
        self.engine=engine;self.emit=emit;self.capture=None;self.path=None;self.generation=0

    def invalidate(self):
        self.capture=None
        path,self.path=self.path,None
        if path is not None:
            # Only our exact two entries, never recursive deletion of a root.
            try:(path/'capture.lrcp').unlink(missing_ok=True)
            except OSError:pass
            try:path.rmdir()
            except OSError:pass

    def _context(self):
        e=self.engine
        why=e._guard_editable('white balance')
        if why:raise ValueError(why)
        inspection=e._inspection_controller()
        if any(value is not None for value in (inspection.tx,inspection.result,inspection.job)):
            raise ValueError('Release full-resolution inspection before WB sampling')
        if not 0<=e._doc_index<len(e._docs):raise ValueError('No active WB document')
        row=e._docs[e._doc_index];v=e._document_versions().version(row)
        spec=Projection.from_pipeline(e._vram)
        full=[int(row.get('src_w') or spec.width),int(row.get('src_h') or spec.height)]
        presentation=e._frame_presentation()
        return {'document_id':str(e._load_id),'recipe_document_id':v.document_id,
                'recipe_revision':str(v.revision),'full_source':full,
                'presentation_width':presentation.width,'presentation_height':presentation.height},spec

    def _matching(self,p, *, recipe=False):
        c=self.capture
        if c is None:raise ValueError('WB input capture expired; select again')
        keys=['capture_id','ticket','document_id','generation']
        if recipe:keys+=['recipe_document_id','recipe_revision']
        if any(p.get(k)!=c['descriptor'][k] for k in keys):raise ValueError('WB input identity changed')
        context,spec=self._context()
        if spec!=c['spec'] or any(c['descriptor'][k]!=v for k,v in context.items()):
            raise ValueError('WB document changed; capture again')
        return c

    def handle(self,p):
        action=p.get('action')
        event={'event':'white_balance_capture','action':action,'capture_id':p.get('capture_id'),
               'ticket':p.get('ticket'),'success':False}
        try:
            allowed={'cmd','action','capture_id','ticket','document_id'}
            allowed|={'epoch'} if action=='arm' else {'generation'}
            if set(p)-allowed or action not in ('arm','presented','cancel'):
                raise ValueError('Invalid WB capture command')
            if not _hex(p.get('capture_id')) or not _uint(p.get('ticket')) or not _uint(p.get('document_id')):
                raise ValueError('Invalid WB capture identity')
            if action=='cancel':
                c=self.capture
                if c and all(c['descriptor'][k]==p[k] for k in ('capture_id','ticket','document_id')):
                    self.invalidate()
            elif action=='presented':
                self._matching(p)['eligible']=True
            else:
                self.invalidate()
                if not _hex(p.get('epoch')):raise ValueError('Invalid WB capture epoch')
                context,spec=self._context()
                if context['document_id']!=p['document_id']:raise ValueError('WB document changed')
                if self.generation==MAX_U64:raise ValueError('WB generation exhausted; restart engine')
                self.generation+=1
                pipeline=self.engine._vram
                admit(spec,available_memory(pipeline.device))
                # Also reserve CPU packing/file-copy headroom for a GPU capture.
                required=spec.width*spec.height*32+16*1024**2
                if required>max(0,available_estimate()-256*1024**2)*65//100:
                    raise ValueError('Insufficient host memory for WB input capture')
                strength,channel=self.engine._retouch_render_args()
                # The display is encoded from the very same projected linear input
                # that sample() re-evaluates under this frozen recipe, never output RGB.
                projected=preview(pipeline,spec,strength,channel,self.engine._params)
                rgb=quantize_t(projected[0].permute(1,2,0)).contiguous().cpu().numpy()
                rgba=np.empty((spec.height,spec.width,4),np.uint8)
                rgba[...,:3]=rgb;rgba[...,3]=255
                d={**context,'version':1,'domain':'wb-input','quality':'proxy-linear-input',
                   'profile':'working-srgb','epoch':p['epoch'],'shm_instance':uuid.uuid4().hex,
                   'seq':'1','generation':str(self.generation),'capture_id':p['capture_id'],'ticket':p['ticket'],
                   'width':spec.width,'height':spec.height,'projection':spec.descriptor()}
                current,current_spec=self._context()
                if current!=context or current_spec!=spec:raise ValueError('WB input changed while capturing')
                root=os.environ.get('LRT_INSPECTION_ROOT')
                if not root:raise ValueError('Private WB capture root unavailable')
                self.path=write_capture(root,d,rgba,purpose="white-balance")
                self.capture={'descriptor':d,'spec':spec,'eligible':False}
                event['descriptor']=d
            event['success']=True
        except Exception as error:
            if action=='arm':self.invalidate()
            event['error']=str(error)[:2000]
        self.emit(event)

    def prepare_apply(self,p):
        c=self._matching(p,recipe=True)
        if not c['eligible']:raise ValueError('WB input was not presented')
        e=self.engine
        strength,channel=e._retouch_render_args()
        rows=sample(e._vram,c['spec'],strength,channel,e._params,p.get('region'))
        before=e.doc_state()['exposure']
        options=check_options(before['options'])
        # Replacement, not accumulation: manual gains exclude the previous pick
        # and EV. Existing algorithm/reference semantics remain authoritative.
        manual=compile_gains({**options,'picked_gains':[1.0,1.0,1.0]},
            6500.0 if before['reference_k'] is None else before['reference_k'],
            before['temperature_shift'],before['tint_shift'])
        picked=calculate(rows,manual)
        self._matching(p,recipe=True)
        proof={k:c['descriptor'][k] for k in ('document_id','capture_id','ticket','generation','recipe_document_id','recipe_revision')}
        proof.update(gains=list(picked.gains),mean_linear=list(picked.mean_linear),
                     samples=picked.samples,policy=picked.policy)
        self.invalidate()
        return proof
