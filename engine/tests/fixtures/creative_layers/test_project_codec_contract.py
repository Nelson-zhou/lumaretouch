"""AUTHORED / UNRUN: Qoder owns local execution and acceptance.

These fixtures cover the canonical codec and its existing recovery/package
boundaries. They do not claim renderer, host UI or end-to-end acceptance.
"""
import base64
import hashlib
import json
import os
import struct
from contextlib import nullcontext
from copy import deepcopy

import pytest
from lumaretouch_engine import project as P
from lumaretouch_engine import creative_document_state as S
from lumaretouch_engine.creative_document_assets import AssetStore, make_asset
from lumaretouch_engine.creative_document_project import (
    KEY, ASSETS_KEY, BASE_KEY, capture_into, restore_from,
    validate_records, validate_history_frames,
)


def make_frame(*, returned_base=False):
    store = AssetStore()
    source = make_asset('rgba', 1, 1, struct.pack('<ffff', .25, .1, .05, .5),
                        original=b'original source bytes', icc=b'original ICC bytes')
    identity = store.intern(source)
    document = S.create('stable-source-uid', identity, store)
    base = make_asset('rgba', 1, 1, struct.pack('<ffff', .4, .2, .1, .5)) if returned_base else None
    return capture_into({}, document, store, base=base), store


def encoded_frame():
    frame, _ = make_frame(returned_base=True)
    assets, dropped = {}, []
    encoded = P.encode(frame, assets, dropped, 'fixture')
    assert dropped == []
    return frame, encoded, assets


def project_fixture(tmp_path):
    from lumaretouch_engine import white_balance_recipe as WB
    from lumaretouch_engine import manual_liquify_state as ML
    from lumaretouch_engine import studio_background_state as SB
    from lumaretouch_engine import optics_state as OP
    from lumaretouch_engine import sky_replacement_state as SKY
    source = tmp_path / 'source.bin'
    source.write_bytes(b'fixture original source, never modified')
    frame, _ = make_frame(returned_base=True)
    frame.update(_wb_options=WB.default_options(), _manual_liquify=ML.empty(),
                 _studio_background=SB.empty(), _optics=OP.empty(),
                 _sky_replacement=SKY.empty())
    project = P.new_project('Creative persistence fixture')
    row = P.add_doc(project, str(source), frame, version_id='live')
    row['document_history'] = P.encode({'undo': [deepcopy(frame)], 'redo': [deepcopy(frame)]},
        project['assets'], [], 'fixture.history')
    return project, row, frame, source


def test_legacy_absence_and_explicit_neutral_defaults():
    for frame in ({}, {KEY: None, ASSETS_KEY: {}, BASE_KEY: None}, {ASSETS_KEY: {}}):
        document, store = restore_from(frame)
        assert document is None and store.records([]) == {}
        assert P.decode(P.encode(frame, {}, [], 'neutral'), {}, [], 'neutral') == frame


def test_null_document_cannot_hide_orphan_records():
    frame, _ = make_frame()
    frame[KEY] = None
    with pytest.raises(ValueError, match='Orphan'):
        restore_from(frame)


@pytest.mark.parametrize('schema', [2, 999, '1', True, 1.0])
def test_unknown_or_coerced_document_schema_is_rejected(schema):
    frame, _ = make_frame()
    frame[KEY]['schema'] = schema
    assets, dropped = {}, []
    with pytest.raises(P.ProjectError):
        P.encode(frame, assets, dropped, 'unknown-schema')
    assert assets == {} and dropped == []


def test_base_is_standalone_and_retained_without_layer_document():
    frame, _ = make_frame(returned_base=True)
    base = frame[BASE_KEY]
    only_base = {BASE_KEY: base, KEY: None, ASSETS_KEY: {}}
    document, store = restore_from(only_base)
    assert document is None and store.get(base['id'], 'rgba') == base
    captured = capture_into(only_base, None, store)
    assert captured[BASE_KEY] == base and captured[BASE_KEY] is not base
    merged = validate_history_frames([{}, only_base])
    assert merged.get(base['id']) == base


