# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable eye-level/size symmetry intent. AUTHORED / UNRUN.

Reference is a size-only measurement-reference policy, never stored measurements. The
independent head axis, source opening areas, landmarks and caches are not state.
"""
import math

OP = 'lnx.eye_symmetry.v1'
VERSION = 1
KEYS = ('horizontal', 'size', 'reference')
REFERENCES = ('auto', 'left', 'right')
CONTROL_IDS = {
    'family': 'LNX-REF-PC-32470-C-2745ac86f5',
    'horizontal': 'LNX-REF-PC-32470-C-a86e5c0175',
    'size': 'LNX-REF-PC-32470-C-4601eb7797',
    'reference': 'LNX-REF-PC-32470-C-118aa67e04',
}
POLICY = 'independent-head-axis-level-polygon-opening-area-v1'


def neutral():
    return {'version': VERSION, 'horizontal': 0.0, 'size': 0.0,
            'reference': 'auto'}


def _strength(value, key):
    # Check the bounded range before isfinite/conversion of arbitrary-size ints.
    if (type(value) not in (int, float) or not 0 <= value <= 1
            or not math.isfinite(value)):
        raise ValueError(f'眼睛对称 {key} 必须为 [0,1] 的有限数值')
    return float(value)


def check(value):
    if value is None:
        return neutral()
    if type(value) is not dict or set(value) != {'version', *KEYS}:
        raise ValueError('眼睛对称配方仅接受版本、水平强度、大小强度和参考侧；'
                         '不接受人物、测量、路径或缓存')
    if type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('不支持此眼睛对称配方版本')
    if type(value['reference']) is not str or value['reference'] not in REFERENCES:
        raise ValueError('眼睛对称大小参考必须为 auto、left 或 right')
    return {'version': VERSION,
            'horizontal': _strength(value['horizontal'], 'horizontal'),
            'size': _strength(value['size'], 'size'),
            'reference': value['reference']}


def active(value):
    recipe = check(value)
    # A reference-only change carries intent but never creates a geometry field.
    return recipe['horizontal'] != 0.0 or recipe['size'] != 0.0


def preset(value):
    return check(value)


def capability():
    """Actual shared ABI/symbol capability, not measured source availability."""
    from .eye_symmetry_native import available
    ready = available()
    return {'eye_symmetry_available': ready,
            'eye_symmetry_reason': None if ready else
            '眼睛对称共用的眼形 Rust 核心未安装或 ABI 不匹配；'
            '未用大眼、眼距或双侧眼形配方替代'}
