"""AUTHORED / UNRUN: native RGB16 encoder and actual-file verification.

Qoder owns execution. No product import, codec, test, fixture generation or
performance run occurred during authoring. This file is not an acceptance result.
"""
from dataclasses import replace
from pathlib import Path
import struct
import zlib

import imagecodecs
import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import export as E
from lumaretouch_engine import png16_export as W
from lumaretouch_engine import png16_source as P
from lumaretouch_engine import export_destination_runtime as runtime
from lumaretouch_engine.export_destination_commit import CommitFailure
from lumaretouch_engine.export_destination_policy import Source, Policy, freeze, DestinationError


def _rich16(h=19, w=23):
    return ((np.arange(h * w * 3, dtype=np.uint32) * 251 + 3) % 65536).astype(np.uint16).reshape(h, w, 3)


def _profile():
    return (Path(__file__).parent / 'fixtures' / 'icc' / 'AdobeCompat-v2.icc').read_bytes()


def _write(path, pixels=None, *, target_icc=None, **kwargs):
    return W.write_verified_png16(_rich16() if pixels is None else pixels, str(path),
                                 target_icc=target_icc, **kwargs)


def _chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))


def _chunks(blob):
    offset = 8
    result = []
    while offset < len(blob):
        length = int.from_bytes(blob[offset:offset + 4], 'big')
        kind = blob[offset + 4:offset + 8]
        payload = blob[offset + 8:offset + 8 + length]
        result.append((kind, payload))
        offset += 12 + length
    return result


def _forbid_codec(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Rejected or skipped output reached native encoding')
    monkeypatch.setattr(imagecodecs, 'png_encode', forbidden)


@pytest.fixture(autouse=True)
def _known_memory_budget(monkeypatch):
    from lumaretouch_engine import cpu_memory_budget
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 16 * 1024**3)


@pytest.mark.parametrize('profile_name', ['none', 'srgb', 'adobe'])
@pytest.mark.parametrize('layout', ['contiguous', 'reversed', 'transposed'])
def test_real_rgb16_pixels_icc_and_low_bits_survive_actual_file(tmp_path, monkeypatch, profile_name, layout):
    pixels = _rich16()
    if layout == 'reversed':
        pixels = pixels[:, ::-1]
    elif layout == 'transposed':
        pixels = pixels.swapaxes(0, 1)
    before = pixels.copy()
    profile = {'none': None, 'srgb': E._srgb_bytes(), 'adobe': _profile()}[profile_name]
    original = imagecodecs.png_encode
    calls = []
    def observe(array, **kwargs):
        calls.append(kwargs)
        assert array.dtype == np.uint16 and array.shape == pixels.shape
        assert array.flags.c_contiguous
        np.testing.assert_array_equal(array, before)
        return original(array, **kwargs)
    monkeypatch.setattr(imagecodecs, 'png_encode', observe)
    def forbidden(*args, **kwargs):
        raise AssertionError('RGB16 writer must not use a Pillow RGB8 plane')
    monkeypatch.setattr(Image, 'fromarray', forbidden)
    path = tmp_path / 'delivery.PNG'
    result = _write(path, pixels, target_icc=profile)
    assert calls == [{'level': 6}]
    np.testing.assert_array_equal(pixels, before)
    np.testing.assert_array_equal(imagecodecs.png_decode(path.read_bytes()), before)
    decoded = P.load_opaque_rgb16(path)
    np.testing.assert_array_equal(decoded.rgb, before)
    assert decoded.rgb.dtype == np.uint16
    assert decoded.source_icc == profile
    assert decoded.source_exif is None and decoded.orientation == 1
    assert P.source_header(path).bits == 16 and P.source_header(path).color_type == 2
    chunks = _chunks(path.read_bytes())
    assert [kind for kind, _ in chunks].count(b'iCCP') == int(profile is not None)
    assert {kind for kind, _ in chunks} <= {b'IHDR', b'iCCP', b'IDAT', b'IEND'}
    if profile is not None:
        assert chunks[1][0] == b'iCCP'
        assert P._inflate_icc(chunks[1][1]) == profile
    assert result['format'] == 'png' and result['bits'] == 16 and not result['skipped']
    assert result['bytes'] == path.stat().st_size
    assert result['readback_max_diff'] == 0
    assert result['levels_per_channel'] == [np.unique(before[..., c]).size for c in range(3)]
    assert all(count > 256 for count in result['levels_per_channel'])
    assert result['low8_nonzero_px'] == int(np.count_nonzero(before & 255)) > 0
    assert result['icc_readback_bytes'] == (len(profile) if profile else 0)
    assert result['icc_readback_matches'] is (True if profile else None)
    assert result['tiff_compression'] is result['tiff_compression_tag'] is None
    assert result['encoder_quality'] is None
    assert result['png_compress_level'] == result['compress_level'] == 6
    assert result['gps_written'] is False and result['exif_bytes'] == 0
    assert result['orientation_tag_written'] is False
    assert result['metadata_policy'] == 'target_icc_only_no_source_exif'
    for field in ('encode_ms', 'write_ms', 'readback_ms', 'verification_ms'):
        assert result[field] >= 0


