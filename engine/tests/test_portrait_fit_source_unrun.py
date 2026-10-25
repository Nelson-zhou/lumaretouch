"""AUTHORED / UNRUN: authenticated immutable full portrait fitting source.

Native/decoder responses are mocked where stated. No tests, product imports,
codecs, builds or inference were executed while authoring these contracts.
These fixtures are not photographic, performance or preview/export acceptance.
"""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import struct
import zlib

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import portrait_fit_source as F
from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import creative_document_base as BASE
from lumaretouch_engine import creative_document_assets as ASSETS
from lumaretouch_engine import decode as D
from lumaretouch_engine import full_source_working as W
from lumaretouch_engine import local_mask_state as M


def png16_bytes(pixels):
    h, w = pixels.shape[:2]
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = b''.join(b'\0' + row.astype('>u2').tobytes() for row in pixels)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 16, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def original(tmp_path, pixels=None):
    if pixels is None:
        pixels = np.array([[[0, 1, 255], [16, 127, 254]], [[12, 31, 47], [89, 211, 235]]], np.uint8)
    path = tmp_path / 'source.png'
    if pixels.dtype == np.uint16:
        path.write_bytes(png16_bytes(pixels))
    else:
        Image.fromarray(pixels).save(path)
    h, w = pixels.shape[:2]
    row = {'path': str(path), 'src_w': w, 'src_h': h, '_local_source_stamp': M.file_stamp(path),
           'document_id': 'document-one', 'document_revision': 3}
    engine = SimpleNamespace(_docs=[row], _doc_index=0, _load_id='load-one', _creative_base=None)
    return engine, SOURCE.binding(engine), pixels


def decoded(pixels, **changes):
    h, w = pixels.shape[:2]
    return SimpleNamespace(**{**dict(rgb=pixels, w=w, h=h, src_w=w, src_h=h,
        draft_used=False, raw=None, source_icc=None), **changes})


def admit(engine, source):
    size = 0 if engine._creative_base is not None else Path(engine._docs[0]['path']).stat().st_size
    return F.memory_estimate(source, original_bytes=size)


def capture(engine, source, **kwargs):
    return F.capture(engine, expected_source=source, byte_budget=admit(engine, source), **kwargs)


def creative():
    linear = np.full((2, 3, 4), .25, np.float32); linear[:, :, 3] = 1
    base = ASSETS.make_asset('rgba', 3, 2, linear.astype('<f4').tobytes())
    row = {'path': '/must/not/open/original.jpg', 'document_id': 'derived-one', 'document_revision': 2}
    engine = SimpleNamespace(_docs=[row], _doc_index=0, _load_id='derived-load', _creative_base=base)
    return engine, SOURCE.binding(engine)


def test_original_uses_full_decoder_and_bytes_are_genuinely_immutable(tmp_path, monkeypatch):
    engine, source, pixels = original(tmp_path)
    calls = []
    def full(path, **kwargs):
        calls.append((path, kwargs)); return decoded(pixels)
    monkeypatch.setattr(D, 'load_full', full)
    monkeypatch.setattr(SOURCE, 'analysis_rgb', lambda *_: pytest.fail('No analysis/display proxy'))
    result = capture(engine, source)
    assert calls == [(engine._docs[0]['path'], {'max_px': 4, 'device': 'cpu', 'want_bits': 8})]
    np.testing.assert_array_equal(result.pixels, pixels.astype(np.float32) / np.float32(255))
    assert result.source == source and result.binding == source
    assert result.owned_bytes == pixels.size * 4
    assert result.input_sha256 == sha256(result.pixels.tobytes()).hexdigest()
    assert result.pixels.dtype == np.float32 and result.pixels.flags.c_contiguous
    with pytest.raises(ValueError): result.pixels.setflags(write=True)
    with pytest.raises(ValueError): result.pixels[0, 0, 0] = 1
    descriptor = result.descriptor; descriptor['source']['width'] = 999
    assert result.source == source
    before = result.pixels.copy(); pixels[:] = 0
    np.testing.assert_array_equal(result.pixels, before)


