# SPDX-License-Identifier: GPL-3.0-or-later
"""Narrow version-2 recovery envelopes and scoped publication handoff.

The client protocol number never owns the dispatcher fence. Only an actual
retained, presented, exact-member review may suppress ordinary photo history.
AUTHORED / UNRUN.
"""
from copy import deepcopy
from hashlib import sha256
import json

from .source_patch_controller import PROOF_KEYS
from .white_balance_controller import identity, error_text
from . import eye_bag_recovery_alias_review as REVIEW

PREVIEW_FIELDS = {'cmd', 'action', 'preview_id', *PROOF_KEYS}
IMAGE_FIELDS = PREVIEW_FIELDS | {'protocol', 'request_id', 'review_sha256', 'member_document_id',
    'member_revision', 'side', 'sha256'}
PRESENTED_FIELDS = PREVIEW_FIELDS | {'protocol', 'ack'}
APPLY_FIELDS = PREVIEW_FIELDS | {'protocol', 'request_id', 'ack'}


def _protocol(request):
    if type(request.get('protocol')) is not int or request['protocol'] != 2:
        raise ValueError('Shared recovery requires its exact version-2 envelope')


def check_preview_request(request):
    """Validate only v2 image/presented syntax; return True, never authority."""
    from .people_state import digest, token
    from .face_style_alias_review import _revision
    _protocol(request)
    action = request.get('action')
    if request.get('cmd') != 'effect_recovery_preview':
        raise ValueError('Invalid shared recovery preview command')
    if action == 'image':
        if (set(request) != IMAGE_FIELDS or identity(request['request_id'], 128) is None
                or request['side'] not in ('before', 'after') or not _revision(request['member_revision'])):
            raise ValueError('Recovery image needs its exact member, revision and request identity')
        token(request['member_document_id']); digest(request['sha256']); digest(request['review_sha256'])
    elif action == 'presented':
        if set(request) != PRESENTED_FIELDS:
            raise ValueError('Recovery presentation requires the complete member ACK')
        REVIEW.check_ack(request['ack'])
    else:
        raise ValueError('Version-2 recovery accepts only image reads or exact presentation')
    return True


def check_apply_request(request):
    _protocol(request)
    if (set(request) != APPLY_FIELDS or request.get('cmd') != 'effect_recovery'
            or request.get('action') != 'apply' or identity(request.get('request_id'), 128) is None):
        raise ValueError('Invalid exact shared recovery apply envelope')
    REVIEW.check_ack(request['ack'])
    return True


def prepared(engine, pending):
    """Read-only dispatcher admission, bound to actual pending review identity."""
    if type(pending) is not dict or 'recovery_alias' not in pending:
        return False
    entry = pending['recovery_alias']; request = pending['request']
    check_apply_request(request)
    owner = engine.__dict__.get('_effect_recovery_preview_owner'); record = getattr(owner, 'record', None)
    transaction = getattr(pending['stage'], 'people_recovery', None)
    if (record is None or record.get('eye_bag_alias_entry') is not entry
            or not record['presented'] or not record['committable'] or record['target'] != REVIEW.TARGET
            or record['id'] != request['preview_id']
            or record['proof'] != {key: request[key] for key in PROOF_KEYS}
            or transaction is None or transaction.get('alias_entry') is not entry
            or pending['result']['protocol'] != 2
            or any(pending['result'].get(key) != request[key] for key in ('request_id', 'preview_id', *PROOF_KEYS, 'ack'))
            or pending['digest'] != sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest()):
        raise ValueError('Shared recovery dispatcher admission lost its exact retained request')
    from .effect_recovery_runtime import stage_key
    if stage_key(engine, pending['value']) != pending['stage'].verified_source_key:
        raise ValueError('Shared recovery prepared source key changed')
    REVIEW.confirm(engine, entry, request['ack'], transaction)
    return True


def apply(engine, pending):
    """Do not enter the ordinary recovery swap/rollback or photo undo path."""
    result = pending['result']; entry = pending['recovery_alias']; transaction = pending['stage'].people_recovery
    try:
        if prepared(engine, pending) is not True:
            raise ValueError('Recovery alias publication lacks exact pending authority')
        from .eye_bag_recovery_alias_transaction import commit
        publication = commit(engine, review=entry['review'], plans=REVIEW._plans(entry),
            targets=deepcopy(entry['targets']), before_assets=entry['before_assets'],
            after_assets=transaction['assets'], request_id=result['request_id'],
            verify_before=lambda: REVIEW.confirm(engine, entry, pending['request']['ack'], transaction))
        if publication is None or publication == (None, None):
            raise ValueError('Shared recovery unexpectedly became a no-op after exact review')
        bid, frame = publication
        entry['claimed'] = True; pending['started'] = True; pending['frame'] = frame
        # Publication identity is retained before later status calls. A failed
        # receipt cannot turn a known scoped batch into a second mutation.
        result.update(batch_id=bid, module_scope=['lnx.people_graph.v1'])
        from .eye_bag_recovery_alias_history import status_summary
        summary = status_summary(entry['batch'].ledger[bid])
        if summary != {'version': 1, 'review_sha256': entry['review']['review_sha256'], 'member_count': len(entry['members'])}:
            raise ValueError('Published recovery ledger differs from its reviewed member set')
        result.update(success=True, no_change=False, no_write=False, eye_bag_recovery_alias_review=summary,
            alias_members=[{'document_id': member['visual']['document_id'],
                'expected_revision': member['visual']['revision'],
                'result_revision': str(int(member['visual']['revision']) + 1)} for member in entry['members']])
    except Exception as error:
        started = pending['started'] or bool(getattr(error, 'side_effects_started', False))
        pending['started'] = started
        if started: entry['claimed'] = True
        rolled_back = bool(getattr(error, 'rolled_back', False))
        result.update(success=False, outcome_unknown=started and not rolled_back,
            requires_reload=bool(getattr(error, 'requires_reload', False)) or (started and not rolled_back),
            no_write=not started, error=error_text(error))
        if rolled_back: result['rolled_back'] = True
        bid = getattr(error, 'batch_id', None)
        if bid is not None:
            result['batch_id'] = bid
            result['module_scope'] = ['lnx.people_graph.v1']
            summary = getattr(error, 'eye_bag_recovery_alias_review', None)
            members = getattr(error, 'alias_members', None)
            expected_summary = {'version': 1, 'review_sha256': entry['review']['review_sha256'],
                'member_count': len(entry['members'])}
            expected_members = [{'document_id': member['visual']['document_id'],
                'expected_revision': member['visual']['revision'],
                'result_revision': str(int(member['visual']['revision']) + 1)} for member in entry['members']]
            if summary == expected_summary and members == expected_members:
                result['eye_bag_recovery_alias_review'] = deepcopy(summary)
                result['alias_members'] = deepcopy(members)


def finish(engine, pending):
    owner = engine.__dict__.get('_effect_recovery_preview_owner')
    entry = pending.get('recovery_alias')
    if entry is None: return
    if owner is not None and (owner.record or {}).get('eye_bag_alias_entry') is entry:
        owner.cancel()
    else:
        REVIEW.discard(engine, entry)
