# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact crop terminal outcomes at the existing recovery boundary, not a ledger."""
from copy import deepcopy

UNKNOWN_REASON = '人像裁剪原提交尚未确认，请查询原请求或重新打开已确认的工程'


def observe(boundary, event):
    request = boundary['message']
    if request.get('cmd') != 'portrait_crop':
        return False
    if (event.get('event') == 'portrait_crop_result'
            and event.get('request_id') == request.get('request_id')
            and event.get('original_request') == request):
        boundary['portrait_crop_outcome'] = deepcopy(event)
    # Working/unknown is provisional. The serialized finish decides whether the
    # final exact request committed, was rejected without writes, or is unknown.
    return True


def finish(engine, boundary, error):
    request = boundary['message']
    if request.get('cmd') != 'portrait_crop':
        return False
    runtime = engine.__dict__.get('_project_recovery_runtime')
    if runtime is None or not boundary['started']:
        return True
    outcome = boundary.get('portrait_crop_outcome') or {}
    action = request.get('action')
    if action == 'status':
        outcome = outcome.get('receipt') or {}
        original = outcome.get('original_request') or {}
        if (outcome.get('phase') != 'committed' or original.get('action') != 'apply'
                or original.get('request_id') != request.get('target_request_id')
                or runtime.__dict__.get('_portrait_crop_taint') != original.get('request_id')
                or runtime.reason != UNKNOWN_REASON):
            return True
        ident = original['request_id']
    elif action == 'apply':
        ident = request.get('request_id')
    else:
        return True  # Capture, preview, capability and cancellation cannot write.
    result = outcome.get('result') or {}
    if (not error and boundary['returned'] and outcome.get('phase') == 'committed'
            and result.get('status') in ('applied', 'no_change')):
        canonical = engine.__dict__.get('_portrait_crop_commit_receipts', {}).get(ident)
        if (canonical is None or canonical.get('workspace') != engine._document_versions().workspace
                or canonical.get('result') != result):
            return True  # Old project receipts are history, never this project's new revision.
        completed = runtime.__dict__.setdefault('_portrait_crop_completed', set())
        if ident not in completed:
            if result['status'] == 'applied':
                runtime.revision += 1
            completed.add(ident)
        if runtime.__dict__.get('_portrait_crop_taint') == ident and runtime.reason == UNKNOWN_REASON:
            runtime.tainted = False
            runtime.reason = None
            runtime.__dict__.pop('_portrait_crop_taint', None)
        return True
    if action == 'apply':
        if not error and outcome.get('no_write') is True and outcome.get('phase') in ('rejected', 'cancelled'):
            return True
        if not runtime.tainted:
            runtime._portrait_crop_taint = ident
            runtime.tainted = True
            runtime.reason = UNKNOWN_REASON
        elif runtime.__dict__.get('_portrait_crop_taint') == ident and runtime.reason == UNKNOWN_REASON:
            runtime.tainted = True
        # Never overwrite another incomplete transaction's reason or authority.
    return True
