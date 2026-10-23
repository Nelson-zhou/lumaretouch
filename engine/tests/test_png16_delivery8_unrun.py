"""AUTHORED / UNRUN: native PNG16 -> edited working RGB8 delivery contracts.

These specifications have not been imported, executed or used as runtime proof.
Qoder owns local CPU/GPU and file-readback validation.
"""
from copy import copy
from pathlib import Path
from types import SimpleNamespace
import struct
import zlib

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import decode, export as ex, export_delivery_render as delivery


def _gradient(height=32, width=48):
    x = np.arange(height * width, dtype=np.uint32).reshape(height, width)
    return np.stack(((x * 37 + 13) % 65536, (x * 19 + 71) % 65536,
                     (x * 53 + 29) % 65536), axis=-1).astype(np.uint16)


def _png16(path, pixels, *, icc=None, exif=None):
    """Independent minimal RGB16/PNG fixture, not an image-library RGB8 save."""
    def chunk(kind, payload):
        return (struct.pack('>I', len(payload)) + kind + payload
                + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))
    height, width = pixels.shape[:2]
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',
        struct.pack('>IIBBBBB', width, height, 16, 2, 0, 0, 0))
    if icc is not None:
        data += chunk(b'iCCP', b'Source\x00\x00' + zlib.compress(icc))
    if exif is not None:
        data += chunk(b'eXIf', exif.removeprefix(b'Exif\x00\x00'))
    rows = b''.join(b'\x00' + row.astype('>u2').tobytes() for row in pixels)
    path.write_bytes(data + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))
    return str(path)


def _decoded(pixels=None, *, icc=None):
    pixels = _gradient() if pixels is None else pixels
    height, width = pixels.shape[:2]
    return decode.Decoded(pixels, width, height, 'PNG', 0., 0., 0., 0., 0.,
        src_bits=16, source_icc=icc,
        raw={'source': 'png16', 'bits': 16, 'used_preview': False, 'half_size': False})


def test_delivery_selection_uses_header_not_extension_and_never_loads_rgb8_first(tmp_path, monkeypatch):
    source = _png16(tmp_path / 'renamed.data', _gradient())
    calls = []
    marker = object()
    def load(path, **options):
        calls.append((path, options))
        return marker
    monkeypatch.setattr(decode, 'load_full', load)
    assert delivery.decode_for_delivery8(source, device='cpu') is marker
    assert calls == [(source, {'device': 'cpu', 'want_bits': 16})]


@pytest.mark.parametrize('name', ['image.jpg', 'image.tif', 'image.dng', 'not-png.png'])
def test_other_source_decoder_precision_is_unchanged(tmp_path, monkeypatch, name):
    path = tmp_path / name
    path.write_bytes(b'not PNG; delegated to established decoder')
    calls = []
    monkeypatch.setattr(decode, 'load_full', lambda source, **kwargs: calls.append(kwargs))
    delivery.decode_for_delivery8(str(path), device='cpu')
    assert calls == [{'device': 'cpu', 'want_bits': 8}]


def test_png8_and_creative_carriers_keep_existing_decode(tmp_path, monkeypatch):
    source8 = tmp_path / 'eight.png'
    Image.new('RGB', (4, 3), (12, 34, 56)).save(source8)
    source16 = _png16(tmp_path / 'sixteen.png', _gradient())
    calls = []
    monkeypatch.setattr(decode, 'load_full', lambda source, **kwargs: calls.append(kwargs))
    delivery.decode_for_delivery8(str(source8), device='cpu')
    delivery.decode_for_delivery8(source16, device='cpu', creative_base={'id': 'derived'})
    assert calls == [{'device': 'cpu', 'want_bits': 8}] * 2


