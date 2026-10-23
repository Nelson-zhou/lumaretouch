"""Existing portrait validators/solvers as per-face consumers, no global owner."""
from . import people_resolver as R
from . import brow_shape_state as B, nose_shape_state as N, eye_shape_state as E, mouth_shape_state as M
from . import lip_makeup_state as L, facial_wrinkle_state as W, hair_colour_state as HAIR
from .ops import deform as D, enhance as H

DEFORM = 'lnx.deform.v1'
ENHANCE = 'lnx.enhance.v1'
WRINKLES = 'lnx.facial_wrinkles.v1'
LIP = 'lnx.lip_makeup.v1'
GEOMETRY = ('lnx.brow_shape.v1', 'lnx.nose_shape.v1', 'lnx.eye_shape.v1', 'lnx.mouth_shape.v1')


def check_enhance(value):
    if type(value) is not dict or set(value) & set(W.INTENT_KEYS):
        raise ValueError('Wrinkle leaves belong to their separate operation')
    checked = H.check_amounts(value)
    return {key: amount for key, amount in checked.items() if key not in W.INTENT_KEYS}


def specifications():
    return {**{op: (module.neutral(), module.check) for op, module in zip(GEOMETRY, (B, N, E, M))},
            LIP: (L.neutral(), L.check), DEFORM: (D.check_amounts({}), D.check_amounts),
            ENHANCE: (check_enhance({}), check_enhance), WRINKLES: (W.check({}), W.check),
            HAIR.OPERATION: (HAIR.neutral(), HAIR.check)}


def leaves(value, prefix=''):
    out = {}
    for key, child in value.items():
        # Recipe versions are schema, not an inheritable user parameter.
        if not prefix and key == 'version': continue
        path = prefix + '/' + key.replace('~', '~0').replace('/', '~1')
        if type(child) is dict: out.update(leaves(child, path))
        else: out[path] = child
    return out


def defaults():
    return {op: leaves(neutral) for op, (neutral, _) in specifications().items()}


def recipes(resolved):
    specs = specifications()
    unknown = set(resolved['operations']) - set(specs)
    if unknown: raise ValueError('Unsupported people operations: ' + ', '.join(sorted(unknown)))
    return {op: R.materialize(resolved, op, neutral, validator) for op, (neutral, validator) in specs.items()}


def build_geometry(face_id, landmarks, values, source, excluded, *, backend):
    from . import brow_shape_runtime as BR, nose_shape_runtime as NR, eye_shape_runtime as ER, mouth_shape_runtime as MR
    from .people_geometry import AutomaticField, FaceGeometry
    if backend != 'mediapipe': raise ValueError('Portrait consumers require actual landmark analysis')
    ER.check_legacy(values[GEOMETRY[2]], values[DEFORM]); MR.check_legacy(values[GEOMETRY[3]], values[DEFORM])
    fields = tuple(runtime.build(landmarks, values[op], source, excluded, backend=backend)
                   for op, runtime in zip(GEOMETRY, (BR, NR, ER, MR)))
    for field in fields:
        if field is not None and any(f['requested'] and not f['applied'] for f in field.facts.values()):
            raise ValueError('A requested portrait control was refused; face result was not partially published')
    return FaceGeometry(face_id, tuple(source.shape[:2]), AutomaticField(landmarks, values[DEFORM], source.shape[:2]), fields)
