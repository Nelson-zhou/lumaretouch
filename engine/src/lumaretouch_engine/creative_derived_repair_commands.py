"""Presented source-patch/clone ownership on an immutable returned source.

Capture verifies the actual ordered replay once. Matching and commit verify its
owned source, stack and float pixels, never a display bitmap or original mask.
"""
from hashlib import sha256
import numpy as np
from .source_patch_controller import PROOF_KEYS,COMMAND_KEYS,CLONE_KEYS

COMMANDS=frozenset(('source_patch_capture','source_patch','clone_stamp'))
INTERNAL_KEYS=('source_binding','repair_stack_sha256','repair_pixels_sha256')


def handles(engine,name,p):
    if name in ('source_patch','clone_stamp'):return True
    if name!='source_patch_capture':return False
    if p.get('action')=='arm':return p.get('purpose','repair')=='repair'
    owner=engine.__dict__.get('_source_patch_owner')
    capture=getattr(getattr(owner,'capture',None),'capture',None)
    return capture is None or capture.get('descriptor',{}).get('domain')=='repair-input'


def _pixels_hash(value):
    value=value[0].permute(1,2,0).detach().cpu().numpy()
    if value.dtype!=np.float32 or value.ndim!=3 or value.shape[2]!=3:
        raise ValueError('Repair input must be working float32 RGB')
    digest=sha256()
    for row in value:
        if not np.isfinite(row).all() or np.any(row<0) or np.any(row>1):
            raise ValueError('Derived repair input cannot silently clip alpha or HDR')
        digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return digest.hexdigest()


def _stack(engine):
    from .creative_derived_repairs import validate_stacks,stack_digest
    from .creative_derived_mask_commands import require_pixels
    require_pixels(engine);validate_stacks(engine)
    pipe=engine._vram
    from .creative_derived_repair_runtime import verify_pipeline
    from .creative_derived_source import binding
    verify_pipeline(pipe,binding(engine))
    state={'_creative_base':engine._creative_base,'_repair_ops':pipe.repair_ops,'_redo_ops':pipe.redo_ops}
    validate_stacks(state)
    digest=stack_digest(engine)
    if stack_digest(state)!=digest:raise ValueError('Repair pipeline and retained ordered stack differ')
    return digest


def capture_state(engine):
    from .creative_derived_source import binding
    digest=_stack(engine);pipe=engine._vram
    actual=pipe.base()
    return {'source_binding':binding(engine),'repair_stack_sha256':digest,'repair_pixels_sha256':_pixels_hash(actual)}


def verify_state(engine,proof):
    from .creative_derived_source import binding,record
    if record(engine) is None or proof.get('source_binding')!=binding(engine):
        raise ValueError('Repair proof belongs to another immutable source')
    if proof.get('repair_stack_sha256')!=_stack(engine):raise ValueError('Repair stack changed after capture')
    if proof.get('repair_pixels_sha256')!=_pixels_hash(engine._vram.base()):raise ValueError('Repair pixels changed after capture')


def capture_binding(engine,capture):
    from .creative_derived_source import binding
    source=binding(engine);d=capture['descriptor']
    if capture.get('effective_source')!=source or d['domain']!='repair-input' or d['full_source']!=[source['width'],source['height']]:
        raise ValueError('Repair capture belongs to another source or input domain')
    verify_state(engine,capture.get('repair_proof') or {})


def require_command(engine,name,p):
    from .source_patch_capture import _hex,_uint
    if name not in COMMANDS or type(p) is not dict or p.get('cmd')!=name:raise ValueError('Unknown derived repair command')
    if name=='source_patch_capture':
        action=p.get('action');keys={'cmd','action','capture_id','ticket','document_id'}
        if action=='arm':keys|={'epoch'}|({'purpose'} if 'purpose' in p else set())
        elif action=='presented' or 'generation' in p:keys.add('generation')
        if action not in ('arm','presented','cancel') or set(p)!=keys:raise ValueError('Invalid derived repair capture envelope')
        if not _hex(p['capture_id']) or not _uint(p['ticket']) or not _uint(p['document_id']):raise ValueError('Invalid repair capture identity')
        if action=='cancel':
            if 'generation' in p and not _uint(p['generation']):raise ValueError('Invalid repair generation')
            return
        if action=='arm':
            if p.get('purpose','repair')!='repair' or not _hex(p['epoch']):raise ValueError('Repair capture needs its own input domain')
            _stack(engine);return
        if not _uint(p['generation']):raise ValueError('Invalid repair generation')
        capture=engine._source_patch_controller().capture._matching(p)
        capture_binding(engine,capture);return
    keys=CLONE_KEYS if name=='clone_stamp' else COMMAND_KEYS
    if set(p)!=keys or p.get('action')!='apply' or (name=='clone_stamp' and p.get('kind')!='clone_stamp'):
        raise ValueError('Invalid derived repair apply envelope')
    if any(type(p[k]) is not str or not 1<=len(p[k])<=128 for k in ('request_id',*PROOF_KEYS)):
        raise ValueError('Invalid repair request identity')
    owner=engine._source_patch_controller();cached=owner.cache.get(p['request_id'])
    if cached is not None:
        if cached[0]!=owner._digest(p):raise ValueError('Repair request identity reused with different content')
        return
    capture=owner.capture._matching(p,recipe=True);capture_binding(engine,capture)
    if not capture['eligible']:raise ValueError('Present the current repair input before applying')
