from types import SimpleNamespace
import math
import pytest
from lumaretouch_engine import white_balance_pick_math as P
from lumaretouch_engine import white_balance_math as M


def test_actual_helper_preserves_linear_mean_y_and_returns_replacement():
    rows=((.1,.2,.3,1,0),(.3,.4,.5,1,0));manual=(.9,1,1.2)
    actual=P.calculate(rows,manual)
    expected=tuple(math.fsum(row[c] for row in rows)/2 for c in range(3))
    assert actual.mean_linear==pytest.approx(expected,abs=1e-15)
    q=tuple(v*m for v,m in zip(expected,manual))
    y=sum(v*w for v,w in zip(q,(87098/409605,175762/245763,12673/175545)))
    assert tuple(v*g for v,g in zip(q,actual.gains))==pytest.approx((y,y,y),abs=1e-14)
    assert P.calculate(rows,manual)==actual and actual.samples==2 and actual.policy==P.POLICY


@pytest.mark.parametrize('rows,manual',[
    ([],(1,1,1)),([(.2,.2,.2,1,0)]*122,(1,1,1)),
    ([(True,.2,.2,1,0)],(1,1,1)),([('0.2',.2,.2,1,0)],(1,1,1)),
    ([(float('nan'),.2,.2,1,0)],(1,1,1)),([(.2,.2,.2,1,0)],(False,1,1)),
    ([(.2,.2,.2,.9,0)],(1,1,1)),([(.2,.2,.2,1,1e-20)],(1,1,1)),
    ([(.00001,.2,.2,1,0)],(1,1,1)),([(.001,.8,.8,1,0)],(1,1,1)),
    ([(.2,.2,.2,1,0)],(17,17,17)),
])
def test_invalid_or_unsafe_regions_reject_whole_action(rows,manual):
    with pytest.raises(ValueError):P.calculate(rows,manual)


@pytest.mark.parametrize('reply',[
    '{}','{"version":true,"policy":"proxy-linear-neutral-v1","samples":1,"mean_linear":[0.2,0.2,0.2],"gains":[1,1,1]}',
    '{"version":1,"policy":"proxy-linear-neutral-v1","samples":2,"mean_linear":[0.2,0.2,0.2],"gains":[1,1,1]}',
    '{"version":1,"policy":"proxy-linear-neutral-v1","samples":1,"mean_linear":[0.2,0.2,0.2],"gains":[1,NaN,1]}',
    '{"version":1,"policy":"wrong","samples":1,"mean_linear":[0.2,0.2,0.2],"gains":[1,1,1]}',
    'x'*1025,
])
def test_invalid_reply_never_becomes_a_recipe(monkeypatch,tmp_path,reply):
    helper=tmp_path/'helper';helper.touch();monkeypatch.setattr(M,'_helper_path',lambda:helper)
    monkeypatch.setattr(P.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=reply,stderr=''))
    with pytest.raises(ValueError):P.calculate([(.2,.2,.2,1,0)],(1,1,1))


def test_missing_helper_has_no_python_fallback(monkeypatch,tmp_path):
    monkeypatch.setattr(M,'_helper_path',lambda:tmp_path/'missing')
    with pytest.raises(RuntimeError):P.calculate([(.2,.2,.2,1,0)],(1,1,1))


def test_maximum_region_fits_existing_bounded_abi():
    result=P.calculate([(.2,.3,.4,1,0)]*121,(1,1,1))
    assert result.samples==121 and len(result.gains)==3