def test_true16_black_and_low_code_values_are_not_mistaken_for_promoted_sources(tmp_path):
    pixels = np.array([[[0, 1, 255], [256, 257, 258], [65533, 65534, 65535]]], dtype=np.uint16)
    result = _write(tmp_path / 'codes.png', pixels)
    assert result['readback_max_diff'] == 0
    np.testing.assert_array_equal(P.load_opaque_rgb16(result['path']).rgb, pixels)


@pytest.mark.parametrize('pixels', [
    np.zeros((3, 4, 3), np.uint8), np.zeros((3, 4, 3), np.float32),
    np.zeros((3, 4, 4), np.uint16), np.zeros((3, 4), np.uint16),
    np.zeros((0, 4, 3), np.uint16), np.zeros((3, 0, 3), np.uint16), None,
])
def test_invalid_rgb_input_refuses_before_codec_or_publication(tmp_path, monkeypatch, pixels):
    _forbid_codec(monkeypatch)
    path = tmp_path / 'refused.png'
    with pytest.raises(E.ExportError, match='uint16|尺寸'):
        W.write_verified_png16(pixels, str(path), target_icc=None)
    assert not path.exists()


@pytest.mark.parametrize('option,value,match', [
    ('metadata_include_gps', True, 'EXIF/GPS'),
    ('conflict_policy', 'overwrite', 'conflict_policy'),
    ('target_icc', b'not an ICC profile', 'ICC'),
    ('target_icc', 'not bytes', 'ICC'),
])
def test_invalid_options_refuse_even_when_output_already_exists(tmp_path, monkeypatch, option, value, match):
    _forbid_codec(monkeypatch)
    path = tmp_path / 'existing.png'
    path.write_bytes(b'previous-result')
    with pytest.raises(E.ExportError, match=match):
        _write(path, **{option: value})
    assert path.read_bytes() == b'previous-result'


def test_wrong_extension_and_pixel_budget_refuse_before_codec(tmp_path, monkeypatch):
    _forbid_codec(monkeypatch)
    with pytest.raises(E.ExportError, match='扩展名'):
        _write(tmp_path / 'wrong.tif')
    monkeypatch.setattr(P, 'MAX_SOURCE_PIXELS', 10)
    with pytest.raises(E.ExportError, match='像素预算'):
        _write(tmp_path / 'large.png')
    assert list(tmp_path.iterdir()) == []


def test_memory_admission_happens_before_encoding_and_any_publication(tmp_path, monkeypatch):
    from lumaretouch_engine import cpu_memory_budget
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 256 * 1024**2)
    _forbid_codec(monkeypatch)
    path = tmp_path / 'out.png'
    with pytest.raises(E.ExportError, match='内存预算不足'):
        _write(path)
    assert not path.exists()


def test_memory_is_rechecked_after_encode_before_publication(tmp_path, monkeypatch):
    from lumaretouch_engine import cpu_memory_budget
    original = imagecodecs.png_encode
    def consume_budget(array, **kwargs):
        blob = original(array, **kwargs)
        monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 256 * 1024**2)
        return blob
    monkeypatch.setattr(imagecodecs, 'png_encode', consume_budget)
    path = tmp_path / 'not-published.png'
    with pytest.raises(E.ExportError, match='内存预算不足'):
        _write(path)
    assert not path.exists()


