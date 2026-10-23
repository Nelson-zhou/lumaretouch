"""AUTHORED / UNRUN. Qoder owns execution and disk-fault acceptance.

These small fixtures check the raw-blob package contract, not production memory,
timing, full-size image acceptance, renderer correctness or UI acceptance.
"""
import copy
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import zipfile

import pytest

from lumaretouch_engine import creative_document_state as S
from lumaretouch_engine import creative_document_storage as B
from lumaretouch_engine import project as P
from lumaretouch_engine import project_package_archive as A
from lumaretouch_engine import project_package_dependencies as D
from lumaretouch_engine.creative_document_assets import AssetStore, make_asset
from lumaretouch_engine.creative_document_project import capture_into


SOURCE = b'exact original encoded source bytes, retained independently of paths'
ICC = b'exact original ICC profile fixture bytes'


def project_fixture(tmp_path):
    from lumaretouch_engine import manual_liquify_state as ML
    from lumaretouch_engine import optics_state as OP
    from lumaretouch_engine import sky_replacement_state as SKY
    from lumaretouch_engine import studio_background_state as SB
    from lumaretouch_engine import white_balance_recipe as WB

    source = tmp_path / 'source.bin'
    source.write_bytes(SOURCE)
    store = AssetStore()
    asset = make_asset('rgba', 1, 1, struct.pack('<ffff', .25, .125, -.0625, .5),
                       original=SOURCE, icc=ICC)
    document = S.create('stable-source-uid', store.intern(asset), store)
    frame = capture_into({}, document, store)
    frame.update(_wb_options=WB.default_options(), _manual_liquify=ML.empty(),
                 _studio_background=SB.empty(), _optics=OP.empty(),
                 _sky_replacement=SKY.empty())
    project = P.new_project('Creative portable raw blob fixture')
    row = P.add_doc(project, str(source), frame, version_id='live')
    row['document_history'] = P.encode(
        {'undo': [copy.deepcopy(frame)], 'redo': [copy.deepcopy(frame)]},
        project['assets'], [], 'fixture.history')
    return project, source


def make_package(tmp_path, *, include_originals=False):
    project, source = project_fixture(tmp_path)
    dependencies = D.inventory(project, include_originals, False)
    archive = tmp_path / 'creative.lrtpack'
    A.create_archive(project, dependencies, archive, operation_id='create-fixture')
    return project, source, archive


def rewrite_package(source, target, mutate):
    with zipfile.ZipFile(source, 'r') as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(entries['manifest.json'])
    mutate(manifest, entries)
    entries['manifest.json'] = json.dumps(manifest).encode()
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, raw in entries.items():
            archive.writestr(name, raw)


def test_creative_blobs_are_mandatory_when_both_optional_flags_are_false(tmp_path):
    project, source, archive = make_package(tmp_path)
    inspected = A.inspect_archive(archive, dependency_validator=D.validate_inventory)
    P.validate(inspected['project'])
    manifest = inspected['manifest']
    assert all(row['status'] == 'excluded' for row in manifest['dependencies'])
    mandatory = manifest['mandatory_blobs']
    assert mandatory and all(row['size'] <= B.CHUNK_BYTES for row in mandatory)
    assert len({row['sha256'] for row in mandatory}) == len(mandatory)
    assert inspected['project']['assets'] == project['assets']
    assert inspected['project']['docs'][0]['document_history'] == project['docs'][0]['document_history']
    source_key = B.identity(SOURCE)
    icc_key = B.identity(ICC)
    assert inspected['creative_blobs'][source_key] == SOURCE
    assert inspected['creative_blobs'][icc_key] == ICC
    for key in inspected['creative_blobs']:
        stored_row = inspected['stored_project']['assets'][key]
        assert set(stored_row) == {'kind', 'shape', 'dtype', 'bytes', 'blob'}
        assert stored_row['blob'] == key
    with zipfile.ZipFile(archive) as saved:
        assert saved.read('blobs/' + source_key[7:]) == SOURCE
        assert len(saved.read('project.json')) < A.MAX_PROJECT
        saved_assets = json.loads(saved.read('project.json'))['assets']
        assert all('b64' not in saved_assets[key] for key in inspected['creative_blobs'])
    assert source.read_bytes() == SOURCE


