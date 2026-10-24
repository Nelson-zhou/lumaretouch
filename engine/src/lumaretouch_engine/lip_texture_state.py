# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable lip-furrow attenuation intent only. AUTHORED / UNRUN.

Source identity, detected mouth geometry, support, measured radius and axis are
not portable recipe fields. Native availability is not source eligibility.
"""
import math

OP = 'lnx.lip_texture.v1'
VERSION = 1
CONTROL_ID = 'LNX-REF-PC-32464-C-b6315c40ca'
KEYS = ('amount',)


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('Lip texture requires only version and amount')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Unsupported lip texture version')
    amount = value['amount']
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Lip texture amount must be a finite number in [0,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def capability():
    from .lip_texture_native import available
    ready = available()
    return {'lip_texture_available': ready,
            'lip_texture_reason': None if ready else
            '唇纹修整 Rust 核心未安装或 ABI 不匹配；未使用唇妆、模糊或填充替代'}
