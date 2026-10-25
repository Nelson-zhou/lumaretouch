# SPDX-License-Identifier: GPL-3.0-or-later
"""Portrait crop lifecycle registration; no renderer or second history owner."""
from copy import deepcopy


def guard_other(engine, name, request):
    owner = engine.__dict__.get('_portrait_crop_service')
    if owner is None:
        return
    owner.maintain()
    if owner.uncertain is None:
        return
    if name in ('hello', 'shutdown'):
        return
    if name == 'portrait_crop' and request.get('action') == 'status':
        return
    if name == 'session' and request.get('action') == 'query':
        return
    if name == 'project' and request.get('action') in ('open', 'create', 'new'):
        return
    if name == 'project_recovery' and request.get('action') in ('list', 'inspect', 'status', 'restore'):
        return
    raise ValueError('Portrait crop write is unresolved; query the exact original request or reopen the authoritative project before editing')


def invalidate_after_reload(engine):
    """Called only by authoritative project loading, never on UI timeout."""
    owner = engine.__dict__.get('_portrait_crop_service')
    if owner is not None:
        owner._drop()
        owner.uncertain = None
    # Preserve old immutable outcomes. Their workspace/document binding prevents
    # treating an earlier project's receipt as authority to change this project.


def dispatch_rejected(engine, request, error, started, emit):
    from .portrait_crop_host import _event
    from .portrait_crop_controller import command_hash, controller
    try:
        sha = command_hash(request)
    except (ValueError, TypeError):
        return
    unknown = bool(started and request.get('action') == 'apply')
    event = _event(request, sha, 'unknown' if unknown else 'rejected',
                   message=str(error)[:2000], **({'outcome_unknown': True}
                   if unknown else {'no_write': True}))
    owner = engine.__dict__.get('_portrait_crop_service')
    if owner is not None:
        old = owner.receipts.get(request['request_id'])
        if old is not None and old.get('original_request') == request:
            emit(deepcopy(old))
            return
    if request.get('action') in ('current', 'preview'):
        controller(engine).retire(request['request_id'], sha)
    emit(event)
