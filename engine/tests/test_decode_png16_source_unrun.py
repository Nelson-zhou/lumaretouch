"""AUTHORED / UNRUN: genuine original PNG16 decode and bounded SDR admission.

No product imports, codec calls, fixture generation or tests were executed while
authoring. Qoder owns local execution. These are not UI/quality/performance or
export acceptance claims. PNG fixtures use independent filter-zero/zlib bytes.
"""
from pathlib import Path
from types import SimpleNamespace
import struct
import zlib

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import decode as D
from lumaretouch_engine import png16_source as P


def _rich16(h=7, w=11):
    return ((np.arange(h * w * 3, dtype=np.uint32) * 251 + 3) % 65536).astype(np.uint16).reshape(h, w, 3)


def _chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))


def _png(pixels, *, before=(), after=(), interlace=0, bits=16):
    pixels = np.asarray(pixels)
    channels = pixels.shape[2] if pixels.ndim == 3 else 1
    kind = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    h, w = pixels.shape[:2]
    header = struct.pack('>IIBBBBB', w, h, bits, kind, 0, 0, interlace)
    passes = ((0, 0, 1, 1),) if not interlace else (
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
        (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
    rows = []
    for x, y, dx, dy in passes:
        block = pixels[y::dy, x::dx]
        if block.shape[1]:
            rows.extend(b'\0' + row.astype('>u2' if bits == 16 else np.uint8).tobytes() for row in block)
    return (P.SIGNATURE + _chunk(b'IHDR', header)
            + b''.join(_chunk(kind, payload) for kind, payload in before)
            + _chunk(b'IDAT', zlib.compress(b''.join(rows)))
            + b''.join(_chunk(kind, payload) for kind, payload in after)
            + _chunk(b'IEND', b''))


def _write(tmp_path, pixels=None, *, name='source.png', **kwargs):
    path = tmp_path / name
    path.write_bytes(_png(_rich16() if pixels is None else pixels, **kwargs))
    return str(path)


def _profile():
    return (Path(__file__).parent / 'fixtures' / 'icc' / 'AdobeCompat-v2.icc').read_bytes()


def _iccp(profile):
    return (b'iCCP', b'Source RGB\0\0' + zlib.compress(profile))


def _quantize8(pixels):
    return ((pixels.astype(np.uint32) + 128) // 257).astype(np.uint8)


def _forbid_native(monkeypatch):
    import imagecodecs
    def forbidden(*args, **kwargs):
        raise AssertionError('Unsafe source reached the native pixel decoder')
    monkeypatch.setattr(imagecodecs, 'png_decode', forbidden)


@pytest.fixture(autouse=True)
def _known_memory_budget(monkeypatch):
    from lumaretouch_engine import cpu_memory_budget
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 16 * 1024**3)


@pytest.mark.parametrize('name', ['source.png', 'content-not-suffix.jpg', 'content-before-raw.dng'])
@pytest.mark.parametrize('interlace', [0, 1])
def test_real_rgb16_low_bits_are_lossless_and_never_enter_pillow8(tmp_path, monkeypatch, name, interlace):
    source = _rich16()
    path = _write(tmp_path, source, name=name, interlace=interlace)
    def forbidden(*args, **kwargs):
        raise AssertionError('PNG16 must not enter Pillow RGB8 or RAW')
    monkeypatch.setattr(D, '_load_full_pillow', forbidden)
    monkeypatch.setattr(D, '_load_rgb_pillow', forbidden)
    monkeypatch.setattr(D, 'is_raw', forbidden)
    header = P.source_header(path)
    assert (header.width, header.height, header.bits, header.color_type, header.interlace) == (11, 7, 16, 2, interlace)
    decoded = D.load_full(path, want_bits=16)
    np.testing.assert_array_equal(decoded.rgb, source)
    assert decoded.rgb.dtype == np.uint16 and decoded.rgb.flags.c_contiguous
    assert np.any(decoded.rgb & 255)
    assert decoded.raw == {'source': 'png16', 'bits': 16, 'used_preview': False, 'half_size': False}
    assert decoded.src_bits == decoded.meta()['src_bits'] == 16
    np.testing.assert_array_equal(D.load_full(path, want_bits=8).rgb, _quantize8(source))
    proxy = D.load_rgb(path)
    np.testing.assert_array_equal(proxy.rgb, _quantize8(source))
    assert proxy.src_bits == 16 and not proxy.draft_used
    assert any('非静默降位' in note for note in proxy.notes)


def test_png8_cannot_be_promoted_to_an_invented_master(tmp_path):
    path = _write(tmp_path, _rich16().astype(np.uint8), bits=8)
    assert P.source_header(path).bits == 8
    with pytest.raises(ValueError, match='16-bit'):
        D.load_full(path, want_bits=16)


def test_png_named_raw_keeps_png_identity_for_full_source_consumers(tmp_path):
    path = _write(tmp_path, name='source.dng')
    assert D.is_raw(path) is False


def test_source_bits_uses_real_png_header_not_pillow_rgb_mode(tmp_path):
    path = _write(tmp_path, name='not-a-png-extension.jpg')
    with Image.open(path) as image:
        assert image.mode == 'RGB'
        assert D._source_bits(image) == 16


@pytest.mark.parametrize('orientation', range(1, 9))
@pytest.mark.parametrize('placement', ['before', 'after'])
def test_png16_orientation_applied_exactly_once_and_original_exif_retained(tmp_path, orientation, placement):
    source = _rich16()
    exif = Image.Exif()
    exif[274] = orientation
    original_exif = exif.tobytes()
    path = _write(tmp_path, source, **{placement: [(b'eXIf', original_exif[6:])]})
    transpose = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
                 4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
                 6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
                 8: Image.Transpose.ROTATE_90}
    planes = [Image.fromarray(source[:, :, channel]) for channel in range(3)]
    expected = np.stack([np.asarray(plane.transpose(transpose[orientation])
                         if orientation != 1 else plane) for plane in planes], axis=2)
    decoded = D.load_full(path, want_bits=16)
    np.testing.assert_array_equal(decoded.rgb, expected)
    assert (decoded.src_w, decoded.src_h) == (expected.shape[1], expected.shape[0])
    assert decoded.source_exif == original_exif
    np.testing.assert_array_equal(D.load_rgb(path).rgb, _quantize8(expected))


def test_native_source_keeps_icc_and_working8_converts_before_quantization(tmp_path, monkeypatch):
    from lumaretouch_engine import color16
    from lumaretouch_engine.export import _srgb_bytes
    source, profile = _rich16(), _profile()
    path = _write(tmp_path, source, before=[_iccp(profile)])
    decoded = D.load_full(path, want_bits=16)
    assert decoded.source_icc == profile
    np.testing.assert_array_equal(decoded.rgb, source)
    expected16 = color16.convert_rgb16(source, profile, _srgb_bytes())
    assert not np.array_equal(expected16, source)
    actual_convert = color16.convert_rgb16
    seen = []
    def observe(pixels, source_icc, target_icc):
        seen.append(pixels.copy())
        assert pixels.dtype == np.uint16 and source_icc == profile
        return actual_convert(pixels, source_icc, target_icc)
    monkeypatch.setattr(color16, 'convert_rgb16', observe)
    for result in (D.load_full(path), D.load_rgb(path)):
        np.testing.assert_array_equal(result.rgb, _quantize8(expected16))
        assert result.source_icc == profile and result.src_bits == 16
    assert len(seen) == 2
    for original in seen:
        np.testing.assert_array_equal(original, source)


def test_proxy_resamples_working_high_precision_channels_before_rgb8(tmp_path):
    from lumaretouch_engine.color16 import convert_rgb16
    from lumaretouch_engine.export import _srgb_bytes
    source, profile = _rich16(120, 160), _profile()
    path = _write(tmp_path, source, before=[_iccp(profile)])
    result = D.load_rgb(path, budget=4096)
    size = D.proxy_size(160, 120, 4096)
    working = convert_rgb16(source, profile, _srgb_bytes())
    expected = np.stack([np.clip(np.rint(np.asarray(
        Image.fromarray(working[:, :, channel].astype(np.float32)).resize(size, Image.LANCZOS)) / 257), 0, 255)
        for channel in range(3)], axis=2).astype(np.uint8)
    np.testing.assert_array_equal(result.rgb, expected)
    assert (result.src_w, result.src_h) == (160, 120)
    assert result.w * result.h <= 4096 and result.src_bits == 16


@pytest.mark.parametrize('alpha', [0, 1, 65534])
@pytest.mark.parametrize('loader', ['full16', 'full8', 'proxy'])
def test_actual16_alpha_is_rejected_even_when_pillow_would_report_opaque(tmp_path, monkeypatch, alpha, loader):
    source = _rich16()
    rgba = np.concatenate([source, np.full((*source.shape[:2], 1), 65535, dtype=np.uint16)], axis=2)
    rgba[0, 0, 3] = alpha
    path = _write(tmp_path, rgba)
    def forbidden(*args, **kwargs):
        raise AssertionError('An 8-bit alpha check would lose real coverage')
    monkeypatch.setattr(Image.Image, 'convert', forbidden)
    with pytest.raises(ValueError, match='透明|transparency'):
        D.load_rgb(path) if loader == 'proxy' else D.load_full(path, want_bits=16 if loader == 'full16' else 8)


def test_exactly_opaque_rgba16_preserves_rgb_low_bits(tmp_path):
    source = _rich16()
    rgba = np.concatenate([source, np.full((*source.shape[:2], 1), 65535, dtype=np.uint16)], axis=2)
    np.testing.assert_array_equal(D.load_full(_write(tmp_path, rgba), want_bits=16).rgb, source)


@pytest.mark.parametrize('matches', [True, False])
def test_trns_compares_true16_values_not_matching_upper_bytes(tmp_path, matches):
    source = np.array([[[257, 258, 259], [65533, 65534, 65535]]], dtype=np.uint16)
    key = tuple(int(value) for value in source[0, 0]) if matches else (256, 256, 256)
    path = _write(tmp_path, source, before=[(b'tRNS', struct.pack('>3H', *key))])
    if matches:
        with pytest.raises(ValueError, match='透明|transparency'):
            D.load_full(path, want_bits=16)
    else:
        np.testing.assert_array_equal(D.load_full(path, want_bits=16).rgb, source)


@pytest.mark.parametrize('alpha', [False, True])
def test_unprofiled_gray16_expands_without_losing_low_bits(tmp_path, alpha):
    gray = np.array([[0, 1, 257], [258, 65534, 65535]], dtype=np.uint16)
    pixels = np.stack([gray, np.full_like(gray, 65535)], axis=2) if alpha else gray
    decoded = D.load_full(_write(tmp_path, pixels), want_bits=16)
    np.testing.assert_array_equal(decoded.rgb, np.repeat(gray[:, :, None], 3, axis=2))


def test_gray16_transparent_key_and_non_rgb_profile_fail_explicitly(tmp_path):
    gray = np.array([[0, 1, 257], [258, 65534, 65535]], dtype=np.uint16)
    with pytest.raises(ValueError, match='透明|transparency'):
        D.load_full(_write(tmp_path, gray, before=[(b'tRNS', struct.pack('>H', 257))]), want_bits=16)
    with pytest.raises(ValueError, match='灰度.*ICC'):
        D.load_full(_write(tmp_path, gray, before=[_iccp(_profile())]), want_bits=16)


@pytest.mark.parametrize('chunk', [(b'acTL', struct.pack('>II', 1, 0)),
                                  (b'fcTL', b'\0' * 26), (b'fdAT', b'\0' * 4)])
@pytest.mark.parametrize('placement', ['before', 'after'])
def test_any_apng_container_refuses_even_one_frame_before_native(tmp_path, monkeypatch, chunk, placement):
    path = _write(tmp_path, **{placement: [chunk]})
    _forbid_native(monkeypatch)
    with pytest.raises(ValueError, match='APNG'):
        D.load_full(path, want_bits=16)


@pytest.mark.parametrize('chunk', [
    (b'cICP', bytes([9, 16, 0, 1])), (b'cICP', bytes([9, 18, 0, 1])),
    (b'cICP', bytes([12, 13, 0, 1])), (b'cICP', bytes([1, 13, 0, 0])),
    (b'mDCV', b'\0' * 24), (b'cLLI', b'\0' * 8),
    (b'gAMA', struct.pack('>I', 100000)), (b'cHRM', struct.pack('>8I', *([25000] * 8))),
])
def test_unsupported_hdr_or_unprofiled_non_srgb_is_not_relabelled(tmp_path, monkeypatch, chunk):
    path = _write(tmp_path, before=[chunk])
    _forbid_native(monkeypatch)
    with pytest.raises(ValueError, match='HDR|sRGB|cICP|gAMA|cHRM'):
        D.load_full(path, want_bits=16)


@pytest.mark.parametrize('before', [
    [(b'sRGB', b'\0')], [(b'cICP', bytes([1, 13, 0, 1]))],
    [(b'gAMA', struct.pack('>I', 45455)), (b'cHRM', struct.pack('>8I', *P._SRGB_CHRM))],
])
def test_explicit_or_conventional_srgb_metadata_keeps_native_codes(tmp_path, before):
    source = _rich16()
    np.testing.assert_array_equal(D.load_full(_write(tmp_path, source, before=before), want_bits=16).rgb, source)


def test_icc_owns_lower_priority_gamma_but_never_overrides_cicp(tmp_path):
    source = _rich16()
    lower_gamma = [(b'gAMA', struct.pack('>I', 100000)), _iccp(_profile())]
    np.testing.assert_array_equal(D.load_full(_write(tmp_path, source, before=lower_gamma), want_bits=16).rgb, source)
    higher_cicp = [(b'cICP', bytes([1, 13, 0, 1])), _iccp(_profile())]
    with pytest.raises(ValueError, match='优先级'):
        D.load_full(_write(tmp_path, source, before=higher_cicp), want_bits=16)


@pytest.mark.parametrize('bad_profile', [b'not an ICC', b'\0' * 132])
def test_malformed_icc_cannot_hide_in_raw_source_passthrough(tmp_path, monkeypatch, bad_profile):
    path = _write(tmp_path, before=[_iccp(bad_profile)])
    _forbid_native(monkeypatch)
    with pytest.raises(ValueError, match='ICC'):
        D.load_full(path, want_bits=16)


def test_icc_inflation_is_bounded_before_native_decode(tmp_path, monkeypatch):
    path = _write(tmp_path, before=[_iccp(b'X' * 10000)])
    monkeypatch.setattr(P, 'MAX_METADATA_BYTES', 1024)
    _forbid_native(monkeypatch)
    with pytest.raises(ValueError, match='ICC.*预算'):
        D.load_full(path, want_bits=16)


@pytest.mark.parametrize('constraint', ['pixels', 'bytes', 'metadata', 'memory', 'chunks'])
def test_resource_budgets_refuse_before_native_allocation(tmp_path, monkeypatch, constraint):
    from lumaretouch_engine import cpu_memory_budget
    path = _write(tmp_path, before=[(b'tEXt', b'Note\0' + b'x' * 256)])
    if constraint == 'bytes': monkeypatch.setattr(P, 'MAX_SOURCE_BYTES', 64)
    if constraint == 'metadata': monkeypatch.setattr(P, 'MAX_METADATA_BYTES', 64)
    if constraint == 'memory': monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 0)
    if constraint == 'chunks': monkeypatch.setattr(P, 'MAX_CHUNKS', 2)
    _forbid_native(monkeypatch)
    with pytest.raises(ValueError, match='预算|内存'):
        D.load_full(path, want_bits=16, max_px=1 if constraint == 'pixels' else 120_000_000)


