# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact derived-source action admission; host owns all review/publication fences."""
from . import people_state as P, body_pose_evidence as B, local_mask_recipe as M
from .skin_colour_body_support import family_spec
import json

COLOUR_ACTIONS = frozenset(('skin_body_reference', 'skin_body_preview',
                            'skin_body_confirm', 'skin_body_detach'))
FINISH_ACTIONS = frozenset(('skin_finish_body_reference', 'skin_finish_body_preview',
                           'skin_finish_body_confirm', 'skin_finish_body_detach'))
EVENNESS_ACTIONS = frozenset(('body_skin_evenness_reference', 'body_skin_evenness_preview',
                             'body_skin_evenness_confirm', 'body_skin_evenness_detach'))
FACE_MATCH_ACTIONS = frozenset(('body_face_match_reference', 'body_face_match_preview',
                              'body_face_match_confirm', 'body_face_match_detach'))
ACTIONS = COLOUR_ACTIONS | FINISH_ACTIONS | EVENNESS_ACTIONS | FACE_MATCH_ACTIONS
MAX_REVIEW_BYTES = 192 * 1024  # Preserve the native people-envelope 256 KiB cap.


def action_name(verb, *, family='skin_colour', operation_id=None):
    family_spec(family, operation_id)
    if verb not in ('reference', 'preview', 'confirm', 'detach'):
        raise ValueError('Unknown body-skin review action')
    prefix = {'skin_colour': 'skin_body_', 'skin_finish': 'skin_finish_body_',
              'body_skin_evenness': 'body_skin_evenness_', 'body_face_match': 'body_face_match_'}[family]
    return prefix + verb


def check_action(action, payload, target, *, family='skin_colour', operation_id=None):
    family_spec(family, operation_id)
    allowed = {'skin_colour': COLOUR_ACTIONS, 'skin_finish': FINISH_ACTIONS,
               'body_skin_evenness': EVENNESS_ACTIONS, 'body_face_match': FACE_MATCH_ACTIONS}[family]
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
        fields = {'review', 'amount'} if family in ('body_skin_evenness', 'body_face_match') else {'review'}
        if set(payload) != fields or type(payload['review']) is not dict:
            raise ValueError('Body-skin candidate needs an explicit reviewed source region')
        if family in ('body_skin_evenness', 'body_face_match'):
            if family == 'body_skin_evenness':
                from .body_skin_evenness_state import check
            else:
                from .body_face_match_state import check
            candidate = check({'version': 1, 'amount': payload['amount']})
            if candidate['amount'] == 0:
                raise ValueError('Choose a positive '+family+' amount for the private comparison')
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
