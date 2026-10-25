# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. ABI mocks prove no pixel algorithm or photographic quality.

Real-native numerical tests at the bottom require the separately built exact
artifact. No test, import, native call or numerical fixture was run at authoring.
"""
import ast
import ctypes as C
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import lens_aperture_native as N


def settings(**changes):
    result = {'version': 1, 'aperture': 'circular_disk', 'max_radius_px': 0.0,
              'focus_near': 0.2, 'focus_far': 0.3, 'depth_falloff': 0.5,
              'occlusion_tolerance': 0.0, 'rotation_radians': 0.0}
    result.update(changes)
    return result


def arrays(width=5, height=4):
    rgba = np.empty((height,width,4),np.float32)
    rgba[...] = [-0.25, 2.0, 4.0, 0.5]
    depth = np.ones((height,width),np.float32)
    return rgba, depth


class MockNative:
    """Transport/cancellation fixture only: copies source, NOT aperture blur."""
    def __init__(self, *, fail_after=None, corrupt=False):
        self.validations = []
        self.tiles = []
        self.fail_after = fail_after
        self.corrupt = corrupt

    def lrt_lens_aperture_validate_v1(self, rgba, n, depth, dn, refinement, rn,
                                     width, height, cancel, context):
        self.validations.append((rgba,depth,refinement,width,height))
        assert n == width*height*4 and dn == width*height
        assert rn in (0,width*height)
        return 4 if cancel(context) else 0

    def lrt_lens_aperture_render_tile_v1(self, rgba, n, depth, dn, refinement, rn,
                                        width, height, x, y, tw, th, native,
                                        output, output_len, cancel, context):
        self.tiles.append((width,height,x,y,tw,th,native.max_radius_px))
        if self.fail_after == len(self.tiles):
            return 7
        if cancel(context):
            return 4
        source = np.ctypeslib.as_array(rgba, shape=(n,)).reshape(height,width,4)
        destination = np.ctypeslib.as_array(output, shape=(output_len,)).reshape(th,tw,4)
        destination[...] = source[y:y+th,x:x+tw]
        if self.corrupt:
            destination[0,0,0] = 0.0
        return 0


@pytest.fixture
def mock_runtime(monkeypatch):
    mock = MockNative()
    monkeypatch.setattr(N, '_query_runtime', lambda: (mock,31))
    monkeypatch.setattr(N, '_available_memory', lambda: 16*1024**3)
    return mock


def test_exact_version_and_keys_preserve_original_intent():
    original = settings()
    normalized = N.normalize_settings(original)
    assert normalized == original and normalized is not original
    for invalid in [settings(version=2), settings(version=True), settings(extra=0),
                    settings(aperture='circle_ii'), settings(max_radius_px=True),
                    settings(max_radius_px=float('nan')), settings(depth_falloff=0),
                    settings(focus_near=0.9), settings(rotation_radians=4)]:
        before = dict(invalid)
        with pytest.raises(ValueError):
            N.normalize_settings(invalid)
        assert invalid.keys() == before.keys()
        assert all(invalid[k] is before[k] for k in invalid)


def test_work_estimate_uses_radius_rounded_for_native_abi():
    small = N.work_estimate((4000,6000), settings(max_radius_px=0.5000000001))
    assert small['halo_pixels'] == 0  # That JSON value rounds to native float32 0.5.
    largest = N.work_estimate((4000,6000), settings(max_radius_px=128))
    assert largest['halo_pixels'] == 129
    assert largest['candidate_taps_per_pixel'] == 259*259
    assert largest['tile_pixels'] == 125
    assert largest['candidate_taps'] == 24_000_000*259*259
    assert largest['quadrature_evaluations_upper_bound'] == 16*24_000_000*259*259


def test_adaptive_tiles_cover_exact_source_without_overlap():
    width,height,limit=23,17,5
    coverage=np.zeros((height,width),np.uint8)
    for x,y,tw,th in N._tiles(width,height,limit):
        assert tw*th <= limit and tw > 0 and th > 0
        coverage[y:y+th,x:x+tw] += 1
    assert np.all(coverage == 1)


def test_memory_estimate_counts_inputs_snapshots_output_and_refinement():
    a=N.memory_estimate((4,5))
    b=N.memory_estimate((4,5),with_refinement=True)
    assert b['additional_bytes']-a['additional_bytes'] == 4*20
    assert b['total_bytes']-a['total_bytes'] == 8*20
    assert a['additional_bytes'] == 36*20+32*N.MAX_TILE_PIXELS+N.SCRATCH_ALLOWANCE_BYTES
    with pytest.raises(MemoryError):
        N.memory_estimate((10001,10000))
    with pytest.raises(ValueError):
        N.memory_estimate((True,5))


def test_neutral_bridge_uses_owned_snapshots_and_returns_exact_new_buffer(mock_runtime):
    source,depth=arrays()
    source[0,0,0]=-0.0
    before=source.copy()
    result=N.apply(source,depth,settings())
    assert np.array_equal(result.view(np.uint32),source.view(np.uint32))
    assert not np.shares_memory(result,source)
    assert np.array_equal(source.view(np.uint32),before.view(np.uint32))
    rgba_pointer,depth_pointer,_,width,height=mock_runtime.validations[0]
    assert C.cast(rgba_pointer,C.c_void_p).value != source.ctypes.data
    assert C.cast(depth_pointer,C.c_void_p).value != depth.ctypes.data
    assert (width,height) == (5,4)


def test_strided_inputs_are_snapshotted_without_resize_or_dtype_conversion(mock_runtime):
    source,depth=arrays(8,6)
    source=source[::2,::2]
    depth=depth[::2,::2]
    result=N.apply(source,depth,settings())
    assert result.flags.c_contiguous and result.shape == (3,4,4)
    assert np.array_equal(result,source)
    with pytest.raises(ValueError):
        N.apply(source.astype(np.float64),depth,settings())
    with pytest.raises(ValueError):
        N.apply(source,depth.astype('>f4' if np.little_endian else '<f4'),settings())


def test_invalid_depth_refinement_alpha_hdr_are_refused_even_when_neutral(mock_runtime):
    source,depth=arrays()
    for value in [np.nan,np.inf,-0.1,1.1]:
        bad=depth.copy();bad[0,0]=value
        with pytest.raises(ValueError):
            N.apply(source,bad,settings())
    bad=source.copy();bad[0,0,3]=0.0
    with pytest.raises(ValueError):
        N.apply(bad,depth,settings())
    bad=source.copy();bad[0,0,0]=65504.0  # Alpha remains .5.
    with pytest.raises(ValueError):
        N.apply(bad,depth,settings())
    correction=np.zeros(depth.shape,np.float32);correction[0,0]=-1.1
    with pytest.raises(ValueError):
        N.apply(source,depth,settings(),refinement=correction)
    assert mock_runtime.validations == []


def test_explicit_colour_and_depth_labels_are_required(mock_runtime):
    source,depth=arrays()
    for arguments in [{'encoding':'encoded-srgb'}, {'premultiplied':False},
                      {'depth_convention':'near-one-far-zero'}]:
        with pytest.raises(ValueError):
            N.apply(source,depth,settings(),**arguments)


def test_disabled_and_missing_module_do_not_turn_neutral_into_success(monkeypatch):
    source,depth=arrays()
    def unavailable():
        raise N.LensApertureUnavailable('fixture missing native artifact')
    monkeypatch.setattr(N,'_query_runtime',unavailable)
    assert not N.capability()['lens_aperture_available']
    assert not N.capability(enabled=False)['lens_aperture_available']
    with pytest.raises(N.LensApertureUnavailable):
        N.apply(source,depth,settings())
    with pytest.raises(N.LensApertureUnavailable):
        N.apply(source,depth,settings(),enabled=False)


def test_capability_mask_does_not_silently_replace_missing_kernel(monkeypatch):
    monkeypatch.setattr(N,'_query_runtime',lambda: (MockNative(),1))
    assert N.capability()['kernels'] == ('circular_disk',)
    source,depth=arrays()
    with pytest.raises(N.LensApertureUnavailable):
        N.apply(source,depth,settings(aperture='regular_pentagon'))


def test_work_and_memory_refusal_happen_before_snapshots_or_native_validation(mock_runtime,monkeypatch):
    source,depth=arrays()
    with pytest.raises(MemoryError):
        N.apply(source,depth,settings(max_radius_px=128),max_candidate_taps=1)
    monkeypatch.setattr(N,'_available_memory',lambda: 0)
    with pytest.raises(MemoryError):
        N.apply(source,depth,settings())
    assert mock_runtime.validations == []


def test_native_tiles_keep_whole_source_and_work_bound(mock_runtime,monkeypatch):
    source,depth=arrays(400,3)
    # Explicitly force tiny tiles to exercise multiple rows and partial tails.
    original=N.work_estimate
    def small_tiles(shape,value):
        result=original(shape,value);result['tile_pixels']=5;return result
    monkeypatch.setattr(N,'work_estimate',small_tiles)
    result=N.apply(source,depth,settings())
    assert np.array_equal(result,source)
    assert len(mock_runtime.validations) == 1
    assert len(mock_runtime.tiles) > 1
    assert all((w,h)==(400,3) and tw*th<=5 for w,h,x,y,tw,th,r in mock_runtime.tiles)


def test_error_after_successful_tile_never_returns_partial_full_image(mock_runtime,monkeypatch):
    source,depth=arrays(8,2)
    before=source.copy()
    mock_runtime.fail_after=2
    original=N.work_estimate
    def small_tiles(shape,value):
        result=original(shape,value);result['tile_pixels']=4;return result
    monkeypatch.setattr(N,'work_estimate',small_tiles)
    with pytest.raises(N.LensApertureRejected) as rejected:
        N.apply(source,depth,settings())
    assert rejected.value.code == 7
    assert len(mock_runtime.tiles) == 2
    assert np.array_equal(source,before)


def test_postcheck_rejects_native_neutral_corruption(mock_runtime):
    source,depth=arrays()
    mock_runtime.corrupt=True
    with pytest.raises(RuntimeError,match='neutral/clear'):
        N.apply(source,depth,settings())


def test_cancel_after_native_success_discards_whole_operation(mock_runtime):
    source,depth=arrays()
    with pytest.raises(InterruptedError):
        N.apply(source,depth,settings(),cancelled=lambda: bool(mock_runtime.tiles))


def test_callback_exception_is_not_swallowed_by_ctypes():
    sentinel=RuntimeError('cancel callback failed')
    def broken():
        raise sentinel
    callback,errors=N._callback(broken)
    assert callback(None) == 1
    assert callback(None) == 1
    assert errors == [sentinel]
    with pytest.raises(RuntimeError) as raised:
        N._status(4,lambda: False,errors)
    assert raised.value is sentinel


def test_abi_settings_layout_matches_rust_header():
    assert C.sizeof(N.NativeSettings) == 28
    assert N.NativeSettings.aperture.offset == 0
    assert N.NativeSettings.max_radius_px.offset == 4
    assert N.NativeSettings.rotation_radians.offset == 24
    native=N._native_settings(N.normalize_settings(settings(aperture='cat_eye_intersection')))
    assert native.aperture == 4


def test_runtime_query_checks_abi_mask_and_exact_signatures(monkeypatch):
    class Symbol:
        def __init__(self,value):
            self.value=value
        def __call__(self,*_arguments):
            return self.value
    class FakePath:
        def resolve(self):
            return self
        @property
        def parent(self):
            return self
        def __truediv__(self,_part):
            return self
        def is_file(self):
            return True
        def __str__(self):
            return '/test/packaged/liblrt_lens_aperture.so'
    library=SimpleNamespace(lrt_lens_aperture_abi=Symbol(1),
        lrt_lens_aperture_kernel_mask_v1=Symbol(31),
        lrt_lens_aperture_validate_v1=Symbol(0),lrt_lens_aperture_render_tile_v1=Symbol(0))
    monkeypatch.setattr(N,'Path',lambda _value: FakePath())
    monkeypatch.setattr(N.C,'CDLL',lambda _path: library)
    lib,mask=N._query_runtime.__wrapped__()
    assert lib is library and mask == 31
    assert len(lib.lrt_lens_aperture_validate_v1.argtypes) == 10
    assert len(lib.lrt_lens_aperture_render_tile_v1.argtypes) == 17
    assert lib.lrt_lens_aperture_render_tile_v1.argtypes[12] is N.NativeSettings
    library.lrt_lens_aperture_abi.value=2
    with pytest.raises(N.LensApertureUnavailable):
        N._query_runtime.__wrapped__()
    library.lrt_lens_aperture_abi.value=1
    for mask in (0,32,63):
        library.lrt_lens_aperture_kernel_mask_v1.value=mask
        with pytest.raises(N.LensApertureUnavailable):
            N._query_runtime.__wrapped__()


def test_module_has_no_top_level_numpy_or_native_loading():
    tree=ast.parse(Path(N.__file__).read_text())
    for node in tree.body:
        if isinstance(node,ast.Import):
            assert all(alias.name != 'numpy' for alias in node.names)
        if isinstance(node,ast.ImportFrom):
            assert node.module != 'numpy'
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
            assert ast.unparse(node.value.func) not in ('C.CDLL','_query_runtime','_numpy')


def test_real_native_circular_impulse_and_alpha_contract_unrun():
    if not N.available():
        pytest.skip('Exact ABI-1 native artifact unavailable; numeric coverage is UNRUN')
    source=np.zeros((7,7,4),np.float32);source[...,3]=1;source[3,3,0]=1
    depth=np.ones((7,7),np.float32)
    result=N.apply(source,depth,settings(max_radius_px=1))
    assert result[3,3,0] == pytest.approx(4/13,abs=2e-6)
    assert result[3,4,0] == pytest.approx(2/13,abs=2e-6)
    assert result[4,4,0] == pytest.approx(1/52,abs=2e-6)
    assert result[3,5,0] == 0
    assert np.all(result[...,3] == 1)


def test_real_native_signed_hdr_clear_and_fullsource_tile_seams_unrun(monkeypatch):
    if not N.available():
        pytest.skip('Exact ABI-1 native artifact unavailable; numeric coverage is UNRUN')
    source,depth=arrays(15,9)
    source[...,0]=np.arange(15,dtype=np.float32)[None,:]-2
    correction=np.zeros(depth.shape,np.float32);correction[:,6:8]=-1
    actual_settings=settings(max_radius_px=3,aperture='regular_octagon')
    expected=N.apply(source,depth,actual_settings,refinement=correction)
    original=N.work_estimate
    def small_tiles(shape,value):
        result=original(shape,value);result['tile_pixels']=7;return result
    monkeypatch.setattr(N,'work_estimate',small_tiles)
    result=N.apply(source,depth,actual_settings,refinement=correction)
    assert np.array_equal(result.view(np.uint32),expected.view(np.uint32))
    assert np.array_equal(result[:,6:8].view(np.uint32),source[:,6:8].view(np.uint32))
    assert result[...,2].max() > 1
