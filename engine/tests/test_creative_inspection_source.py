"""Returned-base inspection contracts. Authored fixtures, not validation evidence."""
import numpy as np
import pytest

from lumaretouch_engine import full_quality as F
from lumaretouch_engine.creative_document_assets import make_asset, validate_asset
from lumaretouch_engine.export import ExportSpec, ExportError
from lumaretouch_engine.render_snapshot import own_render_inputs, SnapshotError, SnapshotTransaction
from lumaretouch_engine.inspection_bundle import BundleWriter, read_bundle
from lumaretouch_engine.inspection_wire import encode_header


def base(width=4, height=3):
    rgba = np.zeros((height, width, 4), dtype='<f4')
    rgba[..., 0] = .25
    rgba[..., 3] = 1
    return make_asset('rgba', width, height, rgba.tobytes(), original=b'original provenance')


def test_immutable_asset_bytes_are_admitted_and_spooled_exactly(tmp_path):
    record = base()
    size = sum(len(record[key]) for key in ('content', 'original', 'icc'))
    with pytest.raises(SnapshotError):
        own_render_inputs({'creative_base': record}, max_asset_bytes=size-1)
    tx = SnapshotTransaction({'creative_base': record}, max_asset_bytes=size)
    assert tx.complete and tx.asset_bytes == size
    owned = tx.take_result()
    assert owned.value['creative_base'] is not record
    assert owned.value['creative_base']['content'] is record['content']
    assert owned.array_count == 0
    writer = BundleWriter(tmp_path, owned)
    while not writer.advance(7):
        pass
    assert writer.written_bytes == size
    out = read_bundle(tmp_path, max_asset_bytes=size)['creative_base']
    assert out == record and type(out['content']) is bytes
    validate_asset(out)
    out['content'] = bytes(len(out['content']))
    with pytest.raises(ValueError):
        validate_asset(out)


def test_mutable_byte_buffers_are_not_snapshot_assets():
    with pytest.raises(SnapshotError):
        own_render_inputs({'content': bytearray(16)}, max_asset_bytes=16)


class UnreadableOriginal:
    def __getattribute__(self, name):
        raise AssertionError('Returned-base inspection read original decoded pixels: '+name)


def test_derived_inspection_uses_baked_dimensions_single_resolver_and_true_precision(monkeypatch):
    record = base()
    spec = ExportSpec(strength=0, creative_base=record)
    calls = []
    def render(carrier, actual_spec, **options):
        assert carrier.shape == (0, 0, 3)
        assert actual_spec.creative_base['id'] == record['id']
        assert options['crop_rect'] == (0., 0., 1., 1.)
        calls.append(options)
        return np.full((3, 4, 3), 32768, np.uint16), {}
    monkeypatch.setattr(F, 'export_image16', render)
    result = F.render_inspection_roi(UnreadableOriginal(), spec, (1, 1, 2, 1),
        max_source_pixels=12, max_display_pixels=2)
    assert len(calls) == 1
    assert (result.canvas_width, result.canvas_height) == (4, 3)
    assert result.decoded_bits == 32 and result.source_bits is None
    assert np.all(result.rgba[..., :3] == 128)
    header = encode_header(result, epoch=b'x'*16, ticket=(1, 2, 3, 4, 5), max_payload=8)
    assert header[104:108] == bytes((32, 0, 0, 0))


def test_derived_admission_and_cancellation_precede_resolution(monkeypatch):
    spec = ExportSpec(strength=0, creative_base=base())
    def forbidden(*args, **kwargs):
        raise AssertionError('Canonical conversion started before admission')
    monkeypatch.setattr(F, 'export_image16', forbidden)
    with pytest.raises(ExportError, match='pixel budget'):
        F.render_inspection_roi(None, spec, (0, 0, 1, 1), max_source_pixels=11, max_display_pixels=1)
    with pytest.raises(F.RefinementCancelled):
        F.render_inspection_roi(None, spec, (0, 0, 1, 1), max_source_pixels=12,
            max_display_pixels=1, cancelled=lambda: True)


