"""Authored acceptance fixtures. NOT executed during source-only development."""
from pathlib import Path
from hashlib import sha256
import json
import pytest
from PIL import Image
from lumaretouch_engine import sample_library_state as S
from lumaretouch_engine.sample_library_controller import SampleLibrary
from lumaretouch_engine.sample_library_store import Store


@pytest.fixture
def library(tmp_path, monkeypatch):
    # Explicit test memory admission, never a production fallback.
    monkeypatch.setattr('lumaretouch_engine.cpu_memory_budget.available_estimate', lambda: 8 * 1024**3)
    monkeypatch.setenv('LRT_PRESET_DIR', str(tmp_path / 'presets'))
    return SampleLibrary(tmp_path / 'library')


def photo(tmp_path, name='original.png', color=(23, 71, 159)):
    path = tmp_path / name
    Image.new('RGB', (96, 80), color).save(path)
    return path


def imported(library, path):
    result = library.command('import_paths', {'paths': [str(path)], 'group_id': S.UNGROUPED}, library.snapshot()['revision'])
    assert result['outcomes'][0]['status'] == 'imported'
    return samples(library)[0]


def samples(library, view='all'):
    head = library.snapshot()
    return library.page({'view': view, 'search': '', 'limit': 100, 'cursor': None}, head['revision'])['samples']


def test_empty_library_and_byte_preserving_lazy_import(library, tmp_path, monkeypatch):
    assert samples(library) == []
    def forbidden(*args, **kwargs): raise AssertionError('import must not create float bundle')
    monkeypatch.setattr('lumaretouch_engine.reference_color_assets.save', forbidden)
    path = photo(tmp_path); raw = path.read_bytes()
    sample = imported(library, path)
    assert sample['reference'] is None
    assert sample['original_sha256'] == sha256(raw).hexdigest()
    retained = list((library.store.root / 'originals').iterdir())
    assert len(retained) == 1 and retained[0].read_bytes() == raw
    assert library.thumbnail(sample['id']).startswith('data:image/jpeg;base64,')
    assert path.read_bytes() == raw


def test_per_file_outcomes_and_dedup(library, tmp_path):
    path = photo(tmp_path); broken = tmp_path / 'broken.png'; broken.write_bytes(b'not a picture')
    result = library.command('import_paths', {'paths': [str(path), str(broken)], 'group_id': S.UNGROUPED}, 0)
    assert [o['status'] for o in result['outcomes']] == ['imported', 'error']
    duplicate = library.command('import_paths', {'paths': [str(path)], 'group_id': S.UNGROUPED}, 1)
    assert duplicate['outcomes'][0]['status'] == 'duplicate'
    assert len(samples(library)) == 1
    assert duplicate['revision'] == 1


def test_atomic_move_delete_group_remove_and_restore(library, tmp_path):
    item = imported(library, photo(tmp_path))
    result = library.command('group_create', {'name': '人像'}, 1)
    gid = next(g['id'] for g in library.snapshot()['groups'] if g['id'] != S.UNGROUPED)
    library.command('sample_move', {'ids': [item['id']], 'group_id': gid}, 2)
    removed = library.command('sample_remove', {'ids': [item['id']]}, 3)
    assert removed['capacity']['active'] == 0
    library.command('group_delete', {'id': gid}, 4)
    restored = library.command('sample_restore', {'ids': [item['id']]}, 5)
    assert samples(library)[0]['group_id'] == S.UNGROUPED
    assert samples(library)[0]['deleted_at'] is None
    assert len(list((library.store.root / 'originals').iterdir())) == 1
    assert library.reclaim_plan()['safe_to_delete'] is False


def test_stale_and_cancelled_mutation_leave_catalogue_unchanged(library):
    library.command('group_create', {'name': 'first'}, 0)
    before = library.store.catalog.read_bytes()
    with pytest.raises(S.LibraryError, match='更新'):
        library.command('group_create', {'name': 'stale'}, 0)
    with pytest.raises(S.LibraryError, match='取消'):
        library.command('group_create', {'name': 'cancelled'}, 1, cancelled=lambda: True)
    assert library.store.catalog.read_bytes() == before


def test_cross_instance_lock_prevents_overwrite(library):
    other = SampleLibrary(library.store.root)
    with library.store.locked():
        with pytest.raises(S.LibraryError) as error: other.snapshot()
        assert error.value.code == 'busy'


def test_corrupt_catalogue_is_not_silently_reset(library):
    library.command('group_create', {'name': 'first'}, 0)
    library.command('group_create', {'name': 'second'}, 1)
    backup = (library.store.root / 'catalog-v1.previous.json').read_bytes()
    library.store.catalog.write_bytes(b'{invalid')
    with pytest.raises(S.LibraryError) as error: library.snapshot()
    assert error.value.code == 'catalog_corrupt'
    assert library.store.catalog.read_bytes() == b'{invalid'
    assert (library.store.root / 'catalog-v1.previous.json').read_bytes() == backup


