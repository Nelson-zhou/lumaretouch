# SPDX-License-Identifier: GPL-3.0-or-later
"""Manual lower-lid preservation intent, not automatic anatomical detection.

AUTHORED / UNRUN. The historical lnx.enhance.v1 eye_bags leaf is unchanged.
Preservation defaults to one; amount alone determines whether v2 is active.
"""
import math

OP = OPERATION = 'lnx.eye_bags.v2'
VERSION = 2
KIND = 'eye_bag_ridge_visibility'
CONTROL_ID = 'LNX-REF-PC-32464-C-e5fac5fdcf'
KEYS = ('amount', 'preserve')


def neutral():
    return {'version': VERSION, 'amount': 0.0, 'preserve': 1.0}


def check(value):
    if value is None:
        return neutral()
    if (type(value) is not dict or set(value) != {'version', *KEYS}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('Eye-bag preservation requires the separate version-2 amount/preserve recipe')
    for key in KEYS:
        number = value[key]
        if type(number) not in (int, float) or not 0 <= number <= 1 or not math.isfinite(number):
            raise ValueError('Eye-bag ' + key + ' must be a finite number in [0,1]')
    return {'version': VERSION, **{key: float(value[key]) for key in KEYS}}


def active(value):
    return check(value)['amount'] > 0


def check_coexistence(value, legacy_amount):
    checked = check(value)
    if (type(legacy_amount) not in (int, float) or not 0 <= legacy_amount <= 1
            or not math.isfinite(legacy_amount)):
        raise ValueError('Legacy eye-bag amount must remain a finite number in [0,1]')
    if active(checked) and legacy_amount > 0:
        raise ValueError('Legacy and reviewed eye-bag corrections are mutually exclusive; disable one explicitly')
    return checked


def preset(value):
    """Only scalar intent transfers. No review, source, mask or FaceRef does."""
    return check(value)


def capability():
    """Actual ABI availability only; never proof of source/photographic quality."""
    from .eye_bag_preserve_native import available
    ready = available()
    return {'eye_bag_preserve_available': ready,
            'eye_bag_preserve_reason': None if ready else
            '卧蚕保留 Rust 核心未安装或 ABI 不匹配；原图审核与重置仍可用，未使用替代效果'}
