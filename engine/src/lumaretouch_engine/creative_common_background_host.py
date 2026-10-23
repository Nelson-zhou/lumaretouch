"""Exact reviewed common-key admission, never legacy/neural guard bypass."""
from hashlib import sha256
import json
from .common_background_review import FIELDS,ident,mutation

COMMANDS=('common_background','common_background_preview')


def require_command(engine,name,p):
    if name not in COMMANDS or type(p) is not dict or p.get('cmd')!=name:raise ValueError('Invalid common command')
    action=p.get('action');apply=name=='common_background'
    fields=FIELDS|({'request_id'} if apply else ({'mutation'} if action=='preview' else set()))
    if set(p)!=fields or action not in (('apply',) if apply else ('preview','presented','cancel')):raise ValueError('Common source requires exact reviewed transport')
    ident(p['preview_id']);ident(p['session_id'])
    if type(p['document_id']) is not str or not 1<=len(p['document_id'])<=128:raise ValueError('Invalid common document')
    if apply:
        rid=p['request_id']
        if type(rid) is not str or not 1<=len(rid)<=128:raise ValueError('Invalid common request')
        owner=engine.__dict__.get('_common_background_owner');cached=getattr(owner,'cache',{}).get(rid)
        if cached is not None:
            digest=sha256(json.dumps(p,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if cached[0]!=digest:raise ValueError('Common request ID reused')
            return
    if action=='cancel':return
    from .creative_derived_common_background import preview_pixels,validate_state
    preview_pixels(engine);validate_state(engine)
    if action=='preview':mutation(p['mutation']);return
    owner=engine.__dict__.get('_common_background_preview_owner')
    if owner is None:raise ValueError('Common review has expired')
    if action=='presented':owner.matching(p)
    else:owner.prepare(p)


def rejected(engine,p,error,emit):
    base={'protocol':1,**{k:p.get(k) for k in ('preview_id','session_id','document_id')},'success':False,'error':str(error)[:2000]}
    if p.get('cmd')=='common_background_preview':emit({'event':'common_background_preview','state':'failed',**base})
    else:emit({'event':'common_background_result','action':'apply','request_id':p.get('request_id'),
        'outcome_unknown':False,'requires_reload':False,'no_change':False,'history':None,**base})


def invalidate_other(engine,name,p):
    if name in COMMANDS or name=='hello' or (name=='inspection_snapshot' and p.get('action','status')=='status'):return
    if name in ('sample_library_cancel','semantic_colour_cancel') and set(p)=={'cmd','request_id'}:return
    owner=engine.__dict__.get('_common_background_preview_owner')
    if owner is not None:owner.cancel()
