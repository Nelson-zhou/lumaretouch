"""AUTHORED / UNRUN. No inference, visual acceptance or runtime result claimed."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_common_background as D
from lumaretouch_engine import common_background_review as R
from lumaretouch_engine import common_background_preview_source as P
from lumaretouch_engine import creative_common_background_host as H


def test_sdr_admits_exact_float_pixels_without_conversion():
    pixels=np.array([[[0.,.5,1.]]],np.float32)
    assert D.sdr(pixels) is pixels


@pytest.mark.parametrize('pixels',[
    np.zeros((1,1,3),np.uint16),np.zeros((1,1,4),np.float32),
    np.full((1,1,3),1.01,np.float32),np.full((1,1,3),-.01,np.float32),
    np.full((1,1,3),np.nan,np.float32),np.full((1,1,3),np.inf,np.float32)])
def test_no_hdr_alpha_or_nonfinite_source_conversion(pixels):
    with pytest.raises(ValueError):D.sdr(pixels)


def test_pixel_hash_binds_shape_dtype_and_content():
    a=np.zeros((2,3,3),np.float32)
    assert D.hash_pixels(a)!=D.hash_pixels(a.reshape(3,2,3))
    assert D.hash_pixels(a)!=D.hash_pixels(a.astype(np.float64))
    b=a.copy();b[0,0,0]=.1
    assert D.hash_pixels(a)!=D.hash_pixels(b)


@pytest.mark.parametrize('value',[
    {'action':'set','bg':[0,0,False],'tol':.12,'softness':.1},
    {'action':'set','bg':[0,0,0],'tol':float('nan'),'softness':.1},
    {'action':'set','bg':[0,0,0],'tol':.12,'softness':0},
    {'action':'clear','backend':'birefnet'}, {'action':'set','matte':'borrowed'}])
def test_mutation_refuses_unreviewed_or_nonfinite_payload(value):
    with pytest.raises(ValueError):R.mutation(value)


def test_clear_retains_source_recipe_for_dormant_recovery(monkeypatch):
    recipe={'source':{'sha256':'a'*64},'version':2}
    engine=SimpleNamespace(_bg={'active':True,'key_recipe':recipe,'matte':np.ones((2,2))})
    monkeypatch.setattr(R.S,'check',lambda bg:recipe)
    candidate=R.candidate(engine,{'action':'clear'})
    assert candidate['active'] is False and candidate['matte'] is None
    assert candidate['key_recipe']==recipe and candidate['key_recipe'] is not recipe
    assert engine._bg['active'] is True


def test_review_requires_presented_and_unchanged_proof(monkeypatch):
    engine=SimpleNamespace();owner=R.Preview(engine,lambda event:None)
    request={'preview_id':'1'*32,'session_id':'2'*32,'document_id':'document'}
    context={'source':'effective-A'}
    monkeypatch.setattr(R,'proof',lambda e:deepcopy(context))
    owner.record={'request':request,'proof':deepcopy(context),'value':{'active':False},'presented':False}
    with pytest.raises(ValueError):owner.prepare(request)
    owner.record['presented']=True
    assert owner.prepare(request)=={'active':False}
    context['source']='effective-B'
    with pytest.raises(ValueError):owner.prepare(request)


def test_proof_binds_float_composition_mode():
    pipe=SimpleNamespace(has_background=lambda:False,bg_matte=None,bg_ref=None)
    before=P.field_proof(pipe);pipe._common_background_preserve=True
    assert P.field_proof(pipe)!=before


def test_readonly_capture_cancel_does_not_revoke_review():
    calls=[];engine=SimpleNamespace(_common_background_preview_owner=SimpleNamespace(cancel=lambda:calls.append(1)))
    H.invalidate_other(engine,'sample_library_cancel',{'cmd':'sample_library_cancel','request_id':'cancel-1'})
    assert not calls
    H.invalidate_other(engine,'tone',{'cmd':'tone'})
    assert calls==[1]


def test_shared_float_compositor_preserves_opaque_extended_edits():
    torch=pytest.importorskip('torch')
    from lumaretouch_engine.ops.matting import composite_linear_fields_t
    rgb=torch.tensor([[[[-.1,1.4]],[[.5,2.]],[[1.2,.3]]]],dtype=torch.float32)
    alpha=torch.ones((1,1,1,2));background=torch.zeros_like(rgb)
    assert torch.equal(composite_linear_fields_t(rgb,alpha,background),rgb)
    mixed=composite_linear_fields_t(rgb,alpha*.9,background)
    assert float(mixed.max())>1 and float(mixed.min())<0


def controller_fixture(monkeypatch, *, fail_record=False, fail_publish=False):
    from lumaretouch_engine import common_background_controller as C
    events=[];history=SimpleNamespace(undo=[],redo=['retained-redo'],group='old',group_ns=7)
    engine=SimpleNamespace(_bg={'active':False},_project_dirty=False,_vram=object())
    engine._guard_editable=lambda reason:None
    engine._history_capture=lambda:deepcopy(engine._bg)
    engine._history_apply=lambda value:setattr(engine,'_bg',deepcopy(value))
    engine._history_controller=lambda:history
    engine._fence_current_document=lambda:None
    engine._cancel_snapshot=lambda reason:None
    engine._write_current_frame=lambda reason:{'event':'frame','reason':reason}
    engine.doc_state=lambda:{'history':{'undo_steps':len(history.undo),'redo_steps':len(history.redo)}}
    def record(group,before,**options):
        engine._project_dirty=True;history.undo.append(before);history.redo=[]
        if fail_record:raise RuntimeError('after ledger mutation')
    engine._history_record=record
    monkeypatch.setattr(C,'state_signature',lambda value:repr(value))
    monkeypatch.setattr(C,'preview',lambda *a:SimpleNamespace(prepare=lambda p:{'active':True},cancel=lambda:None))
    monkeypatch.setattr(C.P,'install',lambda e:None)
    def emit(event):
        if fail_publish and event['event']=='frame':raise RuntimeError('frame transport failure')
        events.append(event)
    request={'cmd':'common_background','action':'apply','request_id':'one',
        'preview_id':'1'*32,'session_id':'2'*32,'document_id':'document'}
    return C.Controller(engine,emit),engine,history,events,request


def test_apply_owns_one_history_step_and_receipt_replay(monkeypatch):
    owner,engine,history,events,request=controller_fixture(monkeypatch)
    owner.handle(request);owner.handle(request)
    assert len(history.undo)==1 and events[-1]['success'] and events[-1]['replayed']


def test_partial_history_failure_restores_ledger_and_dirty(monkeypatch):
    owner,engine,history,events,request=controller_fixture(monkeypatch,fail_record=True)
    owner.handle(request)
    assert engine._bg=={'active':False} and not engine._project_dirty
    assert history.undo==[] and history.redo==['retained-redo']
    assert not events[-1]['success'] and not events[-1]['outcome_unknown']


def test_committed_frame_delivery_failure_is_not_clean_rejection(monkeypatch):
    owner,engine,history,events,request=controller_fixture(monkeypatch,fail_publish=True)
    owner.handle(request)
    assert engine._bg['active'] and len(history.undo)==1
    assert events[-1]['success'] and events[-1]['frame_delivery_unknown']


def test_post_record_status_failure_rolls_back_before_publication(monkeypatch):
    owner,engine,history,events,request=controller_fixture(monkeypatch)
    original=engine.doc_state;calls=[]
    def status():
        calls.append(1)
        if len(calls)==1:raise RuntimeError('status fault before publication')
        return original()
    engine.doc_state=status;owner.handle(request)
    assert not engine._bg['active'] and history.undo==[]
    assert not events[-1]['success'] and not events[-1]['outcome_unknown']
