"""Actual packaged Rust ABI, independent decimal oracle, and production stage hooks."""
from decimal import Decimal, localcontext
from types import SimpleNamespace
import subprocess
import numpy as np
import pytest
from lumaretouch_engine import white_balance_math as M, white_balance_recipe as R
from lumaretouch_engine.ops import exposure as E


@pytest.fixture(autouse=True)
def clear_cache():
    M._request.cache_clear()
    yield
    M._request.cache_clear()


def oracle(reference, shift, tint):
    """Test-only 60-digit Gauss-Jordan solves, not Rust's inverse/cofactor code."""
    with localcontext() as ctx:
        ctx.prec = 60
        D = lambda x: Decimal(str(x))
        B = [[D(x) for x in row] for row in ((.8951,.2664,-.1614),(-.7502,1.7135,.0367),(.0389,-.0685,1.0296))]
        A = [[D(a)/D(b) for a,b in row] for row in (
            ((506752,1228815),(87881,245763),(12673,70218)),
            ((87098,409605),(175762,245763),(12673,175545)),
            ((7918,409605),(87881,737289),(1001167,1053270))) ]
        def solve(matrix, rhs):
            aug = [list(row)+[rhs[i]] for i,row in enumerate(matrix)]
            for col in range(3):
                pivot = max(range(col,3), key=lambda i: abs(aug[i][col]))
                aug[col], aug[pivot] = aug[pivot], aug[col]
                div = aug[col][col]
                aug[col] = [v/div for v in aug[col]]
                for i in range(3):
                    if i == col: continue
                    factor = aug[i][col]
                    aug[i] = [a-factor*b for a,b in zip(aug[i],aug[col])]
            return [row[-1] for row in aug]
        def white(k, t):
            k = D(k); t = D(t)
            if k <= 7000:
                x = -D(4607000000)/k**3 + D(2967800)/k**2 + D('99.11')/k + D('.244063')
            else:
                x = -D(2006400000)/k**3 + D(1901800)/k**2 + D('247.48')/k + D('.237040')
            y = -3*x*x + D('2.870')*x - D('.275')
            xyz = [x/y,D(1),(1-x-y)/y]
            cone = [sum(a*b for a,b in zip(row,xyz)) for row in B]
            cone[0] *= 1+D('.1')*t; cone[1] *= 1-D('.1')*t
            rgb = solve(A,solve(B,cone)); total = sum(rgb)
            return [v/total for v in rgb]
        source = white(reference,0); target = white(D(reference)+D(shift),tint)
        return tuple(float(t/s) for t,s in zip(target,source))


@pytest.mark.parametrize('reference,shift,tint', [(4500,500,.6),(6500,1500,-.8),(9000,-1800,.3),(23000,1500,-.7)])
def test_actual_rust_combined_gains_against_independent_decimal_oracle(reference,shift,tint):
    assert np.allclose(M.manual_gains(reference,shift,tint),oracle(reference,shift,tint),rtol=2e-13,atol=2e-13)


def test_actual_rust_wire_rejects_malformed_and_oversized_requests():
    for payload in ('white-balance-v1 manual 6500 0', 'white-balance-v1 manual 6500 0 0 extra',
                    'white-balance-v1 manual nan 0 0', 'white-balance-v1 unknown 1',
                    'white-balance-v1 neutral 0 .2 .3 1 1 1', 'x'*16385):
        result = subprocess.run([str(M._helper_path())],input=payload,text=True,capture_output=True,timeout=3)
        assert result.returncode != 0 and not result.stdout


def test_strict_inputs_and_options_own_their_nested_values():
    for value in (True,'6500',float('nan'),10**10000):
        with pytest.raises(ValueError): M.manual_gains(value,0,0)
    for value in (None,{}, {'version':True,'algorithm':R.LEGACY,'picked_gains':[1,1,1]},
                  {'version':1,'algorithm':'unknown','picked_gains':[1,1,1]},
                  {'version':1,'algorithm':R.LEGACY,'picked_gains':[1,False,1]}):
        with pytest.raises(ValueError): R.check_options(value)
    original=R.default_options(); checked=R.check_options(original);checked['picked_gains'][0]=2
    assert original['picked_gains']==[1,1,1]


def test_missing_helper_has_no_fallback(monkeypatch,tmp_path):
    monkeypatch.setattr(M,'_helper_path',lambda:tmp_path/'missing')
    with pytest.raises(RuntimeError): M.manual_gains(6500,0,0)


