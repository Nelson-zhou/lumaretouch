# SPDX-License-Identifier: GPL-3.0-or-later
"""Original manually assisted WAIST LENGTH intent. AUTHORED / UNRUN.

Pose33 contains shoulders and hips, but NO waist endpoints. Both visible upper
and lower waist pairs must be marked independently on the exact source, never
inferred from hips, percentages, boxes or a different operation's support.
This is neither a torso-length alias nor an anatomical/3D model measurement.
"""
from copy import deepcopy
import math

OPERATION_ID = 'lnx.waist_length.v1'
OP = OPERATION_ID
CONTROL_ID = 'LNX-REF-PC-32473-C-5d33f285bb'
IDS = {'amount': CONTROL_ID}
VERSION = 1
LENGTH_GAIN = 0.08
REQUIRED_ANCHORS = tuple(range(25))
SUPPORT_KIND = 'waist-length-visible-endpoints-review-v1'
METHOD = 'user-reviewed-visible-waist-length-support'
COLUMNS = ('outer_left', 'inner_left', 'inner_right', 'outer_right',
           'upper_zero', 'upper_plateau')
BOXES = ('head_box', 'left_arm_box', 'right_arm_box')
WAIST_MARKERS = ('waist_upper_left', 'waist_upper_right',
                'waist_lower_left', 'waist_lower_right')
FLAGS = ('joints_visible', 'upright_not_foreshortened', 'ownership_confirmed',
         'complete_head_hair_reviewed', 'complete_arms_hands_reviewed',
         'background_transition_reviewed', 'no_occlusion_or_contacts',
         'bilateral_waist_endpoints_visible', 'waist_endpoints_manually_marked',
         'complete_upper_trunk_reviewed')
