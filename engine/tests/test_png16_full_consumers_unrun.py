"""AUTHORED / UNRUN: original PNG16 precision and working-space consumers.

No imports, tests, codec calls, native execution or image operations were run
while authoring. Decoder samples use independent PNG filter-0/zlib bytes; adapter
doubles establish routing only, not runtime/native/ICC accuracy or visual quality.
"""
from hashlib import sha256
from types import SimpleNamespace
import importlib
import struct
import zlib

import numpy as np
import pytest


def png16(path, pixels):
    """Write independent true 16-bit RGB/RGBA samples, not Pillow RGB8."""
    height, width, channels = pixels.shape
    assert pixels.dtype == np.uint16 and channels in (3, 4)

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    scanlines = b''.join(b'\0' + row.astype('>u2').tobytes() for row in pixels)
    header = struct.pack('>IIBBBBB', width, height, 16, 2 if channels == 3 else 6, 0, 0, 0)
    encoded = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b'')
    path.write_bytes(encoded)
    return encoded


def decoded(pixels):
    height, width = pixels.shape[:2]
    return SimpleNamespace(rgb=pixels, h=height, w=width, src_h=height, src_w=width,
        src_bits=16, source_icc=b'source-profile', draft_used=False,
        raw={'source': 'png16', 'bits': 16, 'used_preview': False, 'half_size': False})


def test_inspection_decodes_independent_rgb16_low_bits(tmp_path):
    from lumaretouch_engine.inspection_worker import _decode_original
    original = np.array([[[256, 257, 258], [32767, 32768, 32769]],
                         [[65533, 65534, 65535], [1, 2, 3]]], np.uint16)
    path = tmp_path / 'genuine.png'
    encoded = png16(path, original)
    result = _decode_original(str(path), 4)
    assert result.rgb.dtype == np.uint16 and result.src_bits == 16
    assert result.raw['source'] == 'png16'
    np.testing.assert_array_equal(result.rgb, original)
    assert path.read_bytes() == encoded


def test_inspection_rgb16_cannot_fall_back_to_rgb8(tmp_path, monkeypatch):
    from lumaretouch_engine import decode, inspection_worker
    path = tmp_path / 'genuine.png'
    png16(path, np.full((2, 3, 3), 257, np.uint16))
    calls = []

    def lower_precision(path, **options):
        calls.append(options)
        return decoded(np.ones((2, 3, 3), np.uint8))

    monkeypatch.setattr(decode, 'load_full', lower_precision)
    with pytest.raises(ValueError, match='genuine RGB16'):
        inspection_worker._decode_original(str(path), 6)
    assert calls == [{'max_px': 6, 'device': 'cpu', 'want_bits': 16}]


def test_inspection_admission_precedes_full_decode(tmp_path, monkeypatch):
    from lumaretouch_engine import decode, inspection_worker
    path = tmp_path / 'genuine.png'
    png16(path, np.full((2, 3, 3), 257, np.uint16))
    monkeypatch.setattr(decode, 'load_full', lambda *a, **kw: pytest.fail('Decoded before admission'))
    with pytest.raises(ValueError, match='pixel budget'):
        inspection_worker._decode_original(str(path), 5)


@pytest.mark.parametrize('precision', [8, 16])
def test_inspection_refuses_actual_transparency_at_native_precision(tmp_path, precision):
    from PIL import Image
    from lumaretouch_engine.inspection_worker import _decode_original
    path = tmp_path / 'coverage.png'
    if precision == 8:
        Image.new('RGBA', (2, 3), (128, 128, 128, 254)).save(path)
    else:
        pixels = np.full((3, 2, 4), 65535, np.uint16)
        pixels[1, 1, 3] = 65534  # Pillow RGB8 can hide this native alpha difference.
        png16(path, pixels)
    with pytest.raises(ValueError):
        _decode_original(str(path), 6)


def test_prompted_source_routes_true16_through_shared_working_space(tmp_path, monkeypatch):
    from lumaretouch_engine import decode, full_source_working as working, prompted_mask_source as source
    path = tmp_path / 'genuine.png'
    original = np.full((2, 3, 3), 32768, np.uint16)
    encoded = png16(path, original)
    binding = {'sha256': sha256(encoded).hexdigest(), 'width': 3, 'height': 2}
    native = decoded(original)
    converted = original.copy(); converted[0, 0, 0] = 32769
    calls = []

    def full(path, **options):
        assert options['want_bits'] == 16
        return native

    monkeypatch.setattr(decode, 'load_full', full)
    monkeypatch.setattr(working, 'working_rgb', lambda actual: calls.append(actual) or converted)
    assert source.decode_source(str(path), binding) is converted
    assert calls == [native] and path.read_bytes() == encoded


