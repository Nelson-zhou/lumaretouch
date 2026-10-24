# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable, person-relative bilateral face-contour intent. AUTHORED / UNRUN.

Original numeric policy, not commercial slider values or proprietary parity.
Relinking does not overwrite unequal sides; a later explicit linked adjustment
sets both. Recipes contain no face identity, landmarks, masks, assets or caches.
"""
import math

OP = 'lnx.face_contour.v1'
VERSION = 1
KEYS = ('temple', 'cheekbone', 'jaw')
SIDES = ('left', 'right')
CONTROL_IDS = {
    'temple': 'LNX-REF-PC-32466-C-94bf91612d',
    'cheekbone': 'LNX-REF-PC-32466-C-d24d97d234',
    'jaw': 'LNX-REF-PC-32466-C-3bc7e245b7',
}


def neutral():
    return {'version': VERSION,
            **{key: {'linked': True, 'left': 0.0, 'right': 0.0} for key in KEYS}}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('脸部轮廓配方只接受版本和三项独立双侧参数，不能携带人脸或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此脸部轮廓配方版本')
    result = {'version': VERSION}
    for key in KEYS:
        setting = value[key]
        if (type(setting) is not dict or set(setting) != {'linked', *SIDES}
                or type(setting['linked']) is not bool):
            raise ValueError(f'脸部轮廓 {key} 需要明确的联动状态和人物左/右值')
        for side in SIDES:
            amount = setting[side]
            # Compare bounds first so arbitrary-size Python ints do not overflow
            # math.isfinite or float conversion. Booleans are not amounts.
            if (type(amount) not in (int, float) or not -1 <= amount <= 1
                    or not math.isfinite(amount)):
                raise ValueError(f'脸部轮廓 {key}/{side} 必须为 [-1,1] 有限数值')
        result[key] = {'linked': setting['linked'],
                       **{side: float(setting[side]) for side in SIDES}}
    return result


def active(value):
    recipe = check(value)
    return any(recipe[key][side] != 0 for key in KEYS for side in SIDES)


def side_active(value, side):
    if side not in SIDES:
        raise ValueError('未知人物侧别')
    recipe = check(value)
    return any(recipe[key][side] != 0 for key in KEYS)


def adjust(value, key, side, amount):
    recipe = check(value)
    if key not in KEYS or side not in SIDES:
        raise ValueError('未知脸部轮廓控件或人物侧别')
    for target in SIDES if recipe[key]['linked'] else (side,):
        recipe[key][target] = amount
    return check(recipe)


def link(value, key, linked):
    recipe = check(value)
    if key not in KEYS or type(linked) is not bool:
        raise ValueError('非法脸部轮廓联动设置')
    recipe[key]['linked'] = linked
    return recipe


def preset(value):
    return check(value)


def capability():
    """Native-load capability only, not anatomy or photographic acceptance."""
    from .face_contour_native import available
    ready = available()
    return {'face_contour_available': ready,
            'face_contour_reason': None if ready else
            '脸部轮廓 Rust 核心未安装或 ABI 不匹配；未使用其他变形算法替代'}
