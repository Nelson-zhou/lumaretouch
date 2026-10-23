"""AUTHORED / UNRUN: source ownership and fringe render adapter contracts.

These small fixtures isolate native dispatch and optical sampling with explicit
mocks. They do not establish native correctness, export parity or photo quality.
No product import or test execution was performed while authoring this file.
"""
from copy import deepcopy
import hashlib
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import fringe_repair_render as F
from lumaretouch_engine import fringe_repair_geometry as G
from lumaretouch_engine import fringe_repair_state as S


def manual(source, *, enabled=False):
    value = S.neutral()
    value.update(source=source, enabled=enabled)
    value['coverage']['strokes'] = [{
        'id': 'a' * 32, 'mode': 'subtract', 'points': [[.5, .5]],
        'axes': [[.1, 0.], [0., .1]], 'opacity': 1., 'feather': 0.,
    }]
    return value


def source_file(tmp_path):
    path = tmp_path / 'source.bin'
    content = b'original source identity fixture, not a decoded photograph'
    path.write_bytes(content)
    return str(path), {'sha256': hashlib.sha256(content).hexdigest(), 'width': 6, 'height': 4}


def test_original_decode_and_export_prove_hash_extent_and_stamp_even_disabled(tmp_path):
    from lumaretouch_engine.local_mask_state import file_stamp
    path, source = source_file(tmp_path)
    snapshot = {'fringe_repair': manual(source)}
    F.check_export_decode(snapshot, path, file_stamp(path), (4, 6))
    spec = SimpleNamespace(creative_base=None)
    F.configure_export(spec, snapshot, (4, 6), for_document=True)
    assert spec.fringe_repair == snapshot['fringe_repair']
    assert spec.fringe_repair_stamp == list(file_stamp(path))
    with pytest.raises(ValueError, match='another effective image source'):
        F.verify_export(spec, (4, 7))
    with pytest.raises(ValueError, match='transfer parameters only'):
        F.configure_export(SimpleNamespace(creative_base=None), snapshot, (4, 6), for_document=False)
    wrong = deepcopy(snapshot)
    wrong['fringe_repair']['source']['sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='another effective image source'):
        F.check_export_decode(wrong, path, file_stamp(path), (4, 6))


def test_original_stamp_cannot_be_replaced_after_the_snapshot(tmp_path):
    from lumaretouch_engine.local_mask_state import file_stamp
    path, source = source_file(tmp_path)
    before = file_stamp(path)
    snapshot = {'fringe_repair': manual(source)}
    F.check_export_decode(snapshot, path, before, (4, 6))
    with open(path, 'ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='changed during full-resolution decode'):
        F.check_export_decode(snapshot, path, before, (4, 6))
    with pytest.raises(ValueError, match='changed after snapshot capture'):
        F.configure_export(SimpleNamespace(creative_base=None), snapshot, (4, 6), for_document=True)


def test_derived_binding_uses_canonical_asset_not_shared_original_path(tmp_path):
    from lumaretouch_engine.creative_document_assets import make_asset
    from lumaretouch_engine.local_mask_state import file_stamp
    path, original = source_file(tmp_path)
    rgba = np.full((2, 3, 4), .25, dtype='<f4'); rgba[..., 3] = 1.
    asset = make_asset('rgba', 3, 2, rgba.tobytes())
    source = {'sha256': asset['id'][7:], 'width': 3, 'height': 2}
    snapshot = {'creative_base': asset, 'fringe_repair': manual(source)}
    # Decode extent describes the original file, not this derived canvas.
    F.check_export_decode(snapshot, path, file_stamp(path), (4, 6))
    spec = SimpleNamespace(creative_base=asset)
    F.configure_export(spec, snapshot, (2, 3), for_document=True)
    with pytest.raises(ValueError, match='effective full-source canvas'):
        F.verify_export(spec, (4, 6))
    wrong = deepcopy(snapshot); wrong['fringe_repair']['source'] = original
    with pytest.raises(ValueError, match='another effective image source'):
        F.check_export_decode(wrong, path, file_stamp(path), (4, 6))
    rgba[0, 0, 0] = .5
    different_asset = make_asset('rgba', 3, 2, rgba.tobytes())
    spec.creative_base = different_asset
    with pytest.raises(ValueError, match='another effective image source'):
        F.verify_export(spec, (2, 3))


@pytest.mark.parametrize('enabled,strength', [(False, 50.), (True, 0.)])
def test_neutral_capture_returns_eligibility_without_guide_or_core(monkeypatch, enabled, strength):
    from lumaretouch_engine import fringe_repair_native as N
    value = S.neutral(); value.update(enabled=enabled, strength=strength)
    spec = SimpleNamespace(fringe_repair=value, scale=1, _fringe_repair_capture_coverage=True)
    edited = np.full((4, 6, 3), .35, np.float32)
    mask = np.full((4, 6), .75, np.float32)
    def capture(recipe, source_size, geometry, canvas_size, *, cancelled):
        assert recipe == value and source_size == (6, 4) and canvas_size == (6, 4)
        return mask
    def forbidden(*args, **kwargs):
        raise AssertionError('Neutral capture must not dispatch the correction kernel')
    monkeypatch.setattr(G, 'coverage', capture)
    monkeypatch.setattr(N, 'render', forbidden)
    assert F.apply_export(edited, None, spec, source_size=(6, 4), geometry=None) is edited
    assert spec._fringe_repair_coverage is mask


def test_active_dispatch_preserves_full_float_frames_and_exact_coverage(monkeypatch):
    from lumaretouch_engine import fringe_repair_native as N
    value = S.neutral(); value['enabled'] = True
    spec = SimpleNamespace(fringe_repair=value, scale=1, _fringe_repair_capture_coverage=True)
    edited = np.full((4, 6, 3), 1.2, np.float32)
    guide = np.full_like(edited, -.1)
    mask = np.full((4, 6), .5, np.float32)
    output = edited.copy(); output[1, 1] = 1.1
    calls = []
    monkeypatch.setattr(G, 'coverage', lambda *args, **kwargs: mask)
    def render(actual_edited, actual_guide, recipe, coverage, *, cancelled):
        assert actual_edited is edited and actual_guide is guide and coverage is mask
        assert recipe == value and actual_guide.dtype == np.float32
        assert actual_guide.shape == actual_edited.shape == (4, 6, 3)
        calls.append(True)
        return output
    monkeypatch.setattr(N, 'render', render)
    assert F.apply_export(edited, guide, spec, source_size=(6, 4), geometry=None) is output
    assert calls == [True] and spec._fringe_repair_coverage is mask
    assert np.all(edited == np.float32(1.2)) and np.all(guide == np.float32(-.1))


@pytest.mark.parametrize('bad', ['absent', 'shape', 'float64', 'nonfinite'])
def test_active_guide_misalignment_rejects_before_mask_or_core(monkeypatch, bad):
    value = S.neutral(); value['enabled'] = True
    spec = SimpleNamespace(fringe_repair=value, scale=1)
    edited = np.zeros((4, 6, 3), np.float32)
    guide = {'absent': None, 'shape': np.zeros((2, 3, 3), np.float32),
             'float64': np.zeros_like(edited, dtype=np.float64),
             'nonfinite': np.full_like(edited, np.nan)}[bad]
    def forbidden(*args, **kwargs):
        raise AssertionError('Misaligned guide reached coverage allocation')
    monkeypatch.setattr(G, 'coverage', forbidden)
    with pytest.raises(ValueError, match='co-registered full-resolution guide'):
        F.apply_export(edited, guide, spec, source_size=(6, 4), geometry=None)


def test_guide_tile_replays_real_deformation_then_manual_liquify_and_restores_timing():
    pixels = np.arange(18, dtype=np.float32).reshape(2, 3, 3)
    class TensorStub:
        def __getitem__(self, key): return self
        def permute(self, *axes): return self
        def detach(self): return self
        def cpu(self): return self
        def numpy(self): return pixels
    original, warped = object(), object()
    calls = []
    pipe = SimpleNamespace(src_f32=original, last_deform_ms=12.,
                           manual_liquify=SimpleNamespace(last_ms=34.))
    def deform(source):
        assert source is original
        calls.append('deform'); pipe.last_deform_ms = 99.
        return warped
    def liquify(source):
        assert source is warped
        calls.append('manual'); pipe.manual_liquify.last_ms = 88.
        return TensorStub()
    pipe.apply_deform = deform; pipe.manual_liquify.apply = liquify
    guide = F.guide_tile(pipe)
    assert calls == ['deform', 'manual'] and guide.dtype == np.float32
    assert guide.flags.c_contiguous and guide.shape == (2, 3, 3)
    np.testing.assert_array_equal(guide, pixels)
    assert (pipe.last_deform_ms, pipe.manual_liquify.last_ms) == (12., 34.)


@pytest.mark.parametrize('branch', ['encoded', 'profile_gain_one', 'manual_gain_one'])
@pytest.mark.parametrize('levels', [(0., 1.), (.2, .8)])
def test_optical_guide_matches_actual_interpolation_space_at_half_pixel(monkeypatch, branch, levels):
    from lumaretouch_engine import optics_stage as OS, optics_native as ON, optics_state as O
    from lumaretouch_engine import cpu_memory_budget as M
    value = O.empty()
    value['lens'].update(distortion=1., crop_lock=False,
                         vignette=10. if branch == 'manual_gain_one' else 0., midpoint=100.)
    guide = np.repeat(np.array([[levels]], np.float32).reshape(1, 2, 1), 3, axis=2)
    untouched = guide.copy()
    def prepare(stage, shape):
        stage.shape = tuple(shape); stage.inverse = np.eye(3)
        stage.profile = (SimpleNamespace(gains=lambda: np.ones((1, 2, 3), np.float64))
                         if branch == 'profile_gain_one' else None)
        return stage
    def coordinates(stage, *, y0=0, rows=None):
        return np.broadcast_to(np.array([.5, 0.]), (rows, 2, 3, 2)).copy()
    sample_sources = []
    def half_pixel_sample(source, coordinates):
        assert source.dtype == np.float64 and source.flags.c_contiguous
        assert np.all(coordinates[..., 0] == .5) and np.all(coordinates[..., 1] == 0.)
        sample_sources.append(source)
        return np.broadcast_to((source[:, :1] + source[:, 1:2]) / 2., (*coordinates.shape[:-1], 3)).copy()
    monkeypatch.setattr(OS.OpticsStage, 'prepare', prepare)
    monkeypatch.setattr(OS.OpticsStage, 'coordinates', coordinates)
    monkeypatch.setattr(OS, 'sample', half_pixel_sample)
    monkeypatch.setattr(ON, 'sample', half_pixel_sample)
    monkeypatch.setattr(M, 'available_estimate', lambda: 1 << 40)
    actual = OS.OpticsStage(value, (1, 2)).apply_np(guide)
    sample_sources.clear()
    result = F.optical_guide(guide, SimpleNamespace(optics=value))
    linear_branch = branch != 'encoded'
    expected_source = OS.linear(guide.astype(np.float64)) if linear_branch else guide.astype(np.float64)
    expected = expected_source.mean(axis=1, keepdims=True)
    if linear_branch:
        expected = OS.encoded(expected)
    np.testing.assert_allclose(result, np.broadcast_to(expected, guide.shape), atol=1e-7, rtol=0.)
    np.testing.assert_array_equal(result, actual)
    np.testing.assert_array_equal(guide, untouched)
    assert result.dtype == np.float32 and result.shape == guide.shape
    assert len(sample_sources) == 3 and all(source is sample_sources[0] for source in sample_sources)
    np.testing.assert_allclose(sample_sources[0], expected_source, atol=1e-15, rtol=0.)
    if levels == (0., 1.) and linear_branch:
        # A gamma-domain .5 guide against the real ~.735 edit is a false halo.
        assert float(result[0, 0, 0]) > .73


def test_optical_guide_omits_gain_values_but_keeps_gain_branch_interpolation(monkeypatch):
    from lumaretouch_engine import optics_stage as OS, optics_native as ON, optics_state as O
    value = O.empty(); value['lens']['distortion'] = 1.
    guide = np.full((1, 2, 3), .25, np.float32)
    def prepare(stage, shape):
        stage.shape = tuple(shape); stage.inverse = np.eye(3)
        stage.profile = SimpleNamespace(gains=lambda: np.full((1, 2, 3), 3., np.float64))
        return stage
    monkeypatch.setattr(OS.OpticsStage, 'prepare', prepare)
    monkeypatch.setattr(OS.OpticsStage, 'coordinates',
                        lambda stage, **kwargs: np.zeros((1, 2, 3, 2), np.float64))
    monkeypatch.setattr(ON, 'sample', lambda source, coords: source.copy())
    result = F.optical_guide(guide, SimpleNamespace(optics=value))
    np.testing.assert_allclose(result, guide, atol=1e-7, rtol=0.)
