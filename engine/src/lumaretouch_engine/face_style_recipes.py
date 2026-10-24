# SPDX-License-Identifier: GPL-3.0-or-later
"""Original, versioned face-style recipes over existing geometry. AUTHORED / UNRUN.

This is parameter composition, not an algorithm, detector, proprietary
calibration or claim of age/gender inference. Only the documented owned leaves
are replaced; the host retains source/face binding, atomic staging and history.
"""
import math
from . import face_contour_state as CONTOUR, face_size_state as SIZE
from . import mid_face_state as MID, lower_face_state as LOWER
from . import chin_shape_state as CHIN, chin_length_state as LENGTH
from . import brow_shape_state as BROW, eye_shape_state as EYE
from . import nose_shape_state as NOSE, mouth_shape_state as MOUTH

VERSION = 1
BINDING_VERSION = 1
FAMILY_CONTROL_ID = 'PC-32466-C-3b31aac970'
AMOUNT_CONTROL_ID = 'PC-32466-C-6c86bf2c55'
COEFFICIENT_LIMIT = 0.30
# Operation order and paths are part of binding v1. Never infer a future schema.
_BINDINGS = (
    (CONTOUR.OP, CONTOUR, ('temple', 'cheekbone', 'jaw')),
    (SIZE.OP, SIZE, ('amount',)),
    (MID.OP, MID, ('amount',)),
    (LOWER.OP, LOWER, ('amount',)),
    (CHIN.OP, CHIN, ('linked', 'left', 'right')),
    (LENGTH.OP, LENGTH, ('amount',)),
    ('lnx.brow_shape.v1', BROW, ('position',)),
    ('lnx.eye_shape.v1', EYE, ('size', 'spacing', 'position')),
    ('lnx.nose_shape.v1', NOSE, ('height',)),
    ('lnx.mouth_shape.v1', MOUTH, ('vertical',)),
)
OWNED_OPERATION_IDS = tuple(op for op, _, _ in _BINDINGS)
# Each amount-1 coefficient is authored locally, not measured from a vendor.
# Contour positive: temple/jaw outward, cheekbone inward. Therefore slimming
# uses negative temple/jaw and positive cheekbone, NOT a uniform positive sign.
_STYLES = (
    ('classic', '经典', '7ce4146bc1', '较纤细轮廓和较大眼睛', {
        CONTOUR.OP: {'temple': -.12, 'cheekbone': .18, 'jaw': -.20},
        'lnx.eye_shape.v1': {'size': .18}}),
    ('youthful', '幼态', 'e4a7970fd2', '温和调整五官布局', {
        MID.OP: {'amount': -.08}, LOWER.OP: {'amount': -.04},
        'lnx.brow_shape.v1': {'position': -.04},
        'lnx.eye_shape.v1': {'spacing': .04, 'position': -.04},
        'lnx.nose_shape.v1': {'height': -.03},
        'lnx.mouth_shape.v1': {'vertical': -.03}}),
    ('bold', '英气', '7e035684d8', '温和缩小整体面部', {
        SIZE.OP: {'amount': .25}}),
    ('youth', '少年', '0e3343d22a', '温和收窄连续轮廓', {
        CONTOUR.OP: {'temple': -.10, 'cheekbone': .14, 'jaw': -.16},
        CHIN.OP: {'left': .06, 'right': .06}}),
    ('round', '圆脸适用', '7b800a0655', '收窄面颊并调整下巴形状', {
        CONTOUR.OP: {'cheekbone': .25, 'jaw': -.12},
        CHIN.OP: {'left': .18, 'right': .18}, LENGTH.OP: {'amount': .06}}),
    ('long', '长脸适用', 'ae54a179f8', '温和缩短中庭和下庭', {
        MID.OP: {'amount': -.25}, LOWER.OP: {'amount': -.18},
        LENGTH.OP: {'amount': -.08}}),
    ('square', '方脸适用', '9fc7c5a61e', '向内调整下颌轮廓', {
        CONTOUR.OP: {'jaw': -.30}, CHIN.OP: {'left': .08, 'right': .08}}),
)


