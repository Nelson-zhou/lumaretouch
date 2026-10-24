# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable medium-texture/fine-sharpening intent. AUTHORED / UNRUN.

This stores intent only, never support, face identity, scale or source evidence.
Availability is ABI availability, not proof of photographic quality or body scope.
"""
import math

OP = 'lnx.skin_texture.v1'
KEYS = ('texture', 'clarity')


def neutral():
    return {'version': 1, 'texture': 0.0, 'clarity': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('Skin texture requires only version, texture and clarity')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Unsupported skin texture version')
    result = {'version': 1}
    for key, low in [('texture', -1), ('clarity', 0)]:
        number = value[key]
        # Bounds precede isfinite so arbitrarily large Python ints are refused
        # without attempting an overflowing float conversion.
        if type(number) not in (int, float) or not low <= number <= 1 or not math.isfinite(number):
            raise ValueError('Skin ' + key + ' must be a finite number in [' + str(low) + ',1]')
        result[key] = float(number)
    return result


def active(value):
    recipe = check(value)
    return any(recipe[key] != 0.0 for key in KEYS)


def capability():
    from .skin_texture_native import available
    ready = available()
    return {'skin_texture_available': ready,
            'skin_texture_reason': None if ready else '皮肤纹理/清晰度 Rust 核心未安装或 ABI 不匹配；未使用旧磨皮、全图锐化或全局对比度替代'}
