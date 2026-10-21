import numpy as np
import pytest
from lumaretouch_engine.quant import quantize16_np
from lumaretouch_engine.ops.upscale import unsharp_float_bands_np,blur_np


def test_quant16_rounds_ties_to_even_clips_and_preserves_source():
    values=np.array([0,.5/65535,1.5/65535,2.5/65535,1,-.5,1.5],np.float64)
    a=np.repeat(values[:,None,None],3,axis=2);before=a.copy()
    got=quantize16_np(a,chunk_pixels=2)
    np.testing.assert_array_equal(got[:,0,0],[0,0,2,2,65535,0,65535])
    np.testing.assert_array_equal(a,before)


def test_quant16_keeps_every_source_code_and_noncontiguous_order():
    a=np.repeat(np.arange(65536,dtype=np.uint16).reshape(256,256,1),3,axis=2)
    f=a.astype(np.float32)/65535
    np.testing.assert_array_equal(quantize16_np(f[:,::-1],chunk_pixels=31),a[:,::-1])


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-float('inf')])
def test_quant16_rejects_nonfinite_before_returning_an_image(bad):
    a=np.zeros((2,3,3),np.float32);a[1,2,0]=bad
    with pytest.raises(ValueError,match='nonfinite'):quantize16_np(a,chunk_pixels=2)


def test_float_sharpen_bands_match_whole_formula_without_integer_step():
    a=np.random.default_rng(18).random((67,49,3)).astype(np.float32)
    x=a.astype(np.float64);d=x-blur_np(x,1.2);d=np.where(np.abs(d)<.01,0,d)
    expected=(x+.23*d).astype(np.float32)
    got=unsharp_float_bands_np(a,1.2,.23,.01,band=13)
    np.testing.assert_array_equal(got,expected)
