"""Authored contracts only. Implementation session did not execute these tests."""
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import eye_shape_state as S
from lumaretouch_engine.eye_shape_field import compose_delta,EyeField
from lumaretouch_engine.eye_shape_project import validate_records


@pytest.mark.parametrize('key',S.KEYS)
def test_every_control_unlinks_and_relinks_without_erasing_unequal_sides(key):
    r=S.link(S.neutral(),key,False)
    r=S.adjust(S.adjust(r,key,'left',.4),key,'right',-.2)
    linked=S.link(r,key,True)
    assert linked[key]=={'linked':True,'left':.4,'right':-.2}
    assert S.link(linked,key,False)==r
    changed=S.adjust(linked,key,'right',.3)
    assert changed[key]=={'linked':True,'left':.3,'right':.3}
    assert all(changed[k]==S.neutral()[k] for k in S.KEYS if k!=key)


@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),1.01,-1.01,'0',None])
def test_invalid_values_rejected_without_mutating_recipe(bad):
    r=S.neutral()
    with pytest.raises(ValueError): S.adjust(r,'size','left',bad)
    assert r==S.neutral()


def test_control_ids_and_height_position_are_distinct():
    assert S.CONTROL_IDS['family']=='PC-32466-C-9069cc8f2c'
    assert S.CONTROL_IDS['height']=='PC-32466-C-c39023ab15'
    assert S.CONTROL_IDS['position']=='PC-32466-C-37e5823f58'
    assert len(S.KEYS)==10 and len(set(S.CONTROL_IDS.values()))==11


def test_project_requires_owner_in_redo_and_rejects_hidden_source_data():
    r=S.adjust(S.neutral(),'width','left',.3)
    with pytest.raises(ValueError): validate_records({'redo':[{'_eye_shape':r}]})
    with pytest.raises(ValueError): validate_records({'_eye_shape':None})
    validate_records({'_eye_shape':r,'_eye_shape_owner':'a'*64})
    with pytest.raises(ValueError): S.check({**r,'landmarks':[]})
    from lumaretouch_engine.eye_shape_scope import check_params
    with pytest.raises(ValueError):check_params({'recipe':r,'source':'other.png'})


class AffineField:
    shape=(5,7)
    state=True
    def __init__(self,scale):self.scale=np.asarray(scale)
    def evaluate(self,X):return X*self.scale


def test_actual_offgrid_e_after_n_after_b_after_a_and_halo_peak():
    a=np.zeros((1,5,7,2),np.float32);a[...,0]=1.25;a[...,1]=.5
    b=AffineField((.1,.2));n=AffineField((.25,.15));e=AffineField((.07,.13))
    result,peak=compose_delta(a,b,n,e,(5,7),band_pixels=7)
    yy,xx=np.mgrid[:5,:7];X=np.stack((xx,yy),-1).astype(np.float64)
    q=X-a[0]
    for f in (b,n,e):q-=q*f.scale
    assert np.allclose(result[0],(X-q).astype(np.float32),atol=1e-6)
    assert peak==float(np.abs(result).max())
    whole,_=compose_delta(a,b,n,e,(5,7),band_pixels=10000)
    assert np.array_equal(result,whole)
    assert not np.allclose(result[0],a[0]+X*(b.scale+n.scale+e.scale))


def test_neutral_preserves_exact_original_auto_object_and_cache():
    a=np.zeros((1,5,7,2),np.float32)
    out,peak=compose_delta(a,None,None,None,(5,7))
    assert out is a and peak==0.
    from lumaretouch_engine.eye_shape_runtime import sync
    warp=object();key=object();pipe=SimpleNamespace(_deform_warp=warp,_deform_warp_key=key)
    sync(SimpleNamespace(_vram=pipe,_eye_shape=S.neutral()))
    assert pipe._deform_warp is warp and pipe._deform_warp_key is key


