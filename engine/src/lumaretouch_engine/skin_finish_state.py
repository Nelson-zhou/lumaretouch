# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded original whitening/rosiness intent, never a transferable skin mask.

AUTHORED / UNRUN. These controls do not imply that semantic support, native
runtime, photo-level preview/export, or photographic acceptance is available.
"""
import math

OP = 'lnx.skin_finish.v1'
KEYS = ('whitening', 'rosiness')


def neutral():
    return {'version': 1, 'whitening': 0.0, 'rosiness': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('Skin finish requires only version, whitening and rosiness')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Unsupported skin finish version')
    for key in KEYS:
        v = value[key]
        # Range comparison before isfinite avoids overflow on huge Python ints.
        if type(v) not in (int, float) or not 0 <= v <= 1 or not math.isfinite(v):
            raise ValueError('Skin finish amounts must be finite numbers in [0,1]')
    return {'version': 1, **{key: float(value[key]) for key in KEYS}}


def active(value):
    recipe = check(value)
    return any(recipe[key] != 0 for key in KEYS)


def capability():
    from .skin_finish_native import available
    ready = available()
    return {'skin_finish_available': ready,
            'skin_finish_reason': None if ready else '肤色美白与红润 Rust 核心未安装或 ABI 不匹配；未使用曝光或色调替代'}
