"""AUTHORED / UNRUN: exact derived mask admission, not native/visual acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import hashlib
import json
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_mask_commands as C
from lumaretouch_engine import creative_derived_source as D, local_mask_state as M


def fixture(monkeypatch,group=None):
    source={'sha256':'a'*64,'width':8,'height':8}
    proof=dict(document_id='1',capture_id='1'*32,ticket='1',generation='1',recipe_document_id='doc',recipe_revision='1')
    capture={'effective_source':source,'descriptor':{'domain':'source-input','full_source':[8,8],'mask_group_id':group},'eligible':True}
    owner=SimpleNamespace(_matching=lambda p,**kw:capture)
    layer={'id':'group','name':'Review','enabled':True,'grade':[0.,0.,0.,1.],'mask':M.empty()}
    engine=SimpleNamespace(_load_id=1,_local_masks=M.empty(),_local_grade_layers={'version':1,'layers':[layer]},
        _source_patch_controller=lambda:SimpleNamespace(capture=owner))
    monkeypatch.setattr(D,'binding',lambda e:deepcopy(source))
    monkeypatch.setattr(C,'require_pixels',lambda e:None)
    return engine,proof,capture


def edit(proof,mutation):return {'cmd':'local_masks','action':'apply','request_id':'request',**proof,'mutation':mutation}


def test_current_capture_allows_exact_mask_mutation(monkeypatch):
    engine,proof,capture=fixture(monkeypatch)
    C.require_command(engine,'local_masks',edit(proof,{'action':'bind','enabled':True}))
    capture['eligible']=False
    with pytest.raises(ValueError,match='Present'):C.require_command(engine,'local_masks',edit(proof,{'action':'clear'}))


@pytest.mark.parametrize('change',[
    lambda c:c.update(effective_source={'sha256':'b'*64,'width':8,'height':8}),
    lambda c:c['descriptor'].update(domain='repair-input'),
    lambda c:c['descriptor'].update(full_source=[9,8]),
    lambda c:c.pop('effective_source')])
def test_capture_source_and_domain_must_match(monkeypatch,change):
    engine,proof,capture=fixture(monkeypatch);change(capture)
    with pytest.raises(ValueError):C.require_command(engine,'local_masks',edit(proof,{'action':'clear'}))


def test_group_capture_cannot_edit_other_group_or_legacy(monkeypatch):
    engine,proof,capture=fixture(monkeypatch,'group')
    C.require_command(engine,'local_masks',edit(proof,{'action':'layer_update','id':'group','name':'New','enabled':False,'grade':[0.,0.,0.,1.]}))
    with pytest.raises(ValueError,match='another captured group'):C.require_command(engine,'local_masks',edit(proof,{'action':'clear'}))
    with pytest.raises(ValueError):C.require_command(engine,'local_masks',edit(proof,{'action':'layer_mask','id':'group','mutation':{'action':'bind','enabled':True}}))


def test_exact_receipt_replay_survives_missing_capture(monkeypatch):
    engine,proof,capture=fixture(monkeypatch);p=edit(proof,{'action':'clear'})
    digest=hashlib.sha256(json.dumps(p,sort_keys=True,allow_nan=False).encode()).hexdigest()
    engine._local_mask_owner=SimpleNamespace(cache={'request':(digest,{'success':True})})
    capture.clear();C.require_command(engine,'local_masks',p)
    p['mutation']={'action':'bind','enabled':True}
    with pytest.raises(ValueError,match='different content'):C.require_command(engine,'local_masks',p)


def test_capture_only_local_mask_purpose_and_exact_fields(monkeypatch):
    engine,_,capture=fixture(monkeypatch)
    p={'cmd':'source_patch_capture','action':'arm','capture_id':'1'*32,'ticket':'1','document_id':'1','epoch':'2'*32,'purpose':'local-masks'}
    C.require_command(engine,'source_patch_capture',p)
    C.require_command(engine,'source_patch_capture',{**p,'group_id':'group'})
    with pytest.raises(ValueError):C.require_command(engine,'source_patch_capture',{**p,'purpose':'repair'})
    with pytest.raises(ValueError):C.require_command(engine,'source_patch_capture',{**p,'path':'original'})
    with pytest.raises(ValueError):C.require_command(engine,'source_patch_capture',{**p,'group_id':'missing'})


def test_cancel_is_narrow_nonmutating_even_after_source_change(monkeypatch):
    engine,proof,capture=fixture(monkeypatch);capture.clear()
    C.require_command(engine,'source_patch_capture',{'cmd':'source_patch_capture','action':'cancel','capture_id':'1'*32,'ticket':'1','document_id':'1'})
    C.require_command(engine,'prompted_masks',{'cmd':'prompted_masks','action':'cancel','preview_id':'2'*32,**proof})
    C.require_command(engine,'local_grade_live',{'cmd':'local_grade_live','action':'cancel','request_id':'r','document_id':'1','session_id':'s','group_id':'group'})


def test_prompted_exact_source_review_and_candidate(monkeypatch):
    engine,proof,_=fixture(monkeypatch)
    p={'cmd':'prompted_masks','action':'predict','preview_id':'2'*32,**proof,'prompts':{'points':[{'x':.5,'y':.5,'label':1}],'box':None},'device':'cpu'}
    C.require_command(engine,'prompted_masks',p)
    with pytest.raises(ValueError):C.require_command(engine,'prompted_masks',{**p,'path':'original'})
    engine._prompted_mask_owner=SimpleNamespace(preview_id='2'*32,proof=proof)
    q={'cmd':'prompted_masks','action':'presented','preview_id':'2'*32,**proof,'candidate':0}
    C.require_command(engine,'prompted_masks',q)
    with pytest.raises(ValueError):C.require_command(engine,'prompted_masks',{**q,'candidate':True})
    engine._prompted_mask_owner.proof={**proof,'generation':'2'}
    with pytest.raises(ValueError):C.require_command(engine,'prompted_masks',q)


def test_live_grade_exact_group_and_session(monkeypatch):
    engine,_,_=fixture(monkeypatch)
    p={'cmd':'local_grade_live','action':'begin','request_id':'r','document_id':'1','session_id':'s','group_id':'group','grade':[0.,0.,0.,1.]}
    C.require_command(engine,'local_grade_live',p)
    with pytest.raises(ValueError):C.require_command(engine,'local_grade_live',{**p,'group_id':'missing'})
    with pytest.raises(ValueError):C.require_command(engine,'local_grade_live',{**p,'action':'preview'})
    calls=[];engine._local_grade_live_owner=SimpleNamespace(matching=lambda p:calls.append(p))
    C.require_command(engine,'local_grade_live',{**p,'action':'preview'})
    assert len(calls)==1


def test_real_pipeline_pixels_must_equal_derived_proxy(monkeypatch):
    import torch
    rgb=np.full((8,8,3),127,np.uint8)
    monkeypatch.setattr(D,'analysis_rgb',lambda e:rgb)
    pipe=SimpleNamespace(src_f32=torch.from_numpy(rgb).permute(2,0,1)[None].float()/255.)
    engine=SimpleNamespace(_vram=pipe)
    C.require_pixels(engine)
    pipe.src_f32=pipe.src_f32+.01
    with pytest.raises(ValueError,match='pixels differ'):C.require_pixels(engine)


def test_only_exact_composed_grade_scope_is_admitted(monkeypatch):
    engine,_,_=fixture(monkeypatch)
    p={'cmd':'grade','action':'scope','scope':'objects'}
    C.require_command(engine,'grade',p)
    for bad in ({**p,'scope':'skin'},{**p,'action':'mask'},{**p,'mask':[]}):
        with pytest.raises(ValueError):C.require_command(engine,'grade',bad)


def test_dormant_wrong_source_masks_still_refuse(monkeypatch):
    engine,proof,_=fixture(monkeypatch)
    engine._local_grade_layers['layers'][0]['enabled']=False
    engine._local_grade_layers['layers'][0]['mask']['source']={'sha256':'b'*64,'width':8,'height':8}
    with pytest.raises(ValueError,match='another effective source'):
        C.require_command(engine,'local_masks',edit(proof,{'action':'clear'}))
