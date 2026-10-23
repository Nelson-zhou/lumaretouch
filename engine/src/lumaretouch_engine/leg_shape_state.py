# SPDX-License-Identifier: GPL-3.0-or-later
"""PC32473 portable thigh/calf intent. Numeric limits are local policy only.

Overall is a simultaneous SET of these two values, not an extra deformation.
No left/right unlock is inferred from the separate shoulder controls.
"""
from copy import deepcopy
import math
OPERATION_ID = 'lnx.leg_shape.v1'
KEYS = ('thigh', 'calf')
IDS = {'overall':'LNX-REF-PC-32473-C-6519e4b67b',
       'thigh':'LNX-REF-PC-32473-C-2cebb24a12',
       'calf':'LNX-REF-PC-32473-C-c63c7afe15'}
REQUIRED_ANCHORS = (23, 24, 25, 26, 27, 28)
SUPPORT_KIND = 'leg-visible-contour-review-v1'
SEGMENTS = ('left_thigh', 'right_thigh', 'left_calf', 'right_calf')
JOINTS = ((23, 25), (24, 26), (25, 27), (26, 28))
STATIONS = (.25, .5, .75)


def neutral():
    return {'version':1, 'thigh':0., 'calf':0.}


def check(value):
    if type(value) is not dict or set(value) != {'version', *KEYS} or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Invalid leg recipe; overall is an editing operation, not a stored amount')
    for key in KEYS:
        n = value[key]
        if type(n) not in (int, float) or not math.isfinite(n) or not -1 <= n <= 1:
            raise ValueError('Leg amount is outside the local implementation range')
    return deepcopy(value)


def adjust(value, key, amount):
    out = check(value)
    if key not in (*KEYS, 'overall'):
        raise ValueError('Unknown leg control')
    for target in KEYS if key == 'overall' else (key,):
        out[target] = amount
    return check(out)


def active(value):
    value = check(value)
    return any(value[key] != 0 for key in KEYS)


def vector(value):
    value = check(value)
    return [value[key] for key in KEYS]


def portable(value):
    return check(value)


def check_support(value):
    """Explicit source-pixel inspection, never widths inferred from bone centres.

    Widths and radius are fractions of min(original width-1,height-1). Each
    transverse width is reviewed at t=.25,.5,.75 along the actual joint axis.
    No filled-in default is valid. Garment outline is visible material, not anatomy.
    Source, BodyRef, full 33-point digest and analysis revision live in the shared
    immutable support envelope and must additionally be checked at preparation.
    """
    confirmations = ('joints_visible', 'separate_legs', 'not_foreshortened',
                     'ownership_confirmed', 'background_support_reviewed')
    required = {'version', 'method', 'stations', 'segments', *confirmations}
    if type(value) is not dict or set(value) != required or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Invalid source-owned leg contour support')
    if value['method'] != 'user-reviewed-visible-silhouette' or value['stations'] != list(STATIONS):
        raise ValueError('Leg support must come from explicit visible source silhouette review')
    if any(value[key] is not True for key in confirmations):
        raise ValueError('Review visibility, separate legs, foreshortening, ownership and neighbouring background')
    if type(value['segments']) is not dict or set(value['segments']) != set(SEGMENTS):
        raise ValueError('Review all four visible leg segments; do not invent hidden contours')
    for key in SEGMENTS:
        item = value['segments'][key]
        if type(item) is not dict or set(item) != {'negative', 'positive', 'support_radius'}:
            raise ValueError('Leg segment support needs both reviewed contour sides and a falloff radius')
        for side in ('negative', 'positive'):
            if type(item[side]) is not list or len(item[side]) != 3:
                raise ValueError('Each visible contour needs three reviewed transverse widths')
            for n in item[side]:
                if type(n) not in (int, float) or not math.isfinite(n) or not 0 < n < 1:
                    raise ValueError('Contour widths must be finite source-normalized measurements')
        radius = item['support_radius']
        if type(radius) not in (int, float) or not math.isfinite(radius) or not 0 < radius < 1:
            raise ValueError('A reviewed finite falloff radius is required')
        width = max(*item['negative'], *item['positive'])
        if not 1.4 * width <= radius <= 2.5 * width:
            raise ValueError('Falloff radius must be 1.4–2.5 times the widest reviewed contour, a local safety policy')
    return deepcopy(value)


def support_vector(value):
    value = check_support(value)
    return [n for key in SEGMENTS for n in
            (*value['segments'][key]['negative'], *value['segments'][key]['positive'], value['segments'][key]['support_radius'])]


def policy_check_support(value, record):
    from . import body_pose_evidence as E
    record = E.check(record); value = check_support(value)
    for index in REQUIRED_ANCHORS:
        p = record['points'][index]
        if p['visibility'] < .8 or p['presence'] < .8 or not 0 < p['x'] < 1 or not 0 < p['y'] < 1:
            raise ValueError('Leg contour review cannot override a hidden or unreliable hip, knee or ankle')
    # Validate actual source-frame cross sections before storing the review.
    w, h = record['source']['width']-1, record['source']['height']-1
    scale = min(w,h)
    for key, (a,b) in zip(SEGMENTS, JOINTS):
        pa, pb = record['points'][a], record['points'][b]
        ax, ay = pa['x']*w, pa['y']*h
        dx, dy = (pb['x']-pa['x'])*w, (pb['y']-pa['y'])*h
        length = math.hypot(dx,dy)
        if length < 32 or length < scale*.05:
            raise ValueError('Visible leg segment is too small to review')
        if abs(pa['z']-pb['z'])*w > length*.7:
            raise ValueError('Leg segment is strongly foreshortened or depth-ambiguous')
        nx, ny = -dy/length, dx/length
        segment = value['segments'][key]; radius = segment['support_radius']*scale
        if radius > length*.5:
            raise ValueError('Visible leg falloff support exceeds the local segment budget')
        for side in ('negative','positive'):
            for t,width in zip(STATIONS,segment[side]):
                distance = width*scale
                if not 2 <= distance <= length*.4:
                    raise ValueError('Visible contour station width is outside the local review budget')
                sign = -1 if side == 'negative' else 1
                x,y = ax+t*dx+sign*distance*nx, ay+t*dy+sign*distance*ny
                if not 1 <= x <= w-1 or not 1 <= y <= h-1:
                    raise ValueError('Reviewed visible contour is cropped')
        for t in (0.,1.):
            for sign in (-1,1):
                x,y = ax+t*dx+sign*radius*nx, ay+t*dy+sign*radius*ny
                if not 1 <= x <= w-1 or not 1 <= y <= h-1:
                    raise ValueError('Reviewed falloff support is cropped')
    return value


def policy():
    from .body_pose_operations import OperationPolicy
    return OperationPolicy(OPERATION_ID, neutral, check, active, REQUIRED_ANCHORS,
                           SUPPORT_KIND, policy_check_support)


def policies():
    return {OPERATION_ID:policy()}
