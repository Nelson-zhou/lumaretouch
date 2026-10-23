"""AUTHORED / UNRUN: genuine RGB16 PNG sky asset import contracts.

No product imports or tests were executed while authoring these fixtures. They
cover byte/ICC/geometry preservation and rejection contracts, not visual sky
quality, the creative-document render pipeline, or release acceptance.
"""
from hashlib import sha256
from pathlib import Path
import struct
import zlib

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import cpu_memory_budget as MEMORY
from lumaretouch_engine import decode as D
from lumaretouch_engine import id_background_assets as ID
from lumaretouch_engine import sky_replacement_assets as A
from lumaretouch_engine import sky_replacement_state as S


@pytest.fixture(autouse=True)
def sufficient_memory(monkeypatch):
    monkeypatch.setattr(MEMORY, 'available_estimate', lambda: 8 * 1024**3)


def rgb16():
    # Adjacent low-bit values catch both RGB8 truncation and zero-padded RGB16.
    return np.array([[[0, 1, 255], [256, 257, 258], [1023, 1024, 1025]],
                     [[10000, 10001, 10002], [32767, 32768, 32769],
                      [65533, 65534, 65535]]], dtype=np.uint16)


def chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))


def png16(pixels, *, icc=None, orientation=1, transparent=None):
    """Small independent PNG writer; no codec download or codec encoder needed."""
    h, w, channels = pixels.shape
    assert pixels.dtype == np.uint16 and channels in (3, 4)
    header = struct.pack('>IIBBBBB', w, h, 16, 6 if channels == 4 else 2, 0, 0, 0)
    parts = [b'\x89PNG\r\n\x1a\n', chunk(b'IHDR', header)]
    if icc is not None:
        parts.append(chunk(b'iCCP', b'fixture\x00\x00' + zlib.compress(icc)))
    if orientation != 1:
        # PNG eXIf stores a TIFF header without JPEG's Exif\0\0 prefix.
        exif = (b'II*\x00' + struct.pack('<IH', 8, 1)
                + struct.pack('<HHIHHI', 274, 3, 1, orientation, 0, 0))
        parts.append(chunk(b'eXIf', exif))
    if transparent is not None:
        parts.append(chunk(b'tRNS', struct.pack('>HHH', *transparent)))
    rows = b''.join(b'\x00' + row.astype('>u2').tobytes() for row in pixels)
    return b''.join(parts + [chunk(b'IDAT', zlib.compress(rows)), chunk(b'IEND', b'')])


def save_png(tmp_path, pixels=None, *, name='sky.png', **metadata):
    path = tmp_path / name
    content = png16(rgb16() if pixels is None else pixels, **metadata)
    path.write_bytes(content)
    return path, content


def forbid_pillow_full_decode(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('PNG16 must not enter the RGB8/full-image fallback')
    monkeypatch.setattr(D, 'load_full', forbidden)


def test_rgb16_png_retains_exact_low_bits_binding_and_readonly_pixels(tmp_path, monkeypatch):
    path, content = save_png(tmp_path)
    forbid_pillow_full_decode(monkeypatch)
    actual = A.read(str(path))
    assert actual.pixels.dtype == np.uint16
    assert np.array_equal(actual.pixels, rgb16())
    assert actual.binding == {'path': str(path), 'sha256': sha256(content).hexdigest(),
                              'width': 3, 'height': 2, 'bits': 16,
                              'working_color': 'encoded-srgb', 'icc_sha256': None}
    assert np.any(actual.pixels & 0xff)
    assert not actual.pixels.flags.writeable
    with pytest.raises(ValueError):
        actual.pixels[0, 0, 0] = 123
    assert A.read(str(path), expected=actual.binding).binding == actual.binding


def test_format_detection_does_not_depend_on_extension(tmp_path, monkeypatch):
    path, _ = save_png(tmp_path, name='still-png.jpg')
    forbid_pillow_full_decode(monkeypatch)
    assert np.array_equal(A.read(str(path)).pixels, rgb16())


@pytest.mark.parametrize('orientation', range(1, 9))
def test_png16_orientation_matches_independent_plane_transpose(tmp_path, orientation):
    path, _ = save_png(tmp_path, orientation=orientation)
    transpose = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
                 4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
                 6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
                 8: Image.Transpose.ROTATE_90}
    planes = [Image.fromarray(rgb16()[:, :, c]) for c in range(3)]
    expected = np.stack([np.asarray(p.transpose(transpose[orientation])
                         if orientation != 1 else p) for p in planes], axis=-1)
    actual = A.read(str(path))
    assert np.array_equal(actual.pixels, expected)
    assert (actual.binding['width'], actual.binding['height']) == (expected.shape[1], expected.shape[0])