def test_float_render_keeps_source_low_bits_and_spec_ownership(monkeypatch):
    from lumaretouch_engine import full_source_working
    source = _decoded()
    original = source.rgb.copy()
    spec = ex.ExportSpec(strength=0, scale=2)
    expected_float = np.full((12, 16, 3), .50001, np.float32)
    calls = []
    def working(decoded):
        assert decoded is source
        return decoded.rgb
    def render(pixels, owned_spec, **options):
        assert pixels.dtype == np.uint16 and np.any(pixels & 255)
        assert owned_spec is not spec and owned_spec.float_output
        assert not owned_spec.provenance_output and owned_spec.scale == 2
        calls.append(options)
        return expected_float, {'bits': 16, 'crop_applied': True, 'geometry_ms': 2.5}
    monkeypatch.setattr(full_source_working, 'working_rgb', working)
    monkeypatch.setattr(ex, 'export_image16', render)
    monkeypatch.setattr(ex, 'export_image', lambda *_args, **_kwargs: pytest.fail('RGB8 edit detour'))
    got, facts = delivery.render_delivery8(source, spec, device='cpu', tile=512,
        crop_rect=(.1, .2, .9, .8), rotation_degrees=90.)
    assert calls == [{'device': 'cpu', 'tile': 512,
        'crop_rect': (.1, .2, .9, .8), 'rotation_degrees': 90.}]
    assert not spec.float_output and not spec.provenance_output
    np.testing.assert_array_equal(source.rgb, original)
    assert got.dtype == np.uint8 and np.all(got == 128)
    assert facts['bits'] == 8 and facts['decoded_bits'] == facts['source_bits'] == 16
    assert facts['pipeline'] == 'png16_float_rgb8' and facts['source'] == 'png16'
    assert facts['working_color_space'] == 'sRGB' and facts['geometry_ms'] == 2.5
    assert (facts['w'], facts['h'], facts['px']) == (16, 12, 192)


@pytest.mark.parametrize('change', [
    {'rgb': np.zeros((32, 48, 3), np.uint8)}, {'src_bits': 8}, {'draft_used': True},
    {'src_w': 49}, {'raw': {'source': 'png16', 'used_preview': True}},
    {'raw': {'source': 'png16', 'half_size': True}},
])
def test_png16_provenance_cannot_hide_a_proxy(change, monkeypatch):
    decoded = _decoded()
    for key, value in change.items():
        setattr(decoded, key, value)
    monkeypatch.setattr(ex, 'export_image16', lambda *_args, **_kwargs: pytest.fail('Invalid source rendered'))
    with pytest.raises(ex.ExportError, match='genuine full-resolution'):
        delivery.render_delivery8(decoded, ex.ExportSpec(strength=0), device='cpu', tile=256)


@pytest.mark.parametrize('invalid', [
    np.full((2, 3, 3), np.nan), np.full((2, 3, 3), np.inf),
    np.zeros((2, 3, 3), np.uint16), np.zeros((2, 3, 4)), np.zeros((0, 3, 3)),
])
def test_final_rgb8_rejects_invalid_float_or_premature_integer_pack(invalid):
    with pytest.raises(ex.ExportError):
        delivery._final_rgb8(invalid)


def test_final_rgb8_uses_existing_range_rounding_in_bounded_blocks(monkeypatch):
    from lumaretouch_engine import quant
    source = np.resize(np.array([-.5, 0., .5, 1., 1.5], np.float64), (2, (1 << 18) + 1, 3))
    expected = quant.quantize_np(source)
    original = quant.quantize_np
    sizes = []
    def quantize(block):
        sizes.append(block.shape[0] * block.shape[1])
        return original(block)
    monkeypatch.setattr(quant, 'quantize_np', quantize)
    np.testing.assert_array_equal(delivery._final_rgb8(source), expected)
    assert len(sizes) > 1 and max(sizes) <= (1 << 18)


@pytest.mark.parametrize('source', ['self_dng', 'libraw', 'libraw_preview'])
def test_source_output_profile_rejects_only_actual_raw_decoder_identities(source):
    with pytest.raises(ex.ExportError, match='RAW'):
        delivery.check_source_profile(SimpleNamespace(raw={'source': source}), 'source')
    delivery.check_source_profile(SimpleNamespace(raw={'source': source}), 'srgb')


@pytest.mark.parametrize('raw', [None, {}, {'source': 'png16'}, {'source': 'tiff16'}])
def test_png_tiff_and_raster_provenance_are_not_false_raw_blockers(raw):
    delivery.check_source_profile(SimpleNamespace(raw=raw), 'source')


def test_untagged_png_source_profile_reports_missing_icc_not_raw(tmp_path):
    from lumaretouch_engine.export_target_size_adapter import write_delivery
    source = _decoded()
    delivery.check_source_profile(source, 'source')
    output = tmp_path / 'must-not-exist.png'
    with pytest.raises(ex.ExportError, match='没有 ICC'):
        write_delivery(np.zeros((2, 3, 3), np.uint8), str(output),
            output_profile='source', source_icc=source.source_icc)
    assert not output.exists()


