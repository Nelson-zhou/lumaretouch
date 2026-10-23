"""Local immutable crash candidates. No original-project writes or automatic restore.

The commit point is renaming a fully fsynced directory into candidates/. A
candidate contains the existing project serializer's bytes plus a hash receipt.
Partial staging directories are never offered as committed recovery candidates.
"""
from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid

from . import project as PJ


class RecoveryError(ValueError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_bounded(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RecoveryError("Recovery file is not a regular local file")
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise RecoveryError("Recovery file exceeds its byte budget")
    return raw


def write_new(path: Path, raw: bytes) -> None:
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def no_dropped(value) -> None:
    """Reject lossy serialization anywhere, including inactive/nested history."""
    if isinstance(value, dict):
        if value.get('dropped'):
            raise RecoveryError("Incomplete serialized assets: resolve dropped records before autosave")
        for child in value.values():
            no_dropped(child)
    elif isinstance(value, list):
        for child in value:
            no_dropped(child)


def validate_assets(project) -> None:
    """Codec-compatible references must be reconstructible, never dropped later."""
    bank = project['assets']
    for identity, asset in bank.items():
        try:
            raw = base64.b64decode(asset['b64'], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise RecoveryError('Invalid immutable recovery asset') from error
        if identity != 'sha256:' + digest(raw) or asset.get('bytes') != len(raw):
            raise RecoveryError('Immutable recovery asset hash/length mismatch')
    def walk(value):
        if isinstance(value, dict):
            if '__asset__' in value and value['__asset__'] not in bank:
                raise RecoveryError('Missing immutable recovery asset reference')
            if '__dc__' in value and value['__dc__'] not in ('RepairOp', 'LightOp', 'FacePrecompute'):
                raise RecoveryError('Unsupported recovery dataclass would be dropped on reopen')
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(project)


class RecoveryStore:
    def __init__(self, root: str, *, budget_bytes=1_024_000_000,
                 reserve_bytes=64_000_000, max_candidates=64):
        self.cancelled = lambda: False
        self.root = Path(root).absolute()
        self.budget_bytes = int(budget_bytes)
        self.reserve_bytes = int(reserve_bytes)
        self.max_candidates = int(max_candidates)
        if self.budget_bytes <= 0 or self.reserve_bytes < 0 or self.max_candidates < 1:
            raise RecoveryError("Invalid recovery budget")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink():
            raise RecoveryError("Recovery root must not be a symbolic link")
        os.chmod(self.root, 0o700)
        for name in ('candidates', 'staging', 'trash', 'backups', 'operations'):
            path = self.root / name
            path.mkdir(exist_ok=True, mode=0o700)
            if path.is_symlink():
                raise RecoveryError("Recovery directories must not be symbolic links")
        PJ._fsync_dir(str(self.root))
        PJ._fsync_dir(str(self.root.parent))

    @contextlib.contextmanager
    def locked(self):
        with (self.root / '.lock').open('a+b') as lock:
            os.chmod(self.root / '.lock', 0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def usage(self) -> dict:
        total = 0
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            for name in dirs + files:
                p = Path(directory) / name
                if p.is_symlink():
                    raise RecoveryError("Unexpected symbolic link in local recovery storage")
            total += sum((Path(directory) / name).stat().st_size for name in files)
        return {'bytes': total, 'budget_bytes': self.budget_bytes,
                'free_bytes': shutil.disk_usage(self.root).free,
                'reserve_bytes': self.reserve_bytes,
                'trash_is_recoverable': True}

    def capacity(self, size: int):
        usage = self.usage()
        if usage['bytes'] + size > self.budget_bytes or usage['free_bytes'] - size < self.reserve_bytes:
            raise RecoveryError("Autosave paused: disk budget/reserve exhausted; retained versions were not deleted")

    def publish(self, frozen: bytes, metadata: dict, commit_guard) -> dict:
        """Worker-only. guard holds the scheduler epoch lock for publication."""
        project = json.loads(frozen)
        PJ.validate(project)
        no_dropped(project)
        validate_assets(project)
        if project['schema_version'] != PJ.SCHEMA:
            raise RecoveryError("Autosave requires already migrated current-schema state")
        with self.locked():
            if len(list((self.root / 'candidates').iterdir())) >= self.max_candidates:
                raise RecoveryError("Recovery candidate limit reached; review retained versions")
            # Serializer indentation can enlarge compact input. Reserve its hard
            # maximum, not an optimistic estimate, before writing anything.
            self.capacity(PJ.MAX_PROJECT_BYTES + 1_048_576)
            token = str(uuid.uuid4())
            stage = self.root / 'staging' / token
            stage.mkdir(mode=0o700)
            path = stage / ('project' + PJ.SUFFIX)
            info = PJ.save(project, str(path))
            os.chmod(path, 0o600)
            raw = read_bounded(path, PJ.MAX_PROJECT_BYTES)
            if digest(raw) != info['sha256']:
                raise RecoveryError("Autosave readback hash mismatch")
            PJ.validate(json.loads(raw))
            receipt = {**metadata, 'schema': 'lrt.recovery.v1', 'candidate_id': token,
                       'project_id': project['project_id'], 'project_sha256': digest(raw),
                       'project_bytes': len(raw), 'created_ns': time.time_ns(),
                       'phase': 'committed', 'kind': metadata.get('kind', 'autosave')}
            receipt_raw = json_bytes(receipt)
            if len(receipt_raw) > 1_048_576:
                raise RecoveryError("Recovery receipt exceeds budget")
            write_new(stage / 'receipt.json', receipt_raw)
            PJ._fsync_dir(str(stage))
            with commit_guard():
                os.rename(stage, self.root / 'candidates' / token)
                PJ._fsync_dir(str(self.root / 'candidates'))
                PJ._fsync_dir(str(self.root / 'staging'))
            return receipt

    def _candidate(self, token: str, area='candidates'):
        if str(uuid.UUID(token)) != token or area not in ('candidates', 'trash'):
            raise RecoveryError("Invalid recovery candidate identity")
        path = self.root / area / token
        if path.is_symlink() or not path.is_dir():
            raise RecoveryError("Recovery candidate is unavailable")
        receipt = json.loads(read_bounded(path / 'receipt.json', 1_048_576))
        raw = read_bounded(path / ('project' + PJ.SUFFIX), PJ.MAX_PROJECT_BYTES)
        if receipt.get('candidate_id') != token or receipt.get('phase') != 'committed' or digest(raw) != receipt.get('project_sha256'):
            raise RecoveryError("Recovery candidate identity/hash mismatch")
        project = json.loads(raw)
        PJ.validate(project)
        no_dropped(project)
        validate_assets(project)
        if project['project_id'] != receipt.get('project_id'):
            raise RecoveryError("Recovery project identity mismatch")
        return receipt, project, raw

    def list_candidates(self, project_id=None, *, area='candidates') -> list:
        if area not in ('candidates', 'trash'):
            raise RecoveryError("Invalid candidate area")
        rows = []
        with self.locked():
            for path in sorted((self.root / area).iterdir()):
                try:
                    receipt, _, _ = self._candidate(path.name, area)
                    if project_id is None or receipt['project_id'] == project_id:
                        rows.append(receipt)
                except (ValueError, OSError, KeyError, TypeError) as error:
                    rows.append({'candidate_id': path.name, 'phase': 'damaged', 'reason': str(error)})
        return rows

    def inspect(self, token: str, *, area='candidates') -> dict:
        with self.locked():
            receipt, project, _ = self._candidate(token, area)
        sources = []
        from .source_relocation_io import Budget, hash_file
        budget = Budget(self.cancelled)
        for row in project['docs']:
            fp = row.get('fingerprint') or {}
            try:
                if not os.path.isfile(row['path']):
                    check, status = {'exists':False}, 'missing'
                elif not fp.get('sha256') or fp.get('hash_level') != 'full':
                    check, status = {'exists':True, 'full_match':None}, 'unverified'
                else:
                    current = hash_file(row['path'], budget, fp.get('bytes'))
                    check = {'exists':True, 'full_match':current['sha256'] == fp['sha256']}
                    status = 'matched' if check['full_match'] else 'changed'
            except (OSError, ValueError) as error:
                if isinstance(error, (InterruptedError, TimeoutError)):
                    raise
                check, status = {'reason':str(error)}, 'unavailable'
            sources.append({'document_id': row['document_id'],
                            'source_asset_id': row['source_asset_id'],
                            'path': row['path'], 'status': status, 'facts': check})
        return {'receipt': receipt, 'sources': sources,
                'source_reconciliation_required': any(s['status'] != 'matched' for s in sources),
                'automatic_render_allowed': all(s['status'] == 'matched' for s in sources),
                'original_will_be_overwritten': False}

    def discard(self, token: str, *, confirmed: bool) -> dict:
        if confirmed is not True:
            raise RecoveryError("Explicit discard confirmation required")
        with self.locked():
            receipt, _, _ = self._candidate(token)
            os.rename(self.root / 'candidates' / token, self.root / 'trash' / token)
            PJ._fsync_dir(str(self.root / 'trash'))
            PJ._fsync_dir(str(self.root / 'candidates'))
        return {'candidate_id': token, 'phase': 'trashed', 'recoverable': True,
                'project_sha256': receipt['project_sha256']}

    def restore_copy(self, token: str, destination: str, *, confirmed: bool,
                     reviewed_sha256: str, area='candidates') -> dict:
        if confirmed is not True:
            raise RecoveryError("Explicit restore confirmation required")
        review = self.inspect(token, area=area)
        # Missing/changed sources must be reconciled through the existing source
        # relocation flow first; never replay stale masks against changed pixels.
        if review['source_reconciliation_required']:
            raise RecoveryError("Source reconciliation required; candidate remains untouched")
        with self.locked():
            receipt, project, _ = self._candidate(token, area)
            if receipt['project_sha256'] != reviewed_sha256:
                raise RecoveryError("Reviewed candidate changed")
            target = Path(destination).absolute()
            # Fresh directory admission is atomic and cannot replace any file.
            if self.cancelled(): raise InterruptedError('恢复操作已取消')
            target.mkdir(mode=0o700, parents=False, exist_ok=False)
            project['project_id'] = str(uuid.uuid4())
            project['recovered_from'] = {'project_id': receipt['project_id'], 'candidate_id': token}
            project.pop('_source_path', None)
            project.pop('_source_sha256', None)
            info = PJ.save(project, str(target / ('recovered' + PJ.SUFFIX)))
            PJ._fsync_dir(str(target.parent))
            return {**info, 'phase': 'restored_copy', 'candidate_id': token,
                    'project_id': project['project_id'], 'recovered_project_id': project['project_id'],
                    'original_untouched': True}

    def relink(self, token, source_asset_id, path, *, reviewed_sha256, confirmed, area='candidates'):
        if confirmed is not True:
            raise RecoveryError('Confirm the selected source path before relinking')
        with self.locked():
            receipt, project, _ = self._candidate(token, area)
            if receipt['project_sha256'] != reviewed_sha256:
                raise RecoveryError('Reviewed candidate changed')
        source = project.get('source_assets', {}).get(source_asset_id)
        if source is None or not (source.get('fingerprint') or {}).get('sha256'):
            raise RecoveryError('No original full SHA256 evidence; cannot guess source identity')
        from .source_relocation_io import Budget, hash_file
        expected = source['fingerprint']
        checked = hash_file(os.path.abspath(path), Budget(self.cancelled), expected['bytes'])
        incoming = {**expected, 'path':os.path.abspath(path), 'sha256':checked['sha256'],
                    'bytes':checked['bytes'], 'mtime_ns':checked['stat'][3], 'hash_level':'full'}
        if incoming['sha256'] != expected['sha256'] or incoming['bytes'] != expected['bytes']:
            raise RecoveryError('Selected source content differs; old masks were not applied')
        from .virtual_copy_storage import relocate_source
        if any(row['path'] == os.path.abspath(path) and row['source_asset_id'] != source_asset_id for row in project['docs']):
            raise RecoveryError('Selected path belongs to an independent source; no silent merge')
        old_path = source['path']
        relocate_source(project, source_asset_id, os.path.abspath(path), incoming)
        for row in project['docs']:
            if row['source_asset_id'] == source_asset_id:
                row.setdefault('source_relocation_aliases', {})[old_path] = expected['sha256']
        # Preserve canonical document IDs and immutable history. Only source path
        # aliases change; original candidate remains available for inspection.
        metadata = {key:receipt[key] for key in ('revision','original_path','native_receipts') if key in receipt}
        metadata.update(kind='version_snapshot', relinked_from=token)
        if self.cancelled(): raise InterruptedError('来源核对已取消')
        result = self.publish(json_bytes(project), metadata, contextlib.nullcontext)
        return {'phase':'relinked_copy', 'candidate_id':result['candidate_id'], 'receipt':result}

    def operation_started(self, request):
        token = request['request_id']
        if str(uuid.UUID(token)) != token:
            raise RecoveryError('Mutation operation requires a canonical UUID')
        with self.locked():
            target = self.root / 'operations' / (token + '.started.json')
            if target.exists():
                raise RecoveryError('Operation already recorded; inspect journal instead of replaying')
            self.capacity(1_048_576)
            write_new(target, json_bytes({'phase':'started', 'request':request, 'created_ns':time.time_ns()}))
            PJ._fsync_dir(str(target.parent))

    def operation_finished(self, request, outcome):
        with self.locked():
            target = self.root / 'operations' / (request['request_id'] + '.result.json')
            write_new(target, json_bytes({'phase':'unknown' if outcome.get('outcome_unknown') else 'finished',
                'request':request, 'result':outcome, 'created_ns':time.time_ns()}))
            PJ._fsync_dir(str(target.parent))

    def operations(self, project_id=None):
        rows = []
        with self.locked():
            for path in sorted((self.root / 'operations').glob('*.started.json')):
                started = json.loads(read_bounded(path, 1_048_576))
                if project_id is not None and started['request']['project_id'] != project_id:
                    continue
                result = path.with_name(path.name.replace('.started.json', '.result.json'))
                rows.append(json.loads(read_bounded(result,1_048_576)) if result.exists() else started)
                if len(rows) >= 256:
                    break
        return rows

    def backup_before_migration(self, source: str) -> dict:
        """Call before PJ.load. Backup exact bytes, then verify migrated memory.

        Does not rewrite source. On failed validation the backup stays available.
        Future schemas are rejected by PJ.validate before migration is attempted.
        """
        source_path = Path(source).absolute()
        raw = read_bounded(source_path, PJ.MAX_PROJECT_BYTES)
        old = json.loads(raw)
        PJ.validate(old)
        if old['schema_version'] == PJ.SCHEMA:
            return {'required': False, 'source_sha256': digest(raw)}
        with self.locked():
            self.capacity(len(raw) + 1_048_576)
            target = self.root / 'backups' / (str(uuid.uuid4()) + PJ.SUFFIX)
            write_new(target, raw)
            PJ._fsync_dir(str(target.parent))
            if read_bounded(target, PJ.MAX_PROJECT_BYTES) != raw:
                raise RecoveryError("Migration backup verification failed")
            # Migrate these exact backed-up bytes, not a concurrently changed file.
            migrated = PJ._migrate(old)
            PJ.validate(migrated)
            no_dropped(migrated)
            if read_bounded(source_path, PJ.MAX_PROJECT_BYTES) != raw:
                raise RecoveryError("Original changed during migration backup; reopen for review")
            return {'required': True, 'backup_path': str(target), 'sha256': digest(raw),
                    'from_schema': old['schema_version'], 'to_schema': PJ.SCHEMA,
                    'project': migrated, 'original_untouched': True}
