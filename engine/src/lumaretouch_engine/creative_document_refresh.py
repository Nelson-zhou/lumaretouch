"""Explicit fresh layer document from current full-resolution photo edits.

Replaces no source pixels and owns no extra history. The prior layer document and
its immutable assets remain in the host's recoverable undo frame.
"""
from copy import deepcopy


def fresh_current(host, envelope):
    controller=host.controller
    payload={'fresh_current':True}
    existing=controller._existing(envelope,payload)
    if existing is not None:return existing
    before=controller._check(envelope,'fresh_current')
    if controller.pending is not None:raise ValueError('Creative return is still pending')
    if not controller.ports.history_recoverable():
        raise ValueError('A fresh creative document requires recoverable unified history')
    from .creative_document_host import token, source_uid, memory_budget, rotate
    from .creative_document_base import capture_current_asset
    from . import creative_document_state as S
    engine=host.e;owner=token(engine);source=source_uid(engine)
    frozen=deepcopy(before)
    cancelled=lambda:token(engine)!=owner or source_uid(engine)!=source or engine._creative_document!=frozen
    record=capture_current_asset(engine,engine._docs[engine._doc_index],engine._capture_state(),
                                 host.assets,max_bytes=memory_budget(),cancelled=cancelled)
    controller._check(envelope,'fresh_current')
    if cancelled():raise ValueError('Current photo changed during creative capture')
    after=S.create(source,record['id'],host.assets)
    try:
        host.commit_document(after,before,'creative:fresh_current')
        rotate(engine)
    except Exception as error:
        controller._cache(envelope,payload,controller._receipt(envelope,'unknown',before['revision'],
                          'Fresh document commit requires authoritative reconciliation'))
        raise RuntimeError('Fresh creative document outcome requires reconciliation; do not retry') from error
    return controller._cache(envelope,payload,controller._receipt(envelope,'applied',after['revision']))
