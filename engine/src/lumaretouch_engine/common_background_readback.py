"""Read-only authoritative lookup, never a replay of an uncertain mutation."""
from copy import deepcopy
from hashlib import sha256
import json
from .studio_background_preview import ident

FIELDS={'cmd','action','request_id','preview_id','session_id','document_id','readback_id'}


def original_request(p):
    if type(p) is not dict or set(p)!=FIELDS or p['cmd']!='common_background_readback' or p['action']!='query':
        raise ValueError('Invalid common readback envelope')
    for key in ('preview_id','session_id','readback_id'):ident(p[key])
    for key in ('request_id','document_id'):
        if type(p[key]) is not str or not 1<=len(p[key])<=128:raise ValueError('Invalid common readback identity')
    return {'cmd':'common_background','action':'apply',
        **{key:p[key] for key in ('request_id','preview_id','session_id','document_id')}}


def handle(engine,p,emit):
    result={'event':'common_background_readback','protocol':1,'action':'query',
        **{key:p.get(key) for key in ('request_id','preview_id','session_id','document_id','readback_id')},
        'phase':'missing','result':None}
    try:
        original=original_request(p)
        # Do not create a controller, prepare a preview, access pixels, or fence
        # history here. A broken pipeline must not prevent reading a receipt.
        owner=engine.__dict__.get('_common_background_owner')
        entry=getattr(owner,'cache',{}).get(original['request_id'])
        if entry is not None:
            digest=sha256(json.dumps(original,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if entry[0]!=digest:raise ValueError('Original common request identity differs from retained receipt')
            receipt=entry[1]
            if any(receipt.get(key)!=original[key] for key in ('request_id','preview_id','session_id','document_id')):
                raise ValueError('Common cached receipt binding is invalid')
            result.update(phase='found',result=deepcopy(receipt))
        else:
            result['error']='Original receipt is absent or evicted; this does not prove the edit was not applied'
    except Exception as error:
        result.update(phase='failed',error=str(error)[:2000])
    emit(result)
