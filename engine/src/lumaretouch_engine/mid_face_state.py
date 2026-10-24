# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable mid-face length intent, distinct from lower-face length and face size.

AUTHORED / UNRUN. Positive lengthens; negative shortens. Numeric gain/envelope
are original local policy, not reference-product calibration or quality proof.
No identity, landmarks, pixels, paths, support geometry or cached data in state.
"""
import math

OP = 'lnx.mid_face.v1'
VERSION = 1
CONTROL_ID = 'LNX-REF-PC-32466-C-ea67c9d99f'
POLICY = 'monotone-head-axis-mid-face-length-v1'
LENGTH_GAIN = 0.08
TAIL_FACTOR = 0.5
MIN_TAIL = 0.25
MAX_TAIL = 4.0


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def _amount(value):
    if (type(value) not in (int, float) or not -1 <= value <= 1
            or not math.isfinite(value)):
        raise ValueError('中庭强度必须为 [-1,1] 的有限数值')
    return float(value)


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('中庭配方只接受 version 和 amount，不接受人脸、路径或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此中庭配方版本')
    return {'version': VERSION, 'amount': _amount(value['amount'])}


def active(value):
    return check(value)['amount'] != 0.0


def preset(value):
    return check(value)


def capability():
    """Native loading only, not usable anatomy, image quality or acceptance."""
    from .mid_face_native import available
    ready = available()
    return {'mid_face_available': ready,
            'mid_face_reason': None if ready else
            '中庭 Rust 核心未安装或 ABI 不匹配；未用下庭、小下巴、小脸或其他算法替代'}
