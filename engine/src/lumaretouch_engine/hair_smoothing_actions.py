# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact current-photo hair smoothing review admission, not a mutation or receipt owner.

AUTHORED / UNRUN. No source path, caller-supplied pixels, borrowed support,
cohort, preset or alias action is admitted here.
"""
import json
from . import people_state as P

FAMILY = 'hair_smoothing'
OP = 'lnx.hair_smoothing.v1'
READS = frozenset(('hair_smoothing_reference', 'hair_smoothing_preview', 'hair_smoothing_crop'))
WRITES = frozenset(('hair_smoothing_confirm', 'hair_smoothing_detach'))
ACTIONS = READS | WRITES
MAX_REVIEW_BYTES = 192 * 1024
MAX_CROP_EDGE = 1024


def check_rect(value, size=None):
    """Integer pixel edges [x, y, width, height], never normalized or resized."""
    if (type(value) is not list or len(value) != 4
            or any(type(n) is not int for n in value)
            or not 0 <= value[0] <= 1_000_000 or not 0 <= value[1] <= 1_000_000
            or not 1 <= value[2] <= MAX_CROP_EDGE or not 1 <= value[3] <= MAX_CROP_EDGE):
        raise ValueError('Hair smoothing inspection requires an exact bounded integer pixel rectangle')
    if size is not None:
        if (type(size) not in (tuple, list) or len(size) != 2
                or any(type(n) is not int or n < 1 for n in size)
                or value[0] + value[2] > size[0] or value[1] + value[3] > size[1]):
            raise ValueError('Hair smoothing inspection rectangle lies outside its actual pixel domain')
    return list(value)


def check_action(action, payload, target):
    if (type(action) is not str or action not in ACTIONS or type(payload) is not dict
            or type(target) is not dict or set(target) != {'scope', 'target_id', 'face_ref'}
            or target['scope'] != 'face'):
        raise ValueError('Hair smoothing fine-wrinkle review requires one exact selected FaceRef')
    ref = P.check_ref(target['face_ref'])
    if target['target_id'] != ref['face_instance_id']:
        raise ValueError('Hair smoothing review target and FaceRef disagree')
    if action in ('hair_smoothing_reference', 'hair_smoothing_detach'):
        if payload != {}:
            raise ValueError('Hair smoothing reference/detach accepts no source override')
    elif action == 'hair_smoothing_preview':
        if set(payload) != {'review', 'amount'}:
            raise ValueError('Hair smoothing preview requires only its independent review and amount')
        from .hair_smoothing_state import check
        from .hair_smoothing_support import check_review
        checked = check({'version': 1, 'amount': payload['amount']})
        if checked['amount'] <= 0:
            raise ValueError('Choose a positive visible-hair directional smoothing amount for comparison')
        check_review(payload['review'])
        if len(json.dumps(payload['review'], separators=(',', ':'), allow_nan=False).encode()) > MAX_REVIEW_BYTES:
            raise ValueError('Hair smoothing review exceeds 192 KiB; simplify explicitly, never silently decimate')
    elif action == 'hair_smoothing_crop':
        id_key = 'reference_id' if payload.get('plane') == 'source' else 'preview_id'
        if (set(payload) != {id_key, 'plane', 'rect'}
                or payload['plane'] not in ('source', 'before', 'after')):
            raise ValueError('Hair smoothing crop needs a source reference or a rendered comparison, never both')
        P.token(payload[id_key]); check_rect(payload['rect'])
    else:
        if (set(payload) != {'preview_id', 'reviewed', 'before_sha256', 'after_sha256',
                            'support_sha256', 'inspection'} or payload['reviewed'] is not True):
            raise ValueError('Confirm all three exact hair smoothing review images and a true-pixel inspection pair')
        P.token(payload['preview_id'])
        for key in ('before_sha256', 'after_sha256', 'support_sha256'):
            P.digest(payload[key])
        inspection = payload['inspection']
        if type(inspection) is not dict or set(inspection) != {'rect', 'before_sha256', 'after_sha256'}:
            raise ValueError('Hair smoothing confirmation needs a matching before/after pixel inspection')
        check_rect(inspection['rect'])
        P.digest(inspection['before_sha256']); P.digest(inspection['after_sha256'])
    return payload


def read_only(raw):
    """Used by the existing people read dispatcher after its normal source guards."""
    if (type(raw) is not dict or set(raw) != {'cmd', 'document_id', 'document_epoch',
            'document_revision', 'state_revision', 'association_revision', 'request_id',
            'target', 'action', 'payload'} or raw.get('cmd') != 'people'
            or type(raw.get('action')) is not str or raw['action'] not in READS):
        return False
    try:
        for key in ('document_id', 'document_epoch', 'request_id'):
            P.token(raw[key])
        for key in ('document_revision', 'state_revision', 'association_revision'):
            P.revision(raw[key])
        check_action(raw['action'], raw['payload'], raw['target'])
        return True
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def neutral_patch(raw):
    """Exact one-leaf local reset shape, usable before/after envelope checking.

    This recognizes request content, not authorization. Existing people fencing
    and require_transition still prove selected-face/document ownership.
    """
    if type(raw) is not dict or raw.get('action') != 'patch':
        return False
    payload = raw.get('payload')
    if type(payload) is not dict or set(payload) != {'patches'}:
        return False
    patches = payload['patches']
    if type(patches) is not list or len(patches) != 1:
        return False
    row = patches[0]
    return (type(row) is dict and set(row) == {'operation_id', 'parameter_path', 'unset', 'value'}
            and row['operation_id'] == OP and row['parameter_path'] == '/amount'
            and row['unset'] is False and type(row['value']) in (int, float) and row['value'] == 0)


def is_hair_smoothing_command(raw):
    """Hair smoothing action or exact neutral patch, never general patch admission."""
    return (type(raw) is dict and ((type(raw.get('action')) is str and raw['action'] in ACTIONS)
                                   or neutral_patch(raw)))
