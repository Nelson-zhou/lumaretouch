# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable whole-face size intent, not contour/slim-face. AUTHORED / UNRUN.

Positive shrinks the whole measured face; negative enlarges it. The local scale
policy is original, not a reference-product slider calibration or quality claim.
No face identity, landmarks, paths, pixels or cached geometry belongs in state.
"""
import math

OP = 'lnx.face_size.v1'
VERSION = 1
CONTROL_ID = 'LNX-REF-PC-32466-C-728fc62cdd'
POLICY = 'whole-measured-face-uniform-scale-v1'
SCALE_GAIN = 0.06
MIN_SCALE = 0.94
MAX_SCALE = 1.06


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def _amount(value):
    # Bound first: huge Python integers cannot overflow isfinite or conversion.
    if (type(value) not in (int, float) or not -1 <= value <= 1
            or not math.isfinite(value)):
        raise ValueError('小脸强度必须为 [-1,1] 的有限数值')
    return float(value)


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('小脸配方只接受 version 和 amount，不接受人脸、路径或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此小脸配方版本')
    return {'version': VERSION, 'amount': _amount(value['amount'])}


def active(value):
    return check(value)['amount'] != 0.0


def scale_for_amount(amount):
    """Original local policy: +1 -> 0.94, 0 -> 1, -1 -> 1.06."""
    return 1.0 - SCALE_GAIN * _amount(amount)


def preset(value):
    return check(value)


def capability():
    """Native load/ABI capability only, not geometry or photographic quality."""
    from .face_size_native import available
    ready = available()
    return {'face_size_available': ready,
            'face_size_reason': None if ready else
            '小脸 Rust 核心未安装或 ABI 不匹配；未用瘦脸、轮廓或其他算法替代'}
