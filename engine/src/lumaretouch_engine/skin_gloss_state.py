# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable signed face-skin gloss intent only. AUTHORED / UNRUN.

No mask, source identity, radius or inferred highlight evidence is transferable
through this recipe. Capability is native ABI availability, not photo acceptance.
"""
import math

OP = 'lnx.skin_gloss.v1'
KEYS = ('amount',)


def neutral():
    return {'version': 1, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('Skin gloss requires only version and amount')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Unsupported skin gloss version')
    amount = value['amount']
    if type(amount) not in (int, float) or not -1 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Skin gloss amount must be a finite number in [-1,1]')
    return {'version': 1, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def capability():
    from .skin_gloss_native import available
    ready = available()
    return {'skin_gloss_available': ready,
            'skin_gloss_reason': None if ready else '皮肤光泽 Rust 核心未安装或 ABI 不匹配；未使用曝光或全局曲线替代'}
