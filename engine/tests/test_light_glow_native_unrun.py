# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Mocks test transport only; real-native cases are separate."""
import ctypes as C
from pathlib import Path
import numpy as np
import pytest
from lumaretouch_engine import light_glow_native as N


def recipe(**changes):
    value = {'version': 1, 'operation_id': N.OPERATION, 'math_identity': N.MATH,
             'mode': 'black_mist', 'strength': .3, 'radius_px': 24, 'threshold': .65,
             'exposure_ev': 0, 'scattering': 0,
             'tint': {'hue_deg': 0, 'saturation': 0, 'lightness': 0}}
    value.update(changes)
    return value


class TransportOnly:
    """Not glow: halves RGB solely to prove source/coverage transport ownership."""
    def __init__(self, *, corrupt=False, failure=0):
        self.regions, self.corrupt, self.failure = [], corrupt, failure

    def lrt_light_glow_plan(self, settings, geometry, budget, pointer):
        s = C.cast(settings, C.POINTER(N.Settings)).contents
        g = C.cast(geometry, C.POINTER(N.Geometry)).contents
        halo = 0 if s.strength == 0 else s.radius_px
        x, y = max(0, g.tile_x-halo), max(0, g.tile_y-halo)
        w = min(g.full_width, g.tile_x+g.tile_width+halo)-x
        h = min(g.full_height, g.tile_y+g.tile_height+halo)-y
        scratch = 0 if s.strength == 0 else w*h*72
        p = N.Plan(C.sizeof(N.Plan), x, y, w, h, halo, 9, 0,
                   w*h*4, g.tile_width*g.tile_height*4,
                   g.tile_width*g.tile_height, scratch,
                   w*h*16+scratch+g.tile_width*g.tile_height*20+8192)
        if p.required_bytes > budget:
            return 5
        C.memmove(pointer, C.byref(p), C.sizeof(p))
        return 0

    def lrt_light_glow_render(self, settings, geometry, source, source_len,
                              output, output_len, coverage, coverage_len, budget, cancel, user):
        if self.failure:
            return self.failure
        if cancel(user):
            return 6
        s = C.cast(settings, C.POINTER(N.Settings)).contents
        g = C.cast(geometry, C.POINTER(N.Geometry)).contents
        p = N.Plan()
        code = self.lrt_light_glow_plan(settings, geometry, budget, C.byref(p))
        if code:
            return code
        region = np.ctypeslib.as_array(source, shape=(source_len,)).reshape(p.region_height, p.region_width, 4)
        tile = np.ctypeslib.as_array(output, shape=(output_len,)).reshape(g.tile_height, g.tile_width, 4)
        mask = np.ctypeslib.as_array(coverage, shape=(coverage_len,)).reshape(g.tile_height, g.tile_width)
        x, y = g.tile_x-p.region_x, g.tile_y-p.region_y
        expected = region[y:y+g.tile_height, x:x+g.tile_width]
        self.regions.append((g.tile_x, p.region_x, region.copy()))
        tile[:] = expected
        if s.strength != 0:
            tile[:, :, :3] *= .5
        mask[:] = np.max(np.abs(tile[:, :, :3]-expected[:, :, :3]), axis=2)
        if self.corrupt:
            mask[:] = 0.12345
        return 0


def pixels(width=513, height=5):
    value = np.zeros((height, width, 4), np.float32)
    value[:, :, 0] = np.linspace(.01, .95, width, dtype=np.float32)
    value[:, :, 1:3] = .2
    value[:, :, 3] = 1
    return value


def test_abi_layout_matches_fixed_native_contract():
    assert C.sizeof(N.Settings) == 56
    assert C.sizeof(N.Geometry) == 32
    assert C.sizeof(N.Plan) == 72
    assert N.ABI == 1 and N.MATH == 65537


@pytest.mark.parametrize('changes', [dict(version=True), dict(math_identity=1), dict(mode='bloom'),
    dict(radius_px=1.5), dict(radius_px=True), dict(strength=float('nan')),
    dict(threshold=1.001), dict(exposure_ev=4.01), dict(scattering=-.1),
    dict(tint={'hue_deg': 0, 'saturation': 0, 'lightness': 0, 'extra': 1})])