def test_png16_keeps_low_bits_and_uses_shared_icc_boundary_once(tmp_path, monkeypatch):
    values = np.array([[[256, 257, 258], [32767, 32768, 32769]], [[1, 2, 3], [65533, 65534, 65535]]], np.uint16)
    engine, source, pixels = original(tmp_path, values)
    calls = []
    def full(path, **kwargs):
        assert kwargs['want_bits'] == 16
        return decoded(pixels, source_icc=b'profile')
    def working(value):
        calls.append(value.source_icc)
        return value.rgb
    monkeypatch.setattr(D, 'load_full', full); monkeypatch.setattr(W, 'working_rgb', working)
    result = capture(engine, source)
    assert calls == [b'profile'] and result.source_bits == 16
    np.testing.assert_array_equal(result.pixels, pixels.astype(np.float32) / np.float32(65535))
    assert len(set(result.pixels[0, 0])) == 3


def test_original_byte_hash_cannot_be_invented_by_caller(tmp_path, monkeypatch):
    engine, source, _ = original(tmp_path)
    monkeypatch.setattr(D, 'load_full', lambda *_a, **_k: pytest.fail('Wrong source must fail before decode'))
    with pytest.raises(ValueError, match='another effective pixel source'):
        capture(engine, {**source, 'sha256': 'a' * 64})


def test_memory_rejects_before_any_pixel_decoder_or_alpha_conversion(tmp_path, monkeypatch):
    engine, source, _ = original(tmp_path)
    monkeypatch.setattr(F, '_inspect_original', lambda *_: pytest.fail('No alpha/header pixel allocation'))
    monkeypatch.setattr(D, 'load_full', lambda *_a, **_k: pytest.fail('No decoder allocation'))
    with pytest.raises(MemoryError, match='no proxy fallback'):
        F.capture(engine, expected_source=source, byte_budget=admit(engine, source) - 1)
    assert admit(engine, source) == 128 * 4 + F.SCRATCH_BYTES + 2 * Path(engine._docs[0]['path']).stat().st_size


@pytest.mark.parametrize('change', [
    {'draft_used': True}, {'raw': {'used_preview': True}}, {'raw': {'half_size': True}},
    {'src_w': 9}, {'w': 1},
])
def test_reduced_or_substituted_full_sources_refuse(tmp_path, monkeypatch, change):
    engine, source, pixels = original(tmp_path)
    monkeypatch.setattr(D, 'load_full', lambda *_a, **_k: decoded(pixels, **change))
    with pytest.raises(ValueError, match='reduced, substituted'):
        capture(engine, source)


def test_rgb16_request_cannot_receive_padded_or_true_rgb8(tmp_path, monkeypatch):
    engine, source, pixels = original(tmp_path, np.full((2, 2, 3), 257, np.uint16))
    monkeypatch.setattr(D, 'load_full', lambda *_a, **_k: decoded(pixels.astype(np.uint8)))
    with pytest.raises(ValueError, match='lower-precision'):
        capture(engine, source)


def test_raw_uses_only_existing_full_16bit_branch(tmp_path, monkeypatch):
    from lumaretouch_engine.ops import libraw
    engine, source, _ = original(tmp_path)
    values = np.full((2, 2, 3), 32769, np.uint16)
    monkeypatch.setattr(D, 'is_raw', lambda _path: True)
    monkeypatch.setattr(libraw, 'identify', lambda _path: {'w': 2, 'h': 2})
    def full(_path, **kwargs):
        assert kwargs == {'max_px': 4, 'device': 'cpu', 'want_bits': 16}
        return decoded(values, raw={'source': 'libraw', 'used_preview': False, 'half_size': False})
    monkeypatch.setattr(D, 'load_full', full)
    assert capture(engine, source).source_bits == 16
    monkeypatch.setattr(libraw, 'identify', lambda _path: None)
    with pytest.raises(ValueError, match='before decoding'): capture(engine, source)