def test_non_srgb_icc_uses_existing_rgb16_conversion_without_double_conversion(tmp_path, monkeypatch):
    from lumaretouch_engine.color16 import convert_rgb16
    from lumaretouch_engine.export import _srgb_bytes
    profile = (Path(__file__).parents[1] / 'icc' / 'AdobeCompat-v2.icc').read_bytes()
    assert sha256(profile).hexdigest() == '60fb2adecacf82132db0b1c09b303316f3bbd9e2823e7ba096d01627d12d57c9'
    path, content = save_png(tmp_path, icc=profile)
    calls = []
    original = ID._colour_manage
    def traced(pixels, icc):
        calls.append((pixels.dtype, icc))
        return original(pixels, icc)
    monkeypatch.setattr(ID, '_colour_manage', traced)
    actual = A.read(str(path))
    expected = convert_rgb16(rgb16(), profile, _srgb_bytes())
    assert calls == [(np.dtype(np.uint16), profile)]
    assert actual.pixels.dtype == np.uint16
    assert np.array_equal(actual.pixels, expected)
    assert not np.array_equal(actual.pixels, rgb16())
    assert actual.binding['icc_sha256'] == sha256(profile).hexdigest()
    assert actual.binding['sha256'] == sha256(content).hexdigest()


def test_invalid_icc_is_not_relabelled_srgb_or_downcast(tmp_path, monkeypatch):
    path, _ = save_png(tmp_path, icc=b'not an ICC profile')
    forbid_pillow_full_decode(monkeypatch)
    with pytest.raises(ValueError):
        A.read(str(path))


def test_exactly_opaque_rgba16_is_accepted_without_losing_rgb_bits(tmp_path):
    rgba = np.dstack((rgb16(), np.full((2, 3), 65535, dtype=np.uint16)))
    path, _ = save_png(tmp_path, rgba)
    assert np.array_equal(A.read(str(path)).pixels, rgb16())


@pytest.mark.parametrize('alpha', [0, 32768, 65280, 65534])
def test_nonopaque_alpha16_is_rejected_even_when_pillow_reports_255(tmp_path, alpha):
    rgba = np.dstack((rgb16(), np.full((2, 3), 65535, dtype=np.uint16)))
    rgba[0, 0, 3] = alpha
    path, _ = save_png(tmp_path, rgba)
    with pytest.raises(ValueError, match='透明'):
        A.read(str(path))


def test_png16_transparent_color_is_still_rejected(tmp_path):
    path, _ = save_png(tmp_path, transparent=(0, 1, 255))
    with pytest.raises(ValueError, match='透明'):
        A.read(str(path))


@pytest.mark.parametrize('failure', ['quantized', 'float', 'geometry', 'channels'])
def test_png_decoder_contract_does_not_clip_pad_or_relabel(tmp_path, monkeypatch, failure):
    import imagecodecs
    path, _ = save_png(tmp_path)
    bad = {'quantized': rgb16().astype(np.uint8), 'float': rgb16().astype(np.float32),
           'geometry': rgb16()[:, :2], 'channels': rgb16()[:, :, :2]}[failure]
    monkeypatch.setattr(imagecodecs, 'png_decode', lambda content: bad)
    forbid_pillow_full_decode(monkeypatch)
    with pytest.raises(ValueError, match='RGB16'):
        A.read(str(path))


def test_failed_png_codec_has_no_lossy_fallback(tmp_path, monkeypatch):
    import imagecodecs
    path, _ = save_png(tmp_path)
    def unavailable(content):
        raise RuntimeError('codec unavailable')
    monkeypatch.setattr(imagecodecs, 'png_decode', unavailable)
    forbid_pillow_full_decode(monkeypatch)
    with pytest.raises(RuntimeError, match='codec unavailable'):
        A.read(str(path))


def test_missing_png_codec_has_no_lossy_fallback(tmp_path, monkeypatch):
    import sys
    path, _ = save_png(tmp_path)
    monkeypatch.setitem(sys.modules, 'imagecodecs', None)
    forbid_pillow_full_decode(monkeypatch)
    with pytest.raises(ImportError):
        A.read(str(path))


def test_sky_does_not_inherit_id_background_full_asset_engine_or_byte_cap(tmp_path, monkeypatch):
    path, _ = save_png(tmp_path)
    monkeypatch.setattr(ID.S, 'MAX_ASSET_BYTES', 1)
    def forbidden(*args, **kwargs):
        raise AssertionError('Sky must not inherit the full ID-background asset contract')
    monkeypatch.setattr(ID, '_decode', forbidden)
    assert np.array_equal(A.read(str(path)).pixels, rgb16())


@pytest.mark.parametrize('changed', ['sha256', 'width', 'height', 'bits', 'icc_sha256'])
def test_expected_binding_checks_all_existing_identity_fields(tmp_path, changed):
    path, _ = save_png(tmp_path)
    value = A.read(str(path)).binding
    altered = dict(value)
    altered[changed] = {'sha256': 'f' * 64, 'width': 4, 'height': 3,
                        'bits': 8, 'icc_sha256': 'e' * 64}[changed]
    with pytest.raises(ValueError):
        A.read(str(path), expected=altered)


def test_relink_allows_identical_bytes_only(tmp_path):
    path, content = save_png(tmp_path)
    original = A.read(str(path))
    moved = tmp_path / 'moved.png'
    moved.write_bytes(content)
    assert A.relink(original.binding, str(moved)).binding['path'] == str(moved)
    different = rgb16().copy()
    different[0, 0, 0] = 2
    moved.write_bytes(png16(different))
    with pytest.raises(ValueError):
        A.relink(original.binding, str(moved))


