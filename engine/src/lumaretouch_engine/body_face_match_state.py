# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable body-to-own-face chromatic matching intent. AUTHORED / UNRUN.

This scalar intent grants neither body support nor face-reference permission.
Source-owned references, masks and fields are derived at render time, not saved.
No learned AI, brightness matching or cross-person donor is implied.
"""
import math

OP = 'lnx.body_face_match.v1'
VERSION = 1
CONTROL_ID = 'LNX-REF-PC-32465-C-d8b09012a9'
KEYS = ('amount',)


def neutral():
    return {'version': 1, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('Body-face match requires only version and amount')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Unsupported body-face match version')
    amount = value['amount']
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Body-face match amount must be a finite number in [0,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def capability():
    from .body_face_match_native import available
    ready = available()
    return {'body_face_match_available': ready,
            'body_face_match_reason': None if ready else
            '身体向本人脸部肤色匹配 Rust 扩展未安装或 ABI 不匹配；未以身体自参考匀色、磨皮或亮度匹配替代'}
