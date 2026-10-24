# SPDX-License-Identifier: GPL-3.0-or-later
"""Existing visible eye makeup: four independently bilateral signed intents.

No colour swatch, generated makeup, iris, lashes, liner or eye-light controls.
Ranges and numerical gains are Lumaretouch policy, not PixCake calibration.
AUTHORED / UNRUN: no native or photographic acceptance has been performed.
"""
import math

OP = OPERATION = 'lnx.eye_makeup_enhance.v1'
VERSION = 1
CONTROL_KEYS = KEYS = ('amount', 'saturation', 'brightness', 'structure')
SIDES = ('left', 'right')
CONTROL_IDS = dict(zip(CONTROL_KEYS, (
    'LNX-REF-PC-32471-C-ee9394fa95', 'LNX-REF-PC-32471-C-707956d003',
    'LNX-REF-PC-32471-C-0985fdcfb9', 'LNX-REF-PC-32471-C-e3b5569011')))
POLICY = 'reviewed-existing-periocular-makeup-oklab-two-scale-v1'


def neutral():
    return {'version': VERSION, **{key: {'linked': True, 'left': 0.0, 'right': 0.0}
                                 for key in CONTROL_KEYS}}


def amount(value):
    if (type(value) not in (int, float) or not -1 <= value <= 1
            or not math.isfinite(value)):
        raise ValueError('眼妆增强数值必须为 [-1,1] 有限数值')
    return float(value)


def check(value):
    if value is None:
        return neutral()
    if (type(value) is not dict or set(value) != {'version', *CONTROL_KEYS}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('眼妆增强只接受版本 1 和四项独立左右控件，不接受人物、支撑或缓存')
    out = {'version': VERSION}
    for key in CONTROL_KEYS:
        row = value[key]
        if (type(row) is not dict or set(row) != {'linked', *SIDES}
                or type(row['linked']) is not bool):
            raise ValueError('每项眼妆控件必须有自己的联动状态及人物左右数值')
        left, right = (amount(row[side]) for side in SIDES)
        if row['linked'] and left != right:
            raise ValueError('联动控件必须一次提交左右相同数值，不能偷偷复制或平均')
        out[key] = {'linked': row['linked'], 'left': left, 'right': right}
    return out


def side_controls(value, side):
    if side not in SIDES:
        raise ValueError('未知眼妆人物侧别')
    recipe = check(value)
    return {key: recipe[key][side] for key in CONTROL_KEYS}


def active(value):
    recipe = check(value)
    return any(recipe[key][side] != 0 for key in CONTROL_KEYS for side in SIDES)


def side_active(value, side):
    return any(side_controls(value, side).values())


def preset(value):
    return check(value)  # Intent only, never source-owned support or reference pixels.


def capability():
    from .eye_makeup_enhance_native import available
    ready = available()
    return {'eye_makeup_enhance_protocol': 1, 'eye_makeup_enhance_available': ready, 'eye_makeup_enhance_reason': None if ready else
            '已有眼妆增强 Rust 核心未安装或 ABI 不符；不会以眼神光、美瞳、眼线或曝光替代'}
