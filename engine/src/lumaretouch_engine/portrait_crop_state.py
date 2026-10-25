# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict scalar portrait-composition records; records are NOT review authority.

The host must review genuine current-composite anchors on the actual image and
bind them to its source/edit/geometry identity. No default, crown estimator,
landmark index, detector claim, image operation, or persisted approval is here.
AUTHORED / UNRUN.
"""
from __future__ import annotations

import math

VERSION = 1
CONVENTION = 'lrt.portrait-crop.source-edge-pixels.v1'
OPERATION_ID = 'lnx.crop.v1'
BACKEND = 'rust-portrait-crop-v1'
MAX_DIMENSION = 2**31 - 1
ANCHOR_NAMES = ('crown', 'chin', 'face_center')
RULE_NAMES = ('aspect_ratio', 'headroom_fraction', 'head_fraction', 'horizontal_position')
CONTROL_IDS = ('control:PC-32478:9', 'control:PC-32478:15',
               'control:PC-32478:16', 'control:PC-32478:17')


class PortraitCropError(ValueError):
    """Invalid or infeasible geometry. A stable code accompanies readable text."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _record(value, fields, name):
    if (type(value) is not dict or set(value) != set(fields) | {'version'}
            or type(value.get('version')) is not int or value['version'] != VERSION):
        raise PortraitCropError('invalid_geometry', f'{name} requires its exact version-1 fields')


def _number(value, name):
    if type(value) not in (int, float):
        raise PortraitCropError('invalid_geometry', f'{name} must be a finite number, not a flag or string')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise PortraitCropError('invalid_geometry', f'{name} is not representable') from error
    if not math.isfinite(result):
        raise PortraitCropError('invalid_geometry', f'{name} must be finite')
    return result


def check_size(width, height):
    """Scalar planning limit, not a pixel-memory or renderer admission promise."""
    if any(type(v) is not int or not 1 <= v <= MAX_DIMENSION for v in (width, height)):
        raise PortraitCropError('invalid_geometry', 'Portrait crop needs positive integer source dimensions within int32')
    return width, height


def check_rules(value):
    """Local fractions, not undocumented PixCake ranges/defaults or percentages."""
    _record(value, RULE_NAMES, 'Portrait crop rules')
    result = {'version': VERSION, **{name: _number(value[name], name) for name in RULE_NAMES}}
    if (result['aspect_ratio'] <= 0.0
            or not 0.0 <= result['headroom_fraction'] <= 1.0
            or not 0.0 < result['head_fraction'] <= 1.0
            or not 0.0 <= result['horizontal_position'] <= 1.0):
        raise PortraitCropError('invalid_geometry', 'Aspect must be positive; head fraction is (0,1]; headroom and horizontal position are [0,1]')
    if result['headroom_fraction'] + result['head_fraction'] > 1.0:
        raise PortraitCropError('infeasible', 'Headroom plus crown-to-chin proportion exceeds the crop height')
    return result


def check_anchors(value, width, height):
    """Continuous source-edge pixels: x right/y down, extent [0,W] × [0,H].

    Integer coordinates are pixel-cell edges; a boundary point is not a claim
    that a pixel centre exists at W/H. Input review/provenance belongs to host.
    """
    check_size(width, height)
    _record(value, ANCHOR_NAMES, 'Portrait crop anchors')
    result = {'version': VERSION}
    for name in ANCHOR_NAMES:
        point = value[name]
        if type(point) not in (list, tuple) or len(point) != 2:
            raise PortraitCropError('invalid_geometry', f'{name} needs exactly x and y')
        x, y = (_number(point[i], f'{name}[{i}]') for i in range(2))
        if not 0.0 <= x <= width or not 0.0 <= y <= height:
            raise PortraitCropError('invalid_geometry', f'{name} is outside the actual source grid')
        result[name] = [x, y]
    if not result['crown'][1] < result['chin'][1]:
        raise PortraitCropError('invalid_geometry', 'Reviewed chin must be strictly below reviewed crown')
    if not result['crown'][1] <= result['face_center'][1] <= result['chin'][1]:
        raise PortraitCropError('invalid_geometry', 'Reviewed face center must lie vertically between crown and chin')
    return result
