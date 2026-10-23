"""AUTHORED / UNRUN: PNG16 shared capture, master and edited-source contracts.

No codecs, product imports or test functions were executed during authoring.
"""
from pathlib import Path
import numpy as np
from lumaretouch_engine import decode as D, export as E
from lumaretouch_engine import creative_document_base as C
from lumaretouch_engine import optics_lensfun as O
from test_full_source_working_unrun import png16_bytes, rgb16


def test_png16_master_preserves_low_bits_and_original(tmp_path):
    source = tmp_path / 'source.png'
    content = png16_bytes()
    source.write_bytes(content)
    target = tmp_path / 'master.tif'
    result = E.export_master_16bit(str(source), str(target), output_profile='none')
    assert result['source'] == 'png16'
    assert result['readback_max_diff'] == 0
    assert result['low8_nonzero_px'] > 0
    np.testing.assert_array_equal(E.read_tiff16(str(target)), rgb16())
    assert source.read_bytes() == content


def test_png16_edited_export_reports_native_source_bits(tmp_path, monkeypatch):
    source = tmp_path / 'source.png'
    source.write_bytes(png16_bytes())
    decoded = D.load_full(str(source), want_bits=16)
    seen = []
    def capture(pixels, spec, **kwargs):
        seen.append(pixels.copy())
        return pixels.copy(), {}
    monkeypatch.setattr(E, 'export_image16', capture)
    actual, _, facts = E.render_edited_rgb16(decoded, E.ExportSpec(strength=0))
    np.testing.assert_array_equal(actual, rgb16())
    np.testing.assert_array_equal(seen[0], rgb16())
    assert facts['source'] == 'png16'
    assert facts['source_bits'] == facts['decoded_bits'] == 16


def test_current_edit_capture_uses_the_shared_genuine_source(tmp_path):
    source = tmp_path / 'source.png'
    content = png16_bytes()
    source.write_bytes(content)
    pixels = C._working_source(str(source), content, max_pixels=6, device='cpu')
    np.testing.assert_array_equal(pixels, rgb16())
    assert source.read_bytes() == content


def test_png16_provenance_is_not_camera_raw(tmp_path):
    source = tmp_path / 'source.png'
    source.write_bytes(png16_bytes())
    decoded = D.load_full(str(source), want_bits=16)
    assert O.metadata(decoded)['is_raw'] is False


def test_shared_candidate_does_not_decode_display_proxy():
    root = Path(__file__).parents[1] / 'src' / 'lumaretouch_engine'
    for name in ('full_candidate_render.py', 'spill_removal_paint_source.py'):
        source = (root / name).read_text()
        assert 'working_rgb(decoded)' in source
        assert 'want_bits=bits' in source
    capture = (root / 'creative_document_base.py').read_text()
    assert 'return working_rgb(decoded)' in capture
    assert 'from .creative_document_import import _png' not in capture
