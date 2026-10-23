"""Exact sky-review admission on an immutable returned source.

This does not admit presets, batch commands or arbitrary background tools.
Automatic proposals remain draft-only and require the final output review.
Native receipt, transaction, rollback and history owners keep
their existing authority; this guard only proves the exact LIVE review route.
"""
from hashlib import sha256
import json

COMMANDS=frozenset(('sky_replacement','sky_replacement_preview','sky_semantic'))
_PREVIEW={'cmd','action','preview_id','session_id','document_id'}
_APPLY=_PREVIEW|{'request_id'}


def _identity(value):
    if type(value) is not str or not 1<=len(value)<=128:
        raise ValueError('Invalid derived sky request identity')


def require_command(engine,name,request):
    from . import sky_replacement_state as S,creative_derived_sky as C,creative_derived_source as D
    from .sky_replacement_preview import ident,validate_draft
    if name not in COMMANDS or type(request) is not dict or request.get('cmd')!=name:
        raise ValueError('Unknown derived sky command')
    if name=='sky_semantic':
        return require_semantic(engine,request)
    action=request.get('action')
    fields=_APPLY if name=='sky_replacement' else _PREVIEW|({'mutation'} if action=='preview' else set())
    actions=('apply',) if name=='sky_replacement' else ('preview','presented','cancel')
    if action not in actions or set(request)!=fields:
        raise ValueError('Derived sky requires its exact native review envelope')
    ident(request['preview_id']);ident(request['session_id']);_identity(request['document_id'])
    if name=='sky_replacement':
        _identity(request['request_id'])
        # Terminal receipt replay is read-only, even after the native owner
        # consumed this preview or a different document became current.
        owner=engine.__dict__.get('_sky_replacement_owner')
        cached=getattr(owner,'cache',{}).get(request['request_id'])
        if cached is not None:
            digest=sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if cached[0]!=digest:raise ValueError('Sky request identity reused with different content')
            return
    if action=='cancel':return  # Stale exact cancellation must release the owner.
    if D.record(engine) is None:raise ValueError('Derived sky admission requires a returned source')
    C.preview(engine,S.empty())
    source=D.binding(engine)
    # Durable intent is checked even when disabled, but an enabled missing
    # linked asset must not prevent viewing its locator and explicitly disabling
    # it. Only a fully prepared, shown and verified final candidate can commit.
    C.validate(S.check(getattr(engine,'_sky_replacement',None)),source)
    owner=engine.__dict__.get('_sky_replacement_preview_owner')
    if action=='preview':
        mutation=request['mutation']
        if type(mutation) is not dict:raise ValueError('Invalid derived sky mutation')
        viewing=mutation.get('action')=='view'
        if (mutation.get('action') not in ('view','replace')
                or set(mutation)!=({'action','target'} if viewing else {'action','target','draft'})
                or mutation['target'] not in (*S.REGIONS,'recovery')):
            raise ValueError('Derived sky only admits manual retained regions and controls')
        if not viewing:
            if owner is None or not owner.matching(request)['shown']:
                raise ValueError('Present the current sky locator before proposing changes')
            validate_draft(engine,mutation['draft'],source)
        return
    if owner is None:raise ValueError('Derived sky review is no longer available')
    if action=='presented':owner.verify_record(request)
    else:owner.prepare(request)  # Read-only; the native apply owner consumes it.


def require_semantic(engine,request):
    """Admit only the existing native proposal lifecycle, never an edit."""
    from . import creative_derived_source as D,creative_derived_sky as C,sky_replacement_state as S
    from .sky_replacement_preview import ident
    fields={'cmd','action','request_id','document_id','session_id','run_id'}
    extras={'start':{'device'},'cancel':set(),'shown':{'proposal_id','region'},
            'accept':{'proposal_id','regions'}}
    action=request.get('action')
    if action not in extras or set(request)!=fields|extras[action]:
        raise ValueError('Derived automatic sky requires its exact native proposal envelope')
    for key in ('request_id','session_id','run_id'):ident(request[key])
    _identity(request['document_id'])
    if action=='cancel':return
    if D.record(engine) is None:raise ValueError('Automatic sky admission requires its immutable source')
    C.preview(engine,S.empty())
    owner=engine.__dict__.get('_sky_replacement_preview_owner')
    if owner is None or not owner.matching(request)['shown']:
        raise ValueError('Present the current sky locator before automatic selection')
    if action=='start':
        if request['device'] not in ('cpu','cuda') or request['request_id']!=request['run_id']:
            raise ValueError('Automatic sky requires an explicit device and exact run identity')
        C.semantic_input(engine)
    else:
        ident(request['proposal_id'])
        semantic=engine.__dict__.get('_sky_semantic_owner')
        binding={key:request[key] for key in ('document_id','session_id','run_id')}
        if semantic is None or semantic.binding!=binding:
            raise ValueError('Automatic sky proposal source session changed')
        semantic.owner.matching(request['proposal_id'])