def test_unused_compressed_text_never_reaches_native_metadata_inflation(tmp_path, monkeypatch):
    import imagecodecs
    source = _rich16()
    path = _write(tmp_path, source, before=[(b'zTXt', b'Note\0\0' + zlib.compress(b'X' * 1000000))])
    native = imagecodecs.png_decode
    observed = []
    def inspect(content):
        observed.append(content)
        assert b'zTXt' not in content
        return native(content)
    monkeypatch.setattr(imagecodecs, 'png_decode', inspect)
    np.testing.assert_array_equal(D.load_full(path, want_bits=16).rgb, source)
    assert len(observed) == 1


@pytest.mark.parametrize('mutation', ['crc', 'truncated', 'trailing', 'duplicate', 'critical'])
def test_malformed_container_refuses_before_native_decode(tmp_path, monkeypatch, mutation):
    content = _png(_rich16())
    if mutation == 'crc': content = content[:-1] + bytes([content[-1] ^ 1])
    elif mutation == 'truncated': content = content[:-7]
    elif mutation == 'trailing': content += _png(_rich16())
    elif mutation == 'duplicate': content = _png(_rich16(), before=[(b'sRGB', b'\0'), (b'sRGB', b'\0')])
    else: content = _png(_rich16(), before=[(b'ABCD', b'unsupported')])
    path = tmp_path / 'invalid.png'
    path.write_bytes(content)
    _forbid_native(monkeypatch)
    with pytest.raises(ValueError):
        D.load_full(str(path), want_bits=16)


@pytest.mark.parametrize('pixels', [np.zeros((7, 11, 3), np.uint8), np.zeros((7, 11, 4), np.uint16),
                                   np.zeros((7, 10, 3), np.uint16), np.zeros((7, 11), np.uint16)])
def test_native_codec_must_match_true_depth_geometry_and_channels(tmp_path, monkeypatch, pixels):
    import imagecodecs
    path = _write(tmp_path)
    monkeypatch.setattr(imagecodecs, 'png_decode', lambda content: pixels)
    with pytest.raises(ValueError, match='位深|尺寸|通道'):
        D.load_full(path, want_bits=16)


def test_changed_file_identity_is_terminal_before_native_decode(tmp_path, monkeypatch):
    path = _write(tmp_path)
    before = Path(path).stat()
    altered = SimpleNamespace(**{key: getattr(before, key) for key in
                              ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')})
    altered.st_ctime_ns += 1
    _forbid_native(monkeypatch)
    monkeypatch.setattr(P, 'os', SimpleNamespace(fstat=P.os.fstat, stat=lambda *args, **kwargs: altered))
    with pytest.raises(ValueError, match='读取期间'):
        P.load_opaque_rgb16(path)
