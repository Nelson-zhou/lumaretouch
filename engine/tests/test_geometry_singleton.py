"""One-pixel crop axes remain visible, without changing normal-size legacy pixels."""
import math
import numpy as np
import pytest
from lumaretouch_engine.ops import geometry as G

SHAPES = [(1, 1), (1, 2), (2, 1), (1, 7), (7, 1), (1, 8), (8, 1)]
ANGLES = [0.5, 17.0, 45.0, -37.5, 60.0]


def source(h, w):
    return np.linspace(0.1, 0.8, h*w*3, dtype=np.float64).reshape(h, w, 3)


def scalar_oracle(src, degrees):
    """Independent per-pixel scalar interpolation, with explicit singleton cells."""
    h, w, _ = src.shape
    a = math.radians(degrees)
    ow = max(1, round(w*abs(math.cos(a)) + h*abs(math.sin(a))))
    oh = max(1, round(w*abs(math.sin(a)) + h*abs(math.cos(a))))
    out = np.zeros((oh, ow, 3), dtype=np.float64)
    c, s = math.cos(-a), math.sin(-a)
    for y in range(oh):
        for x in range(ow):
            dx, dy = x-(ow-1)/2, y-(oh-1)/2
            px, py = c*dx-s*dy+(w-1)/2, s*dx+c*dy+(h-1)/2
            if not (-0.5 <= px <= w-0.5 and -0.5 <= py <= h-0.5):
                continue
            px, py = min(max(px, 0), w-1), min(max(py, 0), h-1)
            ix, iy = math.floor(px), math.floor(py)
            xs = [(ix, 1-(px-ix)), (min(ix+1,w-1), px-ix)]
            ys = [(iy, 1-(py-iy)), (min(iy+1,h-1), py-iy)]
            for xx, wx in xs:
                for yy, wy in ys:
                    out[y, x] += src[yy, xx] * wx * wy
    return out


@pytest.mark.parametrize('h,w', SHAPES)
@pytest.mark.parametrize('angle', ANGLES)
def test_numpy_singleton_rotation_matches_scalar_oracle(h, w, angle):
    src = source(h, w)
    actual = G.rotate_np(src, angle)
    np.testing.assert_allclose(actual, scalar_oracle(src, angle), rtol=0, atol=2e-15)
    assert actual.max() > 0, 'a nonempty crop must not become entirely invalid'


@pytest.mark.parametrize('h,w', SHAPES)
@pytest.mark.parametrize('angle', ANGLES)
def test_torch_singleton_rotation_matches_scalar_oracle(h, w, angle):
    torch = pytest.importorskip('torch')
    src = source(h, w)
    actual = G.crop_rotate_t(torch.from_numpy(src.astype(np.float32)), [0,0,1,1], angle, uint8=False)
    np.testing.assert_allclose(actual.numpy(), scalar_oracle(src, angle), rtol=0, atol=2e-6)
    assert actual.max().item() > 0


@pytest.mark.parametrize('h,w', [(1,1),(1,7),(7,1)])
@pytest.mark.parametrize('backend', ['numpy', 'torch'])
def test_singleton_cell_includes_exact_half_pixel_boundaries_only(h, w, backend):
    src = np.full((h, w, 3), 0.3)
    offsets = np.array([[-0.500001, -0.5, 0.0, 0.5, 0.500001]])
    sx = offsets if w == 1 else np.full_like(offsets, 2.25)
    sy = offsets if h == 1 else np.full_like(offsets, 2.25)
    if backend == 'torch':
        torch = pytest.importorskip('torch')
        actual = G._sample_bilinear_t(torch.from_numpy(src), torch.from_numpy(sx), torch.from_numpy(sy)).numpy()
    else:
        actual = G._sample_bilinear_np(src, sx, sy)
    expected = np.zeros((1,5,3)); expected[:,1:4] = 0.3
    np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize('h,w', [(2,2), (4,7), (3,6)])
def test_normal_dimensions_keep_frozen_legacy_boundary_and_arithmetic(h, w):
    src = source(h, w)
    sx, sy = np.meshgrid(np.linspace(-1, w, 19), np.linspace(-1, h, 17))
    x0, y0 = np.floor(sx).astype(np.int64), np.floor(sy).astype(np.int64)
    fx, fy = (sx-x0)[...,None], (sy-y0)[...,None]
    valid = (x0>=0)&(x0<w-1)&(y0>=0)&(y0<h-1)
    xx, yy = np.clip(x0,0,w-2), np.clip(y0,0,h-2)
    top = src[yy,xx] + (src[yy,xx+1]-src[yy,xx])*fx
    bot = src[yy+1,xx] + (src[yy+1,xx+1]-src[yy+1,xx])*fx
    expected = np.where(valid[...,None], top+(bot-top)*fy, 0.0)
    np.testing.assert_array_equal(G._sample_bilinear_np(src,sx,sy), expected)


def test_public_crop_path_handles_one_pixel_width_in_uint8():
    torch = pytest.importorskip('torch')
    src = np.full((8,8,3), 128, dtype=np.uint8)
    rect = [0.25,0.25,0.375,0.875]
    actual = G.crop_rotate_np(src, rect, 17)
    native = G.crop_rotate_t(torch.from_numpy(src), rect, 17).numpy()
    np.testing.assert_array_equal(actual, native)
    assert actual.max() == 128 and actual.min() == 0


def test_coverage_uses_identical_singleton_footprint_and_rejects_rotation_fill():
    src = np.ones((7,1,3), dtype=np.float64)
    actual = G.rotate_np(src, 37.5)
    expected = scalar_oracle(src, 37.5)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-15)
    assert actual.max() == 1 and actual.min() == 0


@pytest.mark.parametrize('h,w', [(1,2),(2,1)])
@pytest.mark.parametrize('backend', ['numpy','torch'])
def test_other_axis_half_pixel_border_clamps_to_first_and_last_value(h,w,backend):
    src = np.repeat(np.array([0.2,0.8]).reshape(h,w,1),3,axis=2)
    offsets = np.array([[-0.500001,-0.5,0.0,0.5,1.0,1.5,1.500001]])
    sx = offsets if w==2 else np.zeros_like(offsets)
    sy = offsets if h==2 else np.zeros_like(offsets)
    if backend=='torch':
        torch=pytest.importorskip('torch')
        actual=G._sample_bilinear_t(torch.from_numpy(src),torch.from_numpy(sx),torch.from_numpy(sy)).numpy()
    else:
        actual=G._sample_bilinear_np(src,sx,sy)
    expected=np.repeat(np.array([0,0.2,0.2,0.5,0.8,0.8,0]).reshape(1,7,1),3,axis=2)
    np.testing.assert_allclose(actual,expected,rtol=0,atol=2e-16)
