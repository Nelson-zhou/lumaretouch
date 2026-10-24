# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned manual clavicle traces; never inferred from shoulder pose.

Image-left/right identify independent drawings, not inferred anatomical sides.
The product category is explicitly confirmed by the reviewer, never classified
from the photograph. These records stay with the existing immutable support
asset and do not travel in presets. AUTHORED / UNRUN.
"""
from copy import deepcopy
import math

FAMILY = 'collarbone'
KIND = 'collarbone_visibility'
MIN_WIDTH = 4.0
MAX_WIDTH = 256.0
_EPS = 1e-12


def _number(value):
    return (type(value) in (int, float) and -1e100 <= value <= 1e100
            and math.isfinite(value))


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _between(a, b, p):
    return (min(a[0], b[0])-_EPS <= p[0] <= max(a[0], b[0])+_EPS
            and min(a[1], b[1])-_EPS <= p[1] <= max(a[1], b[1])+_EPS)


def _intersects(a, b, c, d):
    values = (_cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b))
    if (((values[0] > _EPS and values[1] < -_EPS) or (values[0] < -_EPS and values[1] > _EPS))
            and ((values[2] > _EPS and values[3] < -_EPS) or (values[2] < -_EPS and values[3] > _EPS))):
        return True
    return any(abs(v) <= _EPS and _between(p, q, r) for v, p, q, r in (
        (values[0], a, b, c), (values[1], a, b, d),
        (values[2], c, d, a), (values[3], c, d, b)))


def check(value, *, source=None):
    keys = {'version', 'domain', 'category', 'eligibility_confirmed',
            'visible_anatomy_confirmed', 'curves'}
    if (type(value) is not dict or set(value) != keys
            or type(value['version']) is not int or value['version'] != 1
            or value['domain'] != 'source-normalized'):
        raise ValueError('Clavicle review needs its exact versioned source-normalized schema')
    if (type(value['category']) is not str or value['category'] not in ('female', 'elder_female')
            or value['eligibility_confirmed'] is not True
            or value['visible_anatomy_confirmed'] is not True):
        raise ValueError('Explicit eligible product category and visible clavicle confirmation are required')
    curves = value['curves']
    if type(curves) is not list or not 1 <= len(curves) <= 2:
        raise ValueError('Review one or two independently visible clavicle traces, never invent a missing side')
    ids = set()
    for curve in curves:
        if (type(curve) is not dict or set(curve) != {'id', 'points', 'width'}
                or type(curve['id']) is not str or curve['id'] not in ('left', 'right')
                or curve['id'] in ids):
            raise ValueError('Clavicle traces need unique explicit image-left/image-right identifiers')
        ids.add(curve['id'])
        if not _number(curve['width']) or not 0 < curve['width'] <= 1:
            raise ValueError('Clavicle transverse width must be a positive finite fraction of the source short side')
        points = curve['points']
        if type(points) is not list or not 3 <= len(points) <= 8:
            raise ValueError('Each visible clavicle trace needs 3 to 8 explicit source points')
        for point in points:
            if (type(point) is not list or len(point) != 2
                    or any(not _number(v) or not 0 < v < 1 for v in point)):
                raise ValueError('Clavicle trace points must be finite source-interior edge-normalized coordinates')
        if any(math.hypot(a[0]-b[0], a[1]-b[1]) <= 1e-6
               for i, a in enumerate(points) for b in points[i+1:]):
            raise ValueError('Clavicle trace points cannot coincide or form a degenerate segment')
        for a, b, c in zip(points, points[1:], points[2:]):
            if (abs(_cross(a, b, c)) <= _EPS
                    and (b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1]) <= 0):
                raise ValueError('Clavicle trace cannot reverse over its own segment')
        segments = list(zip(points, points[1:]))
        if any(_intersects(a, b, c, d) for i, (a, b) in enumerate(segments)
               for c, d in segments[i+2:]):
            raise ValueError('Clavicle trace cannot self-intersect')
    if len(curves) == 2 and any(_intersects(a, b, c, d)
            for a, b in zip(curves[0]['points'], curves[0]['points'][1:])
            for c, d in zip(curves[1]['points'], curves[1]['points'][1:])):
        raise ValueError('Independent clavicle traces cannot cross or duplicate each other')
    if source is not None:
        if (type(source) is not dict or any(type(source.get(k)) is not int or source[k] < 2
                                         for k in ('width', 'height'))):
            raise ValueError('Clavicle width needs exact canonical source dimensions')
        for curve in curves:
            width = curve['width']*min(source['width'], source['height'])
            if not MIN_WIDTH <= width <= MAX_WIDTH:
                raise ValueError('Reviewed clavicle width must be 4..256 pixels at the true source extent; no clamp')
            points = [[p[0]*source['width'], p[1]*source['height']] for p in curve['points']]
            lengths = [math.hypot(a[0]-b[0], a[1]-b[1]) for a, b in zip(points, points[1:])]
            if any(length < 2 for length in lengths):
                raise ValueError('Clavicle trace segments must span at least two actual source pixels')
            if sum(lengths) < 2*width:
                raise ValueError('Clavicle trace length must span at least twice its reviewed half-width')
            if any((b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1]) <= 0
                   for a, b, c in zip(points, points[1:], points[2:])):
                raise ValueError('Clavicle trace adjacent tangents must turn less than 90 degrees on the source grid')
            # Smaller real preview grids are independently admitted by Rust.
            # A valid full-source trace can refuse there; never clamp its scale.
    return deepcopy(value)


def require_eligibility(face, clavicle):
    """Explicit grouping labels cannot be contradicted by a fresh checkbox.

    Unknown labels may use this dedicated eligibility attestation. No gender,
    age or anatomy is inferred. Kept out of historical structural validation:
    active retain/resolve check the actual current face, not a later owner.
    """
    check(clavicle)
    labels = face.get('labels', {})
    if type(labels) is not dict:
        raise ValueError('Collarbone applicability needs the current explicit person labels')
    if labels.get('age_band') == '儿童' or labels.get('gender_label') == '男':
        raise ValueError('Collarbone applicability conflicts with current explicit person labels; do not override them with a review')
