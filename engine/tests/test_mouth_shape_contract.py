"""Authored but unrun contracts: source writing is not runtime acceptance."""
from types import SimpleNamespace
from collections import OrderedDict
import numpy as np
import pytest
from lumaretouch_engine import mouth_shape_state as S
from lumaretouch_engine.mouth_shape_field import compose_delta, MouthField


def test_baseline_ids_and_nine_controls():
    assert len(S.KEYS)==9 and len(set(S.CONTROL_IDS.values()))==10
    assert S.CONTROL_IDS['family']=='PC-32466-C-cbb4c198e8'
    assert S.CONTROL_IDS['vertical']=='PC-32466-C-d9f05e02e0'
    assert S.CONTROL_IDS['m_lip']=='PC-32466-C-64e1410070'


def test_only_gummy_unlinks_and_never_reverses():
    r=S.link(S.neutral(),False)
    r=S.adjust(S.adjust(r,'gummy',.4,'left'),'gummy',.2,'right')
    linked=S.link(r,True)
    assert linked['gummy']=={'linked':True,'left':.4,'right':.2}
    assert S.adjust(linked,'gummy',.3,'right')['gummy']=={'linked':True,'left':.3,'right':.3}
    with pytest.raises(ValueError):S.adjust(r,'gummy',-.1,'left')
    with pytest.raises(ValueError):S.adjust(r,'size',.2,'left')


@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),1.01,-1.01,'0',None])
def test_invalid_scalar_preserves_original(bad):
    r=S.neutral()
    with pytest.raises(ValueError):S.adjust(r,'size',bad)
    assert r==S.neutral()


def test_project_owner_and_parameter_only_transport():
    from lumaretouch_engine.mouth_shape_project import validate_records
    from lumaretouch_engine.mouth_shape_scope import check_params
    r=S.adjust(S.neutral(),'width',.3)
    with pytest.raises(ValueError):validate_records({'redo':[{'_mouth_shape':r}]})
    validate_records({'_mouth_shape':r,'_mouth_shape_owner':'a'*64})
    with pytest.raises(ValueError):check_params({'recipe':r,'source':'other.jpg'})
    with pytest.raises(ValueError):S.check({**r,'landmarks':[]})


class AffineField:
    shape=(5,7)
    state=True
    def __init__(self,scale):self.scale=np.asarray(scale)
    def evaluate(self,X):return X*self.scale


def test_offgrid_m_after_e_n_b_a_and_actual_combined_halo():
    a=np.zeros((1,5,7,2),np.float32);a[...,0]=1.25;a[...,1]=.5
    fields=[AffineField(s) for s in ((.1,.2),(.25,.15),(.07,.13),(.11,.09))]
    result,peak=compose_delta(a,*fields,(5,7),band_pixels=7)
    yy,xx=np.mgrid[:5,:7];X=np.stack((xx,yy),-1).astype(np.float64)
    q=X-a[0]
    for f in fields:q-=q*f.scale
    assert np.allclose(result[0],(X-q).astype(np.float32),atol=1e-6)
    assert peak==float(np.abs(result).max())
    whole,_=compose_delta(a,*fields,(5,7),band_pixels=10000)
    assert np.array_equal(result,whole)
    assert not np.allclose(result[0],a[0]+X*sum((f.scale for f in fields)))


def test_neutral_exact_object_and_cache_and_legacy_smile():
    a=np.zeros((1,5,7,2),np.float32)
    out,peak=compose_delta(a,None,None,None,None,(5,7))
    assert out is a and peak==0
    from lumaretouch_engine.mouth_shape_runtime import sync,check_legacy
    warp=object();key=object();pipe=SimpleNamespace(_deform_warp=warp,_deform_warp_key=key)
    sync(SimpleNamespace(_vram=pipe,_mouth_shape=S.neutral()))
    assert pipe._deform_warp is warp and pipe._deform_warp_key is key
    old={'smile':.6,'big_eye':.2}
    check_legacy(S.adjust(S.neutral(),'m_lip',-.5),old)
    assert old=={'smile':.6,'big_eye':.2}


def test_full_lip_rings_are_not_pinned_by_other_features():
    from lumaretouch_engine.mouth_shape_geometry import RING,ANCHORS,OUTER,INNER
    assert set(RING)==set(OUTER)|set(INNER)
    assert len(OUTER)==20 and len(INNER)==20
    assert not set(RING)&set(ANCHORS)
    assert MouthField._protection.__qualname__.startswith('MouthField.')


def test_cavity_veto_zero_on_lips_and_nonzero_in_observed_interior():
    from lumaretouch_engine.mouth_shape_consumers import cavity_support
    from lumaretouch_engine.lip_makeup_geometry import INNER
    lm=np.zeros((478,2),np.float64)
    # Ordered contour has enough room for an inward bilinear-safe rim.
    angles=np.linspace(np.pi,3*np.pi,len(INNER),endpoint=False)
    lm[list(INNER)]=np.stack((40+20*np.cos(angles),40+10*np.sin(angles)),axis=1)
    lm[61]=[15,40];lm[291]=[65,40]
    support=cavity_support(lm,(80,80))
    assert support[40,40]>0 and support[27,40]==0 and support[30,40]==0
    assert support[40,15]==0 and support[40,65]==0


def test_teeth_veto_precedes_only_final_grid_sample():
    from pathlib import Path
    source=(Path(__file__).parents[1]/'src/lumaretouch_engine/brow_shape_consumers.py').read_text()
    assert source.index('gate_teeth_source(pipe,weight)')<source.index('align_source_grade_mask(weight)')
    assert source.count('align_source_grade_mask(weight)')==1


