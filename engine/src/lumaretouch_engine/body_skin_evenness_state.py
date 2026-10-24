# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable body-region chroma-evenness intent only. AUTHORED / UNRUN.

This is not body-to-face matching. A nonzero recipe neither grants body support
nor asserts automatic person segmentation, learned AI or photographic parity.
The operation-specific source review remains in the canonical support bank.
"""
import math

OP = 'lnx.body_skin_evenness.v1'
VERSION = 1
CONTROL_ID = 'LNX-REF-PC-32465-C-d5ac2d4606'
KEYS = ('amount',)


def neutral():
    return {'version': 1, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('Body skin evenness requires only version and amount')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Unsupported body skin evenness version')
    amount = value['amount']
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Body skin evenness amount must be a finite number in [0,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def capability():
    # Reuse the original Rust source/reference and current-Y application ABI.
    # Availability does not promise reviewed support or reliable pose scale.
    from .skin_evenness_native import available
    ready = available()
    return {'body_skin_evenness_available': ready,
            'body_skin_evenness_reason': None if ready else
            '身体肤色不均匀校正 Rust 核心未安装或 ABI 不匹配；未以脸身匹配、磨皮或曝光替代'}