def test_input_color_conversion_failure_is_not_an_rgb8_fallback(monkeypatch):
    from lumaretouch_engine import full_source_working
    source = _decoded(icc=b'unsupported source profile')
    def fail_conversion(_decoded):
        raise ValueError('ICC conversion unavailable')
    monkeypatch.setattr(full_source_working, 'working_rgb', fail_conversion)
    monkeypatch.setattr(ex, 'export_image16', lambda *_args, **_kwargs: pytest.fail('Color error ignored'))
    monkeypatch.setattr(ex, 'export_image', lambda *_args, **_kwargs: pytest.fail('RGB8 fallback'))
    with pytest.raises(ValueError, match='ICC conversion unavailable'):
        delivery.render_delivery8(source, ex.ExportSpec(strength=0), device='cpu', tile=256)


def test_png16_exposure_crop_scale_stays_float_until_rgb8(tmp_path, monkeypatch):
    pytest.importorskip('torch')
    from lumaretouch_engine.ops import geometry
    from lumaretouch_engine.quant import quantize_np
    pixels = _gradient(40, 60)
    source = delivery.decode_for_delivery8(_png16(tmp_path / 'source.png', pixels), device='cpu')
    spec = ex.ExportSpec(strength=0, exposure=(.37, 0, 0, 0, 0, 0, 0), scale=2,
                         sharpen_amount=.15, sharpen_radius=1)
    rect, rotation = (.1, .2, .9, .8), 90.
    float_spec = copy(spec)
    float_spec.float_output = True
    expected_float, _ = ex.export_image16(pixels, float_spec, device='cpu', tile=256,
        crop_rect=rect, rotation_degrees=rotation)
    expected = quantize_np(expected_float)
    premature8 = quantize_np(pixels.astype(np.float32) / 65535.)
    truncated = premature8.astype(np.uint16) * 257
    truncated_float, _ = ex.export_image16(truncated, copy(float_spec), device='cpu', tile=256,
        crop_rect=rect, rotation_degrees=rotation)
    assert np.any(expected != quantize_np(truncated_float)), 'Fixture must expose premature RGB8 loss'
    seen = []
    original_geometry = geometry.crop_rotate_np
    def geometry_check(frame, *args, **kwargs):
        assert frame.dtype.kind == 'f'
        seen.append(frame.shape)
        return original_geometry(frame, *args, **kwargs)
    monkeypatch.setattr(geometry, 'crop_rotate_np', geometry_check)
    monkeypatch.setattr(ex, 'quantize16_np', lambda *_args, **_kwargs: pytest.fail('Intermediate RGB16 pack'))
    got, facts = delivery.render_delivery8(source, spec, device='cpu', tile=256,
        crop_rect=rect, rotation_degrees=rotation)
    np.testing.assert_array_equal(got, expected)
    assert len(seen) == 1 and facts['crop_applied']
    assert got.shape[:2] == (96, 48) and (facts['h'], facts['w']) == got.shape[:2]
    assert not spec.float_output


def test_input_icc_is_converted_before_float_edit_and_output_source_is_preserved(tmp_path):
    pytest.importorskip('torch')
    from lumaretouch_engine.color16 import convert_rgb16
    from lumaretouch_engine.quant import quantize_np
    from lumaretouch_engine.export_target_size_adapter import write_delivery
    from test_color16 import linear_srgb_profile
    pixels = _gradient(32, 48)
    source_icc = linear_srgb_profile()
    source = delivery.decode_for_delivery8(
        _png16(tmp_path / 'linear.png', pixels, icc=source_icc), device='cpu')
    np.testing.assert_array_equal(source.rgb, pixels)
    spec = ex.ExportSpec(strength=0, exposure=(.23, 0, 0, 0, 0, 0, 0))
    expected_spec = copy(spec)
    expected_spec.float_output = True
    expected_float, _ = ex.export_image16(convert_rgb16(pixels, source_icc, ex._srgb_bytes()),
        expected_spec, device='cpu', tile=256)
    frame, facts = delivery.render_delivery8(source, spec, device='cpu', tile=256)
    np.testing.assert_array_equal(frame, quantize_np(expected_float))
    assert source.source_icc == source_icc and facts['input_color_converted']
    delivery.check_source_profile(source, 'source')
    output = tmp_path / 'delivery.png'
    info = write_delivery(frame, str(output), output_profile='source', source_icc=source.source_icc)
    expected, _ = ex._convert_srgb_to_profile(Image.fromarray(frame), source_icc)
    with Image.open(output) as image:
        assert image.info['icc_profile'] == source_icc
        np.testing.assert_array_equal(np.asarray(image), np.asarray(expected))
    assert info['color_converted'] and info['icc_source'] == 'source'