def _binding(version):
    if type(version) is not int or version != BINDING_VERSION:
        raise ValueError('Unsupported face-style binding version')
    if any(module.VERSION != 1 for _, module, _ in _BINDINGS):
        raise ValueError('Face-style geometry schema changed; explicit rebinding required')


def _leaves(recipe, fields):
    for field in fields:
        value = recipe[field]
        if type(value) is dict:
            for key in ('linked', 'left', 'right'):
                yield '/' + field + '/' + key, value[key]
        else:
            yield '/' + field, value


def catalogue():
    """Return fresh plain metadata; no native loading or model availability claim."""
    _binding(BINDING_VERSION)
    return {
        'version': VERSION, 'binding_version': BINDING_VERSION,
        'family_control_id': FAMILY_CONTROL_ID, 'amount_control_id': AMOUNT_CONTROL_ID,
        'amount_min': 0.0, 'amount_max': 1.0,
        'coefficient_limit': COEFFICIENT_LIMIT,
        'origin': 'original-local-composition-not-vendor-calibration',
        'owned_operation_ids': list(OWNED_OPERATION_IDS),
        'owned_parameters': {op: [path for path, _ in _leaves(module.neutral(), fields)]
                             for op, module, fields in _BINDINGS},
        'styles': [{'id': key, 'label': label, 'control_id': 'PC-32466-C-' + suffix,
                    'intent': intent, 'version': VERSION, 'binding_version': BINDING_VERSION,
                    'owned_operation_ids': list(OWNED_OPERATION_IDS)}
                   for key, label, suffix, intent, _ in _STYLES],
    }


def patches(style, amount, *, binding_version=BINDING_VERSION):
    """Return one deterministic atomic replacement of all 30 owned leaves.

    Zero means neutral owned intent, not unset/inherit and not restore a prior
    manual value. Switching styles clears the previous style's owned values.
    Unowned leaves, operations, identities, masks and legacy controls never enter
    this patch list. Host must merge then validate the COMPLETE effective state.
    """
    _binding(binding_version)
    if type(style) is not str or style not in {row[0] for row in _STYLES}:
        raise ValueError('Unknown face style')
    if (type(amount) not in (int, float) or not 0 <= amount <= 1
            or not math.isfinite(amount)):
        raise ValueError('Face-style amount must be finite in [0,1]')
    coefficients = next(row[4] for row in _STYLES if row[0] == style)
    result = []
    for op, module, fields in _BINDINGS:
        recipe = module.neutral()
        for key, coefficient in coefficients.get(op, {}).items():
            if key not in fields or not -COEFFICIENT_LIMIT <= coefficient <= COEFFICIENT_LIMIT:
                raise ValueError('Face-style coefficient exceeds its declared binding')
            value = 0.0 if amount == 0 else coefficient * float(amount)
            if type(recipe[key]) is dict:
                recipe[key] = {'linked': True, 'left': value, 'right': value}
            else:
                recipe[key] = value
        checked = module.check(recipe)
        result.extend({'operation_id': op, 'parameter_path': path, 'unset': False, 'value': value}
                      for path, value in _leaves(checked, fields))
    if not 1 <= len(result) <= 256:
        raise ValueError('Face-style replacement exceeds the atomic patch budget')
    return result


def validate_compatibility(values):
    """Validate complete merged recipes, without mutation or silently clearing.

    Accept the full people_algorithms recipe map, not a patch list. Existing
    validator remains authoritative; also cover contour vs slim v2 and legacy
    big-eye collisions before expensive preview. This does not check runtime
    anatomy/evidence/native capability or authorize partial rendering.
    """
    from . import people_algorithms as A
    specs = A.specifications()
    if type(values) is not dict or set(values) != set(specs):
        raise ValueError('Face-style compatibility needs the complete effective recipe map')
    checked = {op: validator(values[op]) for op, (_, validator) in specs.items()}
    A.validate_compatibility(checked)
    A.SLIM_FACE.check_coexistence(checked[A.SLIM_FACE.OP],
                                checked[A.DEFORM]['slim_face'], checked[CONTOUR.OP])
    if (any(checked['lnx.eye_shape.v1']['size'][side] != 0 for side in EYE.SIDES)
            and checked[A.DEFORM]['big_eye'] != 0):
        raise ValueError('Face style conflicts with active legacy big-eye; choose explicitly')
    return checked
