"""AUTHORED UNRUN. Local QA owns execution, native compilation and visual acceptance."""
from copy import deepcopy
import pytest
from lumaretouch_engine import photo_detail_state as S
from lumaretouch_engine.photo_detail_controller import PhotoDetailController, Ports
from lumaretouch_engine.photo_detail_project import batch_replace, validate_records

def test_schema_and_neutral():
    assert not S.active(None)
    assert not S.active({**S.default(),'sharpen_detail':100,'luma_detail':100})
    for patch in ({'texture':10},{'luma_detail':True},{'chroma_detail':float('nan')},{'sharpen_radius':0},{'version':2}):
        with pytest.raises(ValueError):S.check({**S.default(),**patch})

def test_receipt_history_owned_once():
    state=S.default();commits=[]
    def commit(spec):
        nonlocal state
        commits.append(deepcopy(spec));state=deepcopy(spec);return {'history':{'undo':1}}
    owner=PhotoDetailController(Ports(guard=lambda:None,document=lambda:'d',read=lambda:state,commit=commit,revision=lambda:3),lambda _:None)
    request={'cmd':'photo_detail','request_id':'r','document_id':'d','revision':3,'action':'set','spec':{**state,'luma_amount':50}}
    assert owner.handle(request)['success']
    assert owner.handle(request)['success']
    assert len(commits)==1
    with pytest.raises(ValueError):owner.handle({**request,'spec':S.default()})

def test_pure_batch_and_old_schema_reject():
    records={'a':{'_extended_tone':{'sentinel':1}},'b':{'unrelated':2}}
    before=deepcopy(records);result=batch_replace(records,{**S.default(),'chroma_amount':30})
    assert records==before
    assert result['a']['_extended_tone']==before['a']['_extended_tone']
    assert result['b'][S.KEY]['chroma_amount']==30
    with pytest.raises(ValueError):validate_records(result,allowed=False)