FACE_BINDING_KEYS = ('associated_face_ref', 'associated_face_box',
                     'associated_face_evidence_sha256')


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if (type(value) is not dict or set(value) != {'version', 'amount'}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('Invalid waist length recipe; only version and amount are portable')
    amount = value['amount']
    # Bounds first also reject huge Python integers without float overflow.
    if type(amount) not in (int, float) or not -1 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Waist length amount must be a finite number in [-1,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def adjust(value, key, amount):
    result = check(value)
    if key != 'amount':
        raise ValueError('Unknown waist length control; torso length and waist width are separate')
    result['amount'] = amount
    return check(result)


def portable(value):
    return check(value)


def vector(value):
    return [check(value)['amount']]


def _normalized(value):
    return type(value) in (int, float) and 0 < value < 1 and math.isfinite(value)


def _box(value):
    return (type(value) is list and len(value) == 4
            and all(_normalized(n) for n in value)
            and value[0] < value[2] and value[1] < value[3])


def _point(value):
    return type(value) is list and len(value) == 2 and all(_normalized(n) for n in value)


def check_support(value, record=None):
    from . import body_pose_evidence as E
    from .people_state import check_ref
    keys = {'version', 'method', 'confirmations', *COLUMNS, *BOXES,
            *WAIST_MARKERS, *FACE_BINDING_KEYS}
    if (type(value) is not dict or set(value) != keys
            or type(value['version']) is not int or value['version'] != VERSION
            or value['method'] != METHOD):
        raise ValueError('Invalid explicit waist length source support')
    flags = value['confirmations']
    if (type(flags) is not dict or set(flags) != set(FLAGS)
            or any(flags[k] is not True for k in FLAGS)):
        raise ValueError('Review actual visible manually marked waist endpoints, complete upper trunk/head/arms, contacts and background; Pose33 does not observe the waist')
    if any(not _normalized(value[k]) for k in COLUMNS):
        raise ValueError('Support boundaries must be finite normalized original-source coordinates')
    if not (value['outer_left'] < value['inner_left'] < value['inner_right'] < value['outer_right']
            and value['upper_zero'] < value['upper_plateau']):
        raise ValueError('Reviewed plateau and surrounding zero boundaries must be strictly ordered')
    if any(not _box(value[k]) for k in (*BOXES, 'associated_face_box')):
        raise ValueError('Complete visible head/hair, arm/hand and associated face boxes are required')
    if any(not _point(value[k]) for k in WAIST_MARKERS):
        raise ValueError('Four explicitly marked source-normalized waist xy endpoints are required; no inferred defaults')
    ul, ur, ll, lr = (value[key] for key in WAIST_MARKERS)
    upper, lower = max(ul[1], ur[1]), min(ll[1], lr[1])
    if not (value['inner_left'] < ul[0] < ur[0] < value['inner_right']
            and value['inner_left'] < ll[0] < lr[0] < value['inner_right']
            and value['upper_plateau'] < min(ul[1], ur[1])
            and upper < lower):
        raise ValueError('Waist markers must use source-left/source-right order inside the plateau, with distinct upper/lower pairs')
    for key in BOXES:
        box = value[key]
        if not (value['inner_left'] < box[0] < box[2] < value['inner_right']
                and value['upper_plateau'] < box[1]):
            raise ValueError('Complete head/hair and arms/hands must lie inside the reviewed horizontal plateau')
    head, face = value['head_box'], value['associated_face_box']
    if not (head[0] < face[0] < face[2] < head[2] and head[1] < face[1] < face[3] < head[3]):
        raise ValueError('The complete associated face must lie inside the reviewed rigid head/hair plateau')
    face_ref = check_ref(value['associated_face_ref'])
    E.digest(value['associated_face_evidence_sha256'])
    if record is not None:
        record = E.check(record)
        if face_ref['asset_sha256'] != record['source']['sha256']:
            raise ValueError('Associated face and upper-body support must name the same source')
        p = record['points']
        w, h = record['source']['width'] - 1, record['source']['height'] - 1
        for i in REQUIRED_ANCHORS:
            q = p[i]
            if not (0 < q['x'] < 1 and 0 < q['y'] < 1
                    and q['visibility'] >= .8 and q['presence'] >= .8):
                raise ValueError('Hidden/cropped actual head, arm, shoulder or hip evidence cannot be overridden by review')
            if not (value['inner_left'] < q['x'] < value['inner_right']
                    and value['upper_plateau'] < q['y'] <= 1 - 1 / h):
                raise ValueError('Observed upper-body points leave the reviewed source plateau or image clearance')
        shoulder = max(p[11]['y'], p[12]['y'])
        hip = min(p[23]['y'], p[24]['y'])
        if not value['upper_plateau'] < head[1] < head[3] < shoulder < hip:
            raise ValueError('Complete head/hair must lie above actual shoulders; upright shoulders must lie above hips')
        if not shoulder < min(ul[1], ur[1]) or not max(ll[1], lr[1]) < hip:
            raise ValueError('Actual marked upper waist must be below both shoulders and lower waist above both hips; hips cannot supply waist endpoints')
        if (lower - upper) * h < 64:
            raise ValueError('Actual common upper-to-lower waist span must be at least 64 source pixels')
        middle_x = ((p[11]['x'] + p[12]['x']) * .5,
                    (p[23]['x'] + p[24]['x']) * .5)
        for left, right in ((ul, ur), (ll, lr)):
            dx = (right[0] - left[0]) * w
            if (dx < 32 or abs(right[1] - left[1]) * h > .25 * dx
                    or not left[0] < min(middle_x) <= max(middle_x) < right[0]):
                raise ValueError('Tilted, tiny or displaced waist pair cannot prove current body ownership')
        for top, bottom in ((ul, ll), (ur, lr)):
            dy = (bottom[1] - top[1]) * h
            if dy < 64 or abs(bottom[0] - top[0]) * w > .35 * dy:
                raise ValueError('Bent or displaced manually marked waist side is unsupported')
        if any(not (1 <= mark[0] * w <= w - 1 and 1 <= mark[1] * h <= h - 1)
               for mark in (ul, ur, ll, lr)):
            raise ValueError('Actual waist markers must leave one source pixel at image boundaries')
        if (hip - shoulder) * h < 64:
            raise ValueError('Upper-body shoulder-to-hip height is too small to verify')
        for a, b in ((11, 23), (12, 24)):
            dy = (p[b]['y'] - p[a]['y']) * h
            if (dy < 64 or abs(p[b]['x'] - p[a]['x']) * w > .35 * dy
                    or abs(p[b]['z'] - p[a]['z']) * w > .35 * dy):
                raise ValueError('Bent or strongly foreshortened upper body is unsupported')
        for a, b in ((11, 12), (23, 24)):
            dx = abs(p[b]['x'] - p[a]['x']) * w
            if (dx < 32 or abs(p[b]['y'] - p[a]['y']) * h > .25 * dx
                    or abs(p[b]['z'] - p[a]['z']) * w > .35 * dx):
                raise ValueError('Tilted, tiny or strongly foreshortened shoulder/hip pair is unsupported')
        groups = (tuple(range(11)), (11, 13, 15, 17, 19, 21), (12, 14, 16, 18, 20, 22))
        for key, indices in zip(BOXES, groups):
            box = value[key]
            if box[3] * h > h - 1:
                raise ValueError('Complete visible contour touches the source edge; no clipping is allowed')
            if any(not (box[0] < p[i]['x'] < box[2] and box[1] < p[i]['y'] < box[3]) for i in indices):
                raise ValueError('Reviewed contour does not contain its actual observed head/arm/hand points')
        if (value['outer_left'] * w < 1 or value['outer_right'] * w > w - 1
                or value['upper_zero'] * h < 1 or hip * h > h - 1):
            raise ValueError('Waist length support must leave one source pixel at every image boundary')
    return deepcopy(value)


def policy_check_support(value, record):
    return check_support(value, record)


def support_vector(value):
    value = check_support(value)
    # ABI v1: six transition columns, three contour boxes, four actual source
    # waist endpoint pairs. Screen/source left and right, NOT inferred anatomy.
    return ([value[key] for key in COLUMNS]
            + [n for key in BOXES for n in value[key]]
            + [n for key in WAIST_MARKERS for n in value[key]])


def policy():
    from .body_pose_operations import OperationPolicy
    return OperationPolicy(OPERATION_ID, neutral, check, active, REQUIRED_ANCHORS,
                           SUPPORT_KIND, policy_check_support)


def policies():
    return {OPERATION_ID: policy()}
