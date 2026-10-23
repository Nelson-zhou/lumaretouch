"""AUTHORED / UNRUN: deterministic legacy replay and lifecycle contracts."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import common_background_source as C


def record():
    return {'active':True,'backend':'color_key','bg':[0.,0.,1.],
        'tol':.12,'softness':.10,'matte':np.ones((2,3),np.uint8),
        'key_recipe':{'version':1,'contract':C.CONTRACT,
            'source':{'sha256':'a'*64,'width':3,'height':2},
            'reference':[0.,0.,0.],'reference_grid':[3,2],'tol':.12,'softness':.10}}


def spec(bg=None):
    bg=record() if bg is None else bg
    return SimpleNamespace(common_background_key=bg['key_recipe'],common_background_color=tuple(bg['bg']),
        common_background_path='/owned/source.png',common_background_stamp=[1,2],
        creative_base=None,bg_matte=None,bg_ref=None)


def test_key_recipe_rejects_parameter_drift_and_wrong_backend():
    for key,value in (('tol',.3),('backend','birefnet'),('bg',[float('nan'),0.,0.])):
        bg=record();bg[key]=value
        with pytest.raises(ValueError):C.check(bg)


def test_old_matte_is_not_upgraded():
    bg=record();del bg['key_recipe']
    assert C.check(bg) is None
    target=SimpleNamespace(creative_base=None)
    assert C.configure_export(target,{'_bg':bg},for_document=True) is False


def test_proxy_change_preserves_only_recipe_intent():
    original=record();out={}
    C.preserve_proxy_recipe({'_bg':original},out)
    assert out['_bg']['matte'] is None
    assert out['_bg']['key_recipe']==original['key_recipe']
    out['_bg']['key_recipe']['reference'][0]=.5
    assert original['key_recipe']['reference'][0]==0.


def test_cross_photo_and_derived_export_refuse():
    for document,base in ((False,None),(True,{'id':'derived'})):
        with pytest.raises(ValueError):C.configure_export(SimpleNamespace(creative_base=base),{'_bg':record()},for_document=document)


def test_full_rgb16_replay_does_not_clip_integer_input(monkeypatch):
    from lumaretouch_engine import cpu_memory_budget
    monkeypatch.setattr(C.M,'file_stamp',lambda path:(1,2))
    monkeypatch.setattr(C.M,'verify_source',lambda *a:None)
    monkeypatch.setattr(cpu_memory_budget,'available_estimate',lambda:2*1024**3)
    pixels=np.full((2,3,3),6000,np.uint16)
    target=spec();C.prepare_export(target,pixels)
    from lumaretouch_engine.ops.matting import key_matte_np
    expected=key_matte_np(pixels.astype(np.float64)/65535.,ref=[0.,0.,0.],tol=.12,softness=.10)
    np.testing.assert_allclose(target.bg_matte,expected,rtol=1e-6)
    assert target.bg_matte.dtype==np.float32
    assert target.bg_ref==(0.,0.,1.)


def test_changed_source_stamp_and_float_input_refuse():
    target=spec();target.common_background_stamp=None
    with pytest.raises(ValueError):C.finish_export(target)
    with pytest.raises(ValueError):C.prepare_export(target,np.zeros((2,3,3),np.float32))


def test_cancelled_replay_never_leaves_previous_field(monkeypatch):
    from lumaretouch_engine import cpu_memory_budget
    monkeypatch.setattr(C.M,'file_stamp',lambda path:(1,2))
    monkeypatch.setattr(C.M,'verify_source',lambda *a:None)
    monkeypatch.setattr(cpu_memory_budget,'available_estimate',lambda:2*1024**3)
    target=spec();target.bg_matte=np.ones((2,3));target.bg_ref=(1.,1.,1.)
    with pytest.raises(InterruptedError):C.prepare_export(target,np.zeros((2,3,3),np.uint8),cancelled=lambda:True)
    assert target.bg_matte is None and target.bg_ref is None


def test_boolean_recipe_version_is_not_a_version():
    bg=record();bg['key_recipe']['version']=True
    with pytest.raises(ValueError):C.check(bg)


def test_history_tracks_recipe_not_disposable_bitmap():
    from lumaretouch_engine.history_policy import state_signature
    first=record();second=deepcopy(first);second['matte']=None
    assert state_signature({'_bg':first})==state_signature({'_bg':second})
    second['key_recipe']['reference'][0]=.1
    assert state_signature({'_bg':first})!=state_signature({'_bg':second})


def test_recipe_project_validation_reaches_nested_history():
    from lumaretouch_engine.id_background_project import validate_records
    bg=record();bg['key_recipe']['source']['sha256']='not-a-source'
    with pytest.raises(ValueError):validate_records({'undo':[{'_bg':bg}]})


def test_full_source_consumers_bind_common_decode_before_build():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'src'/'lumaretouch_engine'
    for name in ('photo_grain_runtime.py','optics_transfer_engine.py','reference_color_engine.py'):
        text=(root/name).read_text()
        binding=text.index('common_background_source as common_background')
        assert binding<text.index('spec,skipped=build_export_spec',binding)
        assert 'common_background)' in text[binding:]
