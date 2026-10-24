# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable collarbone contrast intent, not anatomy or an AI model. UNRUN."""
import math

OP = 'lnx.collarbone.v1'
VERSION = 1
CONTROL_ID = 'LNX-REF-PC-32465-C-abf0a5c8c9'
KEYS = ('amount',)


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('Collarbone recipe accepts only version and amount, never traces or eligibility')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Unsupported collarbone recipe version')
    amount = value['amount']
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Collarbone amount must be finite in [0,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def capability():
    from .collarbone_native import available
    ready = available()
    return {'collarbone_available': ready, 'collarbone_reason': None if ready else
            '锁骨局部对比 Rust 核心未安装或 ABI 不匹配；不会以曝光、磨皮或肩部形变替代'}
