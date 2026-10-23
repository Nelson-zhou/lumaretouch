"""Exact studio-review admission on an immutable returned source.

This is not a background-tool exemption. The existing preview, apply receipt,
history transaction and rollback owners remain authoritative and unchanged.
"""
from hashlib import sha256
import json

COMMANDS=frozenset(('studio_background','studio_background_preview'))
_PREVIEW={'cmd','action','preview_id','session_id','document_id'}
_APPLY=_PREVIEW|{'request_id'}


def _identity(value):
    if type(value) is not str or not 1<=len(value)<=128:
        raise ValueError('Invalid derived studio request identity')


def require_command(engine,name,request):
    from . import studio_background_state as S
    from . import creative_derived_studio as C
    from .studio_background_preview import ident
    if name not in COMMANDS or type(request) is not dict or request.get('cmd')!=name:
        raise ValueError('Unknown derived studio command')
    action=request.get('action')
    fields=_APPLY if name=='studio_background' else _PREVIEW|({'mutation'} if action=='preview' else set())
    actions=('apply',) if name=='studio_background' else ('preview','presented','cancel')
    if action not in actions or set(request)!=fields:
        raise ValueError('Derived studio requires its exact native review envelope')
    ident(request['preview_id']);ident(request['session_id']);_identity(request['document_id'])
    if name=='studio_background':
        _identity(request['request_id'])
        # A terminal receipt is read-only and remains replayable after the
        # accepted gesture consumed its review or the photograph changed.
        owner=engine.__dict__.get('_studio_background_owner')
        cached=getattr(owner,'cache',{}).get(request['request_id'])
        if cached is not None:
            digest=sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if cached[0]!=digest:raise ValueError('Studio request identity reused with different content')
            return
    if action=='cancel':
        return  # Exact non-mutating cancellation must release stale reviews.
    # Readiness and mutation admission prove the actual current source pipeline;
    # neither a matching pathname nor a UI-supplied source label is evidence.
    from .creative_derived_source import record
    if record(engine) is None:raise ValueError('Derived studio admission requires a returned source')
    C.preview(engine,S.empty())
    value=S.check(getattr(engine,'_studio_background',None))
    C.verify(engine,value)  # Dormant retained vectors must still own this source.
    owner=engine.__dict__.get('_studio_background_preview_owner')
    if action=='preview':
        mutation=request['mutation']
        if type(mutation) is not dict:raise ValueError('Invalid derived studio mutation')
        viewing=mutation.get('action')=='view'
        if (mutation.get('action') not in ('view','replace')
                or set(mutation)!=({'action','target'} if viewing else {'action','target','proposal'})
                or mutation['target'] not in S.TARGETS):
            raise ValueError('Derived studio only admits its retained controls and vector targets')
        if not viewing:
            if owner is None:raise ValueError('Present the current studio locator before proposing changes')
            if not owner.matching(request)['shown']:
                raise ValueError('Present the current studio locator before proposing changes')
            value=S.bind_proposal(engine,mutation['proposal'])
        C.preview(engine,value)
        return  # Native preview owner freezes the proposal and starts its job.
    if owner is None:raise ValueError('Derived studio review is no longer available')
    if action=='presented':
        owner.verify_record(request)
    else:
        owner.prepare(request)  # Read-only: native apply consumes it exactly once.