@pytest.mark.parametrize('refusal', ['rgb8', 'half_size', 'preview', 'draft', 'dimensions'])
def test_prompted_source_refuses_highbit_surrogates(tmp_path, monkeypatch, refusal):
    from lumaretouch_engine import decode, full_source_working as working, prompted_mask_source as source
    path = tmp_path / 'genuine.png'
    encoded = png16(path, np.full((2, 3, 3), 32768, np.uint16))
    native = decoded(np.full((2, 3, 3), 32768, np.uint16))
    if refusal == 'rgb8': native.rgb = native.rgb.astype(np.uint8)
    elif refusal == 'half_size': native.raw['half_size'] = True
    elif refusal == 'preview': native.raw['used_preview'] = True
    elif refusal == 'draft': native.draft_used = True
    else: native.src_w += 1
    monkeypatch.setattr(decode, 'load_full', lambda *a, **kw: native)
    monkeypatch.setattr(working, 'working_rgb', lambda value: pytest.fail('Converted a rejected source'))
    with pytest.raises(source.PromptedUnavailable):
        source.decode_source(str(path), {'sha256': sha256(encoded).hexdigest(), 'width': 3, 'height': 2})


def frozen_adapter(monkeypatch, tmp_path):
    """Isolate existing adapters from native render/inference and state owners."""
    from lumaretouch_engine import decode, cpu_memory_budget, export_recipe
    from lumaretouch_engine import local_mask_state as masks, virtual_copy_people, people_export
    from lumaretouch_engine import reference_color_runtime
    original = np.full((2, 3, 3), 32768, np.uint16)
    path = tmp_path / 'genuine.png'
    png16(path, original)
    row = {'path': str(path)}
    native = decoded(original)
    state = {'_params': {'strength': 0}, '_light': {'exposure_ev': 0}}
    spec = SimpleNamespace(provenance_result=np.ones((2, 3), bool))
    stamp = (1, 2, 3, 4, 5)
    calls = []

    class Engine:
        _docs = [row]
        _doc_index = 0
        _load_id = 'loaded'

        def _document_versions(self):
            return SimpleNamespace(version=lambda _: SimpleNamespace(document_id='document', revision=1))

        def _state_to_export_snap(self, *args, **kwargs):
            return {'crop_rect': (0., 0., 1., 1.), 'crop_rotation': 0., 'people': None}

    def full(actual_path, **options):
        assert actual_path == str(path) and options['want_bits'] == 16
        calls.append(('decode', options))
        return native

    monkeypatch.setattr(decode, 'load_full', full)
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 8 * 1024**3)
    monkeypatch.setattr(masks, 'file_stamp', lambda _: stamp)
    monkeypatch.setattr(masks, 'source_digest', lambda _: 'a' * 64)
    monkeypatch.setattr(virtual_copy_people, 'row_context', lambda *args: {})
    monkeypatch.setattr(virtual_copy_people, 'row_snapshot', lambda *args: {})
    monkeypatch.setattr(people_export, 'verify_source', lambda *args: None)
    monkeypatch.setattr(people_export, 'isolated_snapshot', lambda snap, **kw: snap)
    monkeypatch.setattr(reference_color_runtime, 'verify_export', lambda *args: None)
    for name in ('local_grade_source', 'effect_recovery_runtime', 'manual_liquify_runtime',
                 'studio_background_runtime', 'sky_replacement_runtime', 'body_pose_render',
                 'common_background_source', 'id_background_runtime'):
        owner = importlib.import_module('lumaretouch_engine.' + name)
        monkeypatch.setattr(owner, 'check_export_decode', lambda *args: None)
    monkeypatch.setattr(export_recipe, 'build_export_spec', lambda *args, **kwargs: (spec, []))
    return Engine(), row, state, native, calls