@pytest.mark.parametrize('damage', ['missing-inventory', 'missing-inventory-key', 'extra-inventory',
                                  'duplicate-inventory', 'missing-payload', 'extra-payload',
                                  'wrong-size', 'wrong-bytes'])
def test_package_rejects_incomplete_or_extra_mandatory_inventory(tmp_path, damage):
    _, _, source = make_package(tmp_path)
    target = tmp_path / ('damaged-' + damage + '.lrtpack')

    def mutate(manifest, entries):
        first = manifest['mandatory_blobs'][0]
        extra = b'unlisted raw bytes'
        sha = hashlib.sha256(extra).hexdigest()
        if damage == 'missing-inventory':
            manifest['mandatory_blobs'].pop()
        elif damage == 'missing-inventory-key':
            manifest.pop('mandatory_blobs')
        elif damage == 'extra-inventory':
            manifest['mandatory_blobs'].append({'sha256': sha, 'size': len(extra),
                                                'archive_path': 'blobs/' + sha})
            entries['blobs/' + sha] = extra
        elif damage == 'duplicate-inventory':
            manifest['mandatory_blobs'].append(dict(first))
        elif damage == 'missing-payload':
            entries.pop(first['archive_path'])
        elif damage == 'extra-payload':
            entries['blobs/' + sha] = extra
        elif damage == 'wrong-size':
            first['size'] += 1
        else:
            raw = entries[first['archive_path']]
            entries[first['archive_path']] = bytes([raw[0] ^ 1]) + raw[1:]

    rewrite_package(source, target, mutate)
    with pytest.raises(A.PackageError):
        A.inspect_archive(target, dependency_validator=D.validate_inventory)


def test_restore_reopens_external_project_and_readback_checks_same_history(tmp_path):
    project, source, archive = make_package(tmp_path)
    result = A.restore_archive(archive, tmp_path / 'restored',
                               dependency_validator=D.validate_inventory,
                               project_validator=P.validate, operation_id='restore-fixture')
    path = Path(result['project_path'])
    stored = json.loads(path.read_text())
    assert B.blob_inventory(stored)
    reopened = P.load(str(path))
    assert reopened['assets'] == project['assets']
    assert reopened['docs'][0]['document_history'] == project['docs'][0]['document_history']
    assert not Path(reopened['docs'][0]['path']).exists()
    readback = A.readback_restore(result['destination'], dependency_validator=D.validate_inventory,
                                  project_validator=P.validate)
    assert readback['operation_id'] == 'restore-fixture'
    assert readback['manifest_sha256'] == result['manifest_sha256']
    assert source.read_bytes() == SOURCE


@pytest.mark.parametrize('damage', ['corrupt', 'missing', 'extra', 'symlink'])
def test_restore_readback_rejects_damaged_or_extra_sidecar(tmp_path, damage):
    _, _, archive = make_package(tmp_path)
    result = A.restore_archive(archive, tmp_path / 'restored',
                               dependency_validator=D.validate_inventory, project_validator=P.validate)
    project_path = Path(result['project_path'])
    sidecar = B.sidecar_path(project_path)
    blob = next(iter(sidecar.iterdir()))
    if damage == 'corrupt':
        raw = blob.read_bytes()
        blob.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    elif damage == 'missing':
        blob.unlink()
    elif damage == 'extra':
        extra = b'unlisted sidecar generation'
        (sidecar / hashlib.sha256(extra).hexdigest()).write_bytes(extra)
    else:
        outside = tmp_path / 'outside.bin'
        outside.write_bytes(blob.read_bytes())
        blob.unlink()
        blob.symlink_to(outside)
    with pytest.raises((A.PackageError, OSError)):
        A.readback_restore(result['destination'], dependency_validator=D.validate_inventory,
                           project_validator=P.validate)


