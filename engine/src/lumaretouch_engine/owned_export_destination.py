"""Internal output-directory identity for bounded workflow exports.

No JSON command admits this capability. Ordinary exports keep their historical
no-clobber semantics when no internal directory proof is supplied.
"""
from contextvars import ContextVar
import os
from .ingest_session_protocol import path, root_identity
from .source_relocation_io import open_directory

_CURRENT = ContextVar('owned_export_destination_roots', default=None)


def normalize(value):
    if value is None:
        return None
    if type(value) is not dict or not 1 <= len(value) <= 64:
        raise ValueError('Owned export needs bounded exact destination directory identities')
    return {path(root): [str(part) for part in root_identity(pin)] for root, pin in value.items()}


def enter(value):
    return _CURRENT.set(normalize(value))


def leave(token):
    _CURRENT.reset(token)


def check_parent(target, descriptor):
    roots = _CURRENT.get()
    if roots is None:
        return
    parent = os.path.dirname(os.fspath(target))
    if parent not in roots:
        raise OSError('Output parent is not in the original owned directory set')
    expected = tuple(int(part) for part in roots[parent])
    actual = os.fstat(descriptor)
    if (actual.st_dev, actual.st_ino) != expected:
        raise OSError('Original output directory was replaced; no write authorized there')
    current_fd = open_directory(parent)
    try:
        current = os.fstat(current_fd)
        if (current.st_dev, current.st_ino) != expected:
            raise OSError('Output directory pathname no longer names the owned directory')
    finally:
        os.close(current_fd)
