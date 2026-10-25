# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable fine-neck-line intent, not support or inferred anatomy. UNRUN."""
import math

OP = 'lnx.neck_wrinkle.v1'
CONTROL_ID = 'control:PC-32464:19'
VERSION = 1
KEYS = ('amount',)


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('Neck fine-line intent accepts only version and amount')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Unsupported neck fine-line recipe version')
    amount = value['amount']
    # Range checking before conversion also rejects unbounded Python integers.
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Neck fine-line amount must be finite in [0,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def portable(value):
    """Amount only. This does not authorize cross-image or shared-cohort use."""
    return check(value)


def capability():
    from .neck_wrinkle_native import available
    ready = available()
    return {'neck_wrinkle_protocol': 1, 'neck_wrinkle_available': ready, 'neck_wrinkle_reason': None if ready else
            '手动辅助颈部细纹 Rust 核心未安装或 ABI 不匹配；不会以磨皮、面部祛纹或颈部形变替代'}
