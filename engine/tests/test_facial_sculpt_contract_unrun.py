# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. These definitions are not execution or photographic proof."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import facial_sculpt_state as S
from lumaretouch_engine import facial_sculpt_support as V
from lumaretouch_engine import facial_sculpt_project as PROJECT
from lumaretouch_engine import facial_sculpt_composition as C
from lumaretouch_engine import facial_sculpt_native as N
from lumaretouch_engine import facial_sculpt_layer as L


def test_facial_sculpt_exact_mapping_and_no_forged_recipe():
    assert S.CONTROL_IDS == {'highlight': 'LNX-REF-PC-32471-C-8f773e9125', 'shadow': 'LNX-REF-PC-32471-C-01b2ee2d32'}
    assert not S.active(None)
    for raw in (True, -1, 1.001, float('nan'), float('inf'), 10**1000, '0.5'):
        with pytest.raises(ValueError): S.check({**S.neutral(), 'highlight': raw})
    for extra in ('source', 'reviewed', 'mask', 'radius', 'face_ref', 'linked', 'amount'):
        with pytest.raises(ValueError): S.check({**S.neutral(), extra: 1})
    with pytest.raises(ValueError): PROJECT.validate_leaf('/skin_gloss', .5)
    with pytest.raises(ValueError): PROJECT.validate_leaf('/shadow', True)


def test_facial_sculpt_neutral_does_not_acquire_models_or_review(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Neutral must not acquire native or geometry')
    monkeypatch.setattr(N, 'field', forbidden)
    assert L.prepare(None, None, None, S.neutral(), byte_budget=0, reviewed=None) is None


def test_facial_sculpt_source_record_cannot_borrow_another_family():
    ref = {'asset_sha256': 'a'*64, 'face_instance_id': 'person-a', 'analysis_revision': 1}
    record = {'version': 1, 'face_ref': ref, 'source': {'sha256': 'a'*64, 'width': 100, 'height': 100},
              'row': {'target': 'face_decoration_visibility', 'landmark_digest': 'b'*64, 'region': {}}}
    with pytest.raises(ValueError): V.check_record(record)
    for size in (True, 0, 1, 1_000_001):
        with pytest.raises(ValueError): V.check_source({'sha256': 'a'*64, 'width': size, 'height': 100})
    with pytest.raises(ValueError): V.check_region({'recipe': {}, 'visible': 1, 'unoccluded': True, 'ownership_confirmed': True})


def test_facial_sculpt_gain_is_signed_chromaticity_preserving_and_texture_retaining():
    # A constant field multiplies, rather than replaces, fine-scale linear detail.
    source = np.array([[[.2, .3, .4], [.21, .315, .42], [.6, .8, 1.0]]], np.float32)
    gain = np.array([[.1, -.1, .24]], np.float32)
    output = C.apply_np(source, gain)
    assert np.all(output[0, 0] > source[0, 0])
    assert np.all(output[0, 1] < source[0, 1])
    assert np.all((output >= 0) & (output <= 1))
    def linear(value):
        value = value.astype(np.float64)
        return np.where(value <= .04045, value/12.92, ((value+.055)/1.055)**2.4)
    a, b = linear(source), linear(output)
    for i, j in ((0, 1), (0, 2), (1, 2)):
        assert np.max(np.abs(a[..., i]*b[..., j]-a[..., j]*b[..., i])) < 2e-6
    texture = np.array([[[.2, .3, .4], [.22, .31, .42], [.21, .32, .41]]], np.float32)
    transformed = C.apply_np(texture, np.full((1, 3), .1, np.float32))
    assert np.allclose(linear(transformed), linear(texture)*np.exp(.1), atol=2e-7)


def test_facial_sculpt_exact_protection_and_unsupported_inputs():
    source = np.full((4, 5, 3), .4, np.float32); field = np.zeros((4, 5), np.float32); field[2, 2] = .1
    output = C.apply_np(source, field)
    assert np.array_equal(output[field == 0].view(np.uint32), source[field == 0].view(np.uint32))
    assert C.apply_np(source, np.zeros_like(field)) is source
    hdr = source.copy(); hdr[0, 0, 0] = 1.2
    with pytest.raises(ValueError): C.apply_np(hdr, field)
    with pytest.raises(ValueError): C.apply_np(np.ones((4, 5, 4), np.float32), field)
    with pytest.raises(ValueError): C.apply_np(source, np.full((4, 5), .25, np.float32))


def test_facial_sculpt_native_missing_is_honest(monkeypatch):
    def missing(): raise RuntimeError('missing native fixture')
    monkeypatch.setattr(N, 'native', missing)
    assert not N.available()
    with pytest.raises(RuntimeError):
        N.field(np.full((32, 32, 3), .4, np.float32), np.ones((32, 32), np.float32),
                np.ones((32, 32), np.float32), {**S.neutral(), 'highlight': 1}, radius=2)


def _record(name, window, field):
    field = np.ascontiguousarray(field, np.float32); field.setflags(write=False)
    return SimpleNamespace(stage='facial_sculpt', face_ref={'asset_sha256': 'a'*64, 'face_instance_id': name, 'analysis_revision': 1},
                           window=window, log_gain=field, delta=None, weights=None, chroma_shift=None)


def test_facial_sculpt_recovery_is_not_borrowed_and_overlap_deterministic():
    current = np.full((9, 10, 3), .4, np.float32)
    a = _record('a', (1, 2, 4, 5), np.full((4, 5), .1, np.float32))
    b = _record('b', (2, 3, 4, 5), np.full((4, 5), -.1, np.float32))
    left, _ = C.apply_records_np(current, [a, b]); right, _ = C.apply_records_np(current, [b, a])
    assert np.array_equal(left, right)
    with pytest.raises(ValueError): C.apply_records_np(current, [a], {('a', 'facial_sculpt'): {}})


def test_facial_sculpt_torch_full_source_tile_crop_parity():
    torch = pytest.importorskip('torch')
    source = np.full((17, 23, 3), .4, np.float32)
    record = _record('a', (2, 3, 12, 16), np.linspace(-.2, .2, 12*16, dtype=np.float32).reshape(12, 16))
    full, _ = C.apply_records_np(source, [record])
    tensor = torch.tensor(source).permute(2, 0, 1)[None]
    entire = C.apply_records_t(tensor, [record], source_shape=(17, 23))
    tile = C.apply_records_t(tensor[:, :, 5:13, 7:19], [record], source_shape=(17, 23), origin=(5, 7))
    np.testing.assert_allclose(entire[0].permute(1, 2, 0).numpy(), full, atol=2e-7)
    assert torch.equal(tile, entire[:, :, 5:13, 7:19])
