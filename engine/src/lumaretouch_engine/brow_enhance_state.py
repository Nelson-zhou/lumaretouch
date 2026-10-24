# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable existing-brow enhancement intent only. AUTHORED / UNRUN.

Negative reduces existing dark brow contrast; positive strengthens it. Linking
is intent, never a hidden intensity. No source, masks, radius or caches persist.
"""
import math

OP = OPERATION = 'lnx.brow_enhance.v1'
VERSION = 1
SIDES = ('left', 'right')
KEYS = ('linked', *SIDES)
CONTROL_ID = 'LNX-REF-PC-32471-C-18765fa8ea'
CONTROL_IDS = {'family': CONTROL_ID}
POLICY = 'source-local-existing-dark-brow-contrast-v1'


def neutral():
    return {'version': VERSION, 'linked': True, 'left': 0.0, 'right': 0.0}


def _amount(value, side):
    # Range first: arbitrary-size integers must not overflow float conversion.
    if (type(value) not in (int, float) or not -1 <= value <= 1
            or not math.isfinite(value)):
        raise ValueError(f'眉毛增强 {side} 必须为 [-1,1] 有限数值')
    return float(value)


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('眉毛增强配方仅接受版本、联动状态和人物左右数值；不接受人脸、遮罩或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此眉毛增强配方版本')
    if type(value['linked']) is not bool:
        raise ValueError('眉毛增强联动必须为布尔值')
    left, right = (_amount(value[side], side) for side in SIDES)
    if value['linked'] and left != right:
        raise ValueError('联动眉毛增强必须一次提交左右相同数值；不同数值需先解除联动')
    return {'version': VERSION, 'linked': value['linked'], 'left': left, 'right': right}


def active(value):
    recipe = check(value)
    return any(recipe[side] != 0.0 for side in SIDES)


def side_active(value, side):
    if type(side) is not str or side not in SIDES:
        raise ValueError('未知眉毛增强人物侧别')
    return check(value)[side] != 0.0


def preset(value):
    return check(value)


def capability():
    """Required native symbols and ABI only, not source/photographic acceptance."""
    from .brow_enhance_native import available
    ready = available()
    return {'brow_enhance_available': ready,
            'brow_enhance_reason': None if ready else
            '眉毛增强 Rust 核心未安装或 ABI 不匹配；未用曝光、眉妆或毛发重建替代'}
