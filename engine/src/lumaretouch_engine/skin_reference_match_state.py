# SPDX-License-Identifier: GPL-3.0-or-later
"""Selected same-photo face-reference colour/brightness intent. AUTHORED / UNRUN.

Only the amount is portable. A reference FaceRef, reviewed target relation,
source evidence, support or fitted transform never belongs in a recipe. This
partial feature is not automatic brightest-face selection or body matching.
"""
import math

OP = 'lnx.skin_reference_match.v1'
VERSION = 1
CONTROL_ID = 'control:PC-32465:19'
KEYS = ('amount',)


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('Skin-reference matching requires only version and amount')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Unsupported skin-reference matching version')
    amount = value['amount']
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Skin-reference matching amount must be finite in [0,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def capability():
    from .skin_reference_match_native import available
    ready = available()
    return {'skin_reference_match_available': ready,
            'skin_reference_match_reason': None if ready else
            '同图指定人脸肤色及亮度匹配 Rust 扩展未安装或 ABI 不匹配；未以自动最亮脸、身体匹配或简单着色替代'}
