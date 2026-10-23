"""Frozen body identity: immutable effective pixels plus physical provenance.

The original pathname is retained only for relocation/change detection. It is
never a decoder input for derived pose geometry or prompted-arm mask replay.
"""
from copy import deepcopy


def capture_proof(state,path):
    from .creative_derived_source import binding,check_row_proof
    from .local_mask_state import source_digest
    source=binding(state)
    return check_row_proof({'asset_sha256':source['sha256'],'creative_source':source,
                           'original_sha256':source_digest(path)})


def verify_snapshot(snapshot,path=None):
    from .creative_derived_source import binding,check_row_proof,record
    from .body_pose_render import source,check_source
    from .arm_shape_project import check_snapshot
    frozen=snapshot.get('body_pose');proof=snapshot.get('body_pose_source_proof')
    if frozen is None:
        if proof is not None:raise ValueError('Body source proof has no frozen body owner')
        return None
    if record(snapshot) is None:
        if proof is not None:raise ValueError('Derived body proof cannot be rebound to an original file')
        return None
    proof=check_row_proof(proof);effective=binding(snapshot)
    if proof['creative_source']!=effective or proof['asset_sha256']!=effective['sha256']:
        raise ValueError('Frozen body evidence belongs to another immutable composite')
    frame=source(effective)
    bank=check_snapshot(frozen,frame);check_source(bank,frame)
    from .creative_derived_body import validate
    validate(bank,effective)
    if path is not None:
        from .local_mask_state import source_digest
        if source_digest(path)!=proof['original_sha256']:
            raise ValueError('Body export physical-original provenance changed')
    return deepcopy(proof)


def verify_spec(spec):
    return verify_snapshot({'creative_base':getattr(spec,'creative_base',None),
        'body_pose':getattr(spec,'body_pose',None),
        'body_pose_source_proof':getattr(spec,'body_pose_source_proof',None)})


def _pixel_proof(spec,pixels):
    """Bounded row hashing of the export owner's resolved working buffer."""
    from hashlib import sha256
    import numpy as np
    proof=verify_spec(spec)
    if proof is None:return None
    source=proof['creative_source'];value=np.asarray(pixels)
    if value.dtype!=np.float32 or value.shape!=(source['height'],source['width'],3):
        raise ValueError('Derived body pixels need full-resolution float32 working RGB')
    digest=sha256()
    for row in value:
        if not np.isfinite(row).all() or np.any(row<0) or np.any(row>1):
            raise ValueError('Derived body cannot silently clip alpha/HDR or nonfinite input')
        digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return (spec.creative_base['id'],source['width'],source['height'],'working-srgb-f32',digest.hexdigest())


def stamp_pixels(spec,pixels):
    """INTERNAL: called only immediately after canonical export_source resolves.

    This is an ephemeral exporter-to-consumer fence, not externally supplied
    evidence and not a public API for authenticating arbitrary pixel buffers.
    No proof is saved to projects/history or copied from original-file decode.
    """
    spec._creative_body_resolved_pixels=_pixel_proof(spec,pixels)


def verify_pixels(spec,pixels):
    """Require the same owned resolved pixels at the body preparation boundary."""
    actual=_pixel_proof(spec,pixels)
    if actual is not None and getattr(spec,'_creative_body_resolved_pixels',None)!=actual:
        raise ValueError('Derived body input differs from the canonical export-owned pixel buffer')
