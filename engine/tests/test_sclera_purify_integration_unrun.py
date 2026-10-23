"""AUTHORED / UNRUN. Synthetic geometry/schema contracts, not photo quality."""
from pathlib import Path
import numpy as np
import pytest
from lumaretouch_engine import sclera_purify_apply as P, under_eye_layer as U
from lumaretouch_engine import enhance_scope as S, people_algorithms as A
from lumaretouch_engine.ops import enhance as H


def landmarks(radius=8):
    lm=np.full((478,3),.5,np.float32)
    for cx,ring,iris,rim in ((32,H.EYE_RING_LEFT,H.IRIS_LEFT,H.IRIS_RIM_LEFT),
                             (96,H.EYE_RING_RIGHT,H.IRIS_RIGHT,H.IRIS_RIM_RIGHT)):
        lm[iris,:2]=[cx/128,30/64]
        for i,index in enumerate(ring):
            angle=.017+i*2*np.pi/len(ring)
            lm[index,:2]=[(cx+26*np.cos(angle))/128,(30+12*np.sin(angle))/64]
        for i,index in enumerate(rim):
            angle=i*2*np.pi/len(rim)
            lm[index,:2]=[(cx+radius*np.cos(angle))/128,(30+radius*np.sin(angle))/64]
    return lm


def source():
    return np.broadcast_to(np.array([.6,.58,.5],np.float32),(64,128,3)).copy()


def test_candidates_are_per_eye_with_exact_iris_exclusion():
    regions,facts=P.regions(source(),landmarks())
    assert len(regions)==2 and len(facts)==2
    for (y,x,h,w),mask,radius,index in regions:
        yy,xx=np.mgrid[y:y+h,x:x+w]
        centre=32 if index==0 else 96
        assert not np.any(mask[np.hypot(xx+.5-centre,yy+.5-30)<1.2*8-1e-5])
        assert mask.shape==(h,w) and mask.dtype==np.float32 and np.any(mask>.15)
        assert radius==1
    assert H.SUBS==('sclera','iris','teeth')
    assert 'sclera_purify' not in H.PIXEL_KEYS


def test_tiny_eye_or_dark_support_refuses_without_expansion():
    with pytest.raises(ValueError,match='眼白支持'):P.regions(source(),landmarks(.4))
    with pytest.raises(ValueError,match='眼白支持'):P.regions(np.zeros((64,128,3),np.float32),landmarks())


def test_roi_admission_precedes_grid_allocation(monkeypatch):
    from lumaretouch_engine import sclera_purify_native as N
    class ForbiddenGrid:
        def __getitem__(self,key):pytest.fail('Allocated grid before admission')
    def reject(*args):raise MemoryError('fixture budget')
    monkeypatch.setattr(N,'_admit',reject)
    monkeypatch.setattr(P.np,'mgrid',ForbiddenGrid())
    with pytest.raises(MemoryError,match='fixture budget'):P.regions(source(),landmarks())


def test_full_face_private_buffer_admission_precedes_native(monkeypatch):
    from lumaretouch_engine import cpu_memory_budget as B
    monkeypatch.setattr(B,'available_estimate',lambda:0)
    monkeypatch.setattr(U.PURIFY,'correct',lambda *a,**kw:pytest.fail('Native before host budget'))
    layer=U.UnderEyeLayer((0,0,64,128),source(),landmarks()[:,:2]*[128,64])
    with pytest.raises(MemoryError):layer.solve({'sclera_purify':.5})


def test_native_receives_each_original_eye_not_another_corrected_eye(monkeypatch):
    from lumaretouch_engine import sclera_purify_native as N
    inputs=[]
    def copy(rgb,mask,amount,radius,**kw):
        inputs.append((rgb.copy(),mask.copy(),radius))
        return rgb.copy()
    monkeypatch.setattr(N,'apply',copy)
    original=source();out,facts=P.correct(original,landmarks(),.5)
    assert len(inputs)==2
    assert facts['reason']=='no_eligible_local_sclera_correction'
    np.testing.assert_array_equal(out,original)
    assert all(np.all(rgb==np.array([.6,.58,.5],np.float32)) for rgb,_,_ in inputs)


def test_new_only_route_does_not_call_red_eye_or_opencv(monkeypatch):
    from lumaretouch_engine import sclera_purify_native as N
    monkeypatch.setattr(N,'apply',lambda rgb,*args,**kw:rgb.copy())
    monkeypatch.setattr(U.EYES,'cv2',None)
    monkeypatch.setattr(U.RED_EYE,'correct',lambda *a,**kw:pytest.fail('Misrouted to red-eye'))
    monkeypatch.setattr(U.EYES,'apply',lambda *a:pytest.fail('Called under-eye algorithm'))
    monkeypatch.setattr(U.DETAIL,'apply',lambda *a:pytest.fail('Called vessel algorithm'))
    layer=U.UnderEyeLayer((0,0,64,128),source(),landmarks()[:,:2]*[128,64])
    delta=layer.solve({'sclera_purify':.5})
    assert not np.any(delta) and layer.facts['sclera_purify']['geom_px']>0
    assert layer.facts['red_eye']['reason']=='disabled'


def test_purify_and_red_eye_measure_the_same_untouched_source(monkeypatch):
    original=source();seen=[]
    def solver(rgb,lm,amount,**kw):
        seen.append(rgb.copy());out=rgb.copy();out[1,1 if amount<.5 else 2,0]-=.01
        return out,{'gated_px':1,'geom_px':1,'reason':None}
    monkeypatch.setattr(U.RED_EYE,'correct',solver)
    monkeypatch.setattr(U.PURIFY,'correct',solver)
    values=dict.fromkeys(U.KEYS,0.);values.update(red_eye=.4,sclera_purify=.6)
    U.correct(original,landmarks(),tuple(values[k] for k in U.KEYS))
    assert len(seen)==2
    for image in seen:np.testing.assert_array_equal(image,original)


@pytest.mark.parametrize('value',[True,None,'0.5',-.1,1.1,float('nan')])
def test_scalar_validation(value):
    with pytest.raises(ValueError):H.check_amounts({'sclera_purify':value})


def test_presets_are_only_scalars_and_old_recipes_default_to_zero():
    assert H.check_amounts({'sclera':.5})['sclera_purify']==0
    assert '/sclera_purify' in A.defaults()[A.ENHANCE]
    raw={'recipe':{'version':1,'amounts':{'sclera_purify':.3}}}
    assert S.check_params(raw)['recipe']['amounts']['sclera_purify']==.3
    with pytest.raises(ValueError):S.check_params({'recipe':{'version':1,'amounts':{'mask':[]}}})


def test_hard_failure_export_and_replay_guards_remain():
    root=Path(__file__).resolve().parents[1]/'src'/'lumaretouch_engine'
    assert 'ENH.PURIFY.active(enh_amounts)' in (root/'export_recipe.py').read_text()
    assert 'ENH.PURIFY.active(self._enhance.get("amounts",{}))' in (root/'server.py').read_text()
    assert 'except (ENH.EnhanceError, ValueError, RuntimeError, MemoryError, OSError) as e:' in (root/'server.py').read_text()