def test_skip_has_no_native_work_and_no_successful_readback_claim(tmp_path, monkeypatch):
    _forbid_codec(monkeypatch)
    path = tmp_path / 'existing.png'
    path.write_bytes(b'previous-result')
    result = _write(path)
    assert result['skipped'] and result['bytes'] == 0
    assert result['readback_max_diff'] is result['levels_per_channel'] is None
    assert result['icc_readback_matches'] is result['icc_readback_bytes'] is None
    assert result['low8_nonzero_px'] is None
    assert result['encode_ms'] == result['write_ms'] == result['readback_ms'] == 0
    assert path.read_bytes() == b'previous-result'


def test_recheck_uses_shared_unique_target_without_overwriting_existing(tmp_path):
    path = tmp_path / 'existing.png'
    path.write_bytes(b'previous-result')
    result = _write(path, conflict_policy='recheck')
    assert result['path'] == str(tmp_path / 'existing-0001.png')
    assert result['renamed_from'] == str(path)
    assert result['readback_max_diff'] == 0
    assert path.read_bytes() == b'previous-result'


def _plan(tmp_path):
    source = tmp_path / 'original.png'
    source.write_bytes(b'untouched-original')
    row = Source('document:one', str(source), str(tmp_path), 'frozen-frame', 'output.png')
    plan = freeze([row], Policy(chosen_root=str(tmp_path / 'delivery'), create_missing=True),
                  {'format': 'png', 'bit_depth': 16}, 1)
    return row, plan


def test_frozen_destination_creates_only_approved_directory_and_retry_does_not_rename(tmp_path):
    row, plan = _plan(tmp_path)
    target = plan.entries[0].target
    result = runtime.run(plan.payload(), row.item_id, _write, Path(target))
    assert result['path'] == target and result['readback_max_diff'] == 0
    with pytest.raises(DestinationError, match='冻结输出已存在'):
        runtime.run(plan.payload(), row.item_id, _write, Path(target), conflict_policy='recheck')
    assert Path(row.source_path).read_bytes() == b'untouched-original'
    assert not Path(target).with_name('output-0001.png').exists()


def test_frozen_destination_rejects_unowned_path_before_native(tmp_path, monkeypatch):
    row, plan = _plan(tmp_path)
    _forbid_codec(monkeypatch)
    with pytest.raises(DestinationError, match='不属于冻结批次'):
        runtime.run(plan.payload(), row.item_id, _write, tmp_path / 'outside.png')
    assert not (tmp_path / 'outside.png').exists()
    assert not (tmp_path / 'delivery').exists()


def test_no_implicit_directory_creation_without_frozen_permission(tmp_path):
    path = tmp_path / 'unauthorized' / 'output.png'
    with pytest.raises(CommitFailure) as error:
        _write(path)
    assert error.value.committed is False
    assert not path.parent.exists()


def test_raced_in_destination_is_not_overwritten_or_reported_successful(tmp_path, monkeypatch):
    original = E._atomic_write
    path = tmp_path / 'race.png'
    def race(target, data):
        Path(target).write_bytes(b'raced-in-original')
        return original(target, data)
    monkeypatch.setattr(E, '_atomic_write', race)
    with pytest.raises(CommitFailure) as error:
        _write(path)
    assert error.value.committed is False
    assert path.read_bytes() == b'raced-in-original'
    assert list(tmp_path.glob('.lrt-export-*.tmp')) == []


@pytest.mark.parametrize('kind,payload', [
    (b'eXIf', b'II*\0' + bytes(4)), (b'iCCP', b'Unexpected\0\0x'),
    (b'sRGB', b'\0'), (b'cICP', b'\x09\x10\0\x01'),
    (b'tRNS', bytes(6)), (b'acTL', struct.pack('>II', 1, 0)),
])
def test_unpromised_native_metadata_is_rejected_before_publication(tmp_path, monkeypatch, kind, payload):
    blob = imagecodecs.png_encode(_rich16())
    bad = blob[:33] + _chunk(kind, payload) + blob[33:]
    monkeypatch.setattr(imagecodecs, 'png_encode', lambda *a, **k: bad)
    path = tmp_path / 'bad.png'
    with pytest.raises(E.ExportError, match='额外元数据'):
        _write(path)
    assert not path.exists()


