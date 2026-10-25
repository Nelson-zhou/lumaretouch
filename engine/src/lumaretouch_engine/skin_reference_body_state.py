# SPDX-License-Identifier: GPL-3.0-or-later
"""Body-only scalar intent within the selected-reference skin feature. UNRUN.

Separate storage preserves every old face-only v1 recipe and allows correction
of a reviewed body without forcing a face edit. It reuses the existing native
brightness/chroma solver; this is not another algorithm or automatic ownership.
"""
import math

OP = 'lnx.skin_reference_body_match.v1'
VERSION = 1
CONTROL_ID = 'control:PC-32465:19'
KEYS = ('amount',)


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('Body-reference intent stores only version and amount')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Unsupported body-reference intent version')
    amount = value['amount']
    if type(amount) not in (int, float) or not math.isfinite(amount) or not 0 <= amount <= 1:
        raise ValueError('Body-reference amount must be finite in [0,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def capability():
    from .skin_reference_match_native import available
    ready = available()
    return {'skin_reference_body_available': ready,
            'skin_reference_body_reason': None if ready else
            '身体参考匹配所需 Rust 扩展未安装或 ABI 不匹配；不以其他人物蒙版或全图着色代替'}