@pytest.mark.parametrize('adapter', ['reference', 'semantic'])
def test_frozen_float_adapters_convert_native_source_before_editing(tmp_path, monkeypatch, adapter):
    from lumaretouch_engine import export, full_source_working as working
    from lumaretouch_engine import reference_color_engine, semantic_colour_capture, semantic_colour_canvas
    engine, row, state, native, calls = frozen_adapter(monkeypatch, tmp_path)
    converted = native.rgb.copy(); converted[0, 0, 0] = 32769

    def convert(actual):
        assert actual is native
        calls.append(('working', actual))
        return converted

    def render(actual, spec, **options):
        assert actual is converted and actual.dtype == np.uint16
        if adapter == 'semantic': assert options['bits'] == 16
        calls.append(('render', actual))
        return actual.astype(np.float32) / np.float32(65535.), {}

    monkeypatch.setattr(working, 'working_rgb', convert)
    monkeypatch.setattr(export, 'export_float', render)
    monkeypatch.setattr(export, '_export_image_impl', render)
    monkeypatch.setattr(semantic_colour_capture, 'candidate_key', lambda *a: 'b' * 64)
    monkeypatch.setattr(semantic_colour_capture, 'geometry_key', lambda *a: 'c' * 64)
    monkeypatch.setattr(semantic_colour_canvas, 'freeze', lambda rgb, **kw: SimpleNamespace(rgb=rgb))
    owner = reference_color_engine if adapter == 'reference' else semantic_colour_capture
    result = owner.render(engine, row, state, 'document', '1')
    assert [kind for kind, _ in calls] == ['decode', 'working', 'render']
    assert result.rgb[0, 0, 0] != result.rgb[0, 0, 1]
    assert native.rgb[0, 0, 0] == 32768


def test_optics_adapter_passes_unconverted_native16_to_its_icc_owner(tmp_path, monkeypatch):
    from lumaretouch_engine import optics_transfer_engine, optics_transfer_input, full_source_working as working
    from lumaretouch_engine.optics_candidate_identity import fingerprint
    engine, row, state, native, calls = frozen_adapter(monkeypatch, tmp_path)
    monkeypatch.setattr(working, 'working_rgb', lambda _: pytest.fail('Optics would double-convert ICC'))

    def render(actual, spec, **options):
        assert actual is native and actual.source_icc == b'source-profile'
        calls.append(('optics', actual))
        return SimpleNamespace(candidate_key=fingerprint(state))

    monkeypatch.setattr(optics_transfer_input, 'render_target', render)
    optics_transfer_engine.prepare_target(engine, row, state, 'document', '1')
    assert [kind for kind, _ in calls] == ['decode', 'optics']


@pytest.mark.parametrize('shape', ['brow', 'nose', 'eye', 'mouth'])
@pytest.mark.parametrize('bits', [8, 16])
def test_shape_admission_uses_working_pixels_without_changing_geometry_ownership(monkeypatch, shape, bits):
    from lumaretouch_engine import decode, full_source_working as working, cpu_memory_budget, local_mask_state
    owner = importlib.import_module('lumaretouch_engine.' + shape + '_shape_scope')
    runtime = importlib.import_module('lumaretouch_engine.' + shape + '_shape_runtime')
    dtype = np.uint16 if bits == 16 else np.uint8
    native = decoded(np.full((2, 3, 3), 128, dtype))
    converted = np.full((2, 3, 3), 129, dtype)
    landmarks = object()
    pc = SimpleNamespace(landmarks=landmarks)
    recipe = {'test': 'active-owned-recipe'}
    state = {'_' + shape + '_shape': recipe, '_' + shape + '_shape_owner': 'face-id', '_precompute': pc}
    row = {'path': 'bound-original', 'src_h': 2, 'src_w': 3}
    calls = []
    monkeypatch.setattr(owner.S, 'check', lambda value: value)
    monkeypatch.setattr(owner.S, 'active', lambda value: True)
    monkeypatch.setattr(owner, 'identity', lambda value: 'face-id' if value is landmarks else 'other-face')
    monkeypatch.setattr(cpu_memory_budget, 'available_estimate', lambda: 8 * 1024**3)
    monkeypatch.setattr(local_mask_state, 'file_stamp', lambda _: (1, 2, 3, 4, 5))

    def full(path, **options):
        assert path == row['path'] and options == {'max_px': 6, 'device': 'cpu', 'want_bits': 16}
        calls.append('decode')
        return native

    def convert(actual):
        assert actual is native
        calls.append('working')
        return converted

    def field(spec, actual, *, divisor):
        assert actual is converted and divisor == (65535 if bits == 16 else 255)
        assert getattr(spec, shape + '_shape') is recipe
        assert getattr(spec, shape + '_shape_face') is pc and spec.landmarks is landmarks
        calls.append('field')

    monkeypatch.setattr(decode, 'load_full', full)
    monkeypatch.setattr(working, 'working_rgb', convert)
    monkeypatch.setattr(runtime, 'export_field', field)
    owner.validate_target(state, row)
    assert calls == ['decode', 'working', 'field']
    assert np.all(native.rgb == 128)