def test_legacy_size_is_preserved_and_never_double_applied():
    from lumaretouch_engine.eye_shape_runtime import check_legacy
    old={'big_eye':.25,'slim_face':.3}
    check_legacy(S.neutral(),old)
    check_legacy(S.adjust(S.neutral(),'height','left',.2),old)
    with pytest.raises(ValueError):check_legacy(S.adjust(S.neutral(),'size','left',.2),old)
    assert old=={'big_eye':.25,'slim_face':.3}
    check_legacy(S.adjust(S.neutral(),'size','left',.2),{'big_eye':0})


def test_topology_uses_full_lids_and_iris_and_does_not_pin_target_eyes():
    from lumaretouch_engine.eye_shape_geometry import EYES,IRIS,ANCHORS,NOSE,LIPS,BROWS
    assert all(len(v)==16 for v in EYES.values())
    assert set(IRIS['left']+IRIS['right'])==set(range(468,478))
    assert not set(EYES['left']+EYES['right']+IRIS['left']+IRIS['right'])&set(ANCHORS)
    assert set(NOSE+LIPS+BROWS).issubset(ANCHORS)
    assert EyeField._protection.__qualname__.startswith('EyeField.')


def test_unobservable_eye_is_per_control_per_side_refusal():
    from lumaretouch_engine.eye_shape_geometry import evidence
    lm=np.zeros((478,2));lm[468]=[30,30];lm[473]=[70,30];lm[10]=[50,0];lm[1]=[50,60]
    facts,*_=evidence(lm,np.zeros((100,100,3)),None,'left')
    assert set(facts)==set(S.KEYS)
    assert all(f['side']=='left' and f['reason'] for f in facts.values())


def test_export_depth_and_missing_real_face_reject_before_geometry():
    from lumaretouch_engine.eye_shape_runtime import export_field
    spec=SimpleNamespace(eye_shape=S.adjust(S.neutral(),'height','left',.1))
    with pytest.raises(ValueError):export_field(spec,np.zeros((4,4,3),np.float32),divisor=255)
    with pytest.raises(ValueError):export_field(spec,np.zeros((4,4,3),np.uint16),divisor=255)
    with pytest.raises(ValueError):export_field(spec,np.zeros((4,4,3),np.uint16),divisor=65535)


def test_receipt_reconciles_rejection_after_history(monkeypatch):
    from lumaretouch_engine import eye_shape_receipts as R
    from collections import OrderedDict
    recipe=S.neutral();doc={'eye_shape':{'selected_face_id':'face','revision':9,'controls':{}}}
    engine=SimpleNamespace(_vram=object(),_load_id='doc',_eye_shape=recipe,_eye_receipts=OrderedDict(),doc_state=lambda:doc)
    msg={'request_id':'r','gesture_id':'g','face_id':'face','document_id':'doc','control':'size'}
    out=[];R.finish(engine,msg,'refused',out.append)
    assert out[0]['success'] is False and out[0]['outcome_unknown'] is False
    assert out[0]['recipe']==recipe and out[0]['revision']==9


def test_warp_key_and_adopted_export_consumer_gate():
    from lumaretouch_engine.eye_shape_runtime import warp_key,has_source_geometry
    pipe=SimpleNamespace(deform_version=2,deform_amounts={'slim_face':.2},high_precision_warp=True,
        brow_shape_field=SimpleNamespace(state=True),brow_shape_version=5,nose_shape_field=None)
    before=warp_key(pipe)
    pipe.eye_shape_field=SimpleNamespace(state=True);pipe.eye_shape_version=3
    assert warp_key(pipe)==before+(('eye_shape',3),)
    pipe.eye_shape_field=None;pipe.brow_shape_field=None;pipe.eye_shape_combined=True
    assert has_source_geometry(pipe)


def test_registered_target_only_scope():
    from lumaretouch_engine import scope
    from lumaretouch_engine.eye_shape_scope import OP
    assert scope.MODULES[OP]['params']==('recipe',)
    assert scope.MODULES[OP]['single_face'] is True
    assert scope.check_params(OP,{'recipe':S.neutral()})=={'recipe':S.neutral()}


