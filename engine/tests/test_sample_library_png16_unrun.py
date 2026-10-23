"""AUTHORED / UNRUN: genuine sample-library PNG16/ICC16 and legacy reinspection.

No product imports, codecs, fixtures or tests were executed during authoring.
Qoder must run these alongside the established sample-library acceptance suite.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import struct
import zlib

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import sample_library_images as I
from lumaretouch_engine import sample_library_source as N
from lumaretouch_engine import sample_library_state as S
from lumaretouch_engine import reference_color_assets as A
from lumaretouch_engine.sample_library_controller import SampleLibrary


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr('lumaretouch_engine.cpu_memory_budget.available_estimate', lambda: 8 * 1024**3)
    monkeypatch.setenv('LRT_PRESET_DIR', str(tmp_path / 'presets'))
    return SampleLibrary(tmp_path / 'library')


def pixels():
    data = np.full((80, 96, 3), (12001, 23002, 34003), dtype=np.uint16)
    data[24:40, 24:40, 0] += 1
    return data


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def png16(path, data=None, *, kind=2, icc=None, alpha=65535, trns=None, orientation=1, exif_after_idat=False, extra=()):
    data = pixels() if data is None else data
    if kind in (0, 4): data = data[:, :, :1]
    if kind in (4, 6):
        opacity = np.full((*data.shape[:2], 1), 65535, dtype=np.uint16)
        opacity[0, 0, 0] = alpha
        data = np.concatenate((data, opacity), axis=2)
    h, w = data.shape[:2]
    encoded = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 16, kind, 0, 0, 0))
    if icc: encoded += chunk(b'iCCP', b'fixture\0\0' + zlib.compress(icc))
    exif_chunk = b''
    if orientation != 1:
        exif = Image.Exif(); exif[274] = orientation
        exif_chunk = chunk(b'eXIf', exif.tobytes()[6:])
        if not exif_after_idat: encoded += exif_chunk
    if trns is not None: encoded += chunk(b'tRNS', struct.pack('>' + 'H' * len(trns), *trns))
    for kind_, payload in extra: encoded += chunk(kind_, payload)
    encoded += chunk(b'IDAT', zlib.compress(b''.join(b'\0' + row.astype('>u2').tobytes() for row in data)))
    if exif_after_idat: encoded += exif_chunk
    path.write_bytes(encoded + chunk(b'IEND', b''))
    return path


def sample(library):
    with library.store.read() as catalog:
        return deepcopy(catalog['samples'][0])


def import_file(library, path):
    return library.command('import_paths', {'paths': [str(path)], 'group_id': S.UNGROUPED}, library.snapshot()['revision'])


def selected_frame(library, item):
    result = library.select(item['id'], library.snapshot()['revision'])
    return result, A.load(A.cache_root(), result['reference'])


def adobe_profile():
    return (Path(__file__).parent / 'fixtures' / 'icc' / 'AdobeCompat-v2.icc').read_bytes()


def test_png16_import_keeps_original_and_selection_keeps_low_bits(library, tmp_path, monkeypatch):
    path = png16(tmp_path / 'source.png'); original = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(A, 'save', lambda *args: pytest.fail('Import must not materialize a float reference'))
        result = import_file(library, path)
    assert result['outcomes'][0]['status'] == 'imported'
    item = sample(library)
    assert item['reference_supported'] and item['reference'] is None
    assert item['precision'] == '16-bit source; 8-bit display thumbnail'
    assert item['original_sha256'] == sha256(original).hexdigest()
    assert library.store.verify_object(item['object_name'], item['original_sha256']).read_bytes() == original
    result, frame = selected_frame(library, item)
    np.testing.assert_array_equal(frame.rgb, pixels().astype(np.float32) / 65535)
    assert frame.rgb[25, 25, 0] != frame.rgb[0, 0, 0]
    assert frame.authentic_mask[2:-2, 2:-2].all() and not frame.authentic_mask[:2].any()
    assert selected_frame(library, item)[0]['reference'] == result['reference']
    assert path.read_bytes() == original


@pytest.mark.parametrize('fmt', ['PNG', 'TIFF'])
def test_icc16_is_converted_before_thumbnail_and_full_reference(library, tmp_path, monkeypatch, fmt):
    from lumaretouch_engine import decode as D
    from lumaretouch_engine.full_source_working import working_rgb
    data = pixels(); profile = adobe_profile()
    if fmt == 'PNG': path = png16(tmp_path / 'profile.png', data, icc=profile)
    else:
        import tifffile
        path = tmp_path / 'profile.tif'
        tifffile.imwrite(path, data, photometric='rgb', extratags=[(34675, 'B', len(profile), profile, False)])
    expected = working_rgb(D.load_full(str(path), want_bits=16))
    observed = []; original_thumbnail = N.native_thumbnail
    def thumbnail(value):
        observed.append(value.copy())
        return original_thumbnail(value)
    monkeypatch.setattr(N, 'native_thumbnail', thumbnail)
    monkeypatch.setattr(D, '_to_working_srgb', lambda *args: pytest.fail('ICC16 cannot be converted after RGB8 staging'))
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    np.testing.assert_array_equal(observed[0], expected)
    assert observed[0].dtype == np.uint16 and not np.array_equal(expected, data)
    _, frame = selected_frame(library, sample(library))
    np.testing.assert_array_equal(frame.rgb, expected.astype(np.float32) / 65535)


@pytest.mark.parametrize('kind', [0, 2, 4, 6])
def test_opaque_native_png_channels_are_not_rejected_by_alpha_presence(library, tmp_path, kind):
    path = png16(tmp_path / 'opaque.png', kind=kind)
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    item = sample(library); assert item['reference_supported']
    _, frame = selected_frame(library, item)
    expected = pixels() if kind in (2, 6) else np.repeat(pixels()[:, :, :1], 3, axis=2)
    np.testing.assert_array_equal(frame.rgb, expected.astype(np.float32) / 65535)


@pytest.mark.parametrize('kind', [4, 6])
def test_alpha65534_is_rejected_without_rgb8_opacity_rounding(library, tmp_path, kind):
    path = png16(tmp_path / 'transparent.png', kind=kind, alpha=65534)
    original = path.read_bytes()
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    item = sample(library)
    assert not item['reference_supported'] and '透明' in item['reference_reason']
    assert any('占位' in note for note in item['notes'])
    assert library.store.verify_object(item['object_name'], item['original_sha256']).read_bytes() == original
    with pytest.raises(S.LibraryError): selected_frame(library, item)
    # A stale or tampered true flag still cannot bypass native opacity validation.
    with library.store.locked(library.snapshot()['revision']) as catalog:
        catalog['samples'][0].update(reference_supported=True, reference_reason='')
    with pytest.raises(ValueError, match='透明'): selected_frame(library, sample(library))


@pytest.mark.parametrize('trns,supported', [((12000, 23002, 34003), True), ((12001, 23002, 34003), False)])
def test_trns_uses_native_sample_equality(library, tmp_path, trns, supported):
    path = png16(tmp_path / 'trns.png', trns=trns)
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    assert sample(library)['reference_supported'] is supported


@pytest.mark.parametrize('exif_after_idat', [False, True])
@pytest.mark.parametrize('orientation', range(1, 9))
def test_png_orientation_applied_once_in_thumbnail_and_reference(library, tmp_path, orientation, exif_after_idat):
    from lumaretouch_engine.decode import load_full
    path = png16(tmp_path / 'oriented.png', orientation=orientation, exif_after_idat=exif_after_idat)
    expected = load_full(str(path), want_bits=16).rgb
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    item = sample(library)
    assert (item['width'], item['height']) == (expected.shape[1], expected.shape[0])
    _, frame = selected_frame(library, item)
    np.testing.assert_array_equal(frame.rgb, expected.astype(np.float32) / 65535)


@pytest.mark.parametrize('variant', ['hdr', 'grey_icc', 'invalid_icc'])
def test_unsupported_colour_keeps_original_and_never_uses_rgb8_fallback(library, tmp_path, monkeypatch, variant):
    from lumaretouch_engine import decode as D
    kwargs = {'extra': [(b'cICP', b'\x09\x10\x00\x01')]} if variant == 'hdr' else (
        {'kind': 0, 'icc': adobe_profile()} if variant == 'grey_icc' else {'icc': b'invalid ICC'})
    path = png16(tmp_path / 'unsupported.png', **kwargs); original = path.read_bytes()
    monkeypatch.setattr(D, '_load_full_pillow', lambda *args: pytest.fail('Unsupported PNG16 cannot fall back'))
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    item = sample(library)
    assert not item['reference_supported'] and item['reference'] is None
    assert any('占位' in note for note in item['notes'])
    assert library.store.verify_object(item['object_name'], item['original_sha256']).read_bytes() == original


@pytest.mark.parametrize('alpha,supported', [(255, True), (254, False)])
def test_8bit_opacity_is_actual_not_channel_presence(library, tmp_path, alpha, supported):
    path = tmp_path / 'rgba.png'; Image.new('RGBA', (96, 80), (23, 71, 159, alpha)).save(path)
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    assert sample(library)['reference_supported'] is supported


def mark_legacy(library):
    with library.store.locked(library.snapshot()['revision']) as catalog:
        catalog['samples'][0].update(reference_supported=False,
            reference_reason='原片已保留；现有完整参考解码仅支持 RGB8 或 RGB16 TIFF，不会降位')
    return deepcopy(sample(library))


def test_explicit_duplicate_reinspection_upgrades_only_reviewed_metadata(library, tmp_path):
    path = png16(tmp_path / 'legacy.png'); import_file(library, path)
    old = mark_legacy(library)
    result = import_file(library, path)
    current = sample(library)
    assert result['outcomes'][0]['status'] == 'duplicate'
    assert '重新验证' in result['outcomes'][0]['message']
    assert result['affected_ids'] == [old['id']]
    assert current['reference_supported'] and current['reference'] is None
    mutable = {'reference_supported', 'reference_reason', 'notes', 'thumbnail_sha256'}
    assert {k: v for k, v in current.items() if k not in mutable} == {k: v for k, v in old.items() if k not in mutable}
    selected_frame(library, current)


def test_unsupported_legacy_reimport_leaves_catalogue_bytes_unchanged(library, tmp_path):
    path = png16(tmp_path / 'legacy-alpha.png', kind=6, alpha=65534); import_file(library, path)
    mark_legacy(library); before = library.store.catalog.read_bytes()
    result = import_file(library, path)
    assert result['outcomes'][0]['status'] == 'duplicate'
    assert '重新验证' not in result['outcomes'][0]['message']
    assert library.store.catalog.read_bytes() == before


def test_reinspection_never_rewrites_existing_reference_or_replay(library, tmp_path, monkeypatch):
    path = png16(tmp_path / 'retained.png'); import_file(library, path)
    result, _ = selected_frame(library, sample(library)); reference = result['reference']
    bundle = A.cache_root() / (reference['asset_id'] + '.npz'); original = bundle.read_bytes()
    mark_legacy(library)
    monkeypatch.setattr(I, 'inspect_and_thumbnail', lambda *args: pytest.fail('An immutable reference cannot be reinterpreted'))
    import_file(library, path)
    assert sample(library)['reference'] == reference and bundle.read_bytes() == original
    A.load(A.cache_root(), reference)


def test_retained_object_hash_failure_cannot_upgrade_legacy_flag(library, tmp_path):
    path = png16(tmp_path / 'changed.png'); import_file(library, path)
    old = mark_legacy(library); before = library.store.catalog.read_bytes()
    retained = library.store.root / 'originals' / old['object_name']
    retained.write_bytes(retained.read_bytes() + b'corrupt')
    result = import_file(library, path)
    assert result['outcomes'][0]['status'] == 'error'
    assert library.store.catalog.read_bytes() == before


def test_reinspection_cancel_before_publication_does_not_change_row(library, tmp_path, monkeypatch):
    path = png16(tmp_path / 'cancelled.png'); import_file(library, path)
    old = mark_legacy(library); row = deepcopy(old); cancelled = [False]
    original_save = I.save_thumbnail
    def save_and_cancel(*args):
        result = original_save(*args); cancelled[0] = True
        return result
    monkeypatch.setattr(I, 'save_thumbnail', save_and_cancel)
    with pytest.raises(S.LibraryError, match='取消'):
        I.reinspect_import(library.store, row, lambda: cancelled[0])
    assert row == old and sample(library) == old


def test_png16_post_idat_metadata_never_uses_pillow_source_decode(library, tmp_path, monkeypatch):
    path = png16(tmp_path / 'native-only.png', orientation=6, exif_after_idat=True)
    monkeypatch.setattr(Image, 'open', lambda *args, **kwargs: pytest.fail('PNG16 metadata/pixels must use the genuine decoder'))
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    item = sample(library); assert (item['width'], item['height']) == (80, 96)
    _, frame = selected_frame(library, item)
    np.testing.assert_array_equal(frame.rgb, np.rot90(pixels(), -1).astype(np.float32) / 65535)


def test_jpeg_thumbnail_memory_admission_uses_actual_draft_size(library, tmp_path, monkeypatch):
    path = tmp_path / 'large.jpg'; Image.new('RGB', (4000, 3000), (45, 89, 135)).save(path)
    calls = []; admission = N.admit_memory
    def observed(width, height, *, native):
        calls.append((width, height, native)); admission(width, height, native=native)
    monkeypatch.setattr(N, 'admit_memory', observed)
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    assert calls and all(not native and max(width, height) <= 768 for width, height, native in calls)
    assert (sample(library)['width'], sample(library)['height']) == (4000, 3000)


@pytest.mark.parametrize('suffix', ['.png', '.jpg'])
def test_renamed_tiff16_import_uses_verified_format_not_staging_suffix(library, tmp_path, suffix):
    import tifffile
    path = tmp_path / ('renamed-tiff' + suffix)
    tifffile.imwrite(path, pixels(), photometric='rgb')
    assert import_file(library, path)['outcomes'][0]['status'] == 'imported'
    item = sample(library)
    assert item['format'] == 'TIFF' and item['reference_supported']
    _, frame = selected_frame(library, item)
    np.testing.assert_array_equal(frame.rgb, pixels().astype(np.float32) / 65535)