def test_base_cannot_be_a_mask_or_a_path_or_an_asset_locator():
    mask = make_asset('mask', 1, 1, struct.pack('<f', .5))
    for base in (mask, '/tmp/layer.png', {'__asset__': mask['id']}):
        with pytest.raises(ValueError):
            restore_from({BASE_KEY: base})


def test_canonical_roundtrip_retains_bytes_and_never_drops():
    original, encoded, assets = encoded_frame()
    content = encoded[ASSETS_KEY][original[KEY]['source_asset']]['content']
    assert set(content) == {'__creative_bytes__', 'bytes', 'sha256', 'chunks'}
    assert assets[content['chunks'][0]]['kind'] == 'bytes'
    before = deepcopy(encoded)
    validate_records(encoded, assets=assets)
    dropped = []
    restored = P.decode(encoded, assets, dropped, 'fixture')
    assert restored == original and dropped == [] and encoded == before
    assert type(restored[BASE_KEY]['content']) is bytes


def test_separate_recipe_history_decodes_share_identical_immutable_pixels():
    original, encoded, assets = encoded_frame()
    source_id = original[KEY]['source_asset']
    recipe = P.decode(encoded, assets, [], 'recipe')
    history = P.decode({'undo': [encoded, deepcopy(encoded)], 'redo': [encoded]},
                       assets, [], 'history')
    raw = recipe[ASSETS_KEY][source_id]['content']
    for frame in history['undo'] + history['redo']:
        assert frame[ASSETS_KEY][source_id]['content'] is raw
        assert frame[BASE_KEY]['content'] is recipe[BASE_KEY]['content']
    # A hit must not treat the cache as permission to ignore a corrupt new bank.
    corrupt = deepcopy(assets)
    key = encoded[ASSETS_KEY][source_id]['content']['chunks'][0]
    corrupt[key]['b64'] = base64.b64encode(bytes(corrupt[key]['bytes'])).decode()
    with pytest.raises(P.ProjectError):
        P.decode(encoded, corrupt, [], 'corrupt-later-project')


@pytest.mark.parametrize('damage', ['missing', 'hash', 'length', 'kind', 'dtype',
                                   'shape', 'base64', 'extra', 'boolean-length'])
def test_corrupt_canonical_bytes_reject_before_generic_drop(damage):
    original, encoded, assets = encoded_frame()
    identity = encoded[ASSETS_KEY][original[KEY]['source_asset']]['content']['chunks'][0]
    row = assets[identity]
    if damage == 'missing': del assets[identity]
    elif damage == 'hash': row['b64'] = base64.b64encode(bytes(row['bytes'])).decode()
    elif damage == 'length': row['bytes'] += 1
    elif damage == 'kind': row['kind'] = 'raw'
    elif damage == 'dtype': row['dtype'] = 'uint8'
    elif damage == 'shape': row['shape'] = [row['bytes']]
    elif damage == 'base64': row['b64'] = '!' * len(row['b64'])
    elif damage == 'extra': row['unexpected'] = 'not ignored'
    elif damage == 'boolean-length': row['bytes'] = True
    dropped = []
    with pytest.raises(P.ProjectError):
        P.decode(encoded, assets, dropped, 'fixture')
    assert dropped == []


@pytest.mark.parametrize('field', ['content', 'original', 'icc'])
def test_all_original_and_profile_blobs_are_required(field):
    original, encoded, assets = encoded_frame()
    reference = encoded[ASSETS_KEY][original[KEY]['source_asset']][field]
    del assets[reference['chunks'][0]]
    with pytest.raises(ValueError):
        validate_records(encoded, assets=assets)


