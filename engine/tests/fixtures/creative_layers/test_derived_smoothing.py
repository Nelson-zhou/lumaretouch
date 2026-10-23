"""AUTHORED / UNRUN: smoothing source contracts, not model/visual acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_smoothing as S,creative_derived_source as D
from lumaretouch_engine import export as E
from lumaretouch_engine import local_mask_state as M


def recipe(channel='skin'):
    return {'strength':.4,'channel':channel,'params':{'radius':12,'eps':.01,
        'texture_radius':3,'detail_gain':1.,'mid_gain':.7,'broad_gain':.5}}


def context(channel='skin'):
    source={'sha256':'1'*64,'width':8,'height':6}
    mask=np.array([[0.,.1,.2,.3],[.4,.5,.6,.7],[.8,.9,1.,0.]],np.float32)
    return {'version':1,'source':source,'original_sha256':'2'*64,'recipe':recipe(channel),
        'analysis':None if channel is None else {**source,'proxy_width':4,'proxy_height':3,'proxy_sha256':'3'*64},
        'semantic_owner':None if channel is None else {'backend':'mediapipe','contract':M.SEMANTIC_CONTRACT+':'+'4'*64},
        'mask':None if channel is None else mask,'mask_sha256':None if channel is None else S._hash(mask)}


def spec(value):
    return SimpleNamespace(creative_base=object(),creative_smoothing_context=value,
        strength=value['recipe']['strength'],channel=value['recipe']['channel'],repair=[],
        **value['recipe']['params'])


def test_exact_existing_solver_recipe_and_semantic_names():
    assert S.check_recipe(recipe())==recipe()
    for field,bad in [('strength',True),('strength',1.1),('channel','person-instance')]:
        value=recipe();value[field]=bad
        with pytest.raises(ValueError):S.check_recipe(value)
    for key,bad in [('radius',1.5),('texture_radius',0),('eps',0.),('mid_gain',np.nan)]:
        value=recipe();value['params'][key]=bad
        with pytest.raises(ValueError):S.check_recipe(value)


def test_owned_conservative_weights_are_not_replaced_with_raw_probability():
    value=context();assert S.verify_context(value,value['source']) is value
    changed=deepcopy(value);changed['mask']=(changed['mask']+1)/2
    with pytest.raises(ValueError):S.verify_context(changed,value['source'])
    foreign={**value['source'],'sha256':'5'*64}
    with pytest.raises(ValueError):S.verify_context(value,foreign)
    changed=deepcopy(value);changed['analysis']['sha256']='5'*64
    with pytest.raises(ValueError):S.verify_context(changed,value['source'])


def test_unmasked_intent_requires_no_model_and_has_no_hidden_mask():
    value=context(None);assert S.verify_context(value,value['source']) is value
    value['mask']=np.ones((3,4),np.float32)
    with pytest.raises(ValueError):S.verify_context(value,value['source'])


def test_snapshot_recipe_and_canonical_float_pixels_cannot_change(monkeypatch):
    value=context(None);target=spec(value);pixels=np.full((6,8,3),.400001,np.float32)
    monkeypatch.setattr(D,'binding',lambda owner:value['source'])
    with pytest.raises(ValueError):S.verify_export(target,pixels,None,1.)
    S.stamp_pixels(target,pixels)
    assert S.verify_export(target,pixels,None,1.) is pixels
    changed=pixels.copy();changed[0,0,0]+=.001
    with pytest.raises(ValueError):S.verify_export(target,changed,None,1.)
    with pytest.raises(ValueError):S.verify_export(target,pixels,None,255.)
    target.detail_gain=1.5
    with pytest.raises(ValueError):S.verify_export(target,pixels,None,1.)


@pytest.mark.parametrize('bad',[np.nan,-.1,1.1])
def test_float_export_never_clips_signed_hdr_or_nonfinite(monkeypatch,bad):
    value=context(None);target=spec(value);pixels=np.full((6,8,3),.4,np.float32)
    monkeypatch.setattr(D,'binding',lambda owner:value['source'])
    pixels[0,0,0]=bad
    with pytest.raises(ValueError):S.stamp_pixels(target,pixels)


def test_full_size_resampling_is_owned_and_not_a_proxy_filtered_result(monkeypatch):
    value=context();target=spec(value);pixels=np.full((6,8,3),.4,np.float32)
    monkeypatch.setattr(D,'binding',lambda owner:value['source'])
    monkeypatch.setattr(S,'verify_snapshot',lambda snapshot:value)
    seen=[]
    def resize(field,shape):
        seen.append((field.copy(),shape));return np.full((1,*shape),.25,np.float32)
    monkeypatch.setattr(E,'resample_field',resize)
    S.configure_export(target,{},6,8);S.stamp_pixels(target,pixels)
    assert seen[0][1]==(6,8)
    np.testing.assert_array_equal(seen[0][0][0],value['mask'])
    assert S.verify_export(target,pixels,None,1.) is pixels
    target.masks[0,0,0]=.5
    with pytest.raises(ValueError):S.verify_export(target,pixels,None,1.)


def test_zero_command_can_clear_without_inference_but_unknown_fields_refuse(monkeypatch):
    value=recipe();engine=SimpleNamespace(_strength=value['strength'],_channel='skin',_params=value['params'])
    monkeypatch.setattr(S,'preview',lambda *args:(_ for _ in ()).throw(ValueError('no evidence')))
    assert S.require_command(engine,{'cmd':'set_strength','value':0})['strength']==0
    with pytest.raises(ValueError):S.require_command(engine,{'cmd':'set_strength','value':.5})
    with pytest.raises(ValueError):S.require_command(engine,{'cmd':'set_strength','value':0,'mask':[]})
    with pytest.raises(ValueError):S.require_command(engine,{'cmd':'set_strength','value':0,'channel':False})


def test_existing_neutral_derived_snapshot_needs_no_new_context(monkeypatch):
    monkeypatch.setattr(D,'record',lambda owner:object())
    assert S.verify_snapshot({'creative_base':object()}) is None
    assert S.verify_snapshot({'creative_base':object(),'strength':0,'channel':None}) is None
    with pytest.raises(ValueError):S.verify_snapshot({'creative_base':object(),'creative_smoothing_context':context()})


def test_positive_named_scope_refuses_empty_support_but_zero_retains_intent():
    value=context();value['mask'][:]=0;value['mask_sha256']=S._hash(value['mask'])
    with pytest.raises(ValueError):S.verify_context(value,value['source'])
    value['recipe']['strength']=0
    assert S.verify_context(value,value['source'])['recipe']['channel']=='skin'


def test_capture_retains_actual_conservative_edit_weight_and_model_identity(monkeypatch):
    value=context();pc=SimpleNamespace(backend='mediapipe',masks={'skin':value['mask']},
        semantic_model_sha256='4'*64,input_source_binding=value['analysis'])
    owner={'_precompute':pc,'_strength':.4,'_channel':'skin','_params':recipe()['params']}
    monkeypatch.setattr(D,'binding',lambda actual:value['source'])
    seen=[];monkeypatch.setattr(D,'verify_precompute',lambda actual,analysis:seen.append(analysis))
    monkeypatch.setattr(S,'_provenance',lambda actual,path:'2'*64)
    from lumaretouch_engine import creative_document_host as H
    monkeypatch.setattr(H,'memory_budget',lambda:128_000_000)
    captured=S.capture(owner,'original')
    assert seen==[pc] and captured['mask'] is not value['mask']
    np.testing.assert_array_equal(captured['mask'],value['mask'])
    assert not captured['mask'].flags.writeable
    assert captured['semantic_owner']==value['semantic_owner']
    pc.masks['skin'][0,1]=.9
    assert captured['mask'][0,1]==np.float32(.1)