@pytest.mark.parametrize('change', ['rgb8', 'rgba16', 'dimensions', 'interlace'])
def test_native_header_mismatch_cannot_masquerade_as_rgb16(tmp_path, monkeypatch, change):
    blob = imagecodecs.png_encode(_rich16())
    fields = list(struct.unpack('>IIBBBBB', blob[16:29]))
    index, value = {'rgb8': (2, 8), 'rgba16': (3, 6),
                    'dimensions': (0, fields[0] + 1), 'interlace': (6, 1)}[change]
    fields[index] = value
    bad = blob[:8] + _chunk(b'IHDR', struct.pack('>IIBBBBB', *fields)) + blob[33:]
    monkeypatch.setattr(imagecodecs, 'png_encode', lambda *a, **k: bad)
    path = tmp_path / 'bad.png'
    with pytest.raises(E.ExportError, match='真实 RGB16'):
        _write(path)
    assert not path.exists()


@pytest.mark.parametrize('change', ['crc', 'truncated', 'trailing', 'no_iend', 'no_idat', 'huge_chunk'])
def test_malformed_native_container_refuses_before_publication(tmp_path, monkeypatch, change):
    blob = imagecodecs.png_encode(_rich16())
    bad = {
        'crc': blob[:-1] + bytes([blob[-1] ^ 1]),
        'truncated': blob[:-1], 'trailing': blob + b'x', 'no_iend': blob[:-12],
        'no_idat': blob[:33] + _chunk(b'IEND', b''),
        'huge_chunk': blob[:33] + struct.pack('>I', 2**31) + blob[37:],
    }[change]
    monkeypatch.setattr(imagecodecs, 'png_encode', lambda *a, **k: bad)
    path = tmp_path / 'bad.png'
    with pytest.raises(E.ExportError, match='编码'):
        _write(path)
    assert not path.exists()


@pytest.mark.parametrize('budget', ['chunks', 'encoded_bytes', 'icc_bytes'])
def test_container_and_metadata_budgets_are_enforced(tmp_path, monkeypatch, budget):
    if budget == 'chunks':
        monkeypatch.setattr(P, 'MAX_CHUNKS', 3)  # IHDR + iCCP + IDAT + IEND is already four.
    elif budget == 'encoded_bytes':
        monkeypatch.setattr(P, 'MAX_SOURCE_BYTES', 64)
    else:
        monkeypatch.setattr(P, 'MAX_METADATA_BYTES', 64)
        _forbid_codec(monkeypatch)
    path = tmp_path / 'budget.png'
    with pytest.raises(E.ExportError, match='预算'):
        _write(path, target_icc=_profile())
    assert not path.exists()


def test_native_encode_exception_has_no_output_or_pillow_fallback(tmp_path, monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError('deliberate native codec failure')
    monkeypatch.setattr(imagecodecs, 'png_encode', failed)
    path = tmp_path / 'failure.png'
    with pytest.raises(E.ExportError, match='未提交输出.*deliberate'):
        _write(path)
    assert not path.exists()


def test_real_pixel_readback_detects_one_low_bit_corruption_and_retains_file(tmp_path, monkeypatch):
    original = imagecodecs.png_encode
    def corrupt(array, **kwargs):
        changed = array.copy()
        changed[0, 0, 0] ^= 1
        return original(changed, **kwargs)
    monkeypatch.setattr(imagecodecs, 'png_encode', corrupt)
    path = tmp_path / 'corrupt.png'
    with pytest.raises(E.ExportError, match='验证失败.*像素最大差=1'):
        _write(path)
    assert path.exists()
    assert P.load_opaque_rgb16(path).rgb[0, 0, 0] == (_rich16()[0, 0, 0] ^ 1)


@pytest.mark.parametrize('change', ['icc', 'exif', 'orientation', 'rgb8', 'exception'])
def test_readback_metadata_or_decoder_failure_never_returns_success(tmp_path, monkeypatch, change):
    original = P.load_opaque_rgb16
    def corrupt(*args, **kwargs):
        actual = original(*args, **kwargs)
        if change == 'icc':
            return replace(actual, source_icc=b'different ICC')
        if change == 'exif':
            return replace(actual, source_exif=b'unpromised EXIF')
        if change == 'orientation':
            return replace(actual, orientation=6)
        if change == 'rgb8':
            return replace(actual, rgb=actual.rgb.astype(np.uint8))
        raise ValueError('deliberate decoder failure')
    monkeypatch.setattr(P, 'load_opaque_rgb16', corrupt)
    path = tmp_path / 'retained.png'
    with pytest.raises(E.ExportError, match='验证失败.*文件保留'):
        _write(path, target_icc=_profile())
    assert path.exists()
    assert original(path).source_icc == _profile()
