"""Source-added contract cases. Not executed by the implementation task."""
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import nose_shape_state as S
from lumaretouch_engine.nose_shape_field import compose_delta,NoseField
from lumaretouch_engine.nose_shape_project import validate_records


def test_six_independent_controls_and_exact_ids():
    r=S.adjust(S.neutral(),'height',.3)
    assert r['height']==.3
    assert all(r[k]==0 for k in S.KEYS if k!='height')
    assert S.CONTROL_IDS['position']=='PC-32466-C-1ef85157f8'
    assert len(set(S.CONTROL_IDS.values()))==7
    with pytest.raises(ValueError): S.check({**r,'position':{'left':0,'right':0}})


@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),1.01,-1.01,'0',None])
def test_bad_value_does_not_mutate_input(bad):
    r=S.neutral()
    with pytest.raises(ValueError): S.adjust(r,'tip',bad)
    assert r==S.neutral()


def test_project_requires_real_owner_even_in_redo():
    r=S.adjust(S.neutral(),'wing',.2)
    with pytest.raises(ValueError): validate_records({'redo':[{'_nose_shape':r}]})
    with pytest.raises(ValueError): validate_records({'_nose_shape':None})
    validate_records({'_nose_shape':r,'_nose_shape_owner':'b'*64})


class AffineField:
    shape=(5,7)
    state=True
    def __init__(self,scale):self.scale=scale
    def evaluate(self,X):return X*np.asarray(self.scale)


def test_order_is_nose_after_brow_after_auto_in_pullback():
    a=np.zeros((1,5,7,2),np.float32);a[...,0]=1.25;a[...,1]=.5
    b=AffineField((.10,.20));n=AffineField((.25,.15))
    result,peak=compose_delta(a,b,n,(5,7),band_pixels=7)
    yy,xx=np.mgrid[:5,:7];X=np.stack((xx,yy),-1).astype(np.float64)
    q=X-a[0];q-=q*[.10,.20];q-=q*[.25,.15]
    expected=(X-q).astype(np.float32)
    assert np.allclose(result[0],expected,atol=1e-6)
    assert peak==float(np.abs(result).max())
    whole,_=compose_delta(a,b,n,(5,7),band_pixels=1000)
    assert np.array_equal(whole,result)
    assert not np.allclose(result[0],a[0]+X*[.1,.2]+X*[.25,.15])


def test_neutral_nose_preserves_original_object_without_brow():
    a=np.zeros((1,5,7,2),np.float32)
    result,peak=compose_delta(a,None,None,(5,7))
    assert result is a and peak==0.
    assert compose_delta(None,None,None,(5,7))==(None,0.)


def test_neutral_sync_does_not_invalidate_existing_brow_auto_cache():
    from lumaretouch_engine.nose_shape_runtime import sync
    warp=object();key=object()
    pipe=SimpleNamespace(_deform_warp=warp,_deform_warp_key=key)
    sync(SimpleNamespace(_vram=pipe,_nose_shape=S.neutral()))
    assert pipe._deform_warp is warp and pipe._deform_warp_key is key
    assert not hasattr(pipe,'nose_shape_version')


def test_parameter_transport_excludes_identity_and_maps():
    from lumaretouch_engine.nose_shape_scope import check_params
    with pytest.raises(ValueError):check_params({'recipe':S.neutral(),'landmarks':[]})
    with pytest.raises(ValueError):S.check({**S.neutral(),'source':'other-person.png'})
    assert check_params({'recipe':S.neutral()})=={'recipe':S.neutral()}


def test_nose_protection_does_not_inherit_global_nose_identity():
    from lumaretouch_engine.nose_shape_geometry import CENTERLINE,ANCHORS,NOSE,NOSTRILS
    assert CENTERLINE==(168,6,197,195,5,4,1,19,94,2)
    assert not set(CENTERLINE)&set(ANCHORS)
    assert not set(NOSE)&set(ANCHORS)
    assert all(set(n).issubset(NOSE) for n in NOSTRILS)
    assert NoseField._protection.__qualname__.startswith('NoseField.')


