"""LibRaw's default BT.709-like transfer cannot be tagged as standard sRGB."""
import ctypes as C
import numpy as np
import pytest
from lumaretouch_engine.ops import libraw as lr
from lumaretouch_engine.raw import srgb_encode


@pytest.mark.skipif(not lr.available(),reason='matching LibRaw runtime unavailable')
def test_raw_output_uses_srgb_transfer_not_libraw_default(monkeypatch):
    lib=lr.load_lib()
    encoded,info=lr.process(lr.PROBE_DNG,output_bps=16)
    lib.libraw_set_gamma.argtypes=[C.c_void_p,C.c_int,C.c_float]
    lib.libraw_set_gamma.restype=None
    process=lib.libraw_dcraw_process
    def linear_reference(handle):
        lib.libraw_set_gamma(handle,0,1.0)
        lib.libraw_set_gamma(handle,1,1.0)
        return process(handle)
    with monkeypatch.context() as m:
        m.setattr(lib,'libraw_dcraw_process',linear_reference)
        linear,_=lr.process(lr.PROBE_DNG,output_bps=16)
    expected=np.rint(srgb_encode(linear.astype(np.float64)/65535)*65535)
    # The reference itself was rounded to uint16 before gamma: <=0.5 LSB
    # amplified by max sRGB slope 12.92, plus output rounding (<8 LSB total).
    error=np.abs(encoded.astype(np.float64)-expected)
    assert error.max() <= 8, (error.max(),error.mean())
    assert info['output_color_space']=='sRGB'
    assert info['output_gamma']==[1/2.4,12.92]


@pytest.mark.skipif(not lr.available(),reason='matching LibRaw runtime unavailable')
def test_eight_and_sixteen_bit_raw_have_the_same_transfer():
    a16,info16=lr.process(lr.PROBE_DNG,output_bps=16)
    a8,info8=lr.process(lr.PROBE_DNG,output_bps=8)
    assert np.array_equal(a8,(a16>>8).astype(np.uint8))
    assert info8['output_gamma']==info16['output_gamma']
