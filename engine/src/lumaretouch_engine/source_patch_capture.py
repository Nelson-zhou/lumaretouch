"""Single repair-input capture, independent of the editable display SHM.

One immutable private LRCP file is closed before it is advertised. No rendered
pixels become repair parameters; prepare returns a geometry-only owned recipe.
"""
import os
import re
import stat
import struct
import uuid
from pathlib import Path
import numpy as np
from .color_action_sampling import Projection, admit, available_memory
from .cpu_memory_budget import available_estimate
from .source_patch_geometry import inverse_recipe
from .ops.source_patch import selection_mask, check_recipe, VERSION
from .quant import quantize_t

MAX_U64=(1<<64)-1


def _hex(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{32}',value) and int(value,16)>0


def _uint(value, zero=False):
    return (type(value) is str and re.fullmatch('0|[1-9][0-9]{0,19}',value)
            and (0 if zero else 1)<=int(value)<=MAX_U64)


def header(d):
    h=bytearray(128)
    struct.pack_into('<4sHH',h,0,b'LRCP',1,128)
    for off,key in ((8,'epoch'),(24,'shm_instance'),(40,'capture_id')):
        h[off:off+16]=bytes.fromhex(d[key])
    for off,key in ((56,'seq'),(64,'generation'),(72,'document_id'),(80,'ticket')):
        struct.pack_into('<Q',h,off,int(d[key]))
    struct.pack_into('<IIIIQ',h,88,d['width'],d['height'],d['presentation_width'],d['presentation_height'],d['width']*d['height']*4)
    return h


def write_capture(root, d, rgba, *, purpose="source-patch"):
    """Descriptor-relative exclusive creation beneath the native private root."""
    if purpose not in ('source-patch', 'white-balance', 'color-picker'):
        raise ValueError('Unsupported private capture purpose')
    root=Path(root)
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    rootfd=os.open(root,flags)
    name='lumaretouch-'+purpose+'-'+d['capture_id']+'-'+d['ticket']
    directory=None;created=False
    try:
        info=os.fstat(rootfd)
        if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
            raise ValueError('Repair capture root is not private')
        os.mkdir(name,0o700,dir_fd=rootfd);created=True
        directory=os.open(name,flags,dir_fd=rootfd)
        fd=os.open('capture.lrcp',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
        with os.fdopen(fd,'wb') as output:
            output.write(header(d));output.write(memoryview(rgba).cast('B'))
            output.flush();os.fsync(output.fileno())
    except BaseException:
        if directory is not None:
            try:os.unlink('capture.lrcp',dir_fd=directory)
            except FileNotFoundError:pass
        if created:
            try:os.rmdir(name,dir_fd=rootfd)
            except OSError:pass
        raise
    finally:
        if directory is not None:os.close(directory)
        os.close(rootfd)
    return root/name


class CaptureController:
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
        why=e._guard_editable('source_patch')
        if why:raise ValueError(why)
        inspection=e._inspection_controller()
        if any(value is not None for value in (inspection.tx,inspection.result,inspection.job)):
            raise ValueError('Release full-resolution inspection before source patch sampling')
        if not 0<=e._doc_index<len(e._docs):raise ValueError('No active repair document')
        row=e._docs[e._doc_index];v=e._document_versions().version(row)
        spec=Projection.from_pipeline(e._vram)
        full=[int(row.get('src_w') or spec.width),int(row.get('src_h') or spec.height)]
        presentation=e._frame_presentation()
        return {'document_id':str(e._load_id),'recipe_document_id':v.document_id,
                'recipe_revision':str(v.revision),'full_source':full,
                'presentation_width':presentation.width,'presentation_height':presentation.height},spec

    def _matching(self,p, *, recipe=False):
        c=self.capture
        if c is None:raise ValueError('Repair input capture expired; select again')
        keys=['capture_id','ticket','document_id','generation']
        if recipe:keys+=['recipe_document_id','recipe_revision']
        if any(p.get(k)!=c['descriptor'][k] for k in keys):raise ValueError('Repair input identity changed')
        context,spec=self._context()
        if spec!=c['spec'] or any(c['descriptor'][k]!=v for k,v in context.items()):
            raise ValueError('Repair document changed; capture again')
        from .creative_derived_source import record
        if record(self.engine) is not None or c.get('effective_source') is not None:
            if c['descriptor']['domain']=='repair-input':
                from .creative_derived_repair_commands import capture_binding
                capture_binding(self.engine,c)
            else:
                from .creative_derived_mask_commands import capture_binding, require_pixels
                capture_binding(self.engine,c);require_pixels(self.engine)
        return c

    def handle(self,p):
        action=p.get('action')
        event={'event':'source_patch_capture','action':action,'capture_id':p.get('capture_id'),
               'ticket':p.get('ticket'),'success':False}
        try:
            allowed={'cmd','action','capture_id','ticket','document_id'}
            allowed|={'epoch', 'purpose', 'group_id'} if action=='arm' else {'generation'}
            if set(p)-allowed or action not in ('arm','presented','cancel'):
                raise ValueError('Invalid repair capture command')
            if not _hex(p.get('capture_id')) or not _uint(p.get('ticket')) or not _uint(p.get('document_id')):
                raise ValueError('Invalid repair capture identity')
            if action=='cancel':
                c=self.capture
                if c and all(c['descriptor'][k]==p[k] for k in ('capture_id','ticket','document_id')):
                    self.invalidate()
            elif action=='presented':
                self._matching(p)['eligible']=True
            else:
                self.invalidate()
                if not _hex(p.get('epoch')):raise ValueError('Invalid repair capture epoch')
                purpose=p.get('purpose', 'repair')
                if purpose not in ('repair', 'local-masks'): raise ValueError('Invalid capture purpose')
                group_id=p.get('group_id')
                if ((purpose != 'local-masks' and 'group_id' in p)
                        or (group_id is not None and (type(group_id) is not str
                            or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',group_id)))):
                    raise ValueError('Invalid local-mask capture group')
                context,spec=self._context()
                from .creative_derived_source import record, binding, verify
                effective_source=binding(self.engine) if record(self.engine) is not None else None
                repair_proof=None
                if effective_source is not None:
                    if purpose=='repair':
                        from .creative_derived_repair_commands import capture_state
                        repair_proof=capture_state(self.engine)
                    if context['full_source']!=[effective_source['width'],effective_source['height']]:
                        raise ValueError('Derived capture canvas differs from immutable source')
                    from .creative_derived_mask_commands import require_pixels
                    require_pixels(self.engine)
                if context['document_id']!=p['document_id']:raise ValueError('Repair document changed')
                if self.generation==MAX_U64:raise ValueError('Repair generation exhausted; restart engine')
                self.generation+=1
                pipeline=self.engine._vram
                admit(spec,available_memory(pipeline.device))
                # Also reserve CPU packing/file-copy headroom for a GPU capture.
                required=spec.width*spec.height*32+16*1024**2
                if required>max(0,available_estimate()-256*1024**2)*65//100:
                    raise ValueError('Insufficient host memory for repair input capture')
                import torch
                stage=pipeline.src_f32 if purpose == 'local-masks' else pipeline.base()
                if stage.dtype!=torch.float32 or tuple(stage.shape)!=(1,3,spec.height,spec.width) or not torch.isfinite(stage).all():
                    raise ValueError('Invalid repair input pixels')
                projected=spec.apply(stage)
                coverage=spec.apply(torch.ones_like(stage[:,:1]))
                valid=(coverage[0,0]>=1-1e-6).contiguous().cpu().numpy()
                rgb=quantize_t(projected[0].permute(1,2,0)).contiguous().cpu().numpy()
                rgba=np.empty((spec.height,spec.width,4),np.uint8)
                rgba[...,:3]=rgb;rgba[...,3]=255
                mask_reason = None
                if purpose == 'local-masks':
                    from .local_mask_state import diagnostic, sample_valid_rows
                    if group_id is None:
                        mask, mask_reason = diagnostic(self.engine)
                    else:
                        from .local_grade_runtime import diagnostic as group_diagnostic
                        mask, mask_reason = group_diagnostic(self.engine, group_id)
                    field = torch.as_tensor(mask.astype(np.float32)/255., device=pipeline.device)[None,None]
                    rgba[...,3] = quantize_t(spec.apply(field)[0,0]).contiguous().cpu().numpy()

                d={**context,'version':1,'domain':'source-input' if purpose == 'local-masks' else 'repair-input','quality':'proxy-float-input',
                   'profile':'working-srgb','epoch':p['epoch'],'shm_instance':uuid.uuid4().hex,
                   'seq':'1','generation':str(self.generation),'capture_id':p['capture_id'],'ticket':p['ticket'],
                   'width':spec.width,'height':spec.height,'projection':spec.descriptor()}
                if purpose == 'local-masks': d.update(mask_overlay=True, mask_group_id=group_id,
                    mask_suspended=mask_reason, sample_valid_rows=sample_valid_rows(valid))
                current,current_spec=self._context()
                if current!=context or current_spec!=spec:raise ValueError('Repair input changed while capturing')
                if effective_source is not None:
                    verify(effective_source,self.engine);require_pixels(self.engine)
                    if repair_proof is not None:
                        from .creative_derived_repair_commands import verify_state
                        verify_state(self.engine,repair_proof)
                root=os.environ.get('LRT_INSPECTION_ROOT')
                if not root:raise ValueError('Private repair capture root unavailable')
                self.path=write_capture(root,d,rgba)
                self.capture={'descriptor':d,'spec':spec,'eligible':False,'valid':valid,'effective_source':effective_source,'repair_proof':repair_proof}
                event['descriptor']=d
            event['success']=True
        except Exception as error:
            if action=='arm':self.invalidate()
            event['error']=str(error)[:2000]
        self.emit(event)

    def prepare_apply(self,p):
        c=self._matching(p,recipe=True)
        if not c['eligible']:raise ValueError('Repair input was not presented')
        if c['descriptor']['domain'] != 'repair-input': raise ValueError('Repair requires its own input capture')
        if p.get('kind') == 'clone_stamp':
            from .clone_stamp_geometry import inverse_stroke
            params, weight = inverse_stroke(c['spec'], p.get('stroke'), c['valid'], c['descriptor']['full_source'])
            proof = {k:c['descriptor'][k] for k in ('document_id','capture_id','ticket','generation','recipe_document_id','recipe_revision')}
            proof.update(kind='clone_stamp', params=params, weight=weight)
            if c.get('repair_proof') is not None:proof.update(c['repair_proof'])
            self.invalidate()
            return proof
        raw=check_recipe({'version':VERSION,'polygon':p.get('polygon'),'offset':p.get('offset')})
        spec=c['spec']
        donor=[[x+raw['offset'][0],y+raw['offset'][1]] for x,y in raw['polygon']]
        for polygon in (raw['polygon'],donor):
            selected=selection_mask((spec.height,spec.width),polygon)>0
            if not np.any(selected) or not np.all(c['valid'][selected]):
                raise ValueError('Patch target/source intersects rotation padding')
        params=inverse_recipe(spec,raw['polygon'],raw['offset'])
        weight=(selection_mask((spec.height,spec.width),params['polygon'])*255).astype(np.uint8)
        if not np.any(weight):raise ValueError('Patch selection contains no pixels')
        proof={k:c['descriptor'][k] for k in ('document_id','capture_id','ticket','generation','recipe_document_id','recipe_revision')}
        proof.update(params=params,weight=weight)
        if c.get('repair_proof') is not None:proof.update(c['repair_proof'])
        self.invalidate()
        return proof


def make_controller(engine,emit):
    return CaptureController(engine,emit)
