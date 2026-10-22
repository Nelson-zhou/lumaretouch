"""Source-added acceptance tests. Not executed by the implementation task."""
import numpy as np
import pytest
from lumaretouch_engine import brow_shape_state as S
from lumaretouch_engine.brow_shape_field import compose_delta
from lumaretouch_engine.brow_shape_project import validate_records


def test_independent_bilateral_and_non_destructive_relink():
    r=S.link(S.neutral(),'thickness',False)
    r=S.adjust(r,'thickness','left',.6)
    r=S.adjust(r,'thickness','right',-.2)
    linked=S.link(r,'thickness',True)
    assert linked['thickness']=={'linked':True,'left':.6,'right':-.2}
    assert S.link(linked,'thickness',False)==r
    linked=S.adjust(linked,'thickness','right',.3)
    assert linked['thickness']['left']==linked['thickness']['right']==.3
    assert all(linked[k]==S.neutral()[k] for k in S.KEYS if k!='thickness')


@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),1.01,-1.01,'0'])
def test_reject_invalid_amount_without_mutation(bad):
    before=S.neutral()
    with pytest.raises(ValueError): S.adjust(before,'arch','left',bad)
    assert before==S.neutral()


def test_project_refuses_unowned_or_null_active_state():
    r=S.adjust(S.neutral(),'position','left',.2)
    with pytest.raises(ValueError): validate_records({'history':[{'_brow_shape':r}]})
    with pytest.raises(ValueError): validate_records({'_brow_shape':None})
    validate_records({'_brow_shape':r,'_brow_shape_owner':'a'*64})


def test_joint_pullback_is_not_naive_field_addition():
    class NonConstantBrow:
        shape=(4,7)
        state=True
        def evaluate(self,X): return np.stack((.1*X[:,0],.2*X[:,1]),axis=1)
    a=np.zeros((1,4,7,2),np.float32);a[...,0]=2.;a[...,1]=.5
    d,peak=compose_delta(a,NonConstantBrow(),(4,7),band_pixels=7)
    y,x=np.mgrid[:4,:7]
    expected=np.stack((2+.1*(x-2),.5+.2*(y-.5)),axis=-1).astype(np.float32)
    assert np.array_equal(d[0],expected)
    assert peak==float(np.abs(expected).max())
    whole,_=compose_delta(a,NonConstantBrow(),(4,7),band_pixels=1000)
    assert np.array_equal(d,whole)


def test_brow_zero_returns_original_auto_field_object():
    a=np.zeros((1,2,3,2),np.float32);a[...,0]=1
    out,peak=compose_delta(a,None,(2,3))
    assert out is a and peak==1
    assert compose_delta(None,None,(2,3))==(None,0.)


def test_portable_recipe_cannot_contain_face_or_source():
    from lumaretouch_engine.brow_shape_scope import check_params
    with pytest.raises(ValueError): check_params({'recipe':S.neutral(),'landmarks':[]})
    with pytest.raises(ValueError): S.check({**S.neutral(),'source':'face.png'})
    assert check_params({'recipe':S.neutral()})=={'recipe':S.neutral()}


def test_topology_is_person_relative_and_inner_to_outer():
    from lumaretouch_engine.brow_shape_geometry import CHAINS,EYES,ANCHORS
    assert CHAINS['left']==((336,296,334,293,300),(285,295,282,283,276))
    assert CHAINS['right']==((107,66,105,63,70),(55,65,52,53,46))
    assert set(EYES['left']+EYES['right']+tuple(range(468,478))).issubset(ANCHORS)


def test_target_validation_passes_real_landmarks_and_keyword_divisor(monkeypatch):
    # Regression for the source-only review finding: export_field's divisor is keyword-only.
    from types import SimpleNamespace
    from lumaretouch_engine import brow_shape_scope as T,brow_shape_runtime as R
    from lumaretouch_engine import decode,cpu_memory_budget,local_mask_state
    pc=SimpleNamespace(landmarks=np.zeros((478,3),np.float32))
    state={'_brow_shape':S.adjust(S.neutral(),'arch','left',.1),'_precompute':pc,'_brow_shape_owner':R.identity(pc.landmarks)}
    monkeypatch.setattr(cpu_memory_budget,'available_estimate',lambda:1024**3)
    monkeypatch.setattr(local_mask_state,'file_stamp',lambda path:'same')
    monkeypatch.setattr(decode,'load_full',lambda *a,**k:SimpleNamespace(h=20,w=30,rgb=np.zeros((20,30,3),np.uint16)))
    calls=[]
    def field(spec,source,*,divisor):
        assert spec.landmarks is pc.landmarks and spec.brow_shape_face is pc
        calls.append(divisor)
    monkeypatch.setattr(R,'export_field',field)
    T.validate_target(state,{'path':'target.tif','src_h':20,'src_w':30})
    assert calls==[65535.]
