"""AUTHORED / UNRUN: real PNG16 writer dispatch and destination ownership."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import export as E
from lumaretouch_engine import export_destination_runtime as R


def test_verified_rgb16_dispatches_png_without_tiff_settings(monkeypatch):
    from lumaretouch_engine import png16_export
    pixels = np.array([[[1, 257, 65534]]], np.uint16)
    calls = []
    def write(actual, path, **options):
        assert actual is pixels
        calls.append((path, options))
        return {'format': 'png', 'bits': 16}
    monkeypatch.setattr(png16_export, 'write_verified_png16', write)
    monkeypatch.setattr(E, 'write_tiff16', lambda *a, **kw: pytest.fail('PNG became TIFF'))
    result = E._write_verified_rgb16(pixels, 'output.PNG', target_icc=b'profile',
        conflict_policy='recheck', metadata_include_gps=False, tiff_compression='deflate')
    assert result == {'format': 'png', 'bits': 16}
    assert calls == [('output.PNG', {'target_icc': b'profile',
        'conflict_policy': 'recheck', 'metadata_include_gps': False})]


@pytest.mark.parametrize('format,expected', [('png', '.png'), ('tif', '.tif'), ('tiff', '.tif')])
def test_native16_destination_plan_freezes_actual_container(tmp_path, format, expected):
    original = tmp_path / 'original.png'
    original.write_bytes(b'immutable original')
    row = {'path': str(original)}
    versions = SimpleNamespace(workspace='workspace')
    engine = SimpleNamespace(_document_versions=lambda: versions, _docs=[row])
    entries = {'one': {'stem': 'edited', 'fingerprint': {'sha256': 'a' * 64}}}
    settings = {'bit_depth': 16, 'format': format}
    plan = R.build(engine, [row], ['one'], entries, settings,
        {'chosen_root': str(tmp_path / 'delivery'), 'create_missing': True}, 7)
    assert plan.entries[0].target.endswith('edited' + expected)
    assert len(plan.entries[0].frame_receipt) == 64
    assert original.read_bytes() == b'immutable original'
    assert not (tmp_path / 'delivery').exists()


def test_server_native16_capability_route_and_result_match_container():
    source = (Path(__file__).parents[1] / 'src/lumaretouch_engine/server.py').read_text()
    assert '"16": ["tif", "tiff", "png"]' in source
    assert 'if fmt not in ("tif", "tiff", "png"):' in source
    assert '"format": r["format"]' in source
    assert '(".png" if fmt == "png" else ".tif")' in source
    assert 'if bit_depth == 16 and include_gps:' in source
    assert '(bit_depth == 16 and "tiff_compression" in p)' in source


def test_master16_png_preserves_low_bits_and_original(tmp_path, monkeypatch):
    from lumaretouch_engine import cpu_memory_budget, png16_source
    from test_full_source_working_unrun import png16_bytes, rgb16
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 16 * 1024**3)
    original = tmp_path / 'original.png'
    encoded = png16_bytes()
    original.write_bytes(encoded)
    target = tmp_path / 'master.png'
    facts = E.export_master_16bit(str(original), str(target), output_profile='none')
    assert facts['format'] == 'png' and facts['bits'] == 16
    assert facts['readback_max_diff'] == 0 and facts['low8_nonzero_px'] > 0
    np.testing.assert_array_equal(png16_source.load_opaque_rgb16(target).rgb, rgb16())
    assert original.read_bytes() == encoded


def test_edited16_png_and_watermark_route_keep_real_container(tmp_path, monkeypatch):
    from lumaretouch_engine import decode, cpu_memory_budget, watermark, watermark_delivery, png16_source
    from test_full_source_working_unrun import png16_bytes, rgb16
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 16 * 1024**3)
    original = tmp_path / 'source.png'
    original.write_bytes(png16_bytes())
    decoded = decode.load_full(str(original), want_bits=16)
    def render(actual, spec, **kwargs):
        assert actual is decoded
        return rgb16(), None, {'source': 'png16', 'bits': 16,
            'color_converted': False, 'color_conversion_ms': 0.}
    monkeypatch.setattr(E, 'render_edited_rgb16', render)
    plain = E.export_edited_16bit(decoded, E.ExportSpec(strength=0), str(tmp_path / 'edited.png'),
        output_profile='none')
    assert plain['format'] == 'png' and plain['readback_max_diff'] == 0
    # Isolate mark construction here; the existing watermark numeric fixtures
    # own its actual compositor. This verifies both native16 writer deliveries.
    marked = rgb16().copy(); marked[0, 0, 0] = 1234
    monkeypatch.setattr(watermark, 'composite', lambda pixels, settings: (marked, {'review': 'fixture'}))
    result = watermark_delivery.export_delivery16(decoded, E.ExportSpec(strength=0),
        str(tmp_path / 'marked.png'), watermark={'alsoClean': True}, output_profile='none')
    assert {out['variant'] for out in result['outputs']} == {'clean', 'watermarked'}
    for output in result['outputs']:
        expected = rgb16() if output['variant'] == 'clean' else marked
        assert output['format'] == 'png' and output['readback_max_diff'] == 0
        np.testing.assert_array_equal(png16_source.load_opaque_rgb16(output['path']).rgb, expected)