def test_export_rejects_wrong_depth_or_missing_real_face():
    from lumaretouch_engine.mouth_shape_runtime import export_field
    spec=SimpleNamespace(mouth_shape=S.adjust(S.neutral(),'upper',.1))
    with pytest.raises(ValueError):export_field(spec,np.zeros((4,4,3),np.float32),divisor=255)
    with pytest.raises(ValueError):export_field(spec,np.zeros((4,4,3),np.uint16),divisor=255)
    with pytest.raises(ValueError):export_field(spec,np.zeros((4,4,3),np.uint16),divisor=65535)


def test_rejection_receipt_has_post_history_authoritative_base():
    from lumaretouch_engine import mouth_shape_receipts as R
    doc={'mouth_shape':{'selected_face_id':'face','revision':9,'controls':{}}}
    engine=SimpleNamespace(_vram=object(),_load_id='doc',_mouth_shape=S.neutral(),_mouth_receipts=OrderedDict(),doc_state=lambda:doc)
    msg={'request_id':'r','gesture_id':'g','face_id':'face','document_id':'doc','control':'size'}
    out=[];R.finish(engine,msg,'refused',out.append)
    assert out[0]['success'] is False and out[0]['outcome_unknown'] is False
    assert out[0]['recipe']==S.neutral() and out[0]['revision']==9


def test_rollback_failure_preserves_original_exception_and_uncertainty(monkeypatch):
    from lumaretouch_engine import mouth_shape_command as C,mouth_shape_runtime as R
    old=S.neutral();new=S.adjust(old,'width',.1)
    engine=SimpleNamespace(_load_id='doc',_mouth_shape=old,_mouth_shape_owner=None,
        _precompute=None,_vram=SimpleNamespace(),_guard_editable=lambda _:None,doc_state=lambda:{})
    def fail(*a,**k):raise ValueError('deliberate render failure')
    engine._write_current_frame=fail;monkeypatch.setattr(R,'sync',fail)
    out=[]
    with pytest.raises(ValueError,match='deliberate render failure'):
        C.apply(engine,{'cmd':'mouth_shape','recipe':new,'base':old,'document_id':'doc','control':'width'},out.append)
    assert engine._vram is None and out[-1]['event']=='error'


def test_atomic_refusal_never_reports_a_sibling_applied():
    from lumaretouch_engine.mouth_shape_runtime import MouthRefusal
    facts={'gummy:left':{'requested':True,'applied':False,'reason':'closed_or_unobservable_aperture'},
           'width':{'requested':True,'applied':True,'reason':None}}
    refusal=MouthRefusal(facts)
    assert not any(f['applied'] for f in refusal.facts.values())
    assert refusal.facts['width']['reason']=='atomic_request_refused'
    assert facts['width']['applied'] is True


def test_target_recomputes_own_original_pixels_not_source_mesh(monkeypatch):
    from lumaretouch_engine import mouth_shape_scope as T,mouth_shape_runtime as R
    from lumaretouch_engine import decode,cpu_memory_budget,local_mask_state
    pc=SimpleNamespace(landmarks=np.zeros((478,3),np.float32))
    state={'_mouth_shape':S.adjust(S.neutral(),'width',.1),'_precompute':pc,
           '_mouth_shape_owner':R.identity(pc.landmarks),'_deform':{'amounts':{'smile':.3}}}
    monkeypatch.setattr(cpu_memory_budget,'available_estimate',lambda:1024**3)
    monkeypatch.setattr(local_mask_state,'file_stamp',lambda path:'same')
    monkeypatch.setattr(decode,'load_full',lambda *a,**k:SimpleNamespace(h=20,w=30,rgb=np.zeros((20,30,3),np.uint16)))
    calls=[]
    def field(spec,source,*,divisor):
        assert spec.landmarks is pc.landmarks and spec.mouth_shape_face is pc
        assert source.shape==(20,30,3) and spec.deform_amounts=={'smile':.3}
        calls.append(divisor)
    monkeypatch.setattr(R,'export_field',field)
    T.validate_target(state,{'path':'target.tif','src_h':20,'src_w':30})
    assert calls==[65535]


def test_registered_scope_and_both_explicit_gesture_history_paths():
    from pathlib import Path
    from lumaretouch_engine import scope
    from lumaretouch_engine.mouth_shape_scope import OP
    assert scope.MODULES[OP]['params']==('recipe',)
    assert scope.MODULES[OP]['single_face'] is True
    assert scope.check_params(OP,{'recipe':S.neutral()})=={'recipe':S.neutral()}
    src=(Path(__file__).parents[1]/'src/lumaretouch_engine/history_controller.py').read_text()
    assert src.count('"mouth_shape:gesture:"')==2


def test_native_math_missing_never_silently_falls_back(monkeypatch):
    from lumaretouch_engine import mouth_shape_native as N
    def missing():raise RuntimeError('native unavailable')
    monkeypatch.setattr(N,'native',missing)
    with pytest.raises(RuntimeError,match='native unavailable'):
        N.controls(np.zeros((1,2)),np.zeros((1,4)),np.ones(10),np.zeros(10))


def test_export_and_preview_share_mouth_final_grid_and_cavity_source_support():
    from pathlib import Path
    root=Path(__file__).parents[1]/'src/lumaretouch_engine'
    export=(root/'export.py').read_text();vram=(root/'vram.py').read_text()
    assert 'compose_geometry_delta(delta, brow_field, nose_field, eye_field, mouth_field, (h,w))' in export
    assert 'margin = spec.margin_px(peak, manual_peak)' in export
    assert 'mouth_field.teeth_support[cy0:cy1,cx0:cx1]' in export
    assert 'MOUTHR.joint_delta(self, delta)' in vram
    assert 'MOUTHR.has_source_geometry(self)' in vram
