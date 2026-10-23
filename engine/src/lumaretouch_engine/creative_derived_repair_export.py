"""Internal canonical-float repair replay fence; never a persisted bitmap proof."""
from copy import deepcopy
from hashlib import sha256
import numpy as np


def verify_spec(spec):
    from .creative_derived_source import binding, record
    from .creative_derived_repairs import validate_stacks, stack_digest
    state={'creative_base':getattr(spec,'creative_base',None),'repair_ops':getattr(spec,'repair',[])}
    validate_stacks(state)
    if record(state) is None:raise ValueError('Float repair export requires a canonical derived source')
    return binding(state),stack_digest(state)


def _pixels(source,pixels):
    value=np.asarray(pixels)
    if value.dtype!=np.float32 or value.shape!=(source['height'],source['width'],3):
        raise ValueError('Derived repair requires full-resolution float32 working RGB')
    digest=sha256()
    for row in value:
        if not np.isfinite(row).all() or np.any(row<0) or np.any(row>1):
            raise ValueError('Derived repair is SDR-only; no implicit alpha/HDR clipping')
        digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return digest.hexdigest()


def _proof(spec,pixels):
    source,stack=verify_spec(spec)
    return (source['sha256'],source['width'],source['height'],stack,_pixels(source,pixels))


def stamp_pixels(spec,pixels):
    """INTERNAL: exporter calls only after canonical export_source resolution."""
    spec._creative_repair_resolved_pixels=_proof(spec,pixels)
    spec._creative_repair_replayed_pixels=None
    spec._creative_repair_evidence=None


def verify_pixels(spec,pixels):
    proof=_proof(spec,pixels)
    if getattr(spec,'_creative_repair_resolved_pixels',None)!=proof:
        raise ValueError('Repair input or ordered operations changed after canonical resolution')
    return proof


def stamp_replayed(spec,source_pixels,repaired):
    """INTERNAL: after the owned ordered replay succeeds, before consumers see it."""
    input_proof=verify_pixels(spec,source_pixels)
    source,stack=verify_spec(spec)
    from .creative_derived_repair_runtime import make_evidence
    evidence=make_evidence(source,source_pixels,repaired,stack)
    spec._creative_repair_replayed_pixels=(input_proof,_pixels(source,repaired))
    spec._creative_repair_evidence=evidence


def verify_replayed(spec,repaired):
    source,stack=verify_spec(spec)
    input_proof=getattr(spec,'_creative_repair_resolved_pixels',None)
    if not isinstance(input_proof,tuple) or input_proof[:4]!=(source['sha256'],source['width'],source['height'],stack):
        raise ValueError('Repaired export has no current canonical input and operation proof')
    output_hash=_pixels(source,repaired)
    if getattr(spec,'_creative_repair_replayed_pixels',None)!=(input_proof,output_hash):
        raise ValueError('Repaired export pixels differ from the owned ordered replay')
    evidence=getattr(spec,'_creative_repair_evidence',None)
    shape=[source['height'],source['width'],3]
    expected={'version':1,'source':source,'stack_sha256':stack,
        'input':{'shape':shape,'sha256':input_proof[-1]},
        'output':{'shape':shape,'sha256':output_hash}}
    if evidence!=expected:raise ValueError('Repaired export has no exact canonical runtime evidence')
    return deepcopy(evidence)