def test_identical_optional_source_and_mandatory_chunk_share_one_archive_entry(tmp_path):
    _, source, archive = make_package(tmp_path, include_originals=True)
    inspected = A.inspect_archive(archive, dependency_validator=D.validate_inventory)
    manifest = inspected['manifest']
    original = next(row for row in manifest['dependencies'] if row['type'] == 'original')
    sha = hashlib.sha256(SOURCE).hexdigest()
    assert original['status'] == 'bundled' and original['sha256'] == sha
    assert any(row['sha256'] == sha for row in manifest['mandatory_blobs'])
    with zipfile.ZipFile(archive) as saved:
        assert saved.namelist().count('blobs/' + sha) == 1
        assert len(saved.namelist()) == 2 + len(manifest['mandatory_blobs'])
    result = A.restore_archive(archive, tmp_path / 'restored',
                               dependency_validator=D.validate_inventory, project_validator=P.validate)
    reopened = P.load(result['project_path'])
    assert Path(reopened['docs'][0]['path']).read_bytes() == source.read_bytes() == SOURCE
    A.readback_restore(result['destination'], dependency_validator=D.validate_inventory,
                       project_validator=P.validate)


@pytest.mark.parametrize('include_originals', [False, True])
def test_create_reserve_failure_never_publishes_or_changes_source(tmp_path, monkeypatch, include_originals):
    project, source = project_fixture(tmp_path)
    dependencies = D.inventory(project, include_originals, False)
    monkeypatch.setattr(A.shutil, 'disk_usage', lambda _: SimpleNamespace(free=A.RESERVE_BYTES))
    target = tmp_path / 'no-space.lrtpack'
    with pytest.raises(A.PackageError, match='reserve'):
        A.create_archive(project, dependencies, target)
    assert not target.exists() and source.read_bytes() == SOURCE
    assert not list(tmp_path.glob('.lrt-package-*'))


def test_archive_emission_reserves_new_bytes_while_source_staging_still_exists(tmp_path, monkeypatch):
    project, source = project_fixture(tmp_path)
    dependencies = D.inventory(project, True, False)
    observed_staging = []

    def remaining_space(path):
        staged = sum(item.stat().st_size for item in Path(path).glob('source-*'))
        observed_staging.append(staged)
        return SimpleNamespace(free=A.RESERVE_BYTES + len(SOURCE) - staged)

    monkeypatch.setattr(A.shutil, 'disk_usage', remaining_space)
    target = tmp_path / 'no-archive-space.lrtpack'
    with pytest.raises(A.PackageError, match='reserve'):
        A.create_archive(project, dependencies, target)
    assert len(SOURCE) in observed_staging
    assert not target.exists() and source.read_bytes() == SOURCE
    assert not list(tmp_path.glob('.lrt-package-*'))


def test_restore_admits_sidecar_and_manifests_before_any_extraction(tmp_path, monkeypatch):
    _, source, archive = make_package(tmp_path)
    with zipfile.ZipFile(archive) as saved:
        archive_payload = sum(entry.file_size for entry in saved.infolist())
    # Enough for extracted entries alone is not enough for the reopened project.
    monkeypatch.setattr(A.shutil, 'disk_usage',
                        lambda _: SimpleNamespace(free=A.RESERVE_BYTES + archive_payload))
    original_read = A._read_member
    extracted = []

    def observed_read(z, entry, cancel=None, progress=None, sink=None, keep=False):
        if sink is not None:
            extracted.append(entry.filename)
        return original_read(z, entry, cancel, progress, sink, keep)

    monkeypatch.setattr(A, '_read_member', observed_read)
    target = tmp_path / 'no-space-restore'
    with pytest.raises(A.PackageError, match='reserve'):
        A.restore_archive(archive, target, dependency_validator=D.validate_inventory,
                          project_validator=P.validate)
    assert extracted == [] and not target.exists()
    assert source.read_bytes() == SOURCE


def test_legacy_archive_without_mandatory_inventory_remains_accepted(tmp_path):
    project = {'assets': {}, 'docs': []}
    source, target = tmp_path / 'empty.lrtpack', tmp_path / 'legacy.lrtpack'
    A.create_archive(project, [], source)
    rewrite_package(source, target, lambda manifest, _: manifest.pop('mandatory_blobs'))
    inspected = A.inspect_archive(target)
    assert inspected['project'] == inspected['stored_project'] == project
    assert inspected['creative_blobs'] == {}
