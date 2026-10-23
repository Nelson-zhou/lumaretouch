"""AUTHORED / UNRUN: isolated offline migration and installation-proof fixtures.

The main flow uses a tiny explicitly synthetic inventory, not downloaded weights
or real runtime wheels. The offline-policy call is mocked to avoid constraining
the pytest process. Full real inventory, real seccomp, installation duration,
platform/filesystem durability, inference and UI acceptance remain unverified.
No fixture imports or executes a model, installs a package, or opens the network.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
from types import SimpleNamespace
import zipfile

import pytest

from lumaretouch_engine import privacy
from lumaretouch_engine.sky_semantic import install as A
from lumaretouch_engine.sky_semantic import manifest as M
from lumaretouch_engine.sky_semantic import migration as G


pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux-only optional-model contract')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tree_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob('*') if path.is_file()}


@pytest.fixture
def prepared(monkeypatch, tmp_path):
    """Real verifier/copy/publish with a small independently expected inventory."""
    current = {**G.LEGACY_IDENTITY, 'adapter_sha256': 'c' * 64}
    parent = tmp_path / 'models'
    source, target = parent / G.LEGACY_NAMESPACE, parent / M.namespace(current)
    source.mkdir(parents=True)
    payloads = {
        'model/model.bin': b'fixture weights, never loaded',
        'wheels/fixture.whl': b'fixture archive stand-in, not executable',
        'runtime/support.py': b'# fixture support, never imported\n',
        'runtime/package.py': b'# fixture runtime, never imported\n',
    }
    expected = {name: {'size': len(raw), 'sha256': digest(raw)} for name, raw in payloads.items()}
    for name, raw in payloads.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    record = {'identity': dict(G.LEGACY_IDENTITY), 'files': deepcopy(expected),
              'fork': G.LEGACY_IDENTITY['fork_version'], 'licenses': []}
    (source / 'receipt.json').write_text(json.dumps(record, sort_keys=True))
    original = tree_bytes(source)
    code = tmp_path / 'fixture-code'
    code.mkdir()
    (code / 'fork-patches.json').write_text(json.dumps({
        'patches': [], 'support': {'path': 'support.py',
                                  'sha256': expected['runtime/support.py']['sha256']}}))
    events, offline = [], []
    monkeypatch.setattr(M, 'HERE', code)
    monkeypatch.setattr(M, 'identity', lambda: deepcopy(current))
    monkeypatch.setattr(M, 'directory', lambda: target)
    monkeypatch.setattr(M, 'lock', lambda: {
        'files': [{'filename': 'model.bin', **expected['model/model.bin']}]})
    monkeypatch.setattr(M, 'disclosure', lambda: {'runtime': []})
    monkeypatch.setattr(A, 'expected_files', lambda root, *, cancelled=lambda: False: deepcopy(expected))
    monkeypatch.setattr(A, 'plan', lambda: {'identity': deepcopy(current), 'installed': False,
                                           'download_bytes': 0})
    monkeypatch.setattr(A, 'emit', lambda **value: events.append(deepcopy(value)))
    monkeypatch.setattr(privacy, 'install_offline_policy', lambda: offline.append(True))
    monkeypatch.setattr(G.shutil, 'disk_usage', lambda path: SimpleNamespace(free=16 * 1024**3))
    def no_network(*args, **kwargs):
        raise AssertionError('Offline migration must not enter a download path')
    monkeypatch.setattr(A, 'download', no_network)
    return SimpleNamespace(source=source, target=target, parent=parent, current=current,
                           expected=expected, original=original, record=record,
                           events=events, offline=offline)


def test_legacy_namespace_is_frozen_identity_not_current_adapter():
    assert M.namespace(G.LEGACY_IDENTITY) == G.LEGACY_NAMESPACE
    assert G.LEGACY_IDENTITY['adapter_sha256'] == (
        'f02bc1811ddb9787c80cb967fd1e10a334c96e4725a8a020bc9f8da273adf379')
    assert G.LEGACY_IDENTITY['inventory_sha256'] == (
        '32a0d69bfd71205106bd1818892c9525830f2bfa4d8d1b2173367ed6f5a2d7b6')
    assert G.LEGACY_IDENTITY != M.identity()


@pytest.mark.parametrize('field', ['id', 'revision', 'contract', 'weights_sha256',
                                    'fork', 'fork_version', 'inventory_sha256'])
def test_migration_allowlist_refuses_other_payload_or_contract(prepared, monkeypatch, field):
    changed = {**prepared.current, field: 'not-the-audited-legacy-value'}
    monkeypatch.setattr(M, 'identity', lambda: changed)
    with pytest.raises(ValueError):
        G._source()
    assert not prepared.target.exists() and tree_bytes(prepared.source) == prepared.original


def test_receipt_cannot_authorize_an_unknown_legacy_adapter(prepared):
    forged = deepcopy(prepared.record)
    forged['identity']['adapter_sha256'] = 'd' * 64
    (prepared.source / 'receipt.json').write_text(json.dumps(forged))
    with pytest.raises(ValueError):
        G._inspect()
    assert not G.status()['migration_available'] and not prepared.target.exists()


def test_unknown_namespace_is_not_discovered_or_adopted(prepared):
    alternate = prepared.parent / ('e' * 64)
    prepared.source.rename(alternate)
    assert not G.status()['migration_available']
    with pytest.raises((ValueError, OSError)):
        G._inspect()
    assert tree_bytes(alternate) == prepared.original and not prepared.target.exists()


def test_receipt_inventory_must_equal_independently_expected_inventory(prepared):
    forged = deepcopy(prepared.record)
    forged['files']['runtime/package.py']['sha256'] = '0' * 64
    (prepared.source / 'receipt.json').write_text(json.dumps(forged))
    with pytest.raises(ValueError, match='回执'):
        G._inspect()
    assert not prepared.target.exists()


@pytest.mark.parametrize('name', ['model/model.bin', 'wheels/fixture.whl', 'runtime/package.py'])
def test_any_locked_payload_mismatch_prevents_migration(prepared, name):
    path = prepared.source / name
    raw = path.read_bytes()
    path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    with pytest.raises(ValueError):
        G.migrate()
    assert not prepared.target.exists()
    assert not list(prepared.parent.glob('.semantic-migration-*'))
    assert (prepared.source / 'receipt.json').read_bytes() == prepared.original['receipt.json']


def test_original_wheel_bytes_are_hashed_before_archive_is_used(monkeypatch, tmp_path):
    code, wheels = tmp_path / 'code', tmp_path / 'wheels'
    code.mkdir(); wheels.mkdir()
    (code / 'fork-patches.json').write_text(json.dumps({'patches': []}))
    archive = wheels / 'fixture.whl'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('fixture/__init__.py', '# Never imported\n')
    raw = archive.read_bytes()
    selected = [{'filename': archive.name, 'size': len(raw), 'sha256': digest(raw)}]
    archive.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    monkeypatch.setattr(M, 'HERE', code)
    def must_not_unzip(*args, **kwargs):
        raise AssertionError('A wheel hash mismatch must fail before archive processing')
    monkeypatch.setattr(A, '_runtime_archive', must_not_unzip)
    with pytest.raises(ValueError, match='轮子校验失败'):
        list(A.runtime_files(tmp_path, selected))


@pytest.mark.parametrize('extra', ['file', 'empty-directory', 'symlink', 'fifo'])
def test_full_inventory_rejects_extra_or_special_entries(prepared, extra):
    path = prepared.source / 'unexpected'
    if extra == 'file':
        path.write_bytes(b'not inventoried')
    elif extra == 'empty-directory':
        path.mkdir()
    elif extra == 'symlink':
        path.symlink_to(prepared.source / 'model/model.bin')
    else:
        os.mkfifo(path)
    with pytest.raises(ValueError):
        G._inspect()
    assert not prepared.target.exists()


def test_status_verifies_without_mutating_old_installation(prepared):
    status = G.status()
    assert status['migration_available'] and status['requires_descriptor_review']
    assert status['migration_source_identity'] == G.LEGACY_IDENTITY
    assert status['migration_bytes'] == sum(row['size'] for row in prepared.expected.values())
    assert tree_bytes(prepared.source) == prepared.original
    assert not prepared.target.exists() and not prepared.offline


def test_offline_copy_preserves_old_receipt_namespace_and_every_payload(prepared):
    G.migrate()
    assert prepared.offline == [True]
    assert tree_bytes(prepared.source) == prepared.original
    _, current = M.verify(prepared.target)
    assert current['identity'] == prepared.current
    assert current['files'] == prepared.expected
    assert current['migration'] == {
        'version': 1, 'method': 'verified-offline-copy',
        'source_identity': G.LEGACY_IDENTITY,
        'source_receipt_sha256': digest(prepared.original['receipt.json']),
        'descriptors_upgraded': False, 'runtime_executed': False}
    for name in prepared.expected:
        assert (prepared.target / name).read_bytes() == prepared.original[name]
        assert os.stat(prepared.target / name).st_ino != os.stat(prepared.source / name).st_ino
    result = prepared.events[-1]
    assert result['state'] == 'ready' and result['installed'] and result['migrated']
    assert result['requires_descriptor_review'] and not result['migration_available']
    assert 'publication_warning' not in result


@pytest.mark.parametrize('boundary', ['before-copy', 'after-staging-verification'])
def test_cancellation_never_publishes_partial_destination(prepared, monkeypatch, boundary):
    cancelled = {'value': False}
    if boundary == 'before-copy':
        copy_file = G._copy_file
        def cancel_copy(*args, **kwargs):
            cancelled['value'] = True
            return copy_file(*args, **kwargs)
        monkeypatch.setattr(G, '_copy_file', cancel_copy)
    else:
        verify = M.verify
        def cancel_verified(*args, **kwargs):
            result = verify(*args, **kwargs)
            cancelled['value'] = True
            return result
        monkeypatch.setattr(M, 'verify', cancel_verified)
    def forbidden(*args, **kwargs):
        raise AssertionError('Cancellation before publication cannot publish')
    monkeypatch.setattr(G, '_publish', forbidden)
    with pytest.raises(InterruptedError):
        G.migrate(cancelled=lambda: cancelled['value'])
    assert not prepared.target.exists()
    assert not list(prepared.parent.glob('.semantic-migration-*'))
    assert tree_bytes(prepared.source) == prepared.original


@pytest.mark.parametrize('existing_payload', [False, True])
def test_atomic_publication_never_clobbers_existing_directory(tmp_path, existing_payload):
    staging, destination = tmp_path / 'staging', tmp_path / 'destination'
    staging.mkdir(); destination.mkdir()
    (staging / 'new').write_bytes(b'candidate')
    if existing_payload:
        (destination / 'owned').write_bytes(b'preserve destination')
    before = tree_bytes(destination)
    with pytest.raises(FileExistsError):
        G._publish(staging, destination)
    assert tree_bytes(destination) == before and (staging / 'new').read_bytes() == b'candidate'


def test_late_destination_race_cleans_staging_without_touching_old_install(prepared, monkeypatch):
    publish = G._publish
    def conflicting_publish(source, target):
        target.mkdir()
        (target / 'owned').write_bytes(b'external owner')
        publish(source, target)
    monkeypatch.setattr(G, '_publish', conflicting_publish)
    with pytest.raises(FileExistsError):
        G.migrate()
    assert tree_bytes(prepared.target) == {'owned': b'external owner'}
    assert tree_bytes(prepared.source) == prepared.original
    assert not list(prepared.parent.glob('.semantic-migration-*'))


def test_cancellation_after_atomic_publish_reports_committed_success(prepared, monkeypatch):
    cancelled, publish = {'value': False}, G._publish
    def published_then_cancelled(source, target):
        publish(source, target)
        cancelled['value'] = True
    monkeypatch.setattr(G, '_publish', published_then_cancelled)
    G.migrate(cancelled=lambda: cancelled['value'])
    assert M.verify(prepared.target)[1]['identity'] == prepared.current
    assert prepared.events[-1]['state'] == 'ready' and prepared.events[-1]['installed']
    assert tree_bytes(prepared.source) == prepared.original


def test_postpublish_sync_failure_reports_installed_with_warning(prepared, monkeypatch):
    sync = G._sync_dir
    def fail_after_publication(path):
        if Path(path) == prepared.parent:
            raise OSError('fixture parent fsync failure after commit')
        return sync(path)
    monkeypatch.setattr(G, '_sync_dir', fail_after_publication)
    G.migrate()
    result = prepared.events[-1]
    assert result['state'] == 'ready' and result['installed'] and result['migrated']
    assert 'fixture parent fsync failure after commit' in result['publication_warning']
    assert M.verify(prepared.target)[1]['identity'] == prepared.current
    assert tree_bytes(prepared.source) == prepared.original


def test_migrate_signal_handler_sets_flag_without_raising(monkeypatch):
    handlers, observed = {}, []
    monkeypatch.setattr(sys, 'argv', ['optional-installer', '--migrate'])
    monkeypatch.setattr(A.signal, 'signal', lambda number, handler: handlers.update({number: handler}))
    def fake_migrate(*, cancelled):
        assert not cancelled()
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        observed.append(cancelled())
        handlers[signal.SIGINT](signal.SIGINT, None)
        observed.append(cancelled())
    monkeypatch.setattr(G, 'migrate', fake_migrate)
    A.main()
    assert observed == [True, True]


def test_immutable_input_source_bytes_participate_in_current_adapter_hash(monkeypatch):
    names = ('predict.py', 'task_tokens.py', 'resolver.py', 'worker.py', 'immutable_input.py')
    before = M.identity()
    assert before['adapter_sha256'] == digest(b''.join((M.HERE / name).read_bytes() for name in names))
    original = Path.read_bytes
    def changed_source(path):
        raw = original(path)
        return raw + b'\n# fixture-only identity change\n' if path == M.HERE / 'immutable_input.py' else raw
    monkeypatch.setattr(Path, 'read_bytes', changed_source)
    after = M.identity()
    assert after['adapter_sha256'] != before['adapter_sha256']
    assert after['inventory_sha256'] == before['inventory_sha256']
    assert M.namespace(after) != M.namespace(before)
