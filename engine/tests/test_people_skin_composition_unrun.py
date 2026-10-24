"""AUTHORED / UNRUN. Synthetic headroom contracts, not photo/GPU acceptance."""
from pathlib import Path

import pytest

torch = pytest.importorskip('torch')
from lumaretouch_engine import people_skin_composition as S


def pixel(values):
    return torch.tensor(values, dtype=torch.float32).reshape(1, 3, 1, 1)


def test_zero_delta_is_original_object_and_preserves_signed_zero():
    source = pixel([-0., .4, 1.])
    result = S.apply(source, torch.zeros_like(source))
    assert result is source
    assert torch.equal(result.view(torch.int32), source.view(torch.int32))


def test_feasible_vector_is_not_reduced_or_recolored():
    source, delta = pixel([.3, .5, .7]), pixel([.1, -.2, .05])
    assert torch.equal(S.apply(source, delta), source + delta)


def test_one_common_gain_preserves_delta_direction_not_channel_clamp():
    source, delta = pixel([.9, .5, .2]), pixel([.2, -.2, .1])
    result = S.apply(source, delta)
    gains = (result-source)/delta
    assert torch.allclose(gains, torch.full_like(gains, float(gains.flatten()[0])), atol=1e-6)
    assert 0 < float(gains.min()) < .5
    assert not torch.equal(result, (source+delta).clamp(0, 1))
    assert bool(((result >= 0) & (result <= 1)).all())


def test_negative_component_sets_shared_lower_headroom():
    source, delta = pixel([.1, .5, .7]), pixel([-.3, .15, .1])
    result = S.apply(source, delta)
    gains = (result-source)/delta
    assert torch.allclose(gains, torch.full_like(gains, float(gains.flatten()[0])), atol=1e-6)
    assert 0 < float(gains.min()) < 1/3
    assert float(result.min()) >= 0


def test_blocked_channel_means_zero_vector_not_partial_color_change():
    source, delta = pixel([1., .5, .2]), pixel([.1, -.2, .1])
    assert torch.equal(S.apply(source, delta), source)


def test_zero_component_keeps_original_bits():
    source, delta = pixel([-0., .5, .2]), pixel([0., .1, -.1])
    result = S.apply(source, delta)
    assert torch.equal(result[:, :1].view(torch.int32), source[:, :1].view(torch.int32))


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -.1, 1.1])
def test_active_invalid_upstream_refuses_instead_of_clipping(bad):
    with pytest.raises(ValueError):
        S.apply(pixel([bad, .5, .5]), pixel([.1, 0., 0.]))


def test_invalid_delta_and_wrong_dtype_refuse():
    with pytest.raises(ValueError):
        S.apply(pixel([.2, .3, .4]), pixel([float('nan'), 0., 0.]))
    with pytest.raises(ValueError):
        S.apply(pixel([.2, .3, .4]).double(), pixel([.1, 0., 0.]).double())


def test_pointwise_full_frame_and_tile_composition_match():
    source = torch.tensor([.2, .9, .4, .5, .7, .1], dtype=torch.float32).reshape(1, 3, 1, 2)
    delta = torch.tensor([.1, .2, -.1, -.2, .2, .3], dtype=torch.float32).reshape(1, 3, 1, 2)
    full = S.apply(source, delta)
    tiles = torch.cat([S.apply(source[..., i:i+1], delta[..., i:i+1]) for i in range(2)], dim=-1)
    assert torch.equal(full, tiles)


def test_only_existing_skin_stage_uses_new_limiter():
    root = Path(__file__).resolve().parents[2]
    source = (root/'engine/src/lumaretouch_engine/people_pipeline.py').read_text()
    assert "if stage=='skin_colour':" in source
    assert 'return compose_skin(pixels,delta)' in source
    assert "pixels+delta if stage=='eye_light' else (pixels+delta).clamp(0,1)" in source
