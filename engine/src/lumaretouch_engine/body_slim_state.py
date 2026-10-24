# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent measured whole-person WIDTH intent. AUTHORED / UNRUN.

The complete manually traced silhouette is source-owned evidence, not a pose
convex hull or a face-derived box. Its extrema measure the whole-person width.
No model here claims automatic instance ownership or commercial equivalence.
"""
from copy import deepcopy
import math

OPERATION_ID = 'lnx.body_slim.v1'
OP = OPERATION_ID
CONTROL_ID = 'LNX-REF-PC-32473-C-bc54b9eb3c'
IDS = {'amount': CONTROL_ID}
VERSION = 1
WIDTH_GAIN = .08
REQUIRED_ANCHORS = tuple(range(33))
SUPPORT_KIND = 'body-slim-complete-silhouette-review-v1'
METHOD = 'user-traced-complete-person-silhouette-v1'
FLAGS = ('whole_person_visible', 'upright_not_foreshortened',
         'actual_complete_silhouette_traced', 'ownership_confirmed',
         'only_one_person_in_source', 'no_occlusion_or_contacts',
         'background_collar_and_gaps_reviewed')
FACE_BINDING_KEYS = ('associated_face_ref', 'associated_face_box',
                     'associated_face_evidence_sha256')


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if (type(value) is not dict or set(value) != {'version', 'amount'}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('Whole-body width requires its independent version/amount recipe')
    amount = value['amount']
    if type(amount) not in (int, float) or not -1 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Whole-body width amount must be finite in [-1,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def adjust(value, key, amount):
    if key != 'amount':
        raise ValueError('Unknown whole-body width control')
    return check({**check(value), 'amount': amount})


def portable(value):
    return check(value)


def vector(value):
    return [check(value)['amount']]


def _unit(n):
    return type(n) in (int, float) and 0 < n < 1 and math.isfinite(n)


def _cross(a, b, p):
    return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])


def _on_segment(a, b, p):
    return (abs(_cross(a, b, p)) <= 1e-12
            and min(a[0], b[0])-1e-12 <= p[0] <= max(a[0], b[0])+1e-12
            and min(a[1], b[1])-1e-12 <= p[1] <= max(a[1], b[1])+1e-12)


def inside(outline, p):
    """Strict polygon interior; a boundary point cannot prove complete coverage."""
    result = False
    for i, a in enumerate(outline):
        b = outline[(i+1) % len(outline)]
        if _on_segment(a, b, p):
            return False
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
                result = not result
    return result


def contour(value):
    if (type(value) is not list or not 8 <= len(value) <= 128
            or any(type(p) is not list or len(p) != 2 or not all(_unit(v) for v in p) for p in value)):
        raise ValueError('Trace 8–128 actual complete-person contour vertices, without repeating the first point')
    n = len(value)
    for i, a in enumerate(value):
        b = value[(i+1) % n]
        if math.hypot(b[0]-a[0], b[1]-a[1]) <= 1e-6:
            raise ValueError('Whole-person contour has duplicate/degenerate adjacent vertices')
        previous = value[(i-1) % n]
        if abs(_cross(previous, a, b)) <= 1e-12:
            raise ValueError('Remove redundant or reversing collinear contour vertices')
        for j in range(i+1, n):
            if j == (i+1) % n or i == (j+1) % n:
                continue
            c, d = value[j], value[(j+1) % n]
            crossing = ((_cross(a,b,c)*_cross(a,b,d) < 0)
                        and (_cross(c,d,a)*_cross(c,d,b) < 0))
            if crossing or any((_on_segment(a,b,c), _on_segment(a,b,d),
                                _on_segment(c,d,a), _on_segment(c,d,b))):
                raise ValueError('Complete-person contour must be simple, with no crossing or touching edges')
    area = abs(sum(p[0]*value[(i+1)%n][1]-value[(i+1)%n][0]*p[1]
                   for i,p in enumerate(value)))*.5
    if area <= 1e-5:
        raise ValueError('Complete-person silhouette has no measurable area')
    return deepcopy(value)


def bounds(outline):
    return [min(p[0] for p in outline), min(p[1] for p in outline),
            max(p[0] for p in outline), max(p[1] for p in outline)]


def _box(b):
    return (type(b) is list and len(b) == 4 and all(_unit(n) for n in b)
            and b[0] < b[2] and b[1] < b[3])


def check_support(value, record=None):
    from . import body_pose_evidence as E
    from .people_state import check_ref
    keys = {'version', 'method', 'outline', 'collar_box', 'confirmations', *FACE_BINDING_KEYS}
    if (type(value) is not dict or set(value) != keys or type(value['version']) is not int
            or value['version'] != VERSION or value['method'] != METHOD):
        raise ValueError('Invalid independent complete-person silhouette review')
    flags = value['confirmations']
    if type(flags) is not dict or set(flags) != set(FLAGS) or any(flags[k] is not True for k in FLAGS):
        raise ValueError('Review actual complete silhouette, single-person ownership, contacts, background collar and gaps')
    outline = contour(value['outline'])
    outer, inner, face = value['collar_box'], bounds(outline), value['associated_face_box']
    if not _box(outer) or not _box(face):
        raise ValueError('Whole-body width requires explicit valid collar and current associated-face bounds')
    if not (outer[0] < inner[0] < inner[2] < outer[2]
            and outer[1] < inner[1] < inner[3] < outer[3]):
        raise ValueError('The whole manually measured silhouette needs background clearance on all four sides')
    if any(not inside(outline, [x,y]) for x in (face[0], face[2]) for y in (face[1], face[3])):
        raise ValueError('Complete associated face must lie strictly inside the traced complete-person silhouette')
    # Exact segment checks, not sparse probes of a concave contour boundary.
    face_vertices = [[face[0],face[1]],[face[2],face[1]],
                     [face[2],face[3]],[face[0],face[3]]]
    for i, a in enumerate(outline):
        b = outline[(i+1) % len(outline)]
        for j, c in enumerate(face_vertices):
            d = face_vertices[(j+1) % 4]
            if ((_cross(a,b,c)*_cross(a,b,d) < 0 and _cross(c,d,a)*_cross(c,d,b) < 0)
                    or any((_on_segment(a,b,c), _on_segment(a,b,d),
                            _on_segment(c,d,a), _on_segment(c,d,b)))):
                raise ValueError('Associated face boundary crosses or touches the measured silhouette')
    ref = check_ref(value['associated_face_ref'])
    E.digest(value['associated_face_evidence_sha256'])
    if record is not None:
        record = E.check(record)
        if ref['asset_sha256'] != record['source']['sha256']:
            raise ValueError('Whole-person support and associated face must name the identical source')
        w, h = record['source']['width']-1, record['source']['height']-1
        if (outer[0]*w < 1 or outer[1]*h < 1 or outer[2]*w > w-1 or outer[3]*h > h-1):
            raise ValueError('Whole-person collar must leave a source-pixel border; no clipping')
        if (inner[2]-inner[0])*w < 64 or (inner[3]-inner[1])*h < 128:
            raise ValueError('Measured complete silhouette is too small to verify')
        points = record['points']
        for p in points:
            if (not _unit(p['x']) or not _unit(p['y']) or p['visibility'] < .8 or p['presence'] < .8
                    or not inside(outline, [p['x'], p['y']])):
                raise ValueError('All 33 actual points must be visible, uncropped and inside the traced silhouette')
        levels = [max(points[i]['y'] for i in indices) for indices in
                  (range(11), (11,12), (23,24), (25,26), (27,28,29,30,31,32))]
        if any(a >= b for a,b in zip(levels, levels[1:])):
            raise ValueError('Whole-body width v1 requires a complete upright person, not seated/bent or foreshortened anatomy')
        for a,b in ((11,12), (23,24)):
            dx = abs(points[b]['x']-points[a]['x'])*w
            if (dx < 24 or abs(points[b]['y']-points[a]['y'])*h > .4*dx
                    or abs(points[b]['z']-points[a]['z'])*w > .5*dx):
                raise ValueError('Strong rotation, tilt or foreshortening is unsupported')
    return deepcopy(value)


def policy_check_support(value, record):
    return check_support(value, record)


def support_vector(value):
    value = check_support(value)
    return value['collar_box'] + [n for point in value['outline'] for n in point]


def policy():
    from .body_pose_operations import OperationPolicy
    return OperationPolicy(OPERATION_ID, neutral, check, active, REQUIRED_ANCHORS,
                           SUPPORT_KIND, policy_check_support)


def policies():
    return {OPERATION_ID: policy()}
