"""Independent levels math and Rust scalar reference; no engine process needed."""
import copy
import json
import subprocess
import numpy as np
import pytest
from lumaretouch_engine.ops import levels as L
from lumaretouch_engine.ops.curves import _compiler_path


def rust(image,spec):
    numbers=[spec[c][k] for c in L.CHANNELS for k in L.KEYS]
    request='levels '+str(int(spec['enabled']))+' '+' '.join(map(str,numbers))+' '+' '.join(str(float(x)) for x in image.reshape(-1))
    result=subprocess.run([str(_compiler_path())],input=request,text=True,capture_output=True,timeout=3,check=True)
    return np.asarray(json.loads(result.stdout)).reshape(image.shape)


def test_neutral_bypass_and_independent_untouched_channels():
    image=np.array([[.25,-.2,2.],[-0.,.5,1.]],np.float32)
    spec=L.default_levels();assert L.levels_np(image,spec) is image
    spec['red']['gamma']=2
    result=L.levels_np(image,spec)
    assert result[0,0]==.5 and np.array_equal(result[:,1:],image[:,1:])
    spec['enabled']=False;assert L.levels_np(image,spec) is image


def test_schema_rejects_invalid_parameters_and_owns_channels():
    original=L.default_levels();result=L.check_levels(original);result['red']['gamma']=2
    assert original['red']['gamma']==1
    for channel,key,value in [('master','gamma',0),('master','gamma',True),('red','input_white',0),('blue','input_black',float('nan')),('green','output_white',2)]:
        bad=copy.deepcopy(original);bad[channel][key]=value
        with pytest.raises(ValueError):L.check_levels(bad)
    for key,value in [('version',True),('version',2),('space','linear'),('enabled',1),('extra',0)]:
        bad=copy.deepcopy(original);bad[key]=value
        with pytest.raises(ValueError):L.check_levels(bad)


def test_reference_gamma_clipping_master_order_and_output_inversion():
    image=np.array([[-.2,.2,1.2],[.4,.5,.8],[0.,1.,.25]],np.float32)
    spec=L.default_levels();spec['master'].update(input_black=.1,input_white=.9,gamma=2,output_black=.1,output_white=.9)
    spec['red'].update(gamma=.7);spec['blue'].update(output_black=1,output_white=0)
    actual=L.levels_np(image,spec)
    assert actual.dtype==image.dtype and np.max(np.abs(actual-rust(image,spec)))<2e-6
    assert np.isfinite(actual).all()


def test_torch_cpu_reference_and_neutral_object_identity():
    torch=pytest.importorskip('torch')
    image=np.random.default_rng(2).uniform(-.1,1.1,(13,17,3)).astype(np.float32)
    tensor=torch.from_numpy(image.transpose(2,0,1)[None].copy());spec=L.default_levels()
    assert L.levels_t(tensor,L.parameters(spec)) is tensor
    spec['green'].update(input_black=.1,input_white=.8,gamma=1.8)
    actual=L.levels_t(tensor,L.parameters(spec)).numpy()[0].transpose(1,2,0)
    assert np.max(np.abs(actual-L.levels_np(image,spec)))<2e-6
