"""Real CPU stage/preview parity fixtures, to be run by Qoder/CI, not locally."""
from copy import deepcopy
import base64
import io
import numpy as np
import pytest
from PIL import Image
from lumaretouch_engine.color_picker_sampling import stage
from lumaretouch_engine import color_picker_sampling as S
from lumaretouch_engine.color_picker_preview import freeze, render
from lumaretouch_engine.ops import levels as L, curves as C, hsl as H


def test_preview_uses_real_hsl_operator_and_is_bounded():
    torch=pytest.importorskip('torch')
    source=torch.tensor([[[[1.]],[[0.25]],[[0.]]]],dtype=torch.float32).expand(1,3,600,700)
    frozen=freeze(source);bands=[0.]*24;bands[0]=10.;bands[3]=20.
    preview=render(frozen,'hsl','master',bands)
    pixels=np.asarray(Image.open(io.BytesIO(base64.b64decode(preview['data']))))
    from lumaretouch_engine.quant import quantize_t
    truth=quantize_t(H.hsl_t(frozen,bands)[0].permute(1,2,0)).numpy()
    assert np.array_equal(pixels,truth);assert max(pixels.shape[:2])==512
    assert source.shape[-2:]==(600,700)


def test_tool_curve_preview_does_not_apply_upstream_master_twice():
    torch=pytest.importorskip('torch')
    if not C._compiler_path().is_file():pytest.skip('packaged Rust helper required')
    recipe=C.default_curves();recipe['master']=[[0.,0.2],[1.,0.8]];recipe['red']=[[0.,0.],[1.,0.7]]
    # This frozen value already includes master. Only selected red is applied.
    frozen=torch.tensor([[[[0.4]],[[0.5]],[[0.6]]]],dtype=torch.float32)
    before=deepcopy(recipe);preview=render(frozen,'curve','red',recipe)
    pixels=np.asarray(Image.open(io.BytesIO(base64.b64decode(preview['data']))))
    selected=C.default_curves();selected['red']=recipe['red']
    from lumaretouch_engine.quant import quantize_t
    truth=quantize_t(C.curves_t(frozen,C.tensor_bundles(selected,frozen.device,frozen.dtype))[0].permute(1,2,0)).numpy()
    assert np.array_equal(pixels,truth) and recipe==before


def test_node_stage_order_matches_production_without_mutation(monkeypatch):
    torch=pytest.importorskip('torch')
    if not C._compiler_path().is_file():pytest.skip('packaged Rust helper required')
    spec=object();source=torch.tensor([[[[0.2]],[[0.3]],[[0.4]]]],dtype=torch.float32)
    recipe=C.default_curves();recipe['master']=[[0.,0.1],[1.,0.9]];recipe['red']=[[0.,0.],[1.,0.8]]
    class Pipe:
        device=torch.device('cpu');curves_compiled=C.tensor_bundles(recipe,device,torch.float32)
        def retouch(self,*a,**kw):assert kw['render_stage']=='wb-input';return source
        def apply_exposure(self,x):return x+0.1
        def apply_levels(self,x):return x*0.9
        def apply_curves(self,x):return C.curves_t(x,self.curves_compiled)
    pipe=Pipe();monkeypatch.setattr(S.Projection,'from_pipeline',lambda _:spec)
    monkeypatch.setattr(S,'admit',lambda *a:None);monkeypatch.setattr(S,'available_memory',lambda *a:10**9);monkeypatch.setattr(S,'require_warm_prefix',lambda *a:None)
    levels=stage(pipe,spec,0,None,{},'levels_black','master');assert torch.equal(levels,source+0.1)
    curves=(source+0.1)*0.9;assert torch.equal(stage(pipe,spec,0,None,{},'curve','master'),curves)
    red_input=torch.stack([C._eval_t(curves[:,i],pipe.curves_compiled[0]) for i in range(3)],dim=1)
    assert torch.equal(stage(pipe,spec,0,None,{},'curve','red'),red_input)
    assert torch.equal(stage(pipe,spec,0,None,{},'hsl','master'),pipe.apply_curves(curves))