def test_reference_metadata_and_record_digest_are_strict():
    original, encoded, assets = encoded_frame()
    source = encoded[ASSETS_KEY][original[KEY]['source_asset']]
    for key, value in [('at', 1), ('path', '/untrusted/fallback')]:
        broken = deepcopy(encoded)
        broken[ASSETS_KEY][original[KEY]['source_asset']]['content'][key] = value
        with pytest.raises(P.ProjectError):
            P.decode(broken, assets, [], 'fixture')
    source['source_hash'] = 'sha256:' + '0' * 64
    with pytest.raises(P.ProjectError):
        P.decode(encoded, assets, [], 'fixture')


def test_frame_cannot_borrow_missing_assets_from_another_frame():
    frame, _ = make_frame()
    missing = deepcopy(frame)
    missing[ASSETS_KEY] = {}
    with pytest.raises(ValueError):
        validate_history_frames([frame, missing])


def test_unreferenced_asset_and_bytearray_fail_instead_of_being_dropped():
    frame, _ = make_frame(returned_base=True)
    frame[ASSETS_KEY][frame[BASE_KEY]['id']] = frame[BASE_KEY]
    with pytest.raises(ValueError):
        restore_from(frame)
    frame, _ = make_frame()
    frame[ASSETS_KEY][frame[KEY]['source_asset']]['content'] = bytearray(16)
    with pytest.raises(P.ProjectError):
        P.encode(frame, {}, [], 'mutable-bytes')


def test_generic_codec_marker_cannot_discard_a_creative_frame():
    _, encoded, assets = encoded_frame()
    encoded['__asset__'] = next(iter(assets))
    with pytest.raises(P.ProjectError):
        P.decode(encoded, assets, [], 'disguised-frame')


def test_creative_chunk_markers_cannot_escape_owned_record_budget():
    original, encoded, assets = encoded_frame()
    marker = encoded[ASSETS_KEY][original[KEY]['source_asset']]['content']
    with pytest.raises(P.ProjectError, match='validated creative record'):
        P.decode({'unowned': marker}, assets, [], 'unowned-chunk-graph')


def test_encode_canonical_kind_collision_is_atomic():
    frame, _ = make_frame()
    raw = frame[ASSETS_KEY][frame[KEY]['source_asset']]['content']
    identity = 'sha256:' + hashlib.sha256(raw).hexdigest()
    assets = {identity: {'kind': 'raw', 'shape': [len(raw)], 'dtype': 'uint8',
                        'bytes': len(raw), 'b64': base64.b64encode(raw).decode()}}
    before = deepcopy(assets)
    with pytest.raises(P.ProjectError):
        P.encode(frame, assets, [], 'kind-collision')
    assert assets == before


def test_history_keeps_deleted_layer_assets_and_one_global_budget():
    frame, store = make_frame()
    extra = make_asset('rgba', 1, 1, struct.pack('<ffff', .1, .2, .3, 1.0))
    identity = store.intern(extra)
    with_layer = S.apply(frame[KEY], {'action': 'add_image', 'asset_id': identity}, store)
    deleted = S.apply(with_layer, {'action': 'delete'}, store)
    history = {'state': capture_into({}, deleted, store),
               'undo': [capture_into({}, with_layer, store)], 'redo': [frame]}
    assert identity not in history['state'][ASSETS_KEY]
    assets, dropped = {}, []
    encoded = P.encode(history, assets, dropped, 'all-history')
    restored = P.decode(encoded, assets, dropped, 'all-history')
    assert restored == history and dropped == []
    merged = validate_records(restored)
    assert merged.get(identity) == extra
    source = frame[ASSETS_KEY][frame[KEY]['source_asset']]
    budget = sum(len(source[key]) for key in ('content', 'original', 'icc'))
    validate_history_frames([frame, deepcopy(frame)], max_bytes=budget)
    with pytest.raises(ValueError, match='budget'):
        validate_records(history, max_bytes=budget)


