# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable nose-safe philtrum-length intent. AUTHORED / UNRUN.

Negative shortens; positive lengthens the measured nose-to-above-lips gap.
This is distinct from mid-face eye-to-nose length and from lower-face/chin
controls. Geometry, face/source identity, pixels, paths and caches are not state.
"""
import math

OP = 'lnx.philtrum.v1'
VERSION = 1
CONTROL_ID = 'LNX-REF-PC-32466-C-2605502c27'
POLICY = 'monotone-head-axis-nose-safe-philtrum-length-v1'
LENGTH_GAIN = 0.08
TAIL_FACTOR = 0.5
MIN_TAIL = 0.25
MAX_TAIL = 4.0
MIN_PLATEAU_END = 1.25
MAX_PLATEAU_END = 8.0


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def _amount(value):
    # Bound arbitrary-size integers before conversion or isfinite can overflow.
    if (type(value) not in (int, float) or not -1 <= value <= 1
            or not math.isfinite(value)):
        raise ValueError('人中强度必须为 [-1,1] 的有限数值')
    return float(value)


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('人中配方只接受 version 和 amount，不接受人脸、路径或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此人中配方版本')
    return {'version': VERSION, 'amount': _amount(value['amount'])}


def active(value):
    return check(value)['amount'] != 0.0


def preset(value):
    return check(value)


def capability():
    """Actual shared-core load/ABI only, not source/anatomy or image acceptance."""
    from .philtrum_native import available
    ready = available()
    return {'philtrum_available': ready,
            'philtrum_reason': None if ready else
            '人中共用的中庭 Rust 几何核心未安装或 ABI 不匹配；'
            '未用中庭、下庭或下巴操作替代'}
