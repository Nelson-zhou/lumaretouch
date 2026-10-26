# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent visible-hair intent. Source/support/review are never portable. UNRUN."""
import math

OP = 'lnx.hair_smoothing.v1'
CONTROL_ID = 'control:PC-32472:8'
KIND = 'hair_smoothing_visibility'
STAGE = 'hair_smoothing'
VERSION = 1
KEYS = ('amount',)


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if (type(value) is not dict or set(value) != {'version', 'amount'}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('Hair smoothing accepts only independent version and amount')
    amount = value['amount']
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Hair smoothing amount must be finite in [0,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def portable(value):
    return check(value)


def capability():
    from .hair_smoothing_native import available
    ready = available()
    return {'hair_smoothing_protocol': 1, 'hair_smoothing_available': ready,
            'hair_smoothing_reason': None if ready else
            '可见本人头发方向柔顺 Rust 核心未安装或 ABI 不匹配；不会以磨皮、全图模糊或几何拉直替代'}
