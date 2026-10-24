# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable bilateral chin roundness/sharpness intent. AUTHORED / UNRUN.

Positive contracts horizontal chin width; negative expands. No chin shortening,
tip translation, geometry, identity, pixels, paths or caches in this state.
"""
import math

OP = 'lnx.chin_shape.v1'
VERSION = 1
KEYS = ('linked', 'left', 'right')
SIDES = ('left', 'right')
CONTROL_ID = 'LNX-REF-PC-32466-C-ed7837df9a'
POLICY = 'bilateral-monotone-horizontal-chin-taper-v1'
WIDTH_GAIN = 0.08
TAIL_FACTOR = 0.5


def neutral():
    return {'version': VERSION, 'linked': True, 'left': 0.0, 'right': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('尖下巴配方只接受 version、linked、left 和 right')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此尖下巴配方版本')
    if type(value['linked']) is not bool:
        raise ValueError('尖下巴 linked 必须为明确布尔值')
    for side in SIDES:
        amount = value[side]
        # Compare bounds before conversion/isfinite, including arbitrary ints.
        if (type(amount) not in (int, float) or not -1 <= amount <= 1
                or not math.isfinite(amount)):
            raise ValueError(f'尖下巴 {side} 必须为 [-1,1] 的有限数值')
    if value['linked'] and value['left'] != value['right']:
        raise ValueError('尖下巴联动配方要求左右强度相同；不自动平均或覆盖')
    return {'version': VERSION, 'linked': value['linked'],
            **{side: float(value[side]) for side in SIDES}}


def active(value):
    recipe = check(value)
    return any(recipe[side] != 0.0 for side in SIDES)


def adjust(value, side, amount):
    recipe = check(value)
    if side not in SIDES:
        raise ValueError('未知尖下巴人物侧别')
    for target in SIDES if recipe['linked'] else (side,):
        recipe[target] = amount
    return check(recipe)


def link(value, linked):
    recipe = check(value)
    if type(linked) is not bool:
        raise ValueError('尖下巴 linked 必须为明确布尔值')
    recipe['linked'] = linked
    # Explicitly refuse unequal relinking, rather than inventing a chosen side.
    return check(recipe)


def preset(value):
    return check(value)


def capability():
    """Native load/ABI capability only, not anatomy or photographic acceptance."""
    from .chin_shape_native import available
    ready = available()
    return {'chin_shape_available': ready, 'chin_shape_reason': None if ready else
            '尖下巴 Rust 核心未安装或 ABI 不匹配；未用小下巴、下庭或瘦脸替代'}
