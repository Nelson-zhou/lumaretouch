# SPDX-License-Identifier: GPL-3.0-or-later
"""Known pre-handler refusal only; never reconcile a started batch write.

The serialized server boundary proves whether the real handler was entered.
This helper owns no transaction, terminal cache, retry or history. UNRUN.
"""


def _text(value):
    if type(value) is not str or any(ord(char) < 32 or 0x7f <= ord(char) <= 0x9f for char in value):
        return False
    try:
        return 1 <= len(value.encode('utf-8')) <= 128
    except UnicodeError:
        return False


def rejected(request, error, boundary, emit):
    if (type(request) is not dict or request.get('cmd') != 'batch'
            or type(boundary) is not dict or boundary.get('started') is not False
            or boundary.get('message') is not request):
        return
    identity = request.get('request_id')
    if not _text(identity):
        return
    from .eye_bag_batch_store import read_only, failure_context
    action = request.get('action')
    history = (action in ('undo', 'redo')
        and set(request) == {'cmd', 'action', 'request_id', 'batch_id'}
        and _text(request.get('batch_id')))
    eye_commit = (action == 'commit' and 'eye_bag_review_ack' in request
        and set(request) in ({'cmd', 'action', 'request_id', 'preflight_token', 'eye_bag_review_ack'},
            {'cmd', 'action', 'request_id', 'preflight_token', 'eye_bag_review_ack', 'collarbone_review_ack'}))
    if not (history or eye_commit or read_only(request)):
        return
    context = failure_context(request)
    if not context:
        return
    emit({'event': 'batch_result', 'action': action, 'request_id': identity,
        'success': False, 'outcome_unknown': False, 'error': str(error)[:2000] or 'Batch handler was not started',
        **context})
