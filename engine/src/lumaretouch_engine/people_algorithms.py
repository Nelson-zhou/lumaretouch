"""Existing portrait validators/solvers as per-face consumers, no global owner."""
from . import people_resolver as R
from . import skin_colour_state as SKIN_COLOUR, skin_finish_state as SKIN_FINISH
from . import skin_gloss_state as SKIN_GLOSS
from . import skin_texture_state as SKIN_TEXTURE
from . import face_contour_state as FACE_CONTOUR
from . import slim_face_state as SLIM_FACE
from . import face_size_state as FACE_SIZE
from . import lower_face_state as LOWER_FACE
from . import mid_face_state as MID_FACE
from . import chin_shape_state as CHIN_SHAPE
from . import chin_length_state as CHIN_LENGTH
from . import philtrum_state as PHILTRUM
from . import eye_symmetry_state as EYE_SYMMETRY
from . import brow_enhance_state as BROW_ENHANCE
from . import facial_sculpt_state as FACIAL_SCULPT
from . import body_face_match_state as BODY_FACE_MATCH
from . import body_skin_evenness_state as BODY_SKIN_EVENNESS
from . import collarbone_state as COLLARBONE
from . import skin_evenness_state as SKIN_EVENNESS
from . import lip_texture_state as LIP_TEXTURE
from . import eye_bag_preserve_state as EYE_BAG_PRESERVE
from . import brow_shape_state as B, nose_shape_state as N, eye_shape_state as E, mouth_shape_state as M
from . import lip_makeup_state as L, facial_wrinkle_state as W, hair_colour_state as HAIR
from .ops import deform as D, enhance as H
from . import face_decoration_state as FACE_DECORATION
from . import eye_light_state as EYE_LIGHT, blush_makeup_state as BLUSH, lipstick_state as LIPSTICK, eyeliner_state as EYELINER, eyelash_state as EYELASH, brow_makeup_state as BROW_MAKEUP, iris_makeup_state as IRIS

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
    return {BODY_FACE_MATCH.OP: (BODY_FACE_MATCH.neutral(), BODY_FACE_MATCH.check),
            BODY_SKIN_EVENNESS.OP: (BODY_SKIN_EVENNESS.neutral(), BODY_SKIN_EVENNESS.check),
            COLLARBONE.OP: (COLLARBONE.neutral(), COLLARBONE.check),
            SKIN_EVENNESS.OP: (SKIN_EVENNESS.neutral(), SKIN_EVENNESS.check),
            EYE_BAG_PRESERVE.OP: (EYE_BAG_PRESERVE.neutral(), EYE_BAG_PRESERVE.check),
            LIP_TEXTURE.OP: (LIP_TEXTURE.neutral(), LIP_TEXTURE.check),
            BROW_ENHANCE.OP: (BROW_ENHANCE.neutral(), BROW_ENHANCE.check),
            FACIAL_SCULPT.OP: (FACIAL_SCULPT.neutral(), FACIAL_SCULPT.check),
            EYE_SYMMETRY.OP: (EYE_SYMMETRY.neutral(), EYE_SYMMETRY.check),
            PHILTRUM.OP: (PHILTRUM.neutral(), PHILTRUM.check),
            CHIN_LENGTH.OP: (CHIN_LENGTH.neutral(), CHIN_LENGTH.check),
            CHIN_SHAPE.OP: (CHIN_SHAPE.neutral(), CHIN_SHAPE.check),
            MID_FACE.OP: (MID_FACE.neutral(), MID_FACE.check),
            LOWER_FACE.OP: (LOWER_FACE.neutral(), LOWER_FACE.check),
            FACE_SIZE.OP: (FACE_SIZE.neutral(), FACE_SIZE.check),
            SLIM_FACE.OP: (SLIM_FACE.neutral(), SLIM_FACE.check),
            FACE_CONTOUR.OP: (FACE_CONTOUR.neutral(), FACE_CONTOUR.check),
            SKIN_TEXTURE.OP: (SKIN_TEXTURE.neutral(), SKIN_TEXTURE.check),
            SKIN_GLOSS.OP: (SKIN_GLOSS.neutral(), SKIN_GLOSS.check),
            SKIN_FINISH.OP: (SKIN_FINISH.neutral(), SKIN_FINISH.check),
            SKIN_COLOUR.OP: (SKIN_COLOUR.neutral(), SKIN_COLOUR.check),
            **{op: (module.neutral(), module.check) for op, module in zip(GEOMETRY, (B, N, E, M))},
            LIP: (L.neutral(), L.check), DEFORM: (dict.fromkeys(D.KINDS, 0.0), D.check_amounts),
            ENHANCE: (check_enhance({}), check_enhance), WRINKLES: (W.check({}), W.check),
            HAIR.OPERATION: (HAIR.neutral(), HAIR.check),
            EYE_LIGHT.OPERATION: (EYE_LIGHT.neutral(), EYE_LIGHT.check),
            FACE_DECORATION.OP: (FACE_DECORATION.neutral(), FACE_DECORATION.check),
            BLUSH.OP: (BLUSH.neutral(), BLUSH.check), LIPSTICK.OP: (LIPSTICK.neutral(), LIPSTICK.check),
            EYELINER.OP: (EYELINER.neutral(), EYELINER.check), EYELASH.OP: (EYELASH.neutral(), EYELASH.check), IRIS.OP: (IRIS.neutral(), IRIS.check), BROW_MAKEUP.OP: (BROW_MAKEUP.neutral(), BROW_MAKEUP.check)}


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


def validate_compatibility(values):
    # Keep intent readable for conflict disclosure and neutral recovery. Enforce
    # compatibility on the complete staged candidate and before rendering, not
    # while capturing intent or after the first leaf of an atomic replacement.
    CHIN_LENGTH.check_coexistence(values[CHIN_LENGTH.OP], values[DEFORM]['small_chin'])
    EYE_BAG_PRESERVE.check_coexistence(values[EYE_BAG_PRESERVE.OP], values[ENHANCE]['eye_bags'])


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