def test_overlimit_import_has_no_partial_side_effect(library, tmp_path):
    paths = [str(tmp_path / f'{i}.png') for i in range(1001)]
    with pytest.raises(S.LibraryError) as error:
        library.command('import_paths', {'paths': paths, 'group_id': S.UNGROUPED}, 0)
    assert error.value.code == 'import_limit'
    assert samples(library) == []


def test_symlink_rejected_per_file_without_following(library, tmp_path):
    target = photo(tmp_path); link = tmp_path / 'alias.png'; link.symlink_to(target)
    result = library.command('import_paths', {'paths': [str(link), str(target)], 'group_id': S.UNGROUPED}, 0)
    assert [o['status'] for o in result['outcomes']] == ['error', 'imported']
    assert target.is_file()


def test_lazy_selection_reuses_reference_and_trash_preserves_it(library, tmp_path):
    item = imported(library, photo(tmp_path))
    selected = library.select(item['id'], 1)
    reference = selected['reference']
    assert selected['revision'] == 2
    from lumaretouch_engine import reference_color_assets as A
    frame = A.load(A.cache_root(), reference)
    assert frame.authentic_mask[2:-2, 2:-2].all()
    assert not frame.authentic_mask[:2].any()
    again = library.select(item['id'], 2)
    assert again['reference'] == reference
    library.command('sample_remove', {'ids': [item['id']]}, 2)
    assert (A.cache_root() / (reference['asset_id'] + '.npz')).is_file()
    A.load(A.cache_root(), reference)


def test_missing_catalogue_with_retained_original_is_not_new_empty_library(library, tmp_path):
    imported(library, photo(tmp_path))
    library.store.catalog.unlink()
    with pytest.raises(S.LibraryError) as error: library.snapshot()
    assert error.value.code == 'catalog_corrupt'
    assert len(list((library.store.root / 'originals').iterdir())) == 1


def test_pagination_pins_query_and_revision_without_truncation(library, tmp_path):
    imported(library, photo(tmp_path, 'a.png'))
    library.command('import_paths', {'paths': [str(photo(tmp_path, 'b.png', (9, 31, 72)))], 'group_id': S.UNGROUPED}, 1)
    header = library.snapshot()
    assert 'samples' not in header and header['counts'] == {'active': 2, 'trash': 0, 'total': 2}
    query = {'view': 'all', 'search': '', 'limit': 1, 'cursor': None}
    first = library.page(query, 2)
    assert len(first['samples']) == 1 and first['total'] == 2 and first['next_cursor']
    second = library.page({**query, 'cursor': first['next_cursor']}, 2)
    assert second['samples'][0]['id'] != first['samples'][0]['id']
    assert second['next_cursor'] is None
    with pytest.raises(S.LibraryError) as error:
        library.page({**query, 'search': 'changed', 'cursor': first['next_cursor']}, 2)
    assert error.value.code == 'stale_page'
    receipt = library.command('sample_rename', {'id': second['samples'][0]['id'], 'name': 'changed'}, 2)
    assert 'snapshot' not in receipt and receipt['revision'] == 3
    with pytest.raises(S.LibraryError) as error: library.page(query, 2)
    assert error.value.code == 'stale_page'


def test_trash_and_group_counts_are_not_page_counts(library, tmp_path):
    item = imported(library, photo(tmp_path))
    library.command('sample_remove', {'ids': [item['id']]}, 1)
    head = library.snapshot()
    assert head['counts'] == {'active': 0, 'trash': 1, 'total': 1}
    assert head['group_counts'][S.UNGROUPED] == {'active': 0, 'trash': 1}
    assert head['order_ids'] == [] and samples(library) == []
    assert samples(library, 'trash')[0]['id'] == item['id']


def test_two_thousand_metadata_rows_are_all_pageable_without_large_receipts(library):
    # Metadata-only fixture, not photographic acceptance. No decoder is invoked.
    from copy import deepcopy
    base = {'name': 'fixture', 'group_id': S.UNGROUPED, 'kind': 'import',
            'original_sha256': 'a' * 64, 'bytes': 1, 'width': 64, 'height': 64,
            'format': 'PNG', 'precision': '8-bit source', 'created_at': 0,
            'deleted_at': None, 'reference': None, 'object_name': 'a' * 64 + '.png',
            'thumbnail_sha256': 'b' * 64, 'reference_supported': True,
            'reference_reason': '', 'notes': []}
    with library.store.locked(0) as catalog:
        catalog['samples'] = [{**deepcopy(base), 'id': f'{index:032x}'} for index in range(2000)]
    head = library.snapshot()
    assert head['counts']['active'] == len(head['order_ids']) == 2000
    assert 'samples' not in head
    cursor = None; seen = []
    while True:
        page = library.page({'view': 'all', 'search': '', 'limit': 48, 'cursor': cursor}, 1)
        seen.extend(row['id'] for row in page['samples'])
        assert len(page['samples']) <= 48 and page['total'] == 2000
        cursor = page['next_cursor']
        if cursor is None: break
    assert seen == head['order_ids'] and len(set(seen)) == 2000
    receipt = library.command('sample_rename', {'id': seen[-1], 'name': 'last'}, 1)
    assert receipt['affected_ids'] == [seen[-1]] and 'samples' not in receipt
    head['groups'][0]['name'] = 'caller mutation must not alias cached catalogue'
    assert library.snapshot()['groups'][0]['name'] != head['groups'][0]['name']


