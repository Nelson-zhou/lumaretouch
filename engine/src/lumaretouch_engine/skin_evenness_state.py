# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable facial skin-evenness intent only. AUTHORED / UNRUN.

No source, target palette, identity, support or scale belongs in this recipe.
The native availability flag is not photographic acceptance or proprietary parity.
"""
import math

OP = 'lnx.skin_evenness.v1'
VERSION = 1
CONTROL_ID = 'LNX-REF-PC-32465-C-60b7c0e3d1'
KEYS = ('amount',)


def neutral():
    return {'version': 1, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('Skin evenness requires only version and amount')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Unsupported skin evenness version')
    amount = value['amount']
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Skin evenness amount must be a finite number in [0,1]')
    return {'version': 1, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def capability():
    from .skin_evenness_native import available
    ready = available()
    return {'skin_evenness_available': ready,
            'skin_evenness_reason': None if ready else '脸部肤色统一 Rust 核心未安装或 ABI 不匹配；未以旧磨皮、肤色预设或全图调色替代'}
