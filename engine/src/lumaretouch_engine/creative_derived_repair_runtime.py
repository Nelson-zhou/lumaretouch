"""Ephemeral atomic replay evidence for source-owned derived repairs.

No rendered pixels are persisted. Hashes cover the actual immutable input,
ordered recipes/coverage, and completed output, not a claimed filename.
"""
from copy import deepcopy
from hashlib import sha256
import numpy as np


def _pixels(value):
    if type(value) is not np.ndarray or value.dtype!=np.float32 or value.ndim!=3 or value.shape[2]!=3:
        raise ValueError('Repair evidence requires float32 RGB')
    digest=sha256()
    for row in value:
        if not np.isfinite(row).all() or np.any(row<0) or np.any(row>1):
            raise ValueError('Derived repair supports opaque SDR only; no silent HDR clipping')
        digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return {'shape':list(value.shape),'sha256':digest.hexdigest()}


def _array(tensor):
    # Do not coerce a wrong pipeline dtype into evidence of the expected dtype.
    return tensor[0].permute(1,2,0).detach().cpu().numpy()


def make_evidence(source,pixels,repaired,stack_digest):
    from .creative_derived_repairs import check_binding
    from .people_state import digest
    source=check_binding(source)
    if source is None:raise ValueError('Derived repair evidence needs an immutable source')
    before=_pixels(pixels);after=None if repaired is None else _pixels(repaired)
    if after is not None and after['shape']!=before['shape']:
        raise ValueError('Repaired pixels changed the immutable source grid')
    digest(stack_digest)
    return {'version':1,'source':source,'input':before,'output':after,'stack_sha256':stack_digest}


def verify_evidence(evidence,source,pixels,repaired):
    if type(evidence) is not dict or set(evidence)!={'version','source','input','output','stack_sha256'}:
        raise ValueError('Derived repair replay evidence is missing')
    expected=make_evidence(source,pixels,repaired,evidence['stack_sha256'])
    if evidence!=expected:raise ValueError('Derived repair pixels differ from atomic replay evidence')
    return deepcopy(evidence)


def _digest(ops,redo,source):
    from .creative_derived_repairs import digest_ops
    return digest_ops(ops,redo,source)


def bind(engine):
    """Only at source installation, before any repair replay, never at capture."""
    from . import creative_derived_source as D
    from .creative_derived_repairs import validate_stacks
    validate_stacks(engine)
    pipe=engine._vram
    if pipe.repair_ops or pipe.redo_ops or pipe.repair_base is not None:
        raise ValueError('Repair source can only bind a freshly loaded pipeline')
    if D.record(engine) is None:
        pipe._creative_repair_source=None;pipe._creative_repair_input=None;pipe._creative_repair_evidence=None
        return
    source=D.binding(engine);rgb=_array(pipe.src_f32);proxy=D.analysis_rgb(engine)
    if rgb.shape!=proxy.shape or rgb.dtype!=np.float32:
        raise ValueError('Derived repair pipeline source extent differs from actual proxy')
    for y in range(0,rgb.shape[0],128):
        if not np.allclose(rgb[y:y+128],proxy[y:y+128].astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps):
            raise ValueError('Derived repair pipeline pixels differ from actual source')
    evidence=make_evidence(source,rgb,None,_digest([],[],source))
    D.verify(source,engine)
    pipe._creative_repair_source=deepcopy(source)
    pipe._creative_repair_input=evidence['input']
    pipe._creative_repair_evidence=evidence


def prepare_commit(pipe,ops,redo):
    from .creative_derived_repairs import validate_source_ops
    source=getattr(pipe,'_creative_repair_source',None)
    validate_source_ops(ops,source);validate_source_ops(redo,source)
    if source is None:return None
    rgb=_array(pipe.src_f32)
    if _pixels(rgb)!=getattr(pipe,'_creative_repair_input',None):
        raise ValueError('Immutable derived repair input changed before replay')
    return deepcopy(source),_digest(ops,redo,source)


def complete_commit(pipe,prepared,base):
    if prepared is None:return None
    source,digest=prepared
    return make_evidence(source,_array(pipe.src_f32),None if base is None else _array(base),digest)


def verify_pipeline(pipe,source):
    """Read-only proof check; never bless a changed source, recipe or buffer."""
    from .creative_derived_repairs import validate_source_ops
    if getattr(pipe,'_creative_repair_source',None)!=source:
        raise ValueError('Repair pipeline is bound to another immutable source')
    validate_source_ops(pipe.repair_ops,source);validate_source_ops(pipe.redo_ops,source)
    evidence=verify_evidence(getattr(pipe,'_creative_repair_evidence',None),source,
        _array(pipe.src_f32),None if pipe.repair_base is None else _array(pipe.repair_base))
    if evidence['input']!=getattr(pipe,'_creative_repair_input',None) or evidence['stack_sha256']!=_digest(pipe.repair_ops,pipe.redo_ops,source):
        raise ValueError('Repair stack changed after atomic replay')
    return evidence