def test_v23_save_load_and_inactive_history_roundtrip(tmp_path):
    project, row, frame, source = project_fixture(tmp_path)
    before_source = source.read_bytes()
    target = tmp_path / 'creative.lrproject.json'
    P.save(project, str(target))
    restored = P.load(str(target))
    recipe, dropped = P.active_recipe(restored, document_id=row['document_id'])
    history = P.decode(restored['docs'][0]['document_history'], restored['assets'], [], 'history')
    assert recipe == frame and history == {'undo': [frame], 'redo': [frame]}
    assert dropped == [] and source.read_bytes() == before_source
    assert restored['schema_version'] == P.SCHEMA == 'lrt.project.v23'


@pytest.mark.parametrize('location', ['inactive-version', 'undo', 'redo', 'base'])
def test_project_validation_checks_every_saved_location(tmp_path, location):
    project, row, _, _ = project_fixture(tmp_path)
    if location == 'inactive-version':
        old = deepcopy(row['versions'][0])
        old['id'] = 'inactive'
        old['recipe'][KEY]['schema'] = 99
        row['versions'].append(old)
    elif location == 'base':
        row['versions'][0]['recipe'][BASE_KEY]['kind'] = 'mask'
    else:
        row['document_history'][location][0][KEY]['schema'] = 99
    with pytest.raises(P.ProjectError):
        P.validate(project)


def test_project_downgrade_rejected_but_old_absence_migrates(tmp_path):
    project, _, _, _ = project_fixture(tmp_path)
    project['schema_version'] = P.COLOUR_EDITOR_SCHEMA
    with pytest.raises(P.ProjectError, match='downgrade'):
        P.validate(project)
    old = P.new_project('Old neutral project')
    old['schema_version'] = P.COLOUR_EDITOR_SCHEMA
    target = tmp_path / 'old.lrproject.json'
    target.write_text(json.dumps(old))
    assert P.load(str(target))['schema_version'] == P.SCHEMA


def test_recovery_candidate_reuses_full_assets_and_rejects_bad_history(tmp_path):
    from lumaretouch_engine.project_recovery_store import RecoveryStore
    project, row, _, _ = project_fixture(tmp_path)
    store = RecoveryStore(str(tmp_path / 'recovery'), reserve_bytes=0)
    receipt = store.publish(json.dumps(project).encode(),
        {'revision': 1, 'native_receipts': [], 'transaction_open': False}, nullcontext)
    assert store.list_candidates(project['project_id'])[0]['candidate_id'] == receipt['candidate_id']
    row['document_history']['redo'][0][KEY]['schema'] = 99
    with pytest.raises(ValueError):
        store.publish(json.dumps(project).encode(),
            {'revision': 2, 'native_receipts': [], 'transaction_open': False}, nullcontext)
    assert len(store.list_candidates(project['project_id'])) == 1


def test_portable_package_keeps_creative_history_without_external_layer_files(tmp_path):
    from lumaretouch_engine.project_package_archive import create_archive, inspect_archive
    from lumaretouch_engine.project_package_dependencies import inventory
    project, _, _, _ = project_fixture(tmp_path)
    dependencies = inventory(project, include_originals=False, include_references=False)
    assert len(dependencies) == 1 and dependencies[0]['type'] == 'original'
    archive = tmp_path / 'creative.lrtpackage'
    create_archive(project, dependencies, str(archive))
    restored = inspect_archive(str(archive))['project']
    P.validate(restored)
    assert restored['assets'] == project['assets']
    assert restored['docs'][0]['document_history'] == project['docs'][0]['document_history']


def test_save_manifest_is_bounded_and_sidecar_tamper_blocks_open(tmp_path):
    from lumaretouch_engine import creative_document_storage as CS
    project, _, _, _ = project_fixture(tmp_path)
    path = tmp_path / 'sidecar.lrproject.json'
    info = P.save(project, str(path))
    disk = json.loads(path.read_bytes())
    inventory = CS.blob_inventory(disk)
    assert inventory and info['blob_count'] == len(inventory)
    assert all('b64' not in disk['assets'][key] for key in inventory)
    key = next(iter(inventory))
    (CS.sidecar_path(path) / key[7:]).write_bytes(b'corrupt')
    with pytest.raises(P.ProjectError, match='sidecar'):
        P.load(str(path))


