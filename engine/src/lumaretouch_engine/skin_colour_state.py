# SPDX-License-Identifier: GPL-3.0-or-later
"""Original signed face-skin colour intent, never a transferable source mask.

The handbook supplies directions, not numerical ranges. This project's [-1,1]
scale is a local design; it is not Kelvin or a proprietary preset conversion.
"""
import math

OP = 'lnx.skin_colour.v1'
KEYS = ('temperature', 'tint')


def neutral():
    return {'version': 1, 'temperature': 0.0, 'tint': 0.0}


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('Face-skin colour requires only its version and signed scalars')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Unsupported face-skin colour version')
    for key in KEYS:
        v = value[key]
        if type(v) not in (int, float) or not -1 <= v <= 1 or not math.isfinite(v):
            raise ValueError('Face-skin colour amounts must be finite numbers in [-1,1]')
    return {'version': 1, **{key: float(value[key]) for key in KEYS}}


def active(value):
    recipe = check(value)
    return any(recipe[key] != 0 for key in KEYS)


def capability():
    from .skin_colour_native import available
    ready = available()
    return {'skin_colour_available': ready,
            'skin_colour_reason': None if ready else '面部肤色 Rust 核心未安装或 ABI 不匹配；未使用全图白平衡替代'}