def test_real_disk_guard_preserves_catalogue_and_recovery_bytes(library, monkeypatch):
    library.command('group_create', {'name': 'before'}, 0)
    before = library.store.catalog.read_bytes()
    backup = (library.store.root / 'catalog-v1.previous.json').read_bytes()
    monkeypatch.setattr(library.store, 'free_bytes', lambda path=None: 0)
    with pytest.raises(S.LibraryError) as error:
        library.command('group_create', {'name': 'no disk space'}, 1)
    assert error.value.code == 'disk_full'
    assert library.store.catalog.read_bytes() == before
    assert (library.store.root / 'catalog-v1.previous.json').read_bytes() == backup


def test_storage_policy_is_configurable_and_shared_orphans_are_counted(tmp_path, monkeypatch):
    monkeypatch.setenv('LRT_SAMPLE_LIBRARY_MAX_BYTES', str(128 * 1024 * 1024))
    monkeypatch.setenv('LRT_PRESET_DIR', str(tmp_path / 'presets'))
    library = SampleLibrary(tmp_path / 'library')
    from lumaretouch_engine import reference_color_assets as A
    orphan = A.cache_root() / 'retained-unindexed.npz'; orphan.write_bytes(b'retained orphan fixture')
    storage = library.snapshot()['storage']
    assert storage['budget_bytes'] == 128 * 1024 * 1024
    assert storage['shared_reference_bytes'] == orphan.stat().st_size
    assert storage['bytes'] == storage['library_bytes'] + storage['shared_reference_bytes']
    assert library.reclaim_plan()['reference_cache_excluded'] is True and orphan.is_file()


def test_host_cancel_can_overtake_dispatcher_queue(monkeypatch):
    from lumaretouch_engine import sample_library_host as H
    host = H.SampleLibraryHost(); seen = []
    assert host.observe_line(json.dumps({'cmd': 'sample_library_cancel', 'request_id': 'queued-capture'}))
    command = {'cmd': 'sample_library', 'request_id': 'queued-capture', 'action': 'request',
               'request': {'method': 'snapshot'}}
    assert not host.observe_line(json.dumps(command))
    monkeypatch.setattr(H, 'dispatch', lambda *args, **kwargs: pytest.fail('Cancelled request executed'))
    host.handle(object(), command, seen.append)
    assert seen[-1]['success'] is False
    assert seen[-1]['error_code'] == 'cancelled'
    assert seen[-1]['outcome_unknown'] is False and seen[-1]['committed'] is False


def test_host_duplicate_receipt_never_redispatches(monkeypatch):
    from lumaretouch_engine import sample_library_host as H
    host = H.SampleLibraryHost(); seen = []; calls = []
    monkeypatch.setattr(H, 'dispatch', lambda *args, **kwargs: calls.append('dispatch') or {'revision': 0})
    command = {'cmd': 'sample_library', 'request_id': 'once', 'action': 'request', 'request': {'method': 'snapshot'}}
    host.handle(object(), command, seen.append); host.handle(object(), command, seen.append)
    assert calls == ['dispatch'] and seen[0] == seen[1]
    host.handle(object(), {**command, 'request': {'method': 'context'}}, seen.append)
    assert calls == ['dispatch'] and seen[-1]['error_code'] == 'request_conflict'


def test_host_control_overflow_does_not_forget_cancellation():
    from lumaretouch_engine import sample_library_host as H
    host = H.SampleLibraryHost()
    for number in range(H.MAX_RECORDS + 1): host.cancel('cancel-' + str(number))
    assert host.control_overflow
    assert host.register('late-request').is_set()


def test_context_separates_viewport_load_id_from_canonical_document():
    from types import SimpleNamespace
    from lumaretouch_engine.sample_library_capture import context
    canonical = SimpleNamespace(document_id='canonical', revision=7)
    engine = SimpleNamespace(_image_loaded=True, _doc_index=0, _docs=[{'path': '/owned/photo.jpg'}],
                             _load_id='viewport-load', _guard_editable=lambda _: None,
                             _document_versions=lambda: SimpleNamespace(version=lambda _: canonical))
    result = context(engine)
    assert result['document_id'] == 'canonical' and result['load_id'] == 'viewport-load'
    assert result['revision'] == '7' and result['available']


def test_host_oversize_result_is_small_unknown_receipt(monkeypatch):
    from lumaretouch_engine import sample_library_host as H
    host = H.SampleLibraryHost(); seen = []
    monkeypatch.setattr(H, 'MAX_RESULT_BYTES', 1024)
    monkeypatch.setattr(H, 'dispatch', lambda *args, **kwargs: {'too_large': 'x' * 4096})
    command = {'cmd': 'sample_library', 'request_id': 'oversize', 'action': 'request', 'request': {'method': 'snapshot'}}
    host.handle(object(), command, seen.append)
    assert seen[-1]['error_code'] == 'receipt_capacity' and seen[-1]['outcome_unknown']
    assert 'result' not in seen[-1] and len(H.encoded(seen[-1])) < 1024
