"""Bounded retained fringe intent, never a rendered mask or analysis cache.

Coverage belongs to the effective immutable image source after optics and before
crop/rotation. The automatic algorithm always estimates its own image support;
only a user's additive/subtractive vector strokes are retained here.
"""
import math

KEY = '_fringe_repair'
VERSION = 1
ALGORITHM = 'lrt-fringe-repair-v1'
DOMAIN = 'post-optics-pre-crop-normalized-v1'
MAX_STROKES = 128
MAX_POINTS = 8192
MAX_STROKE_POINTS = 1024
MAX_SOURCE_DIMENSION = 1_000_000


def neutral():
    # A newly available feature must not alter every previously saved photo.
    return {'version': VERSION, 'algorithm': ALGORITHM, 'enabled': False,
            'strength': 50.0, 'source': None,
            'coverage': {'domain': DOMAIN, 'strokes': []}}


def number(value, lo, hi, name='number'):
    if type(value) not in (int, float) or not lo <= value <= hi or not math.isfinite(value):
        raise ValueError('Fringe repair requires a finite bounded ' + name)
    return float(value)


def check_source(value):
    if value is None:
        return None
    if type(value) is not dict or set(value) != {'sha256', 'width', 'height'}:
        raise ValueError('Fringe repair source requires exact identity and extent')
    digest = value['sha256']
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Fringe repair source digest is invalid')
    if any(type(value[key]) is not int or not 1 <= value[key] <= MAX_SOURCE_DIMENSION
           for key in ('width', 'height')):
        raise ValueError('Fringe repair source extent is invalid')
    return dict(value)


def check_stroke(value):
    fields = {'id', 'mode', 'points', 'axes', 'opacity', 'feather'}
    if type(value) is not dict or set(value) != fields:
        raise ValueError('Fringe repair stroke requires complete vector intent')
    identity = value['id']
    if type(identity) is not str or not 1 <= len(identity) <= 96 or not identity.isprintable() or identity.strip() != identity:
        raise ValueError('Fringe repair stroke identity is invalid')
    if value['mode'] not in ('add', 'subtract'):
        raise ValueError('Fringe repair stroke mode must be add or subtract')
    points = value['points']
    if type(points) is not list or not 1 <= len(points) <= MAX_STROKE_POINTS:
        raise ValueError('Fringe repair stroke exceeds the retained point budget')
    clean_points = []
    for point in points:
        if type(point) is not list or len(point) != 2:
            raise ValueError('Fringe repair points must be normalized coordinate pairs')
        clean_points.append([number(v, 0.0, 1.0, 'point coordinate') for v in point])
    axes = value['axes']
    if type(axes) is not list or len(axes) != 2 or any(type(axis) is not list or len(axis) != 2 for axis in axes):
        raise ValueError('Fringe repair brush requires two ellipse basis vectors')
    axes = [[number(v, -2.0, 2.0, 'ellipse axis') for v in axis] for axis in axes]
    a, b = axes[0]
    c, d = axes[1]
    lengths = (math.hypot(a, b), math.hypot(c, d))
    determinant = a * d - b * c
    if min(lengths) < 1e-9 or abs(determinant) < 1e-12 or abs(determinant) / (lengths[0] * lengths[1]) < 1e-6:
        raise ValueError('Fringe repair ellipse is singular or too ill-conditioned')
    return {'id': identity, 'mode': value['mode'], 'points': clean_points,
            'axes': axes, 'opacity': number(value['opacity'], 0.0, 1.0, 'opacity'),
            'feather': number(value['feather'], 0.0, 1.0, 'feather')}


def check(value):
    if type(value) is not dict or set(value) != set(neutral()):
        raise ValueError('Fringe repair requires a complete versioned recipe')
    if type(value['version']) is not int or value['version'] != VERSION or value['algorithm'] != ALGORITHM:
        raise ValueError('Unsupported fringe repair recipe version or algorithm')
    if type(value['enabled']) is not bool:
        raise ValueError('Fringe repair enabled must be boolean')
    coverage = value['coverage']
    if type(coverage) is not dict or set(coverage) != {'domain', 'strokes'} or coverage['domain'] != DOMAIN:
        raise ValueError('Unsupported fringe repair coverage domain')
    strokes = coverage['strokes']
    if type(strokes) is not list or len(strokes) > MAX_STROKES:
        raise ValueError('Fringe repair exceeds the retained stroke budget')
    # Count before copying to bound the accepted recipe, not only each stroke.
    total = 0
    for stroke in strokes:
        if type(stroke) is not dict or type(stroke.get('points')) is not list:
            raise ValueError('Invalid fringe repair stroke')
        total += len(stroke['points'])
        if total > MAX_POINTS:
            raise ValueError('Fringe repair exceeds the total retained point budget')
    clean = [check_stroke(stroke) for stroke in strokes]
    if len({stroke['id'] for stroke in clean}) != len(clean):
        raise ValueError('Fringe repair stroke identities must be unique')
    source = check_source(value['source'])
    if bool(clean) != (source is not None):
        raise ValueError('Fringe repair source is required exactly when manual coverage exists')
    return {'version': VERSION, 'algorithm': ALGORITHM, 'enabled': value['enabled'],
            'strength': number(value['strength'], 0.0, 100.0, 'strength'),
            'source': source, 'coverage': {'domain': DOMAIN, 'strokes': clean}}


def from_state(state):
    if type(state) is not dict:
        raise ValueError('Fringe repair requires an owned document state')
    return check(state[KEY]) if KEY in state else neutral()


def active(value):
    recipe = check(value)
    return recipe['enabled'] and recipe['strength'] != 0.0


def verify_source(recipe, state_or_engine, path=None, original_size=None):
    """Use effective original/derived identity, never the original path alone.

    original_size is (width, height), exactly like creative_derived_source.binding.
    Disabled recipes retain their ownership too; re-enabling must not rebind them.
    """
    recipe = check(recipe)
    if recipe['source'] is None:
        return None
    from .creative_derived_source import binding
    actual = check_source(binding(state_or_engine, path, original_size))
    if recipe['source'] != actual:
        raise ValueError('Fringe repair coverage belongs to another effective image source')
    return actual