@pytest.mark.parametrize('limit', ['memory', 'pixels', 'bytes'])
def test_budgets_are_enforced_before_png_decode(tmp_path, monkeypatch, limit):
    import imagecodecs
    path, content = save_png(tmp_path)
    if limit == 'memory':
        monkeypatch.setattr(MEMORY, 'available_estimate', lambda: 0)
    elif limit == 'pixels':
        monkeypatch.setattr(S, 'MAX_ASSET_PIXELS', 5)
    else:
        monkeypatch.setattr(S, 'MAX_ASSET_BYTES', len(content) - 1)
    def forbidden(content):
        raise AssertionError('An over-budget file must not reach the decoder')
    monkeypatch.setattr(imagecodecs, 'png_decode', forbidden)
    with pytest.raises(ValueError):
        A.read(str(path))


def test_snapshot_memory_is_included_before_decode(tmp_path, monkeypatch):
    import imagecodecs
    path, content = save_png(tmp_path)
    old_cost = 6 * 64 + 32 * 1024**2
    monkeypatch.setattr(MEMORY, 'available_estimate',
                        lambda: 256 * 1024**2 + (old_cost + len(content) / 2) / .65)
    def forbidden(content):
        raise AssertionError('PNG snapshot bytes must count against the budget')
    monkeypatch.setattr(imagecodecs, 'png_decode', forbidden)
    with pytest.raises(ValueError, match='内存'):
        A.read(str(path))


def test_cancellation_before_decode_and_after_decode_is_respected(tmp_path):
    path, _ = save_png(tmp_path)
    with pytest.raises(InterruptedError):
        A.read(str(path), cancelled=lambda: True)
    checks = iter([False, False, True])
    with pytest.raises(InterruptedError):
        A.read(str(path), cancelled=lambda: next(checks))


def test_source_change_during_png_decode_is_rejected(tmp_path, monkeypatch):
    import imagecodecs
    path, _ = save_png(tmp_path)
    original = imagecodecs.png_decode
    def replaced(content):
        result = original(content)
        path.write_bytes(content + b'changed during read')
        return result
    monkeypatch.setattr(imagecodecs, 'png_decode', replaced)
    with pytest.raises(ValueError, match='发生变化'):
        A.read(str(path))


def test_apng_is_not_silently_reduced_to_first_frame(tmp_path):
    path = tmp_path / 'animated.png'
    first = Image.new('RGB', (3, 2), (12, 34, 56))
    second = Image.new('RGB', (3, 2), (56, 34, 12))
    first.save(path, save_all=True, append_images=[second], duration=100, loop=0)
    with pytest.raises(ValueError, match='页'):
        A.read(str(path))


@pytest.mark.parametrize('suffix', ['jpg', 'bmp', 'png'])
def test_existing_rgb8_formats_keep_decoder_and_icc_contract(tmp_path, suffix):
    from lumaretouch_engine.export import _srgb_bytes
    path = tmp_path / ('ordinary.' + suffix)
    pixels = (rgb16() // 257).astype(np.uint8)
    Image.fromarray(pixels).save(path, icc_profile=_srgb_bytes())
    expected = D.load_full(str(path), max_px=S.MAX_ASSET_PIXELS, want_bits=8)
    actual = A.read(str(path))
    assert actual.pixels.dtype == np.uint8
    assert np.array_equal(actual.pixels, expected.rgb)
    assert actual.binding['bits'] == 8
    assert actual.binding['icc_sha256'] == (sha256(expected.source_icc).hexdigest()
                                            if expected.source_icc else None)


def test_existing_rgb16_tiff_retains_orientation_icc_and_low_bits(tmp_path):
    import tifffile
    from lumaretouch_engine.color16 import convert_rgb16
    from lumaretouch_engine.export import _srgb_bytes
    path = tmp_path / 'ordinary16.tif'
    profile = (Path(__file__).parents[1] / 'icc' / 'AdobeCompat-v2.icc').read_bytes()
    tifffile.imwrite(path, rgb16(), photometric='rgb',
                     extratags=[(274, 'H', 1, 6, False), (34675, 'B', len(profile), profile, False)])
    expected = D.load_full(str(path), max_px=S.MAX_ASSET_PIXELS, want_bits=16)
    actual = A.read(str(path))
    assert actual.pixels.dtype == np.uint16
    assert np.array_equal(actual.pixels, convert_rgb16(expected.rgb, profile, _srgb_bytes()))
    assert (actual.binding['width'], actual.binding['height'], actual.binding['bits']) == (2, 3, 16)
    assert actual.binding['icc_sha256'] == sha256(profile).hexdigest()


def test_float_tiff_is_not_clipped_to_integer_sky(tmp_path):
    import tifffile
    path = tmp_path / 'scene-linear.tif'
    values = rgb16().astype(np.float32) / 32768 - .25
    tifffile.imwrite(path, values, photometric='rgb')
    # Pillow may reject the RGB-float header before the genuine TIFF decoder.
    with pytest.raises((ValueError, OSError)):
        A.read(str(path))
