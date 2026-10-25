# SPDX-License-Identifier: GPL-3.0-or-later
"""Historical validation using existing people graph/support owners. UNRUN.

Only per-current-photo FaceRef intent is admitted in this first slice. No second
project schema, body operation bank, cached raster, cross-image cohort or generic
face-recovery authority is introduced by these hooks.
"""
from . import neck_wrinkle_state as S


def validate_leaf(path, value):
    if path != '/amount':
        raise ValueError('Neck fine-line intent cannot carry source, body, mask or review data')
    S.check({'version': 1, 'amount': value})


def require_face_scope(scope):
    if scope != 'face':
        raise ValueError('Neck fine-line correction is current-photo/current-face only; shared scopes are fenced')


def validate_graph(state):
    from . import people_state as P
    out = P.check(state)
    for row in out['overrides']:
        if row['operation_id'] == S.OP:
            validate_leaf(row['parameter_path'], row['value'])
            require_face_scope(row['scope'])
    return out


def validate_records(value):
    """Check portable historical intent, without rebinding history to live poses."""
    if isinstance(value, dict):
        for key in ('people_graph', '_people_state'):
            if key in value:
                if value[key] is None:
                    raise ValueError('Saved neck people state cannot be null')
                validate_graph(value[key])
        for child in value.values():
            validate_records(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_records(child)


def validate_project(value):
    from . import skin_colour_body_support as OWNER
    from .neck_wrinkle_support import FAMILY
    validate_records(value)
    OWNER.validate_project(value, family=FAMILY, operation_id=S.OP)


def refuse_transfer(*args, **kwargs):
    raise ValueError('Neck fine-line cross-image, batch and shared-cohort transfer is not admitted in this slice')


def refuse_recovery(*args, **kwargs):
    raise ValueError('Neck fine-line recovery needs its exact BodyRef/support owner; generic face recovery is fenced')


def require_parked_transition(before, candidate):
    """No current-photo review can authorize an unreviewed parked target."""
    from .neck_wrinkle_host import _neck_signature
    if _neck_signature(before) != _neck_signature(candidate):
        raise ValueError('Parked neck intent/support/ownership needs its own target review; transfer is not admitted')
    return candidate
