"""Local-only optional model pack verification. Status never imports model code.

No discovery from HF caches, remote identifiers, user-authored manifests, downloads,
or pickle fallback. Full verification streams files on every call; there is no
mtime-based integrity cache. Runtime must verify again around model loading and
must never accept results if verification fails. Pack storage must not be writable
by another actor during inference; path-returning loaders cannot eliminate races.
"""
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath
import stat

from . import creative_generation_manifest as manifest


class PackUnavailable(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class VerifiedPack:
    prior_path: Path
    decoder_path: Path
    identity: str
    namespace: str


def model_root(root: str | Path | None = None) -> Path:
    if root is None:
        data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        root = data / "lumaretouch/optional-models" / manifest.NAMESPACE
    path = Path(root)
    if not path.is_absolute() or ".." in path.parts:
        raise PackUnavailable("invalid_pack_path", "Pack root must be an absolute local path without traversal")
    return path


def _open_root(path: Path) -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise PackUnavailable("unsupported_platform", "Secure directory traversal requires Linux no-follow opens")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _inventory(fd: int, prefix: str = "") -> set[str]:
    found: set[str] = set()
    allowed_directories = {str(parent) for pin in manifest.FILES
                           for parent in PurePosixPath(pin.path).parents if str(parent) != "."}
    entries = os.listdir(fd)
    if len(entries) > len(manifest.FILES) * 4:
        raise PackUnavailable("unexpected_pack_files", "Pack directory exceeds allowlist bounds")
    for name in entries:
        relative = prefix + name
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            if relative not in allowed_directories:
                raise PackUnavailable("unexpected_pack_directory", f"Unreviewed directory: {relative}")
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                found.update(_inventory(child, relative + "/"))
            finally:
                os.close(child)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            found.add(relative)
        else:
            raise PackUnavailable("unsafe_pack_entry", f"Non-regular, linked, or symlink entry: {relative}")
        if len(found) > len(manifest.FILES):
            raise PackUnavailable("unexpected_pack_files", "Pack contains files outside the reviewed allowlist")
    return found


def _digest(root_fd: int, pin: manifest.FilePin) -> str:
    parts = PurePosixPath(pin.path).parts
    if not parts or any(p in (".", "..") for p in parts) or pin.path.startswith("/"):
        raise PackUnavailable("invalid_manifest", "Invalid bundled relative path")
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        data_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(data_fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != pin.size:
                raise PackUnavailable("pack_file_size", f"Unexpected type, links, or byte length: {pin.path}")
            digest = hashlib.sha256()
            size = 0
            while chunk := os.read(data_fd, 1024 * 1024):
                size += len(chunk)
                if size > pin.size:
                    raise PackUnavailable("pack_changed", f"File grew during verification: {pin.path}")
                digest.update(chunk)
            after = os.fstat(data_fd)
            # A successful read may update atime without changing the bytes.
            identity_fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, name) != getattr(after, name) for name in identity_fields) or size != pin.size:
                raise PackUnavailable("pack_changed", f"File changed during verification: {pin.path}")
            value = digest.hexdigest()
            if value != pin.sha256:
                raise PackUnavailable("pack_file_hash", f"SHA256 mismatch: {pin.path}")
            return value
        finally:
            os.close(data_fd)
    finally:
        os.close(fd)


def _verify_runtime_provenance() -> None:
    # No flag or owner-authored manifest can turn this into a provenance proof.
    # Authentication of distribution artifacts AND actual installed code is a
    # separate unfinished admission operation. Keep this unconditional refusal
    # until that verifier exists; populating constants alone is insufficient.
    raise PackUnavailable("runtime_provenance_unverified", "Runtime distribution artifact SHA256 and installed-code inventory admission are not implemented; version metadata cannot authenticate the pinned code revision")


def verify_pack(root: str | Path | None = None) -> VerifiedPack:
    path = model_root(root)
    unresolved = [p.path for p in manifest.FILES if p.sha256 is None or p.size is None]
    if unresolved or not manifest.UPSTREAM_REVISION_MEMBERSHIP_VERIFIED:
        raise PackUnavailable("upstream_manifest_incomplete", "Pinned upstream file sizes, config/tokenizer hashes and revision membership are not fully verified; generation remains unavailable")
    if any(version is None for version in manifest.RUNTIME_VERSIONS.values()):
        raise PackUnavailable("runtime_contract_incomplete", "Optional runtime compatibility pins remain under review")
    _verify_runtime_provenance()
    versions = {}
    for name, expected in manifest.RUNTIME_VERSIONS.items():
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError as exc:
            raise PackUnavailable("runtime_missing", f"Missing external runtime package: {name}") from exc
        if actual != expected:
            raise PackUnavailable("runtime_version", f"Requires {name}=={expected}; found {actual}")
        versions[name] = actual
    try:
        fd = _open_root(path)
        try:
            if _inventory(fd) != {p.path for p in manifest.FILES}:
                raise PackUnavailable("pack_file_set", "Pack must contain exactly the bundled reviewed file allowlist")
            hashes = {p.path: _digest(fd, p) for p in manifest.FILES}
        finally:
            os.close(fd)
    except OSError as exc:
        raise PackUnavailable("pack_unavailable", "Local pack missing, unreadable, or unsafe; no network fallback") from exc
    identity = hashlib.sha256(json.dumps({"namespace": manifest.NAMESPACE, "files": hashes,
        "runtime": versions}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return VerifiedPack(path / "prior", path / "decoder", identity, manifest.NAMESPACE)


def status(root: str | Path | None = None) -> dict:
    try:
        pack = verify_pack(root)
        return {"available": True, "modelId": manifest.MODEL_ID, "namespace": pack.namespace,
                "packIdentity": pack.identity, "inferenceAcceptance": "UNRUN"}
    except (PackUnavailable, ValueError, TypeError) as exc:
        return {"available": False, "modelId": manifest.MODEL_ID, "namespace": manifest.NAMESPACE,
                "code": getattr(exc, "code", "invalid_pack_path"), "reason": str(exc),
                "inferenceAcceptance": "UNRUN", "downloadsAttempted": False}
