# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent original crown/side geometry intent. AUTHORED / UNRUN.

The reference publishes directions and a side lock, not numbers, defaults or
the difference between its two crown variants. These are our local controls.
"""
from copy import deepcopy
import math

VERSION = 1
OPERATION_ID = OPERATION = OP = 'lnx.hair_volume.v1'
STAGE = 'hair_volume'
CONTROL_IDS = {'crown': 'control:PC-32472:2', 'sides': 'control:PC-32472:3'}
REGIONS = ('crown', 'left', 'right')
SUPPORT_KIND = 'hair_volume'


def neutral():
    return {'version': 1, 'crown': {'version': 1, 'amount': 0.},
            'sides': {'version': 1, 'linked': True, 'left': 0., 'right': 0.}}


def check(value):
    if value is None:
        return neutral()
    if (type(value) is not dict or set(value) != {'version', 'crown', 'sides'}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('Unsupported hair volume family version')
    crown, sides = value['crown'], value['sides']
    if (type(crown) is not dict or set(crown) != {'version', 'amount'}
            or type(sides) is not dict or set(sides) != {'version', 'linked', 'left', 'right'}
            or any(type(part['version']) is not int or part['version'] != 1 for part in (crown, sides))
            or type(sides['linked']) is not bool):
        raise ValueError('Crown and side controls need their independent versions')
    out = deepcopy(value)
    for group, key in (('crown', 'amount'), ('sides', 'left'), ('sides', 'right')):
        amount = value[group][key]
        if type(amount) not in (int, float) or not math.isfinite(amount) or not -1 <= amount <= 1:
            raise ValueError('Hair geometry uses an original finite signed [-1,1] range')
        out[group][key] = float(amount)
    if sides['linked'] and sides['left'] != sides['right']:
        raise ValueError('Linked side amounts must agree; no silent reconciliation')
    return out


def amounts(value):
    value = check(value)
    return (value['crown']['amount'], value['sides']['left'], value['sides']['right'])


def active(value):
    return any(amounts(value))


def vector(value):
    return [1., *amounts(value)]


def transferable(value):
    """Transfer scalar intent only; never source geometry, reviews or evidence."""
    return check(value)
