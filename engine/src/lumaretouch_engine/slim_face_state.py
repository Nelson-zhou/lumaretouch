# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit bilateral corrected slim-face intent. AUTHORED / UNRUN.

This NEW version is a compound of the existing measured face-contour controls,
not a conversion of the legacy lnx.deform.v1/slim_face value or appearance.
Positive values narrow and negative values expand the subject's named side.
The contour Rust kernel uses 0.035 face-width regional gain, not legacy 0.11.
Its existing face_contour capability is required; no new kernel is substituted.
Only portable intent is stored here, never landmarks, source identity or masks.
"""
import math

OP = 'lnx.slim_face.v2'
VERSION = 2
KEYS = ('linked', 'left', 'right')
SIDES = ('left', 'right')
CONTROL_ID = 'LNX-REF-PC-32466-C-da1d54e292'
POLICY = 'corrected-compound-contour-v2'
REGION_GAIN_OF_FACE_WIDTH = 0.035
LEGACY_PEAK_OF_FACE_WIDTH = 0.11


def neutral():
    return {'version': VERSION, 'linked': True, 'left': 0.0, 'right': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('Slim face v2 requires only version, linked and subject-left/right amounts')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Unsupported slim face version; legacy intent is not converted')
    if type(value['linked']) is not bool:
        raise ValueError('Slim face v2 linked must be an explicit boolean')
    for side in SIDES:
        amount = value[side]
        # Bound before isfinite/float so arbitrary-size integers cannot overflow.
        # Booleans, numeric strings and other coercible values are not amounts.
        if (type(amount) not in (int, float) or not -1 <= amount <= 1
                or not math.isfinite(amount)):
            raise ValueError(f'Slim face v2 {side} must be a finite number in [-1,1]')
    return {'version': VERSION, 'linked': value['linked'],
            **{side: float(value[side]) for side in SIDES}}


def active(value):
    recipe = check(value)
    return any(recipe[side] != 0.0 for side in SIDES)


def adjust(value, side, amount):
    recipe = check(value)
    if side not in SIDES:
        raise ValueError('Unknown slim face subject side')
    for target in SIDES if recipe['linked'] else (side,):
        recipe[target] = amount
    return check(recipe)


def link(value, linked):
    recipe = check(value)
    if type(linked) is not bool:
        raise ValueError('Slim face v2 linked must be an explicit boolean')
    # Relinking preserves both saved values. Only a later explicit linked
    # adjustment sets both sides, matching the existing contour interaction.
    recipe['linked'] = linked
    return recipe


def preset(value):
    return check(value)


def contour_recipe(value):
    """Map signed subject-side intent without changing contour's native signs."""
    recipe = check(value)
    from . import face_contour_state as C
    return C.check({'version': C.VERSION,
        **{key: {'linked': recipe['linked'],
                 **{side: sign * recipe[side] for side in SIDES}}
           for key, sign in (('temple', -1.0), ('cheekbone', 1.0), ('jaw', -1.0))}})


def check_coexistence(recipe, legacy_amount, contour_recipe):
    """Reject concurrent contour owners; never erase or reinterpret saved edits.

    Neutral v2 has no dependency, geometry, evidence or compatibility requirement.
    Active v2 validates the old amount using its unchanged legacy checker and
    validates the standalone contour with that operation's own recipe checker.
    """
    recipe = check(recipe)
    if not active(recipe):
        return recipe
    from .ops import deform as D
    from . import face_contour_state as C
    legacy = D.check_amounts({'slim_face': legacy_amount})['slim_face']
    contour = C.check(contour_recipe)
    if legacy != 0.0:
        raise ValueError('Slim face v2 requires neutral legacy lnx.deform.v1/slim_face; '
                         'disable it explicitly without converting saved intent')
    if C.active(contour):
        raise ValueError('Slim face v2 cannot coexist with active lnx.face_contour.v1; '
                         'disable one explicitly without clearing saved intent')
    return recipe
