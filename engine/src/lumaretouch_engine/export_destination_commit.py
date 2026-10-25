"""Linux no-clobber byte commit for frozen destination targets.

Encoder must finish its existing validation before calling this function. All path
components are opened relative to pinned directory descriptors with O_NOFOLLOW.
Unlike export._atomic_write's os.replace this cannot overwrite a raced-in original.
The canonical export writers call this module. This change has NOT been exercised
against real exports; source linkage is not runtime acceptance.
"""
from __future__ import annotations
import os
import secrets
from .export_destination_policy import absolute


class CommitFailure(OSError):
    def __init__(self, cause, target, committed):
        super().__init__(str(cause))
        self.target = str(target)
        self.committed = committed
        self.outputs = [{"path":str(target), "committed":True, "durability_confirmed":False}] if committed else []


def commit_encoded_bytes(target, encoded, *, create_missing=False, cancelled=lambda: False):
    path = absolute(target)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open('/', flags)
    temporary = None
    committed = False
    try:
        if cancelled():
            return {"path": str(path), "committed": False, "cancelled": True}
        for part in path.parts[1:-1]:
            try:
                child = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create_missing:
                    raise
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass  # Re-open NOFOLLOW, never trust a raced-in directory.
                child = os.open(part, flags, dir_fd=fd)
            os.close(fd); fd = child
        from .owned_export_destination import check_parent
        check_parent(path, fd)
        temporary = '.lrt-export-' + secrets.token_hex(16) + '.tmp'
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(out, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if cancelled():
            return {"path": str(path), "committed": False, "cancelled": True}
        check_parent(path, fd)
        # link is atomic and fails EEXIST, including dangling symlink targets.
        os.link(temporary, path.name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        committed = True
        os.unlink(temporary, dir_fd=fd); temporary = None
        os.fsync(fd)
        return {"path": str(path), "committed": True, "cancelled": False}
    except OSError as exc:
        raise CommitFailure(exc, path, committed) from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=fd)
            except OSError:
                pass  # Preserve commit/cancellation outcome; orphan temp is safe to clean later.
        os.close(fd)
