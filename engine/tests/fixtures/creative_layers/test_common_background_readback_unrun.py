"""AUTHORED / UNRUN: receipt readback is never a mutation retry."""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
import pytest
from lumaretouch_engine import common_background_readback as R


def request():
    return {'cmd':'common_background_readback','action':'query','request_id':'original-1',
        'preview_id':'1'*32,'session_id':'2'*32,'document_id':'old-load','readback_id':'3'*32}


def engine(success=True,unknown=False):
    p=request();original=R.original_request(p)
    digest=sha256(json.dumps(original,sort_keys=True,allow_nan=False).encode()).hexdigest()
    receipt={'event':'common_background_result','protocol':1,'action':'apply',
        **{key:p[key] for key in ('request_id','preview_id','session_id','document_id')},
        'success':success,'outcome_unknown':unknown,'requires_reload':unknown,'no_change':False,
        'history':{'undo_steps':1,'redo_steps':0} if success else None}
    return SimpleNamespace(_common_background_owner=SimpleNamespace(cache={'original-1':(digest,receipt)}),
        _vram=None,_load_id='new-load'),receipt


@pytest.mark.parametrize('success',[True,False])
def test_exact_terminal_readback_does_not_need_live_preview_or_pipeline(success):
    e,receipt=engine(success);events=[];before=deepcopy(e._common_background_owner.cache)
    R.handle(e,request(),events.append)
    assert events[-1]['phase']=='found' and events[-1]['result']==receipt
    assert events[-1]['result'] is not receipt and e._common_background_owner.cache==before
    assert e._vram is None and e._load_id=='new-load'


def test_genuine_rollback_unknown_is_not_promoted_to_success():
    e,receipt=engine(False,True);events=[];R.handle(e,request(),events.append)
    assert events[-1]['result']['outcome_unknown'] and events[-1]['result']['requires_reload']
    assert not events[-1]['result']['success']


def test_missing_owner_does_not_create_controller_or_prove_noncommit():
    e=SimpleNamespace();events=[];R.handle(e,request(),events.append)
    assert events[-1]['phase']=='missing' and events[-1]['result'] is None
    assert e.__dict__=={}


def test_evicted_receipt_remains_missing_not_rejected():
    e,_=engine();e._common_background_owner.cache.clear();events=[]
    R.handle(e,request(),events.append)
    assert events[-1]['phase']=='missing' and 'not applied' in events[-1]['error']


@pytest.mark.parametrize('key,value',[('preview_id','4'*32),('session_id','4'*32),('document_id','foreign')])
def test_query_must_match_original_request_digest(key,value):
    e,_=engine();p=request();p[key]=value;events=[];R.handle(e,p,events.append)
    assert events[-1]['phase']=='failed' and events[-1]['result'] is None


def test_repeated_readback_never_changes_cache_or_runs_apply():
    e,_=engine();before=deepcopy(e._common_background_owner.cache);events=[]
    R.handle(e,request(),events.append);R.handle(e,request(),events.append)
    assert len(events)==2 and all(v['phase']=='found' for v in events)
    assert e._common_background_owner.cache==before


def test_extra_fields_and_apply_action_are_not_admitted():
    for patch in ({'action':'apply'},{'mutation':{'action':'clear'}},{'readback_id':'0'*32}):
        e,_=engine();events=[];R.handle(e,{**request(),**patch},events.append)
        assert events[-1]['phase']=='failed'


def test_corrupted_cached_binding_is_not_returned():
    e,receipt=engine();receipt['session_id']='5'*32;events=[]
    R.handle(e,request(),events.append)
    assert events[-1]['phase']=='failed' and events[-1]['result'] is None