def test_failed_manifest_commit_preserves_old_save_and_all_history(tmp_path, monkeypatch):
    from lumaretouch_engine import creative_document_storage as CS
    project, _, _, _ = project_fixture(tmp_path)
    path = tmp_path / 'atomic.lrproject.json'
    P.save(project, str(path))
    before = path.read_bytes()
    original_replace = P.os.replace
    def interrupted(source, target):
        if str(target) == str(path):
            raise OSError('injected manifest commit failure')
        return original_replace(source, target)
    monkeypatch.setattr(P.os, 'replace', interrupted)
    with pytest.raises(OSError, match='injected'):
        P.save(project, str(path))
    assert path.read_bytes() == before
    restored = P.load(str(path))
    assert restored['assets'] == project['assets']
    assert CS.read_blobs(json.loads(before), path)


def test_autosave_freeze_owns_manifest_and_blobs_outside_json_budget(tmp_path):
    from lumaretouch_engine import creative_document_storage as CS
    from lumaretouch_engine.project_recovery_store import RecoveryStore
    project, _, _, _ = project_fixture(tmp_path)
    frozen = CS.freeze(project, 64_000_000)
    assert b'"blob":' in frozen.manifest and b'"b64":' not in frozen.manifest
    assert CS.thaw(frozen) == project
    store = RecoveryStore(str(tmp_path / 'sidecar-recovery'), reserve_bytes=0)
    receipt = store.publish(frozen, {'revision': 1, 'native_receipts': []}, nullcontext)
    assert receipt['creative_blob_bytes'] > 0 and receipt['creative_blob_count'] > 0
    candidate = store.root / 'candidates' / receipt['candidate_id'] / ('project' + P.SUFFIX)
    loaded = P.load(str(candidate))
    assert loaded['assets'] == project['assets']


@pytest.mark.skipif(os.environ.get('LRT_RUN_LARGE_CREATIVE_FIXTURES') != '1',
                    reason='Opt-in 24 MP source+base recovery qualification; AUTHORED / UNRUN')
def test_24mp_source_and_returned_base_fit_fresh_recovery_budget(tmp_path):
    from lumaretouch_engine import creative_document_storage as CS
    from lumaretouch_engine.project_recovery_store import RecoveryStore
    _, _, frame, path = project_fixture(tmp_path)
    def pixels(seed):
        return b''.join(struct.pack('<ffff', seed + index * .001, -.02, 1.2, 1.0)
                       * (min(CS.CHUNK_BYTES, 384_000_000 - start) // 16)
                       for index, start in enumerate(range(0, 384_000_000, CS.CHUNK_BYTES)))
    original = b''.join(bytes([index + 1]) * min(CS.CHUNK_BYTES, 25_000_000 - start)
                        for index, start in enumerate(range(0, 25_000_000, CS.CHUNK_BYTES)))
    assets = AssetStore()
    source = make_asset('rgba', 6000, 4000, pixels(.1), original=original)
    base = make_asset('rgba', 6000, 4000, pixels(.6))
    source_id = assets.intern(source)
    document = S.create('24mp-synthetic-source', source_id, assets)
    frame = capture_into(frame, document, assets, base=base)
    project = P.new_project('24 MP source and returned base')
    P.add_doc(project, str(path), frame, version_id='large')
    frozen = CS.freeze(project, 64_000_000)
    assert sum(len(raw) for _, raw in frozen.blobs) == 793_000_000
    store = RecoveryStore(str(tmp_path / 'large-recovery'), reserve_bytes=0)
    assert store.budget_bytes == 1_024_000_000
    receipt = store.publish(frozen, {'revision': 1, 'native_receipts': []}, nullcontext)
    assert receipt['creative_blob_bytes'] == 793_000_000
    assert store.usage()['bytes'] < store.budget_bytes
