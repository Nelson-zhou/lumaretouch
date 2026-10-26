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
    from .portrait_preset_batch import read_only as portrait_preset_read_only
    from .portrait_preset_delivery import command as delivery_command, identity as delivery_identity
    portrait_commit = (action == 'portrait_preset_commit'
        and set(request) == {'cmd', 'action', 'request_id', 'preflight_token',
                            'portrait_preset_ack', 'accepted'})
    portrait_prepare = (action == 'portrait_preset_prepare' and set(request) ==
        {'cmd', 'action', 'request_id', 'docs', 'preset_id', 'preset_sha256'})
    if portrait_preset_read_only(request) or portrait_commit or portrait_prepare or delivery_command(request):
        identity_fields = {
            'portrait_preset_prepare': ('preset_id', 'preset_sha256', 'docs'),
            'portrait_preset_preflight': ('preset_id', 'preset_sha256', 'docs'),
            'portrait_preset_image': ('preflight_token', 'document_id', 'side', 'page'),
            'portrait_preset_commit': ('preflight_token', 'portrait_preset_ack', 'accepted'),
        }.get(action, ())
        emit({'event': 'batch_result', 'action': action, 'request_id': identity,
            'success': False, 'outcome_unknown': False, 'no_write': True,
            'portrait_preset': True,
            **(delivery_identity(request) if delivery_command(request) else {}),
            **({'preparation': True, 'portrait_preset_docs': request.get('docs'),
                'preparation_results': [], 'editor_restored': True} if portrait_prepare else {}),
            **{key: request.get(key) for key in identity_fields},
            'error': str(error)[:2000] or 'Portrait preset group handler was not started'})
        return
    history = (action in ('undo', 'redo')
        and set(request) == {'cmd', 'action', 'request_id', 'batch_id'}
        and _text(request.get('batch_id')))
    eye_commit = (action == 'commit' and 'eye_bag_review_ack' in request
        and set(request) in ({'cmd', 'action', 'request_id', 'preflight_token', 'eye_bag_review_ack'},
            {'cmd', 'action', 'request_id', 'preflight_token', 'eye_bag_review_ack', 'collarbone_review_ack'}))
    from .eye_bag_cohort_store import read_only as cohort_read_only, failure_context as cohort_failure_context
    cohort_fields = {'cmd', 'action', 'request_id', 'preflight_token', 'module_scope', 'eye_bag_cohort_ack'}
    cohort_commit = (action == 'commit' and set(request) in (cohort_fields,
        cohort_fields | {'portrait_cohort_ack'}, cohort_fields | {'collarbone_review_ack'},
        cohort_fields | {'portrait_cohort_ack', 'collarbone_review_ack'}))
    from .face_decoration_batch_store import read_only as decoration_read_only,failure_context as decoration_failure_context
    decoration_read=decoration_read_only(request)
    decoration_commit=(action=='commit' and 'face_decoration_review_ack' in request
        and not set(request)-{'cmd','action','request_id','preflight_token','face_decoration_review_ack','eye_bag_review_ack','collarbone_review_ack'})
    from .face_decoration_cohort_store import read_only as decoration_cohort_read_only,failure_context as decoration_cohort_failure
    decoration_cohort_read=decoration_cohort_read_only(request)
    decoration_cohort_commit=(action=='commit' and 'face_decoration_cohort_ack' in request
        and not set(request)-{'cmd','action','request_id','preflight_token','module_scope','face_decoration_cohort_ack','eye_bag_cohort_ack','portrait_cohort_ack','collarbone_review_ack'})
    cohort_read = cohort_read_only(request)
    if not (history or eye_commit or read_only(request) or cohort_commit or cohort_read or decoration_read or decoration_commit or decoration_cohort_read or decoration_cohort_commit):
        return
    context = cohort_failure_context(request) if cohort_commit or cohort_read else failure_context(request)
    if decoration_read or decoration_commit:context.update(decoration_failure_context(request))
    if decoration_cohort_read or decoration_cohort_commit:context.update(decoration_cohort_failure(request))
    if history:
        # The serialized boundary retains its real engine, never a user-supplied
        # owner. Read an existing ledger only; this cannot create a controller.
        engine = boundary.get('engine')
        owner = None if engine is None else engine.__dict__.get('_batch_sync')
        if owner is not None:
            from .face_decoration_support_alias_transaction import failure_context as support_failure_context
            support = support_failure_context(owner, request)
            if support: context.update(support, no_write=True, restored=[])
            from .face_decoration_preset_alias_transaction import failure_context as dp_failure_context
            mixed = dp_failure_context(owner, request)
            if mixed: context.update(mixed, no_write=True, restored=[])
    if not context:
        return
    emit({'event': 'batch_result', 'action': action, 'request_id': identity,
        'success': False, 'outcome_unknown': False, 'error': str(error)[:2000] or 'Batch handler was not started',
        **context})