def test_changed_file_or_active_document_during_decode_refuses(tmp_path, monkeypatch):
    engine, source, pixels = original(tmp_path)
    def replace(_path, **_kwargs):
        Path(_path).write_bytes(b'changed actual source')
        return decoded(pixels)
    monkeypatch.setattr(D, 'load_full', replace)
    with pytest.raises(ValueError, match='changed'): capture(engine, source)
    engine, source, pixels = original(tmp_path)
    def switch(_path, **_kwargs):
        engine._load_id = 'another-load'; return decoded(pixels)
    monkeypatch.setattr(D, 'load_full', switch)
    with pytest.raises(ValueError, match='document changed'): capture(engine, source)


def test_actual_alpha_rejected_before_rgb_decoder(tmp_path, monkeypatch):
    pixels = np.full((2, 2, 4), 100, np.uint8); pixels[:, :, 3] = 254
    engine, source, _ = original(tmp_path, pixels)
    monkeypatch.setattr(D, 'load_full', lambda *_a, **_k: pytest.fail('No RGB alpha discard'))
    with pytest.raises(ValueError, match='transparency'): capture(engine, source)


def test_derived_uses_exact_export_bridge_and_never_opens_original(tmp_path, monkeypatch):
    engine, source = creative()
    values = np.full((2, 3, 3), .500001, np.float32); values[0, 0, 0] = np.float32(-0.)
    monkeypatch.setattr(M, 'file_stamp', lambda *_: pytest.fail('Derived source is not original path'))
    monkeypatch.setattr(M, 'source_digest', lambda *_: pytest.fail('No original provenance substitution'))
    monkeypatch.setattr(D, 'load_full', lambda *_a, **_k: pytest.fail('No original or proxy decode'))
    seen = []
    def bridge(base, **kwargs):
        seen.append(base['id']); return values
    monkeypatch.setattr(BASE, 'export_source', bridge)
    result = capture(engine, source)
    assert seen == [engine._creative_base['id']] and result.kind == 'creative' and result.source_bits == 32
    np.testing.assert_array_equal(result.pixels.view(np.uint32), values.view(np.uint32))
    assert result.owned_bytes == 2 * 3 * 12


@pytest.mark.parametrize('bad', [np.nan, np.inf, -.0001, 1.0001])
def test_derived_nonfinite_or_hdr_cannot_be_clipped(monkeypatch, bad):
    engine, source = creative()
    values = np.full((2, 3, 3), .5, np.float32); values[0, 0, 0] = bad
    monkeypatch.setattr(BASE, 'export_source', lambda *_a, **_k: values)
    with pytest.raises(ValueError, match='clipping is forbidden'): capture(engine, source)


def test_native_alpha_hdr_rejection_is_terminal_and_no_proxy_retry(monkeypatch):
    engine, source = creative()
    def refuse(*_a, **_k): raise ValueError('Native source refuses alpha/HDR')
    monkeypatch.setattr(BASE, 'export_source', refuse)
    monkeypatch.setattr(SOURCE, 'analysis_rgb', lambda *_: pytest.fail('No fallback'))
    with pytest.raises(ValueError, match='alpha/HDR'): capture(engine, source)


def test_derived_content_changed_during_bridge_is_reauthenticated(monkeypatch):
    engine, source = creative()
    def changed(*_args, **_kwargs):
        rgba = np.ones((2, 3, 4), np.float32)
        engine._creative_base = ASSETS.make_asset('rgba', 3, 2, rgba.astype('<f4').tobytes())
        return np.full((2, 3, 3), .5, np.float32)
    monkeypatch.setattr(BASE, 'export_source', changed)
    with pytest.raises(ValueError, match='another effective pixel source'): capture(engine, source)


