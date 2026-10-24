# SPDX-License-Identifier: GPL-3.0-or-later
"""Original complete-head/hair shrink intent and independent source review.

AUTHORED / UNRUN. Pose33 observes facial points, NOT hair, skull or a head
silhouette. The complete head/hair plateau, surrounding clear transition and
pivot must be explicitly marked on this exact source. No bounds or checkboxes
are inferred from pose, the face box, or another operation's review.
"""
from copy import deepcopy
import math

OPERATION_ID = 'lnx.head_size.v1'
OP = OPERATION_ID
CONTROL_ID = 'LNX-REF-PC-32473-C-dc1b0ba40a'
IDS = {'amount': CONTROL_ID}
VERSION = 1
SHRINK_GAIN = 0.08
REQUIRED_ANCHORS = tuple(range(13))
SUPPORT_KIND = 'head-size-complete-head-hair-review-v1'
METHOD = 'user-reviewed-complete-head-hair-support'
BOXES = ('head_box', 'transition_box')
FLAGS = ('complete_head_hair_reviewed', 'head_bounds_manually_marked',
         'transition_bounds_manually_marked', 'pivot_manually_marked',
         'clear_background_transition_reviewed', 'no_contacts',
         'ownership_confirmed', 'not_occluded', 'upright_not_foreshortened',
         'head_and_shoulders_visible')
FACE_BINDING_KEYS = ('associated_face_ref', 'associated_face_box',
                     'associated_face_evidence_sha256')


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if (type(value) is not dict or set(value) != {'version', 'amount'}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('Invalid head size recipe; only version and amount are portable')
    amount = value['amount']
    # Range first rejects arbitrarily large integers without float overflow.
    if type(amount) not in (int, float) or not 0 <= amount <= 1 or not math.isfinite(amount):
        raise ValueError('Head size amount must be finite in [0,1]; positive means smaller')
    return {'version': VERSION, 'amount': float(amount)}


def active(value):
    return check(value)['amount'] != 0.0


def adjust(value, key, amount):
    result = check(value)
    if key != 'amount':
        raise ValueError('Unknown head size control; face shape and neck controls are separate')
    result['amount'] = amount
    return check(result)


def portable(value):
    return check(value)


def vector(value):
    checked = check(value)
    return [checked['version'], checked['amount']]


def _normalized(value):
    return type(value) in (int, float) and 0 < value < 1 and math.isfinite(value)


def _box(value):
    return (type(value) is list and len(value) == 4
            and all(_normalized(n) for n in value)
            and value[0] < value[2] and value[1] < value[3])


def _inside_box(outer, inner):
    return (outer[0] < inner[0] < inner[2] < outer[2]
            and outer[1] < inner[1] < inner[3] < outer[3])


def check_support(value, record=None):
    from . import body_pose_evidence as E
    from .people_state import check_ref
    keys = {'version', 'method', 'confirmations', *BOXES, 'pivot', *FACE_BINDING_KEYS}
    if (type(value) is not dict or set(value) != keys
            or type(value['version']) is not int or value['version'] != VERSION
            or value['method'] != METHOD):
        raise ValueError('Invalid independent complete-head/hair source review')
    flags = value['confirmations']
    if (type(flags) is not dict or set(flags) != set(FLAGS)
            or any(flags[key] is not True for key in FLAGS)):
        raise ValueError('Explicitly review the entire visible head/hair, manual bounds and pivot, clear background, ownership, posture, occlusion and contacts')
    if any(not _box(value[key]) for key in (*BOXES, 'associated_face_box')):
        raise ValueError('Complete head/hair, outer transition and actual associated face need finite source-normalized boxes')
    pivot = value['pivot']
    if type(pivot) is not list or len(pivot) != 2 or not all(_normalized(n) for n in pivot):
        raise ValueError('Head size needs an explicitly marked finite source-normalized xy pivot')
    head, transition, face = (value[key] for key in (*BOXES, 'associated_face_box'))
    if not _inside_box(transition, head):
        raise ValueError('The clear transition must strictly enclose the complete-head/hair plateau')
    if not _inside_box(head, face):
        raise ValueError('The entire actual associated face must lie strictly inside the complete-head/hair plateau')
    if not (head[0] < pivot[0] < head[2] and head[1] < pivot[1] < head[3]):
        raise ValueError('The independently marked pivot must lie strictly inside the complete-head/hair plateau')
    face_ref = check_ref(value['associated_face_ref'])
    E.digest(value['associated_face_evidence_sha256'])
    if record is not None:
        record = E.check(record)
        if face_ref['asset_sha256'] != record['source']['sha256']:
            raise ValueError('Head support, actual face and BodyRef must name the same canonical source')
        points = record['points']
        w, h = record['source']['width'] - 1, record['source']['height'] - 1
        for index in REQUIRED_ANCHORS:
            point = points[index]
            if not (0 < point['x'] < 1 and 0 < point['y'] < 1
                    and point['visibility'] >= .8 and point['presence'] >= .8):
                raise ValueError('Manual review cannot override hidden or cropped actual head/shoulder observations')
        if any(not (head[0] < points[index]['x'] < head[2]
                       and head[1] < points[index]['y'] < head[3]) for index in range(11)):
            raise ValueError('Every actual observed head point 0 through 10 must lie inside the complete-head/hair plateau')
        if any(points[index]['y'] <= transition[3] for index in (11, 12)):
            raise ValueError('Both actual shoulders must lie below and outside the transition; long hair, contacts or an overlapping shoulder cannot be guessed away')
        if (transition[0] * w < 1 or transition[1] * h < 1
                or transition[2] * w > w - 1 or transition[3] * h > h - 1):
            raise ValueError('The complete transition must leave one original-source pixel at every image boundary; no crop or clipping')
        if (head[2] - head[0]) * w < 32 or (head[3] - head[1]) * h < 32:
            raise ValueError('The independently reviewed complete head/hair is too small to verify')
        if min((head[0] - transition[0]) * w, (transition[2] - head[2]) * w,
               (head[1] - transition[1]) * h, (transition[3] - head[3]) * h) < 16:
            raise ValueError('Every clear transition margin must span at least 16 original-source pixels')
        left, right = points[11], points[12]
        shoulder_width = abs(right['x'] - left['x']) * w
        if (shoulder_width < 32 or abs(right['y'] - left['y']) * h > .25 * shoulder_width
                or abs(right['z'] - left['z']) * w > .35 * shoulder_width):
            raise ValueError('Tilted, tiny or strongly foreshortened actual shoulders do not prove upright head support')
    return deepcopy(value)


def policy_check_support(value, record):
    return check_support(value, record)


def support_vector(value):
    value = check_support(value)
    # ABI 1 geometry only. Face ownership is independently bound metadata and
    # must never be interpreted as a guessed hairline, ear or skull contour.
    return [*value['head_box'], *value['transition_box'], *value['pivot']]


def policy():
    from .body_pose_operations import OperationPolicy
    return OperationPolicy(OPERATION_ID, neutral, check, active, REQUIRED_ANCHORS,
                           SUPPORT_KIND, policy_check_support)


def policies():
    return {OPERATION_ID: policy()}
