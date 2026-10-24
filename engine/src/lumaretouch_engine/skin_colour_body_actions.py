# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact derived-source action admission; host owns all review/publication fences."""
from . import people_state as P, body_pose_evidence as B, local_mask_recipe as M
import json

ACTIONS = frozenset(('skin_body_reference', 'skin_body_preview',
                     'skin_body_confirm', 'skin_body_detach'))
MAX_REVIEW_BYTES = 192 * 1024  # Preserve the native people-envelope 256 KiB cap.


def check_action(action, payload, target):
    if action not in ACTIONS or target['scope'] != 'face' or type(payload) is not dict:
        raise ValueError('Body-skin review needs an exact local FaceRef and known action')
    P.check_ref(target['face_ref'])
    if action in ('skin_body_reference', 'skin_body_detach'):
        if payload != {}:
            raise ValueError('Body-skin reference/detach accepts no source override')
    elif action == 'skin_body_confirm':
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
