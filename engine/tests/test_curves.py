"""Curves math contracts; pipeline/state/UI integration is tested separately."""
import copy
import numpy as np
import pytest
from lumaretouch_engine.ops import curves as C


def test_identity_preserves_values_object_and_hdr():
    image = np.array([[[-1., 0.2, 4.]]], dtype=np.float32)
    assert C.curves_np(image, C.default_curves()) is image


def test_schema_validation_is_strict_and_owns_points():
    value = C.default_curves()
    checked = C.check_curves(value)
    checked['red'][0][1] = 0.2
    assert value['red'][0][1] == 0
    for change in [{'version': 2}, {'enabled': 1}, {'space': 'linear'}, {'extra': 1},
                   {'red': [[0, 0], [0, .5], [1, 1]]}, {'red': [[0, float('nan')], [1, 1]]}]:
        bad = copy.deepcopy(value); bad.update(change)
        with pytest.raises(ValueError): C.check_curves(bad)


def test_real_rust_compiler_golden_vector_and_extrapolation():
    spec = C.default_curves(); spec['master'] = [[0, 0], [.5, 1], [1, 1]]
    x = np.array([-.1, .25, .75, 1.1], dtype=np.float32)
    image = np.repeat(x[:, None], 3, axis=1)
    result = C.curves_np(image, spec)
    assert np.allclose(result[:, 0], [-.3, .6875, 1., 1.], atol=1e-6)
    assert result.dtype == image.dtype


def test_master_then_channel_and_disabled_bypass():
    spec = C.default_curves()
    spec['master'] = [[0, .2], [1, .8]]
    spec['red'] = [[0, .1], [1, .9]]
    image = np.full((2, 3), .25, dtype=np.float32)
    result = C.curves_np(image, spec)
    assert np.allclose(result, [.38, .35, .35], atol=1e-6)
    spec['enabled'] = False
    assert C.curves_np(image, spec) is image


def test_nonmonotone_points_do_not_create_extra_overshoot():
    spec = C.default_curves(); spec['blue'] = [[0, .1], [.1, .9], [.6, .2], [1, .8]]
    for a, b in zip(spec['blue'], spec['blue'][1:]):
        x = np.linspace(a[0], b[0], 1001, dtype=np.float32)
        result = C.curves_np(np.repeat(x[:, None], 3, axis=1), spec)[:, 2]
        assert result.min() >= min(a[1], b[1]) - 1e-6
        assert result.max() <= max(a[1], b[1]) + 1e-6


def test_torch_cpu_matches_numpy_and_keeps_identity():
    torch = pytest.importorskip('torch')
    spec = C.default_curves(); spec['green'] = [[0, .1], [.3, .7], [1, .9]]
    image = np.random.default_rng(42).uniform(-.1, 1.2, (13, 17, 3)).astype(np.float32)
    tensor = torch.from_numpy(image.transpose(2, 0, 1)[None].copy())
    identity = C.tensor_bundles(C.default_curves(), 'cpu', torch.float32)
    assert C.curves_t(tensor, identity) is tensor
    result = C.curves_t(tensor, C.tensor_bundles(spec, 'cpu', torch.float32))
    assert np.max(np.abs(result.numpy()[0].transpose(1, 2, 0)-C.curves_np(image, spec))) < 2e-6


def test_resident_pipeline_curves_are_independent_and_clearable():
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import make_pipeline
    image = np.full((16, 16, 3), 64, dtype=np.uint8)
    pipe = make_pipeline('cpu', 16, 16, image)
    pipe.render(0.)
    before = pipe.read_back().copy()
    spec = C.default_curves(); spec['red'] = [[0, .1], [1, 1.]]
    pipe.set_curves(spec)
    pipe.render(0.)
    changed = pipe.read_back().copy()
    assert np.any(changed[..., 0] != before[..., 0])
    assert np.array_equal(changed[..., 1:], before[..., 1:])
    assert not pipe.has_lut()
    pipe.clear_curves(); pipe.render(0.)
    assert np.array_equal(pipe.read_back(), before)


def test_curve_export16_uses_same_recipe_without_eight_bit_steps():
    pytest.importorskip('torch')
    from lumaretouch_engine.export import export_image16, ExportSpec
    spec=C.default_curves();spec['master']=[[0,.05],[.5,.6],[1,.95]]
    source=np.broadcast_to(np.linspace(0,65535,513,dtype=np.uint16)[None,:,None],(64,513,3)).copy()
    expected=np.rint(np.clip(C.curves_np(source.astype(np.float32)/65535,spec),0,1)*65535).astype(np.uint16)
    actual,_=export_image16(source,ExportSpec(strength=0,curves=spec),device='cpu',tile=256)
    assert np.max(np.abs(actual.astype(np.int32)-expected.astype(np.int32)))<=1
    assert len(np.unique(actual[0,:,0]))>256