def test_cancellation_returns_no_partial_result_and_allocates_nothing_when_already_cancelled(tmp_path, monkeypatch):
    engine, source, _ = original(tmp_path)
    monkeypatch.setattr(D, 'load_full', lambda *_a, **_k: pytest.fail('Cancelled before decode'))
    with pytest.raises(InterruptedError): capture(engine, source, cancelled=lambda: True)


def test_provider_has_no_inference_repairs_transform_or_mutable_cache():
    text = (Path(__file__).parents[1] / 'src/lumaretouch_engine/portrait_fit_source.py').read_text()
    assert 'pipe.src_f32' not in text and 'analysis_rgb(' not in text and 'load_rgb(' not in text
    assert 'export_float(' not in text and 'setattr(engine' not in text
    assert 'np.clip' not in text  # No hidden SDR clamp.
    assert 'working_rgb(decoded)' in text and 'export_source(base,' in text


def test_original_snapshot_provider_authenticates_real_bytes_without_engine(tmp_path, monkeypatch):
    engine, source, pixels = original(tmp_path)
    row = engine._docs[0]
    monkeypatch.setattr(D, 'load_full', lambda *_a, **_k: decoded(pixels))
    direct = F.capture_original(row['path'], expected_source=source,
        expected_stamp=row['_local_source_stamp'], byte_budget=admit(engine, source))
    current = capture(engine, source)
    assert direct.descriptor == current.descriptor
    np.testing.assert_array_equal(direct.pixels, current.pixels)
    with pytest.raises(ValueError, match='expected source'):
        F.capture_original(row['path'], expected_source={**source, 'sha256': '0' * 64},
            expected_stamp=row['_local_source_stamp'], byte_budget=admit(engine, source))
    with pytest.raises(ValueError, match='stamp changed'):
        F.capture_original(row['path'], expected_source=source,
            expected_stamp=(0, 0, 0, 0, 0), byte_budget=admit(engine, source))


def test_original_snapshot_raw_fit_remains_16bit_independent_of_delivery_decode(tmp_path, monkeypatch):
    from lumaretouch_engine.ops import libraw
    engine, source, _ = original(tmp_path)
    row = engine._docs[0]
    high = np.array([[[256, 257, 258], [512, 513, 514]], [[1001, 1002, 1003], [32767, 32768, 32769]]], np.uint16)
    monkeypatch.setattr(D, 'is_raw', lambda _: True)
    monkeypatch.setattr(libraw, 'identify', lambda _: {'w': 2, 'h': 2})
    def load(_path, **kwargs):
        assert kwargs['want_bits'] == 16
        return decoded(high, raw={'source': 'libraw', 'used_preview': False, 'half_size': False})
    monkeypatch.setattr(D, 'load_full', load)
    result = F.capture_original(row['path'], expected_source=source,
        expected_stamp=row['_local_source_stamp'], byte_budget=admit(engine, source))
    np.testing.assert_array_equal(result.pixels, high.astype(np.float32) / np.float32(65535))


@pytest.mark.parametrize('kind,data', [
    (b'cICP', b'\x09\x10\x00\x01'), (b'mDCV', b'\0' * 24), (b'cLLI', b'\0' * 8),
])
def test_png8_hdr_metadata_cannot_hide_behind_pillow_info(tmp_path, monkeypatch, kind, data):
    engine, _, pixels = original(tmp_path)
    row = engine._docs[0]; path = Path(row['path'])
    chunk = struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    content = path.read_bytes(); path.write_bytes(content[:33] + chunk + content[33:])
    row['_local_source_stamp'] = M.file_stamp(path)
    source = SOURCE.binding(engine)
    monkeypatch.setattr(D, 'load_full', lambda *_a, **_k: pytest.fail('No RGB8 HDR relabelling'))
    with pytest.raises(ValueError): capture(engine, source)