def test_cancelled_derived_result_never_publishes(monkeypatch):
    rendered = []
    def render(*args, **kwargs):
        rendered.append(True)
        return np.zeros((3, 4, 3), np.uint16), {}
    monkeypatch.setattr(F, 'export_image16', render)
    with pytest.raises(F.RefinementCancelled):
        F.render_inspection_roi(None, ExportSpec(strength=0, creative_base=base()), (0, 0, 1, 1),
            max_source_pixels=12, max_display_pixels=1, cancelled=lambda: bool(rendered))


def test_actual_native_derived_pixels_match_export_after_crop_and_rotation():
    # This is an integration fixture, not a stub-based numerical acceptance.
    # Missing packaged native code is an explicit skip, never a Python fallback.
    from pathlib import Path
    from lumaretouch_engine import creative_layer_native
    if not (Path(creative_layer_native.__file__).parent/'bin/liblrt_creative_layers.so').is_file():
        pytest.skip('Packaged creative Rust library unavailable')
    from lumaretouch_engine.export import export_image16
    record = base(96, 64)
    spec = ExportSpec(strength=0, creative_base=record)
    crop = (.125, .125, .875, .875)
    result = F.render_inspection_roi(UnreadableOriginal(), spec, (2, 3, 8, 7),
        max_source_pixels=6144, max_display_pixels=56, device='cpu',
        crop_rect=crop, rotation_degrees=90.)
    frame, _ = export_image16(np.empty((0, 0, 3), np.uint16), spec,
        device='cpu', crop_rect=crop, rotation_degrees=90.)
    expected = ((frame[3:10, 2:10].astype(np.uint32)+128)//257).astype(np.uint8)
    np.testing.assert_array_equal(result.rgba[..., :3], expected)
    assert result.decoded_bits == 32 and result.source_bits is None


@pytest.mark.parametrize('identity_matches', [True, False])
def test_worker_binds_canonical_identity_and_never_decodes_original(tmp_path, monkeypatch, identity_matches):
    import json
    import torch
    from lumaretouch_engine import inspection_worker as worker, inspection_bundle, decode, export_recipe
    record = base()
    original = tmp_path/'original-provenance.bin'
    original.write_bytes(b'Not an image: returned source must not decode this')
    request = dict(path=str(original), source_identity=worker.source_identity(original),
        source_asset_id=record['id'] if identity_matches else 'sha256:'+'0'*64,
        epoch='12'*16, ticket=['1','1','1','1','1'], roi=[0,0,1,1],
        source_size=[4,3], canvas_size=[4,3], max_source_pixels=12,
        max_display_pixels=1, max_address_bytes=512*1024**2, timeout_seconds=1,
        max_asset_bytes=1024)
    (tmp_path/'request.json').write_text(json.dumps(request))
    monkeypatch.setattr(torch, 'set_num_threads', lambda _: None)
    monkeypatch.setattr(torch, 'set_num_interop_threads', lambda _: None)
    monkeypatch.setattr(inspection_bundle, 'read_bundle', lambda *a, **kw: {'creative_base':record})
    def forbidden(*args, **kwargs):
        raise AssertionError('Original file was decoded for derived inspection')
    monkeypatch.setattr(decode, 'load_full', forbidden)
    monkeypatch.setattr(decode, 'is_raw', forbidden)
    def build(snap, height, width, *, for_document):
        assert (height, width, for_document) == (3,4,True)
        return ExportSpec(strength=0, creative_base=snap['creative_base']), []
    monkeypatch.setattr(export_recipe, 'build_export_spec', build)
    def render(decoded, spec, roi, **options):
        assert decoded is None and spec.creative_base['id'] == record['id']
        return F.InspectionPixels(np.array([[[20,30,40,255]]],np.uint8),4,3,tuple(roi),32)
    monkeypatch.setattr(F, 'render_inspection_roi', render)
    if not identity_matches:
        with pytest.raises(ValueError, match='source identity mismatch'):
            worker.render(str(tmp_path))
        assert not (tmp_path/'result.lrif').exists()
    else:
        worker.render(str(tmp_path))
        packet = (tmp_path/'result.lrif').read_bytes()
        assert packet[104:108] == bytes((32,0,0,0))
        assert packet[128:] == bytes((20,30,40,255))