def test_exact_recipe_rejects_lossy_or_foreign_intent(changes):
    with pytest.raises(ValueError):
        N.recipe(recipe(**changes))


def test_every_region_reads_immutable_original_and_returns_real_coverage(monkeypatch):
    mock = TransportOnly()
    monkeypatch.setattr(N, 'native', lambda: mock)
    source = pixels()
    content = source.astype('<f4').tobytes()
    output, coverage = N.render(content, 513, 5, recipe(), max_bytes=64*1024*1024)
    assert len(mock.regions) == 3
    np.testing.assert_array_equal(output[:, :, :3], source[:, :, :3]*.5)
    np.testing.assert_array_equal(coverage, np.max(np.abs(output[:, :, :3]-source[:, :, :3]), axis=2))
    assert content == source.astype('<f4').tobytes()
    assert not output.flags.writeable and not coverage.flags.writeable
    # The second halo contains source pixels, never the first tile's halved RGB.
    _, left, region = mock.regions[1]
    np.testing.assert_array_equal(region, source[:, left:left+region.shape[1]])


def test_neutral_is_bit_exact_but_still_calls_core(monkeypatch):
    mock = TransportOnly()
    monkeypatch.setattr(N, 'native', lambda: mock)
    source = pixels(4, 3)
    source[0, 0, 0] = -0.0
    content = source.astype('<f4').tobytes()
    output, coverage = N.render(content, 4, 3, recipe(strength=0), max_bytes=32*1024*1024)
    assert mock.regions and output.astype('<f4').tobytes() == content
    assert not np.any(coverage)


@pytest.mark.parametrize('mock,error', [(TransportOnly(corrupt=True), ValueError),
    (TransportOnly(failure=6), InterruptedError), (TransportOnly(failure=5), MemoryError)])
def test_invalid_or_cancelled_native_result_never_returns_partial_output(monkeypatch, mock, error):
    monkeypatch.setattr(N, 'native', lambda: mock)
    with pytest.raises(error):
        N.render(pixels(4, 3).astype('<f4').tobytes(), 4, 3, recipe(), max_bytes=32*1024*1024)


def test_missing_library_is_not_a_neutral_success(monkeypatch):
    def unavailable():
        raise N.Unavailable('missing fixture')
    monkeypatch.setattr(N, 'native', unavailable)
    assert N.capability()['status'] == 'unavailable'
    with pytest.raises(N.Unavailable):
        N.render(pixels(4, 3).astype('<f4').tobytes(), 4, 3, recipe(strength=0), max_bytes=32*1024*1024)


def installed():
    if not (Path(N.__file__).parent/'bin/liblrt_light_glow.so').is_file():
        pytest.skip('Exact native glow artifact is not installed; numeric acceptance is UNRUN')


@pytest.mark.parametrize('mode', N.MODES)
def test_real_native_tiling_preserves_same_full_source_result(monkeypatch, mode):
    installed()
    source = pixels(509, 7)
    content = source.astype('<f4').tobytes()
    first, mask = N.render(content, 509, 7, recipe(mode=mode), max_bytes=128*1024*1024)
    monkeypatch.setattr(N, 'TILE_EDGE', 64)
    second, other = N.render(content, 509, 7, recipe(mode=mode), max_bytes=128*1024*1024)
    np.testing.assert_allclose(first, second, rtol=0, atol=3e-6)
    np.testing.assert_allclose(mask, other, rtol=0, atol=3e-6)
    assert content == source.astype('<f4').tobytes()


@pytest.mark.parametrize('channel,value', [(0, 1.01), (0, -.01), (3, .5)])
def test_real_native_rejects_hdr_signed_or_nonpremultiplied_input(channel, value):
    installed()
    source = pixels(4, 3)
    source[0, 3, channel] = value
    with pytest.raises(ValueError):
        N.render(source.astype('<f4').tobytes(), 4, 3, recipe(), max_bytes=32*1024*1024)
