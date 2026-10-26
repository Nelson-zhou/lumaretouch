# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-bound current-photo hand tone intent. Authored source; execution UNRUN."""
from copy import deepcopy
import math
import re

FAMILY = 'hand_tone'
OP = 'lnx.hand_tone.v1'
VERSION = 1


def digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Hand tone requires an exact SHA-256 identity')
    return value


def source(value):
    if type(value) is not dict or set(value) != {'sha256', 'width', 'height'}:
        raise ValueError('Hand tone requires the exact canonical source')
    digest(value['sha256'])
    if any(type(value[k]) is not int or not 1 <= value[k] <= 65536 for k in ('width', 'height')) or value['width'] * value['height'] > 32_000_000:
        raise ValueError('Hand tone canonical source exceeds 32 MP')
    return deepcopy(value)


def amount(value):
    if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
        raise ValueError('Hand tone amount must be finite in [0,1]')
    return float(value)


def radius(value):
    if type(value) is not int or not 2 <= value <= 128:
        raise ValueError('Hand tone radius must be 2..128 canonical pixels')
    return value


def neutral():
    return None


def check(value):
    if value is None:
        return None
    if type(value) is not dict or set(value) != {'version', 'source', 'input_sha256', 'repair_sha256', 'amount', 'radius_px', 'review'} or value['version'] != VERSION or type(value['version']) is not int:
        raise ValueError('Unsupported hand tone recipe')
    from .hand_tone_support import check_review
    return {'version': VERSION, 'source': source(value['source']),
            'input_sha256': digest(value['input_sha256']), 'repair_sha256': digest(value['repair_sha256']),
            'amount': amount(value['amount']), 'radius_px': radius(value['radius_px']),
            'review': check_review(value['review'])}


def active(value):
    row = check(value)
    return row is not None and row['amount'] != 0
