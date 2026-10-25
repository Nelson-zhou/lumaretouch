"""Authored acceptance fixtures only. NOT EXECUTED for this source slice."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import struct
import zlib
import pytest
import numpy as np
from PIL import Image, ImageCms
from lumaretouch_engine import background_material_state as S
from lumaretouch_engine import background_material_images as I
from lumaretouch_engine import background_material_store as storage
from lumaretouch_engine.background_material_controller import BackgroundMaterialLibrary
from lumaretouch_engine.background_material_selection import resolve_for_id_background


def image_file(tmp_path, name='background.png', alpha=False):
    pytest.importorskip('imagecodecs')
    path = tmp_path / name
    image = Image.new('RGBA' if alpha else 'RGB', (9, 7), (42, 83, 127, 128) if alpha else (42, 83, 127))
    image.save(path); image.close()
    return path


def imported(tmp_path, path):
    library = BackgroundMaterialLibrary(tmp_path / 'materials')
    result = library.command('import_paths', {'paths': [str(path)], 'group_id': 'ungrouped'}, 0)
    assert result['changed'] and result['outcomes'][0]['status'] == 'imported'
    ident = result['outcomes'][0]['material_id']
    return library, ident, result['revision']


def page_query(**patch):
    return {'group_id': None, 'text': '', 'trash': False, 'sort': 'manual', 'offset': 0, 'limit': 48, **patch}


def test_original_bytes_copied_without_rewrite_and_lazy_page(tmp_path):
    path = image_file(tmp_path); original = path.read_bytes()
    library, ident, revision = imported(tmp_path, path)
    page = library.page(page_query(), revision)
    assert page['items'][0]['sha256'] == sha256(original).hexdigest()
    assert not any(key in page['items'][0] for key in ('path', 'binding', 'pixels', 'data_url'))
    with library.store.read() as catalog:
        row = catalog['materials'][0]
        assert library.store.object_path(row).read_bytes() == original
    assert path.read_bytes() == original
    selected = library.select(ident, revision)
    assert set(selected) == {'version', 'library_id', 'material_id', 'catalog_revision', 'sha256'}
    thumb = library.thumbnail(ident, revision)
    assert thumb['data_url'].startswith('data:image/png;base64,')


def test_real_alpha_bundle_survives_catalogue_removal(tmp_path):
    from lumaretouch_engine import id_background_assets as A
    path = image_file(tmp_path, alpha=True)
    library, ident, revision = imported(tmp_path, path)
    selection = library.select(ident, revision)
    asset = resolve_for_id_background(selection, root=library.store.root)
    assert asset.alpha is not None and np.allclose(asset.alpha, 128 / 255)
    bundle = A.pack(asset)
    removed = library.command('material_remove', {'ids': [ident]}, revision)
    with pytest.raises(S.MaterialError, match='版本'):
        resolve_for_id_background(selection, root=library.store.root)
    assert A.unpack(bundle).content == path.read_bytes()
    with library.store.read() as catalog: assert library.store.object_path(catalog['materials'][0]).exists()
    restored = library.command('material_restore', {'ids': [ident]}, removed['revision'])
    assert restored['counts']['active'] == 1


def test_png16_icc_keeps_original_samples_and_original_bytes(tmp_path):
    codecs = pytest.importorskip('imagecodecs')
    values = np.array([[[1000, 1001, 1002], [30000, 30001, 30002]],
                       [[40000, 40001, 40002], [65000, 65001, 65002]]], dtype=np.uint16)
    raw = codecs.png_encode(values)
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    payload = b'sRGB\0\0' + zlib.compress(icc)
    chunk = struct.pack('>I', len(payload)) + b'iCCP' + payload + struct.pack('>I', zlib.crc32(b'iCCP' + payload) & 0xffffffff)
    raw = raw[:33] + chunk + raw[33:]
    path = tmp_path / 'precise.png'; path.write_bytes(raw)
    library, ident, revision = imported(tmp_path, path)
    asset = resolve_for_id_background(library.select(ident, revision), root=library.store.root)
    assert asset.content == raw and asset.binding['bits'] == 16
    assert asset.binding['icc_sha256'] == sha256(icc).hexdigest()
    # Near-level channels must not all collapse through an RGB8 thumbnail path.
    assert asset.pixels[0, 0, 0] != asset.pixels[0, 0, 1]


def test_catalogue_search_cas_move_reorder_and_duplicate(tmp_path):
    path = image_file(tmp_path); library, ident, revision = imported(tmp_path, path)
    created = library.command('group_create', {'name': 'Portrait'}, revision)
    snapshot = library.snapshot(); gid = snapshot['groups'][-1]['id']
    with pytest.raises(S.MaterialError): library.command('material_rename', {'id': ident, 'name': 'old'}, revision)
    moved = library.command('material_move', {'ids': [ident], 'group_id': gid}, created['revision'])
    named = library.command('material_rename', {'id': ident, 'name': 'Blue Room'}, moved['revision'])
    assert library.page(page_query(text='BLUE', group_id=gid), named['revision'])['total'] == 1
    duplicate = library.command('import_paths', {'paths': [str(path)], 'group_id': 'ungrouped'}, named['revision'])
    assert duplicate['outcomes'][0]['status'] == 'duplicate' and not duplicate['changed']
    removed_group = library.command('group_delete', {'id': gid}, duplicate['revision'])
    assert library.page(page_query(group_id='ungrouped'), removed_group['revision'])['total'] == 1
    with pytest.raises(S.MaterialError): library.command('material_reorder', {'ids': []}, removed_group['revision'])


def test_cancel_after_first_import_retains_first_and_reports_rest(tmp_path, monkeypatch):
    first = image_file(tmp_path, 'first.png'); second = image_file(tmp_path, 'second.png')
    library = BackgroundMaterialLibrary(tmp_path / 'materials'); stop = [False]
    original = I.copy_original
    def copy(store, path, check):
        if path == second: stop[0] = True
        return original(store, path, check)
    monkeypatch.setattr(I, 'copy_original', copy)
    result = library.command('import_paths', {'paths': [str(first), str(second)], 'group_id': 'ungrouped'},
                             0, cancelled=lambda: stop[0])
    assert result['changed'] and result['counts']['active'] == 1
    assert [row['status'] for row in result['outcomes']] == ['imported', 'cancelled']
    assert library.snapshot()['revision'] == result['revision']


def test_corrupt_catalogue_and_missing_catalogue_never_reset(tmp_path):
    library = BackgroundMaterialLibrary(tmp_path / 'materials'); library.snapshot()
    raw = b'{"broken":true}'
    library.store.catalog.write_bytes(raw)
    with pytest.raises(S.MaterialError): library.snapshot()
    assert library.store.catalog.read_bytes() == raw


def test_duplicate_json_keys_refused(tmp_path):
    library = BackgroundMaterialLibrary(tmp_path / 'materials'); library.snapshot()
    raw = library.store.catalog.read_bytes().decode()
    raw = raw.replace('"version":1', '"version":1,"version":1')
    library.store.catalog.write_text(raw)
    with pytest.raises(S.MaterialError, match='重复'): library.snapshot()


def test_symlink_input_is_not_followed(tmp_path):
    path = image_file(tmp_path); alias = tmp_path / 'alias.png'; alias.symlink_to(path)
    library = BackgroundMaterialLibrary(tmp_path / 'materials')
    result = library.command('import_paths', {'paths': [str(alias)], 'group_id': 'ungrouped'}, 0)
    assert not result['changed'] and result['outcomes'][0]['status'] == 'error'


def test_changed_owned_object_and_cross_library_selection_refused(tmp_path):
    path = image_file(tmp_path); library, ident, revision = imported(tmp_path, path)
    selection = library.select(ident, revision)
    other = BackgroundMaterialLibrary(tmp_path / 'other'); other.snapshot()
    with pytest.raises(S.MaterialError): resolve_for_id_background(selection, root=other.store.root)
    with library.store.read() as catalog: owned = library.store.object_path(catalog['materials'][0])
    owned.chmod(0o600); owned.write_bytes(b'changed')
    with pytest.raises(S.MaterialError): resolve_for_id_background(selection, root=library.store.root)


def test_catalogue_change_during_real_decode_is_not_accepted(tmp_path, monkeypatch):
    from lumaretouch_engine import id_background_assets as A
    path = image_file(tmp_path); library, ident, revision = imported(tmp_path, path)
    selection = library.select(ident, revision); decode = A.read
    def changed(*args, **kwargs):
        result = decode(*args, **kwargs)
        library.command('material_rename', {'id': ident, 'name': 'changed'}, revision)
        return result
    monkeypatch.setattr(A, 'read', changed)
    with pytest.raises(S.MaterialError, match='版本'):
        resolve_for_id_background(selection, root=library.store.root)


def test_post_publication_fsync_failure_is_uncertain_not_not_applied(tmp_path, monkeypatch):
    library = BackgroundMaterialLibrary(tmp_path / 'materials'); library.snapshot()
    sync = storage._sync_dir
    def fail_after_publication(path):
        current = json.loads(library.store.catalog.read_bytes())
        if current['revision'] == 1: raise OSError('injected fsync failure')
        return sync(path)
    monkeypatch.setattr(storage, '_sync_dir', fail_after_publication)
    with pytest.raises(S.MaterialError) as caught:
        library.command('group_create', {'name': 'kept'}, 0)
    assert caught.value.outcome_unknown and caught.value.committed
    assert json.loads(library.store.catalog.read_bytes())['revision'] == 1


def test_cancel_before_catalogue_publication_keeps_revision(tmp_path):
    library = BackgroundMaterialLibrary(tmp_path / 'materials'); library.snapshot()
    with library.store.locked(0) as before:
        candidate = deepcopy(before); candidate['groups'].append({'id': S.new_id(), 'name': 'cancelled'})
        with pytest.raises(S.MaterialError): library.store.commit(before, candidate, cancelled=lambda: True)
    assert library.snapshot()['revision'] == 0


def test_imported_labels_cannot_emit_control_characters(tmp_path):
    assert I.display_name(tmp_path / 'blue\u0085room.png') == 'blueroom'
    with pytest.raises(S.MaterialError): S.name('blue\u0085room')
