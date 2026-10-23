"""UNRUN: Qoder must build packaged Rust library before numerical fixtures."""
import numpy as np
import pytest
from lumaretouch_engine import photo_grain_state as S
from lumaretouch_engine.photo_grain_stage import PhotoGrainStage
from lumaretouch_engine.photo_grain_source import SourceBand, render_source_bands


def render(pixels, recipe, origin=(0, 0)):
    return PhotoGrainStage(recipe).apply_np(pixels, source_pixels=True, source_origin=origin)


def test_legacy_neutral_identity_and_missing_context():
    p = np.array([[[-0.5, 1.4, 0.5]]], dtype=np.float32)
    assert PhotoGrainStage(S.from_state({})).apply_np(p) is p
    with pytest.raises(ValueError):
        PhotoGrainStage({**S.neutral(), 'strength': 40}).apply_np(p)


@pytest.mark.parametrize('field,value', [('seed', True), ('seed', -1), ('size', 0), ('strength', float('nan')), ('size_unit', 'output_pixels')])
def test_strict_schema(field, value):
    with pytest.raises(ValueError):
        S.check({**S.neutral(), field: value})


def test_refresh_tile_crop_seed():
    p = np.full((73, 129, 3), 0.5, dtype=np.float32)
    r = {**S.neutral(), 'strength': 70, 'seed': 276923}
    full = render(p, r)
    assert np.array_equal(full, render(p, r))
    assert np.array_equal(full[19:51, 29:91], render(p[19:51, 29:91], r, (29, 19)))
    tiled = np.concatenate([render(p[:31], r), render(p[31:], r, (0, 31))])
    assert np.array_equal(full, tiled)
    assert not np.array_equal(full, render(p, {**r, 'seed': r['seed']+1}))


@pytest.mark.parametrize('key,value', [('strength', 70), ('shadows', 0), ('midtones', 0), ('highlights', 0), ('size', 4), ('roughness', 100), ('colour', 100)])
def test_seven_controls_meaningful(key, value):
    p = np.repeat(np.linspace(0, 1, 129, dtype=np.float32)[None, :, None], 64, axis=0)
    p = np.repeat(p, 3, axis=2)
    r = {**S.neutral(), 'strength': 35, 'roughness': 0}
    assert not np.array_equal(render(p, r), render(p, {**r, key: value}))


def test_colour_and_signed_headroom():
    p = np.full((16, 17, 3), 0.5, dtype=np.float32)
    r = {**S.neutral(), 'strength': 80}
    mono = render(p, r)
    assert np.array_equal(mono[:, :, 0], mono[:, :, 1])
    colour = render(p, {**r, 'colour': 100})
    assert not np.array_equal(colour[:, :, 0], colour[:, :, 1])
    p[:] = [-0.4, 2, 4]
    out = render(p, r)
    assert np.all(out[:, :, 0] < 0) and np.all(out[:, :, 1] > 1)


def test_band_sink_aborts_partial_source():
    class Sink:
        discarded = False
        finished = False
        def write_source_band(self, band): pass
        def finish(self, *, cancelled): self.finished = True
        def discard(self): self.discarded = True
    sink = Sink()
    with pytest.raises(ValueError):
        render_source_bands(S.neutral(), [SourceBand(0, 0, np.zeros((2, 4, 3), dtype=np.float32))], sink, source_size=(4, 5), encoding=S.SPACE)
    assert sink.discarded and not sink.finished


@pytest.mark.parametrize('angle', [0., 90., -90., 180.])
def test_mapped_quarter_turn_matches_source_field(angle):
    from lumaretouch_engine.photo_grain_native import apply_canvas
    from lumaretouch_engine.ops.geometry import crop_rotate_np
    p=np.full((47,61,3),0.5,dtype=np.float32)
    r={**S.neutral(),'strength':60,'seed':41}
    rect=(0.1,0.2,0.9,0.8)
    expected=crop_rotate_np(render(p,r),rect,angle,uint8=False)
    canvas=np.ascontiguousarray(crop_rotate_np(p,rect,angle,uint8=False),dtype=np.float32)
    actual=apply_canvas(canvas,r,source_size=(61,47),geometry=(rect,angle))
    assert np.array_equal(actual,expected)


def test_mapping_rejects_proxy_canvas():
    from lumaretouch_engine.photo_grain_geometry import mapping
    with pytest.raises(ValueError):mapping((4000,3000),None,(1000,750))