def test_watermarked_and_clean_png16_delivery_keep_writer_color_and_metadata_contract(tmp_path):
    pytest.importorskip('torch')
    from lumaretouch_engine import watermark
    from lumaretouch_engine.export_target_size_adapter import write_delivery
    from test_color16 import linear_srgb_profile
    from test_export_profile import _gps_exif
    icc = linear_srgb_profile()
    source = delivery.decode_for_delivery8(_png16(tmp_path / 'source.png', _gradient(48, 72),
        icc=icc, exif=_gps_exif(orient=6).tobytes()), device='cpu')
    spec = ex.ExportSpec(strength=0, exposure=(.17, 0, 0, 0, 0, 0, 0))
    frame, _ = delivery.render_delivery8(source, spec, device='cpu', tile=256,
        crop_rect=(.1, .1, .9, .9))
    logo = tmp_path / 'logo.png'
    Image.new('RGBA', (8, 4), (220, 40, 90, 160)).save(logo)
    frozen = watermark.freeze_settings({'enabled': True, 'alsoClean': True,
        'profiles': {name: {'kind': 'image', 'imagePath': str(logo)}
                     for name in watermark.ORIENTATIONS}})
    marked, _ = watermark.composite(frame, frozen)
    output = tmp_path / 'result.png'
    info = write_delivery(frame, str(output), watermark=frozen, output_profile='source',
        source_icc=source.source_icc, source_exif=source.source_exif)
    assert {entry['variant'] for entry in info['outputs']} == {'clean', 'watermarked'}
    for entry in info['outputs']:
        working = frame if entry['variant'] == 'clean' else marked
        expected, _ = ex._convert_srgb_to_profile(Image.fromarray(working), icc)
        with Image.open(entry['path']) as image:
            np.testing.assert_array_equal(np.asarray(image), np.asarray(expected))
            assert image.info['icc_profile'] == icc
            assert 0x0112 not in image.getexif() and not image.getexif().get_ifd(0x8825)
        assert entry['gps_written'] is False


def test_legacy_rgb8_geometry_retains_pixels_and_reports_final_canvas(monkeypatch):
    from lumaretouch_engine.ops.geometry import crop_rotate_np
    pixels = np.arange(8 * 12 * 3, dtype=np.uint8).reshape(8, 12, 3)
    decoded = SimpleNamespace(rgb=pixels, raw=None)
    spec = ex.ExportSpec(strength=0)
    calls = []
    def render(frame, own_spec, **options):
        calls.append(options['geometry'])
        return frame, {'bits': 8, 'w': 12, 'h': 8, 'px': 96}
    monkeypatch.setattr(ex, 'export_image', render)
    rect = (.25, .25, .75, .75)
    got, facts = delivery.render_delivery8(decoded, spec, device='cpu', tile=256,
        crop_rect=rect, rotation_degrees=90)
    np.testing.assert_array_equal(got, crop_rotate_np(pixels, rect, 90))
    assert calls == [None] and facts['crop_applied']
    assert (facts['h'], facts['w'], facts['px']) == (6, 4, 24)


def test_server_routes_ordinary_exports_through_native_precision_boundary():
    """Source-only wiring guard, not evidence that the application was run."""
    source = (Path(__file__).parents[1] / 'src/lumaretouch_engine/server.py').read_text()
    assert 'd = decode_for_delivery8(path, device=snap_i["device"]' in source
    assert 'frame, st = render_delivery8(d, spec' in source
    assert 'check_source_profile(d, opts["output_profile"])' in source
    assert 'opts["output_profile"] == "source" and d.raw is not None' not in source