def test_target_validation_uses_own_original_pixels_and_owner(monkeypatch):
    from lumaretouch_engine import eye_shape_scope as T,eye_shape_runtime as R
    from lumaretouch_engine import decode,cpu_memory_budget,local_mask_state
    pc=SimpleNamespace(landmarks=np.zeros((478,3),np.float32))
    state={'_eye_shape':S.adjust(S.neutral(),'width','left',.1),'_precompute':pc,
           '_eye_shape_owner':R.identity(pc.landmarks),'_deform':{'amounts':{'big_eye':.2}}}
    monkeypatch.setattr(cpu_memory_budget,'available_estimate',lambda:1024**3)
    monkeypatch.setattr(local_mask_state,'file_stamp',lambda path:'same')
    monkeypatch.setattr(decode,'load_full',lambda *a,**k:SimpleNamespace(h=20,w=30,rgb=np.zeros((20,30,3),np.uint16)))
    calls=[]
    def field(spec,source,*,divisor):
        assert spec.landmarks is pc.landmarks and spec.eye_shape_face is pc
        assert source.shape==(20,30,3) and spec.deform_amounts=={'big_eye':.2}
        calls.append(divisor)
    monkeypatch.setattr(R,'export_field',field)
    T.validate_target(state,{'path':'target.tif','src_h':20,'src_w':30})
    assert calls==[65535]


def test_refused_edit_restores_recipe_and_keeps_structured_refusal(monkeypatch):
    from lumaretouch_engine import eye_shape_command as C,eye_shape_runtime as R
    lm=np.zeros((478,3),np.float32);old=S.neutral();new=S.adjust(old,'iris_size','left',.2)
    facts={'left:iris_size':{'requested':True,'applied':False,'reason':'iris_not_fully_observable'}}
    engine=SimpleNamespace(_load_id='doc',_eye_shape=old,_eye_shape_owner=None,
        _precompute=SimpleNamespace(landmarks=lm),_vram=SimpleNamespace(),
        _guard_editable=lambda _:None,_write_current_frame=lambda _: {},doc_state=lambda:{})
    def refuse(*a,**k):raise R.EyeRefusal(facts)
    monkeypatch.setattr(R,'sync',refuse)
    with pytest.raises(R.EyeRefusal):
        C.apply(engine,{'cmd':'eye_shape','recipe':new,'base':old,'document_id':'doc','control':'iris_size'},lambda _:None)
    assert engine._eye_shape==old and engine._eye_shape_owner is None
    assert engine._eye_shape_refusal==('doc',R.identity(lm),facts)


def test_rollback_failure_preserves_uncertain_result_not_unbound_exception(monkeypatch):
    from lumaretouch_engine import eye_shape_command as C,eye_shape_runtime as R
    old=S.neutral();new=S.adjust(old,'width','left',.1)
    engine=SimpleNamespace(_load_id='doc',_eye_shape=old,_eye_shape_owner=None,
        _precompute=None,_vram=SimpleNamespace(),_guard_editable=lambda _:None,doc_state=lambda:{})
    def fail(*a,**k):raise ValueError('deliberate render failure')
    engine._write_current_frame=fail
    monkeypatch.setattr(R,'sync',fail)
    out=[]
    with pytest.raises(ValueError,match='deliberate render failure'):
        C.apply(engine,{'cmd':'eye_shape','recipe':new,'base':old,'document_id':'doc','control':'width'},out.append)
    assert engine._vram is None and out[-1]['event']=='error'


def test_atomic_refusal_never_labels_admissible_sibling_as_applied():
    from lumaretouch_engine.eye_shape_runtime import EyeRefusal
    facts={'left:iris_size':{'requested':True,'applied':False,'reason':'iris_not_fully_observable'},
           'left:width':{'requested':True,'applied':True,'reason':None}}
    refusal=EyeRefusal(facts)
    assert not any(f['applied'] for f in refusal.facts.values())
    assert refusal.facts['left:width']['reason']=='atomic_request_refused'
    assert facts['left:width']['applied'] is True  # no mutation of diagnostic input
