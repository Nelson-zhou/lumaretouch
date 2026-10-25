# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict vector-only creative selection wire recipe. AUTHORED / UNRUN.

This is an original manual geometric selection tool, not person segmentation.
Coordinates refer to full creative-canvas pixel edges, never the display proxy.
"""
from copy import deepcopy
import hashlib
import json
import math

MAX_OPERATIONS = 256
MAX_POINTS = 65_536
MAX_COORDINATE = 1_048_576.0
SPACE = 'canvas-pixel-edge-v1'
COMBINES = ('new', 'add', 'subtract', 'intersect')
POLICIES = ('create', 'replace', 'union', 'intersect', 'subtract')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def valid_id(value):
    return (type(value) is str and 1 <= len(value) <= 256
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def number(value, lower=-MAX_COORDINATE, upper=MAX_COORDINATE):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('Selection geometry must be finite and within safety bounds')
    return value


def validate(recipe, canvas):
    keys = {'version', 'coordinate_space', 'canvas', 'feather_radius', 'operations'}
    if type(recipe) is not dict or set(recipe) != keys or type(recipe['version']) is not int or recipe['version'] != 1:
        raise ValueError('Unsupported selection vector recipe')
    expected = {'width': canvas['width'], 'height': canvas['height']}
    extent = recipe['canvas']
    if (type(extent) is not dict or set(extent) != set(expected)
            or any(type(extent[k]) is not int for k in expected) or extent != expected
            or recipe['coordinate_space'] != SPACE):
        raise ValueError('Selection coordinates do not belong to the full current canvas')
    if (any(not 1 <= extent[k] <= 131_072 for k in expected)
            or extent['width'] * extent['height'] > 100_000_000):
        raise ValueError('Selection authoritative canvas exceeds the full-resolution dimension budget')
    if type(recipe['feather_radius']) is not int or not 0 <= recipe['feather_radius'] <= 256:
        raise ValueError('Selection feather must be an integer canvas-pixel radius in [0,256]')
    operations = recipe['operations']
    if type(operations) is not list or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise ValueError('An explicit nonempty selection is required; operation budget is 256')
    points = 0
    for operation in operations:
        if type(operation) is not dict:
            raise ValueError('Malformed selection operation')
        kind = operation.get('kind')
        if kind == 'invert':
            if set(operation) != {'kind'}:
                raise ValueError('Invert has no hidden geometry or combine policy')
            continue
        if operation.get('combine') not in COMBINES:
            raise ValueError('Unsupported explicit selection combine policy')
        if kind in ('rectangle', 'ellipse'):
            if set(operation) != {'kind', 'combine', 'x0', 'y0', 'x1', 'y1'}:
                raise ValueError('Malformed selection shape')
            for key in ('x0', 'y0', 'x1', 'y1'):
                number(operation[key])
            if operation['x1'] <= operation['x0'] or operation['y1'] <= operation['y0']:
                raise ValueError('Selection shape bounds must have positive extent')
        elif kind in ('lasso', 'brush'):
            keys = {'kind', 'combine', 'points'}
            if kind == 'brush':
                keys |= {'diameter', 'hardness', 'opacity'}
            if set(operation) != keys:
                raise ValueError('Malformed selection path')
            path = operation['points']
            if type(path) is not list or not (3 if kind == 'lasso' else 1) <= len(path) <= MAX_POINTS:
                raise ValueError('Selection path has too few points or exceeds its point budget')
            points += len(path)
            if points > MAX_POINTS:
                raise ValueError('Selection total vector point budget exceeded')
            for point in path:
                if type(point) is not list or len(point) != 2:
                    raise ValueError('Selection point requires [x,y] canvas coordinates')
                number(point[0]); number(point[1])
            if kind == 'brush':
                if operation['combine'] not in ('add', 'subtract'):
                    raise ValueError('Brush explicitly adds or subtracts coverage')
                number(operation['diameter'], 1 / 64, 262_144.0)
                number(operation['hardness'], 0, 1)
                number(operation['opacity'], 0, 1)
        else:
            raise ValueError('Only manual rectangle, ellipse, lasso, brush and invert are supported')
    return deepcopy(recipe)


def mask_policy(policy, existing):
    if policy not in POLICIES:
        raise ValueError('Choose an explicit existing-mask policy')
    if (policy == 'create') != (existing is None):
        raise ValueError('Create requires no existing mask; an existing mask requires an explicit replace/union/intersect/subtract choice')
    return policy
