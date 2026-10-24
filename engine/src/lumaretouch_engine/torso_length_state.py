# SPDX-License-Identifier: GPL-3.0-or-later
"""Original upper-body LENGTH intent and source review. AUTHORED / UNRUN.

No width, waist-length, head-length or face-size alias. Manual boxes describe
observed contours and surrounding background, never fabricated anatomy.
"""
from copy import deepcopy
import math

OPERATION_ID = 'lnx.torso_length.v1'
OP = OPERATION_ID
CONTROL_ID = 'LNX-REF-PC-32473-C-f1662d2dec'
IDS = {'amount': CONTROL_ID}
VERSION = 1
LENGTH_GAIN = 0.08
REQUIRED_ANCHORS = tuple(range(25))
SUPPORT_KIND = 'torso-length-visible-upper-body-review-v1'
METHOD = 'user-reviewed-visible-torso-length-support'
COLUMNS = ('outer_left', 'inner_left', 'inner_right', 'outer_right',
           'upper_zero', 'upper_plateau')
BOXES = ('head_box', 'left_arm_box', 'right_arm_box')
FLAGS = ('joints_visible', 'upright_not_foreshortened', 'ownership_confirmed',
         'complete_head_hair_reviewed', 'complete_arms_hands_reviewed',
         'background_transition_reviewed', 'no_occlusion_or_contacts')
FACE_BINDING_KEYS = ('associated_face_ref', 'associated_face_box',
                     'associated_face_evidence_sha256')


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if (type(value) is not dict or set(value) != {'version', 'amount'}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('Invalid upper-body length recipe; only version and amount are portable')
    amount = value['amount']
    # Bounds first also reject huge Python integers without float overflow.
    if type(amount) not in (int, float) or not -1 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Upper-body length amount must be a finite number in [-1,1]')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def adjust(value, key, amount):
    result = check(value)
    if key != 'amount':
        raise ValueError('Unknown upper-body length control; waist length is separate')
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


def check_support(value, record=None):
    from . import body_pose_evidence as E
    from .people_state import check_ref
    keys = {'version', 'method', 'confirmations', *COLUMNS, *BOXES, *FACE_BINDING_KEYS}
    if (type(value) is not dict or set(value) != keys
            or type(value['version']) is not int or value['version'] != VERSION
            or value['method'] != METHOD):
        raise ValueError('Invalid explicit upper-body length source support')
    flags = value['confirmations']
    if (type(flags) is not dict or set(flags) != set(FLAGS)
            or any(flags[k] is not True for k in FLAGS)):
        raise ValueError('Review actual joints, complete head/hair, both arms/hands, contacts and surrounding background')
    if any(not _normalized(value[k]) for k in COLUMNS):
        raise ValueError('Support boundaries must be finite normalized original-source coordinates')
    if not (value['outer_left'] < value['inner_left'] < value['inner_right'] < value['outer_right']
            and value['upper_zero'] < value['upper_plateau']):
        raise ValueError('Reviewed plateau and surrounding zero boundaries must be strictly ordered')
    if any(not _box(value[k]) for k in (*BOXES, 'associated_face_box')):
        raise ValueError('Complete visible head/hair, arm/hand and associated face boxes are required')
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
            raise ValueError('Upper-body length support must leave one source pixel at every image boundary')
    return deepcopy(value)


def policy_check_support(value, record):
    return check_support(value, record)


def support_vector(value):
    value = check_support(value)
    return [value[key] for key in COLUMNS] + [n for key in BOXES for n in value[key]]


def policy():
    from .body_pose_operations import OperationPolicy
    return OperationPolicy(OPERATION_ID, neutral, check, active, REQUIRED_ANCHORS,
                           SUPPORT_KIND, policy_check_support)


def policies():
    return {OPERATION_ID: policy()}
