# SPDX-License-Identifier: GPL-3.0-or-later
"""User-invoked workflow preset save using the existing project codec and CAS.

No import/relocation receipt is fabricated. A possible replacement is Unknown,
never permission to retry. Callers own the serialized project mutation gate and
exact before/after document validation. Runtime and durability acceptance UNRUN.
"""
import fcntl
import hashlib
import os
import stat
import uuid
from .source_relocation_io import open_directory
from .source_relocation_transaction import MAX_PROJECT


def _read_at(parent, target):
    """Read only the pinned directory's bounded, unchanged regular leaf.

    A pathname re-traversal could CAS a substituted directory while replace
    still targets the retained descriptor. This does not make a content CAS
    atomic against unrelated writers that ignore the transaction lock.
    """
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_PROJECT:
            raise ValueError('Workflow project is not a bounded regular file')
        blocks, count = [], 0
        while count <= MAX_PROJECT:
            block = os.read(fd, min(1024 * 1024, MAX_PROJECT + 1 - count))
            if not block:
                break
            blocks.append(block)
            count += len(block)
        after = os.fstat(fd)
        current = os.stat(target, dir_fd=parent, follow_symlinks=False)
        def signature(value):
            return (value.st_dev, value.st_ino, value.st_size,
                    value.st_mtime_ns, value.st_ctime_ns)
        if (count > MAX_PROJECT or count != before.st_size
                or signature(before) != signature(after)
                or signature(after) != signature(current)
                or not stat.S_ISREG(current.st_mode)):
            raise ValueError('Workflow project changed during its pinned read')
        raw = b''.join(blocks)
        return raw, hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


def persist(project, path, expected_sha256, recheck):
    from . import project as PJ, creative_document_storage as CS
    if not callable(recheck):
        raise ValueError('Workflow save requires its exact retained owner check')
    prepared = PJ._prepare_save(project)
    body, data, blobs = prepared
    expected_after = hashlib.sha256(data).hexdigest()
    path = os.path.abspath(path)
    parent = open_directory(os.path.dirname(path))
    identity = None
    target = os.path.basename(path)
    lock = None
    temp = None
    replacement_attempted = False
    outcome = None

    def same_parent():
        latest = open_directory(os.path.dirname(path))
        try:
            found = os.fstat(latest)
            if (found.st_dev, found.st_ino) != (identity.st_dev, identity.st_ino):
                raise ValueError('Workflow project directory was replaced')
        finally:
            os.close(latest)

    try:
        identity = os.fstat(parent)
        lock = os.open(target + '.relocation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            raise ValueError('Project transaction lock is not a regular file')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        same_parent()
        if _read_at(parent, target)[1] != expected_sha256:
            raise ValueError('Saved project changed before workflow save')
        same_parent()
        recheck()
        # Existing lossless codec owns immutable creative blob layout/precision.
        # Unused blobs after a refused commit do not overwrite prior originals.
        CS.write_blobs(body, blobs, path, reserve_bytes=CS.RESERVE_BYTES + len(data))
        same_parent()
        temp = '.lrt-workflow-preset-' + uuid.uuid4().hex
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        recheck()
        same_parent()
        if _read_at(parent, target)[1] != expected_sha256:
            raise ValueError('Saved project CAS changed before replacement')
        same_parent()
        replacement_attempted = True
        os.replace(temp, target, src_dir_fd=parent, dst_dir_fd=parent)
        temp = None
        os.fsync(parent)
        same_parent()
        raw, actual = _read_at(parent, target)
        if actual != expected_after or raw != data:
            raise ValueError('Committed workflow project readback differs')
        same_parent()
        outcome = {'status': 'succeeded', 'sha256': actual, 'bytes': len(data),
                   'updated_ns': body['updated_ns'], 'project': body}
    except Exception as error:
        if replacement_attempted:
            outcome = {'status': 'unknown', 'expected_sha256': expected_after,
                       'error': str(error), 'requires_readback': True}
        else:
            raise
    finally:
        if temp is not None:
            try:
                os.unlink(temp, dir_fd=parent)
            except OSError:
                pass
        cleanup_error = None
        for descriptor in (lock, parent):
            if descriptor is not None:
                try:
                    # A failed close is never retried: its descriptor may have
                    # been closed already and reused by the operating system.
                    os.close(descriptor)
                except OSError as error:
                    cleanup_error = error
        if cleanup_error is not None and replacement_attempted and (
                outcome is None or outcome['status'] == 'succeeded'):
            outcome = {'status': 'unknown', 'expected_sha256': expected_after,
                       'error': str(cleanup_error), 'requires_readback': True}
    return outcome
