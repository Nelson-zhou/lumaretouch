"""Read-only, bounded catalogue of the genuine existing preset store.

Selection is not application authority. No image, recipe, organisation state,
lock file or directory is created or changed here. Existing store writers use
the same process RLock and .organisation.lock inode; readers never create it.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import os
import re
import stat

from . import preset_store as PS
from . import preset_organisation_store as PO
from . import scope as S
from . import workflow_owner_protocol as P

SCHEMA = 'lrt.workflow-preset-catalogue.v1'
MAX_PRESETS = 256
MAX_DIRECTORY_ENTRIES = 4096
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
MAX_JSON_DEPTH = 48
MAX_JSON_NODES = 200000
SUPPORT_REASON = 'preset_owner_not_bound'


class CatalogueError(S.ScopeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _identity(value):
    if type(value) is not str:
        raise CatalogueError('invalid_preset_id', 'Preset ID must be an exact saved ID')
    try:
        return PO.identity(value)
    except PO.OrganisationError as error:
        raise CatalogueError('invalid_preset_id', str(error)) from error


def _issue(error, filename=None):
    return {'code': getattr(error, 'code', 'catalogue_unreadable'),
            'file': None if filename is None else _diagnostic_text(filename),
            'message': _diagnostic_text(str(error))}


def _diagnostic_text(value):
    # POSIX names may contain surrogate-escaped bytes; diagnostics must still
    # be bounded JSON/UTF-8 for the owner transport, not break the whole reply.
    return str(value).encode('utf-8', 'backslashreplace').decode('utf-8')[:512]


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _same_file(fd, root_fd, filename):
    opened = os.fstat(fd)
    current = os.stat(filename, dir_fd=root_fd, follow_symlinks=False)
    if not stat.S_ISREG(current.st_mode) or _stamp(opened) != _stamp(current):
        raise CatalogueError('catalogue_changed', 'Preset catalogue entry changed during read')


@contextmanager
def _read_lock(root):
    """Reuse store ownership, or take its existing flock without any write.

    A previously unused (nonexistent) preset directory has builtin-only content.
    An existing directory without the established store lock is not a consistent
    user snapshot: report the condition instead of silently creating the lock.
    """
    if not PO.LOCK.acquire(blocking=False):
        raise CatalogueError('catalogue_busy', 'Preset catalogue is being changed; refresh later')
    root_fd = lock_fd = None
    try:
        active = getattr(PO.LOCAL, 'root', None)
        if active is not None and active != root:
            raise CatalogueError('catalogue_busy', 'Another preset directory owns the store lock')
        try:
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            yield None
            if os.path.lexists(root):
                raise CatalogueError('catalogue_changed', 'Preset directory appeared during read; refresh')
            return
        before = os.fstat(root_fd)
        try:
            lock_fd = os.open('.organisation.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                              dir_fd=root_fd)
        except FileNotFoundError as error:
            raise CatalogueError('catalogue_lock_missing',
                'Existing preset directory has no store lock; read-only catalogue cannot initialise it') from error
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise CatalogueError('catalogue_lock_invalid', 'Preset store lock is not a regular file')
        if active is None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise CatalogueError('catalogue_busy', 'Preset catalogue is being changed; refresh later') from error
        _same_file(lock_fd, root_fd, '.organisation.lock')
        yield root_fd
        current = os.stat(root, follow_symlinks=False)
        if (not stat.S_ISDIR(current.st_mode) or _stamp(before) != _stamp(current)
                or _stamp(before) != _stamp(os.fstat(root_fd))):
            raise CatalogueError('catalogue_changed', 'Preset directory changed during read; refresh')
        if lock_fd is not None:
            _same_file(lock_fd, root_fd, '.organisation.lock')
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        if root_fd is not None:
            os.close(root_fd)
        PO.LOCK.release()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogueError('duplicate_json_key', 'Preset catalogue JSON has duplicate object keys')
        result[key] = value
    return result


def _constant(_value):
    raise CatalogueError('nonfinite_json', 'Preset catalogue JSON must contain finite numbers')


def _bounded_tree(value):
    pending, visited = [(value, 0)], 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if depth > MAX_JSON_DEPTH or visited > MAX_JSON_NODES:
            raise CatalogueError('json_structure_limit', 'Preset catalogue JSON structure exceeds its bound')
        if isinstance(current, dict):
            if visited + len(pending) + len(current) > MAX_JSON_NODES:
                raise CatalogueError('json_structure_limit', 'Preset catalogue JSON has too many members')
            pending.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            if visited + len(pending) + len(current) > MAX_JSON_NODES:
                raise CatalogueError('json_structure_limit', 'Preset catalogue JSON has too many members')
            pending.extend((child, depth + 1) for child in current)


def _read_json(root_fd, filename, maximum, *, optional=False, budget=None, observed=None):
    if budget is not None:
        if budget[0] <= 0:
            raise CatalogueError('catalogue_byte_limit', 'Preset catalogue exceeds its total byte budget')
        maximum = min(maximum, budget[0])
    try:
        fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
    except FileNotFoundError:
        if optional:
            return None, 0
        raise
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise CatalogueError('not_regular_file', 'Preset catalogue entries must be regular files')
        if before.st_size > maximum:
            raise CatalogueError('entry_byte_limit', 'Preset catalogue entry exceeds the bounded read budget')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            raw = handle.read(maximum + 1)
        if budget is not None:
            # Failed JSON/validation still consumed read work and cannot reset
            # the aggregate budget for the next malformed entry.
            budget[0] -= len(raw)
        if len(raw) > maximum:
            raise CatalogueError('entry_byte_limit', 'Preset catalogue entry exceeds the bounded read budget')
        if _stamp(before) != _stamp(os.fstat(fd)):
            raise CatalogueError('catalogue_changed', 'Preset catalogue entry changed during read')
        _same_file(fd, root_fd, filename)
        if observed is not None:
            observed[filename] = _stamp(before)
    finally:
        os.close(fd)
    try:
        text = raw.decode('utf-8')
        if text.startswith(('#!', '<?php')) or '<script' in text.lower():
            raise CatalogueError('executable_content', 'Preset entries are data, not executable content')
        value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_constant)
        _bounded_tree(value)
        return value, len(raw)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise CatalogueError('malformed_json', 'Preset catalogue entry is not bounded valid UTF-8 JSON') from error


def _canonical(doc, *, builtin=False):
    """Use the existing schema, module and asset validators, never a new recipe."""
    clean = S.validate_preset(doc, builtin=builtin)
    # The JSON boundary also rejects infinities accepted by permissive parsers,
    # non-JSON values and invalid Unicode. No asset or provenance is stripped.
    canonical = P.encoded(clean, sorted_keys=True)
    if len(canonical) > S.PRESET_MAX_BYTES:
        raise CatalogueError('entry_byte_limit', 'Validated preset content exceeds the preset byte limit')
    return clean, len(canonical)


def _names(root_fd):
    names, visited = [], 0
    with os.scandir(root_fd) as entries:
        for entry in entries:
            visited += 1
            if visited > MAX_DIRECTORY_ENTRIES:
                raise CatalogueError('directory_entry_limit', 'Preset directory scan exceeds its entry limit')
            if entry.name.endswith('.json'):
                names.append(entry.name)
                if len(names) > MAX_PRESETS:
                    raise CatalogueError('preset_count_limit', 'Preset catalogue exceeds its entry limit')
    return sorted(names)


def _snapshot():
    documents, errors = [], []
    try:
        validated_bytes = 0
        for doc in PS.builtin_docs():
            clean, size = _canonical(doc, builtin=True)
            validated_bytes += size
            if validated_bytes > MAX_TOTAL_BYTES:
                raise CatalogueError('canonical_byte_limit', 'Validated preset catalogue exceeds its byte budget')
            documents.append(clean)
        if len({doc['id'] for doc in documents}) != len(documents):
            raise CatalogueError('duplicate_preset_id', 'Builtin catalogue contains repeated preset IDs')
        if len(documents) > MAX_PRESETS:
            raise CatalogueError('preset_count_limit', 'Builtin catalogue exceeds its entry limit')
        root = os.path.abspath(PS.preset_dir())
        with _read_lock(root) as root_fd:
            if root_fd is None:
                return documents, errors
            budget = [MAX_TOTAL_BYTES]
            observed = {}
            state, _ = _read_json(root_fd, '.organisation.state', PO.MAX_BYTES, optional=True,
                                  budget=budget, observed=observed)
            state = PO.empty() if state is None else PO.validate(state)
            names = _names(root_fd)
            if len(names) + len(documents) > MAX_PRESETS:
                raise CatalogueError('preset_count_limit', 'Preset catalogue exceeds its entry limit')
            by_id = {doc['id']: doc for doc in documents}
            duplicates = set()
            for filename in names:
                try:
                    raw, _ = _read_json(root_fd, filename, S.PRESET_MAX_BYTES,
                                       budget=budget, observed=observed)
                    doc, size = _canonical(raw)
                    validated_bytes += size
                    if validated_bytes > MAX_TOTAL_BYTES:
                        raise CatalogueError('canonical_byte_limit', 'Validated preset catalogue exceeds its byte budget')
                    if doc['id'] in by_id:
                        duplicates.add(doc['id'])
                        raise CatalogueError('duplicate_preset_id',
                            'Repeated preset ID or attempted builtin override: ' + doc['id'])
                    by_id[doc['id']] = doc
                    documents.append(doc)
                except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
                    errors.append(_issue(error, filename))
            # Ambiguous saved IDs are never silently resolved by directory order.
            # Genuine builtins retain their identity but incompleteness still
            # prevents load/resolve until the colliding user entry is repaired.
            documents = [doc for doc in documents if doc['builtin'] or doc['id'] not in duplicates]
            state = PO.reconcile(state, documents)
            ordered = []
            for doc in documents:
                item = state['items'][doc['id']]
                if item['deleted']:
                    continue
                if item['name'] is not None:
                    doc = {**doc, 'name': item['name']}
                ordered.append(doc)
            documents = sorted(ordered, key=lambda doc: state['items'][doc['id']]['position'])
            for filename, stamp in observed.items():
                current = os.stat(filename, dir_fd=root_fd, follow_symlinks=False)
                if not stat.S_ISREG(current.st_mode) or stamp != _stamp(current):
                    raise CatalogueError('catalogue_changed', 'Preset catalogue changed before snapshot completed')
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        errors.append(_issue(error))
    return documents, errors


def list_catalogue(*, group_support=False):
    """Return bounded metadata with explicit partial/invalid-store diagnostics.

    No embedded assets or raw recipe parameters are sent in catalogue rows.
    Module metadata describes the current scope registry, not target readiness.
    """
    documents, errors = _snapshot()
    registry = {row['operation_id']: row for row in S.describe()}
    rows = []
    for doc in documents:
        module_ids = sorted(doc['modules'])
        rows.append({'id': doc['id'], 'name': doc['name'], 'kind': doc['kind'],
                     'builtin': doc['builtin'], 'preset_sha256': P.digest(doc),
                     'module_ids': module_ids,
                     'modules': [deepcopy(registry[op]) for op in module_ids],
                     'workflow_supported': False, 'support_reason': SUPPORT_REASON})
        if group_support:
            from .portrait_group_retained import support
            rows[-1]['portrait_group_support'] = support(doc)
    result = {'schema': SCHEMA, 'presets': rows, 'errors': errors, 'complete': not errors}
    if len(P.encoded(result, sorted_keys=True)) > MAX_RESPONSE_BYTES:
        result = {'schema': SCHEMA, 'presets': [], 'complete': False,
                  'errors': [_issue(CatalogueError('catalogue_response_limit',
                      'Preset catalogue metadata exceeds the response limit'))]}
    return result


def load(preset_id):
    """Load fresh exact validated content, refusing any incomplete catalogue."""
    preset_id = _identity(preset_id)
    documents, errors = _snapshot()
    if errors:
        raise CatalogueError('catalogue_incomplete',
            'Preset catalogue is incomplete; refresh or repair it before selection: ' + errors[0]['message'])
    for doc in documents:
        if doc['id'] == preset_id:
            return deepcopy(doc)
    raise CatalogueError('preset_not_found', 'Saved preset no longer exists or is in the recycle bin')


def fingerprint(preset_id):
    """Hash actual current store content; arbitrary caller-supplied recipes are not accepted."""
    return P.digest(load(preset_id))


def resolve(preset_id, preset_sha256):
    """Re-read exact current content and fail rather than rebase a stale selection.

    Returned content is detached from store state. The pin covers the canonical
    validated document, including metadata, builtin provenance and all portable
    assets. It is neither a preview, applicability verdict nor review receipt.
    """
    if type(preset_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', preset_sha256):
        raise CatalogueError('invalid_preset_sha256', 'Preset fingerprint must be a lowercase SHA-256')
    doc = load(preset_id)
    if P.digest(doc) != preset_sha256:
        raise CatalogueError('preset_changed', 'Saved preset content changed; refresh and select it again')
    return doc
