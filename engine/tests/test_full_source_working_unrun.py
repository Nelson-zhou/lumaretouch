"""AUTHORED / UNRUN: exact working-source precision, ICC and alpha boundary.

No product imports, fixtures, codecs or tests were executed while authoring.
These contracts are not export, UI, performance or image-quality acceptance.
"""
from pathlib import Path
from types import SimpleNamespace
import struct
import zlib

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import decode as D
from lumaretouch_engine import export as E
from lumaretouch_engine import full_source_working as W
from lumaretouch_engine.color16 import convert_rgb16


def rgb16():
    return np.array([[[0, 1, 255], [256, 257, 258], [1023, 1024, 1025]],
                     [[10000, 10001, 10002], [32767, 32768, 32769],
                      [65533, 65534, 65535]]], dtype=np.uint16)


def decoded(pixels, icc=None):
    h, w = pixels.shape[:2]
    return SimpleNamespace(rgb=pixels, source_icc=icc, src_w=w, src_h=h,
                           src_bits=pixels.dtype.itemsize * 8, fmt='TIFF',
                           raw={'source': 'tiff16'}, notes=[])


def test_rgb8_is_already_working_and_must_not_be_icc_converted_again(monkeypatch):
    from lumaretouch_engine import color16
    def forbidden(*args, **kwargs):
        raise AssertionError('RGB8 was already ICC-converted by load_full')
    monkeypatch.setattr(color16, 'convert_rgb16', forbidden)
    pixels = np.array([[[7, 97, 211]]], dtype=np.uint8)
    # The retained source profile describes the original file, not these pixels.
    assert W.working_rgb(decoded(pixels, b'retained-source-profile')) is pixels


def test_unprofiled_rgb16_keeps_exact_low_bits_and_does_not_mutate():
    pixels = rgb16()
    original = pixels.copy()
    assert W.working_rgb(decoded(pixels)) is pixels
    np.testing.assert_array_equal(pixels, original)
    assert np.any(pixels & 255)


def test_profiled_rgb16_matches_the_ordinary_export_input_exactly(monkeypatch):
    profile = (Path(__file__).parent / 'fixtures' / 'icc' / 'AdobeCompat-v2.icc').read_bytes()
    d = decoded(rgb16(), profile)
    original = d.rgb.copy()
    observed = []
    def capture(source, spec, **kwargs):
        observed.append(source.copy())
        return source.copy(), {}
    monkeypatch.setattr(E, 'export_image16', capture)
    E.render_edited_rgb16(d, E.ExportSpec(strength=0), device='cpu', output_profile='srgb')
    actual = W.working_rgb(d)
    np.testing.assert_array_equal(actual, observed[0])
    np.testing.assert_array_equal(actual, convert_rgb16(original, profile, E._srgb_bytes()))
    np.testing.assert_array_equal(d.rgb, original)
    assert actual.dtype == np.uint16
    assert not np.array_equal(actual, original)


def test_invalid_rgb16_icc_is_terminal_not_an_srgb_relabel():
    with pytest.raises(ValueError):
        W.working_rgb(decoded(rgb16(), b'invalid-icc'))


@pytest.mark.parametrize('pixels', [
    np.zeros((2, 3, 4), np.uint16), np.zeros((2, 3), np.uint8),
    np.zeros((2, 3, 3), np.float32), np.zeros((2, 3, 3), np.int16),
    np.zeros((0, 3, 3), np.uint8),
])
def test_non_rgb_or_invented_precision_is_rejected(pixels):
    with pytest.raises(ValueError, match='genuine RGB'):
        W.working_rgb(SimpleNamespace(rgb=pixels, source_icc=None))


def png16_bytes():
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    pixels = rgb16()
    h, w = pixels.shape[:2]
    header = struct.pack('>IIBBBBB', w, h, 16, 2, 0, 0, 0)
    rows = b''.join(b'\0' + row.astype('>u2').tobytes() for row in pixels)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


@pytest.mark.parametrize('name', ['source.png', 'png-disguised-as-jpeg.jpg'])
def test_png16_is_detected_from_header_and_refused_without_rgb8_fallback(tmp_path, monkeypatch, name):
    path = tmp_path / name
    path.write_bytes(png16_bytes())
    def forbidden(*args, **kwargs):
        raise AssertionError('Unsupported PNG16 must not enter Pillow RGB8')
    monkeypatch.setattr(D, '_load_full_pillow', forbidden)
    with Image.open(path) as header:
        assert W.source_bits(str(path), header) == 16
        with pytest.raises(ValueError, match='16-bit'):
            D.load_full(str(path), want_bits=16)


@pytest.mark.parametrize('mutation', ['short', 'signature', 'chunk', 'width', 'bits'])
def test_png_header_mismatch_is_terminal(tmp_path, mutation):
    content = bytearray(png16_bytes())
    if mutation == 'short': content = content[:24]
    elif mutation == 'signature': content[0] = 0
    elif mutation == 'chunk': content[12] = 0
    elif mutation == 'width': content[19] = 7
    else: content[24] = 12
    path = tmp_path / 'changed.png'
    path.write_bytes(content)
    with pytest.raises(ValueError, match='PNG header'):
        W.source_bits(str(path), SimpleNamespace(format='PNG', width=3, height=2))


def test_transparent_rgb8_cannot_be_silently_flattened():
    with Image.new('RGBA', (3, 2), (100, 80, 60, 254)) as image:
        with pytest.raises(ValueError, match='transparency'):
            W.require_opaque_8bit(image)
    with Image.new('RGBA', (3, 2), (100, 80, 60, 255)) as image:
        W.require_opaque_8bit(image)


@pytest.mark.parametrize('orientation', range(1, 9))
def test_tiff16_orientation_is_owned_once_by_existing_decoder(tmp_path, orientation):
    import tifffile
    path = tmp_path / 'oriented.tif'
    source = rgb16()
    tifffile.imwrite(path, source, photometric='rgb',
                     extratags=[(274, 'H', 1, orientation, False)])
    transpose = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
                 4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
                 6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
                 8: Image.Transpose.ROTATE_90}
    planes = [Image.fromarray(source[:, :, c]) for c in range(3)]
    expected = np.stack([np.asarray(p.transpose(transpose[orientation])
                         if orientation != 1 else p) for p in planes], axis=-1)
    result = W.working_rgb(D.load_full(str(path), want_bits=16))
    np.testing.assert_array_equal(result, expected)


def test_full_candidate_uses_shared_boundary_without_new_png_codec():
    source = (Path(__file__).parents[1] / 'src' / 'lumaretouch_engine'
              / 'full_candidate_render.py').read_text()
    assert 'source_bits(path,image)' in source
    assert 'require_opaque_8bit(image)' in source
    assert 'pixels=working_rgb(decoded)' in source
    assert 'imagecodecs' not in source