@pytest.mark.parametrize('reply',['{}','{"version":true,"action":"manual","gains":[1,1,1]}','{"version":1,"action":"manual","gains":[1,0,1]}',
                                  '{"version":1,"action":"manual","gains":[1,NaN,1]}',
                                  '{"version":1,"action":"neutral","gains":[1,1,1]}','x'*513])
def test_invalid_helper_reply_is_not_cached(monkeypatch,tmp_path,reply):
    helper=tmp_path/'helper';helper.touch()
    monkeypatch.setattr(M,'_helper_path',lambda:helper)
    monkeypatch.setattr(M.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=reply,stderr=''))
    with pytest.raises(ValueError): M.manual_gains(6500,0,0)
    assert M._request.cache_info().currsize==0


def test_legacy_prepared_path_preserves_pixels_and_corrected_picks_change_them():
    image=np.linspace(0,1,63,dtype=np.float32).reshape(3,7,3)
    for shift,tint in ((0,0),(1000,.2),(-800,-.6)):
        legacy=R.compile_gains(R.default_options(),6500,shift,tint)
        assert np.array_equal(E.exposure_np(image,.5,shift,tint),E.exposure_np(image,.5,shift,tint,prepared_wb=legacy))
    corrected=R.default_options(R.CORRECTED);corrected['picked_gains']=[1.2,.8,1.1]
    gains=R.compile_gains(corrected,6500,0,0)
    assert not np.array_equal(E.exposure_np(image),E.exposure_np(image,prepared_wb=gains))


def test_pipeline_prepares_once_reuses_vector_and_rejects_atomically(monkeypatch):
    torch=pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline
    pipe=PreviewPipeline.__new__(PreviewPipeline)
    pipe.device=torch.device('cpu');pipe.clear_exposure()
    image=torch.full((1,3,3,3),.4)
    assert pipe.apply_exposure(image) is image
    options=R.default_options(R.CORRECTED);options['picked_gains']=[1.2,.8,1.1]
    pipe.set_exposure(wb_options=options)
    before=(pipe.exposure_params,pipe.exposure_ref_k,pipe.wb_options,pipe.prepared_wb)
    assert pipe.has_exposure()
    monkeypatch.setattr(M,'_request',lambda *a: (_ for _ in ()).throw(AssertionError('helper called from render')))
    actual=pipe.apply_exposure(image)
    expected=E.exposure_np(image.numpy().transpose(0,2,3,1),prepared_wb=before[3])
    assert np.allclose(actual.numpy().transpose(0,2,3,1),expected,atol=1e-7)
    for raw in (True, '500'):
        with pytest.raises(ValueError): pipe.set_exposure(temperature_shift=raw,wb_options=options)
    with pytest.raises(ValueError): pipe.set_exposure(ref_k=0,wb_options=options)
    underflow=R.default_options();underflow['picked_gains']=[5e-324,1,1]
    with pytest.raises(ValueError): pipe.set_exposure(ev=-1,wb_options=underflow)
    overflow=R.default_options();overflow['picked_gains']=[1e308,1,1]
    with pytest.raises(ValueError): pipe.set_exposure(ev=5,wb_options=overflow)
    with pytest.raises(AssertionError): pipe.set_exposure(temperature_shift=500,wb_options=options)
    with pytest.raises(ValueError): pipe.set_exposure(wb_options={'version':99})
    assert (pipe.exposure_params,pipe.exposure_ref_k,pipe.wb_options,pipe.prepared_wb)==before
    pipe.clear_exposure();assert pipe.apply_exposure(image) is image


def test_actual_neutral_replacement_and_cached_result_are_immutable(monkeypatch):
    mean=(.12,.24,.36); manual=M.manual_gains(6500,500,.2)
    result=M.neutral_gains(mean,manual)
    q=np.asarray(mean)*manual
    corrected=q*result
    expected=np.dot(q,[87098/409605,175762/245763,12673/175545])
    assert np.allclose(corrected,expected,atol=1e-14,rtol=1e-14)
    monkeypatch.setattr(M.subprocess,'run',lambda *a,**k: (_ for _ in ()).throw(AssertionError('cache missed')))
    assert M.neutral_gains(mean,manual) is result
    assert isinstance(result,tuple) and M._request.cache_info().maxsize==256
