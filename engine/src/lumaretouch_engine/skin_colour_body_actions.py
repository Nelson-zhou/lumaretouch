# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact derived-source action admission; host owns all review/publication fences."""
from . import people_state as P, body_pose_evidence as B, local_mask_recipe as M
from .skin_colour_body_support import family_spec
import json

COLOUR_ACTIONS = frozenset(('skin_body_reference', 'skin_body_preview',
                            'skin_body_confirm', 'skin_body_detach'))
FINISH_ACTIONS = frozenset(('skin_finish_body_reference', 'skin_finish_body_preview',
                           'skin_finish_body_confirm', 'skin_finish_body_detach'))
ACTIONS = COLOUR_ACTIONS | FINISH_ACTIONS
MAX_REVIEW_BYTES = 192 * 1024  # Preserve the native people-envelope 256 KiB cap.


def action_name(verb, *, family='skin_colour', operation_id=None):
    family_spec(family, operation_id)
    if verb not in ('reference', 'preview', 'confirm', 'detach'):
        raise ValueError('Unknown body-skin review action')
    prefix = 'skin_body_' if family == 'skin_colour' else 'skin_finish_body_'
    return prefix + verb


def check_action(action, payload, target, *, family='skin_colour', operation_id=None):
    family_spec(family, operation_id)
    allowed = COLOUR_ACTIONS if family == 'skin_colour' else FINISH_ACTIONS
    if (type(action) is not str or action not in allowed or type(target) is not dict
            or target.get('scope') != 'face' or type(payload) is not dict):
        raise ValueError('Body-skin review needs an exact local FaceRef and known action')
    P.check_ref(target['face_ref'])
    if action in (action_name('reference', family=family), action_name('detach', family=family)):
        if payload != {}:
            raise ValueError('Body-skin reference/detach accepts no source override')
    elif action == action_name('confirm', family=family):
        if set(payload) != {'preview_id', 'reviewed'} or payload['reviewed'] is not True:
            raise ValueError('Confirm the exact displayed body-skin candidate')
        P.token(payload['preview_id'])
    else:
        if set(payload) != {'review'} or type(payload['review']) is not dict:
            raise ValueError('Body-skin candidate needs an explicit reviewed source region')
        review = payload['review']
        if set(review) != {'body_ref', 'points_sha256', 'recipe', 'visible',
                           'unoccluded', 'ownership_confirmed'}:
            raise ValueError('Unknown body-skin review fields')
        B.ref(review['body_ref']); P.digest(review['points_sha256'])
        M.check_stack(review['recipe'])
        if any(review[key] is not True for key in ('visible', 'unoccluded', 'ownership_confirmed')):
            raise ValueError('Explicit visible, unoccluded, correct-person ownership is required')
        if len(json.dumps(review, separators=(',', ':'), allow_nan=False).encode()) > MAX_REVIEW_BYTES:
            raise ValueError('Body-skin review exceeds 192 KiB; simplify the drawing explicitly, never silently decimate it')