def test_export_requires_matching_original_rgb_depth_before_geometry():
    from lumaretouch_engine.nose_shape_runtime import export_field
    spec=SimpleNamespace(nose_shape=S.adjust(S.neutral(),'size',.1))
    with pytest.raises(ValueError):export_field(spec,np.zeros((4,4,3),np.float32),divisor=255)


def test_parked_target_calls_keyword_divisor_and_sets_own_landmarks(monkeypatch):
    from lumaretouch_engine import nose_shape_scope as scope,nose_shape_runtime as runtime,decode,cpu_memory_budget,local_mask_state
    lm=np.zeros((478,3),np.float32)
    pc=SimpleNamespace(landmarks=lm)
    state={'_nose_shape':S.adjust(S.neutral(),'size',.1),'_nose_shape_owner':runtime.identity(lm),'_precompute':pc}
    monkeypatch.setattr(cpu_memory_budget,'available_estimate',lambda:10**9)
    monkeypatch.setattr(local_mask_state,'file_stamp',lambda path:'stamp')
    monkeypatch.setattr(decode,'load_full',lambda *a,**k:SimpleNamespace(h=20,w=20,rgb=np.zeros((20,20,3),np.uint16)))
    seen=[]
    def verify(spec,source,*,divisor):seen.append((spec.landmarks is lm,divisor))
    monkeypatch.setattr(runtime,'export_field',verify)
    scope.validate_target(state,{'src_h':20,'src_w':20,'path':'target'})
    assert seen==[(True,65535)]


def test_latest_full_recipe_preserves_multiple_queued_controls(monkeypatch):
    from lumaretouch_engine import nose_shape_command as command,nose_shape_runtime as runtime
    old=S.neutral();new=S.adjust(S.adjust(old,'bridge',.2),'tip',.3)
    pipe=SimpleNamespace()
    engine=SimpleNamespace(_load_id='doc',_nose_shape=old,_nose_shape_owner=None,_precompute=None,_vram=pipe,
                           _guard_editable=lambda _:None,_write_current_frame=lambda _: {},doc_state=lambda:{})
    monkeypatch.setattr(runtime,'sync',lambda *a,**k:None)
    command.apply(engine,{'cmd':'nose_shape','recipe':new,'base':old,'document_id':'doc','control':'tip'},lambda _:None)
    assert engine._nose_shape==new
    with pytest.raises(ValueError):
        command.apply(engine,{'cmd':'nose_shape','recipe':old,'base':old,'document_id':'doc','control':'tip'},lambda _:None)


def test_warp_key_neutral_compatibility_and_tile_consumer_gate():
    from lumaretouch_engine.nose_shape_runtime import warp_key,has_source_geometry
    pipe=SimpleNamespace(deform_version=2,deform_amounts={'slim_face':.2},high_precision_warp=True,
        brow_shape_field=SimpleNamespace(state=True),brow_shape_version=5,nose_shape_field=None)
    assert warp_key(pipe)==(2,(('slim_face',.2),),True,5)
    pipe.nose_shape_field=SimpleNamespace(state=True);pipe.nose_shape_version=7
    assert warp_key(pipe)==(2,(('slim_face',.2),),True,5,('nose_shape',7))
    pipe.brow_shape_field=None;pipe.nose_shape_field=None;pipe.nose_shape_combined=True
    assert has_source_geometry(pipe)  # adopted export delta, not a second field


def test_registered_recipe_matches_portable_parameters():
    from lumaretouch_engine import scope
    from lumaretouch_engine.nose_shape_scope import OP
    assert scope.MODULES[OP]['params']==('recipe',)
    assert scope.MODULES[OP]['single_face'] is True
    assert scope.check_params(OP,{'recipe':S.neutral()})=={'recipe':S.neutral()}
