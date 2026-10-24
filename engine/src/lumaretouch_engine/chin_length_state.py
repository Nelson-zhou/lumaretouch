# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable below-lips chin-length intent. AUTHORED / UNRUN.

Positive lengthens; negative shortens. This is not lower-third length, chin
width/sharpness, legacy small_chin or the broader jaw-and-chin 收下巴 control.
Geometry, face/source identity, pixels, paths and caches never enter state.
"""
import math

OP = 'lnx.chin_length.v1'
VERSION = 1
CONTROL_ID = 'LNX-REF-PC-32466-C-44a42baef4'
POLICY = 'monotone-head-axis-below-lips-chin-length-v1'
LENGTH_GAIN = 0.08
TAIL = 0.5


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def _amount(value):
    # Check bounds before float conversion/isfinite, including arbitrary ints.
    if (type(value) not in (int, float) or not -1 <= value <= 1
            or not math.isfinite(value)):
        raise ValueError('下巴长短强度必须为 [-1,1] 的有限数值')
    return float(value)


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', 'amount'}:
        raise ValueError('下巴长短配方只接受 version 和 amount，不接受人脸、路径或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此下巴长短配方版本')
    return {'version': VERSION, 'amount': _amount(value['amount'])}


def active(value):
    return check(value)['amount'] != 0.0


def preset(value):
    return check(value)


def check_coexistence(recipe, legacy_amount):
    """Refuse an active legacy small_chin overlap; never reset either recipe.

    Neutral remains independent of the legacy deformation dependency. Active
    recipes use its unchanged validator rather than reinterpret legacy amounts.
    """
    recipe = check(recipe)
    if not active(recipe):
        return recipe
    from .ops import deform as D
    legacy = D.check_amounts({'small_chin': legacy_amount})['small_chin']
    if legacy != 0.0:
        raise ValueError('下巴长短不能与非零旧版小下巴同时使用；请明确选择，不自动重置')
    return recipe


def capability():
    """Actual shared-core load/ABI only, not anatomy or image acceptance."""
    from .chin_length_native import available
    ready = available()
    return {'chin_length_available': ready,
            'chin_length_reason': None if ready else
            '下巴长短共用的下庭 Rust 几何核心未安装或 ABI 不匹配；'
            '未用下庭操作、小下巴或收下巴替代'}
