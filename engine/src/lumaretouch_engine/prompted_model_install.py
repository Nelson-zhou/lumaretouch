"""Explicit opt-in installer, separate from the offline image engine.

Native shell launches ``python -m lumaretouch_engine.prompted_model_install
--install`` using the chosen engine interpreter, never engine/bootstrap. This
module accepts no photo path. Import, status and inference never use network.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable
import urllib.request

from .prompted_model_manifest import (
    MODEL_ID, SOURCE_REVISION, CHECKPOINT_REVISION, CHECKPOINT_FILENAME,
    CHECKPOINT_SIZE_BYTES, CHECKPOINT_SHA256, CHECKPOINT_URL,
    CONFIG_RELATIVE_PATH, CONFIG_SHA256, CONFIG_SIZE_BYTES,
    SOURCE_REQUIREMENT, OPTIONAL_REQUIREMENTS, BUILD_REQUIREMENTS,
)

Progress = Callable[[dict], None]
Cancel = Callable[[], bool]
_INSTALL_LOCK = threading.Lock()


class ModelInstallError(RuntimeError):
    pass


class InstallCancelled(ModelInstallError):
    pass


def model_root(*, root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return data / "lumaretouch" / "optional-models" / MODEL_ID / SOURCE_REVISION


def runtime_path(*, root: Path | None = None) -> Path:
    return model_root(root=root) / "site-packages"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verified_file(path: Path, size: int, digest: str) -> bytes:
    # One bounded read: caller consumes these exact bytes, never reopens a path.
    with path.open("rb") as handle:
        data = handle.read(size + 1)
    if len(data) != size or _digest(data) != digest:
        raise ModelInstallError("Optional model bytes failed integrity verification: " + path.name)
    return data


def verified_checkpoint_bytes(*, root: Path | None = None) -> bytes:
    return _verified_file(model_root(root=root) / CHECKPOINT_FILENAME,
                          CHECKPOINT_SIZE_BYTES, CHECKPOINT_SHA256)


def verified_config_bytes(*, root: Path | None = None) -> bytes:
    return _verified_file(runtime_path(root=root) / CONFIG_RELATIVE_PATH,
                          CONFIG_SIZE_BYTES, CONFIG_SHA256)


def _inventory(site: Path) -> dict[str, str]:
    result = {}
    for path in sorted(site.rglob("*")):
        if path.is_symlink():
            raise ModelInstallError("Symlink in optional runtime")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            result[path.relative_to(site).as_posix()] = _digest(path.read_bytes())
    if not result:
        raise ModelInstallError("Optional runtime is empty")
    return result


def _check_source(site: Path) -> None:
    # PEP 610 records the original pinned archive URL plus the digest pip
    # computed at installation time. That digest is observed, not pre-reviewed.
    records = list(site.glob("*dist-info/direct_url.json"))
    matches = []
    for record in records:
        data = json.loads(record.read_text())
        if not isinstance(data, dict):
            raise ModelInstallError("Malformed optional runtime source record")
        if data.get("url") == SOURCE_REQUIREMENT:
            archive = data.get("archive_info", {})
            digest = archive.get("hashes", {}).get("sha256")
            if not digest and archive.get("hash", "").startswith("sha256="):
                digest = archive["hash"].partition("=")[2]
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ModelInstallError("SAM source archive has no installation SHA-256 record")
            matches.append(digest)
    if len(matches) != 1:
        raise ModelInstallError("SAM 2 runtime source archive is not the approved revision URL")


def installed_runtime_identity(*, root: Path | None = None) -> dict:
    base = model_root(root=root)
    receipt = json.loads((base / "receipt.json").read_text())
    if not isinstance(receipt, dict) or receipt.get("model_id") != MODEL_ID or receipt.get("code_revision") != SOURCE_REVISION:
        raise ModelInstallError("Optional runtime receipt identity mismatch")
    site = runtime_path(root=root)
    _check_source(site)
    inventory = _inventory(site)
    if inventory != receipt.get("runtime_files"):
        raise ModelInstallError("Optional runtime was modified; reinstall it explicitly")
    verified_config_bytes(root=root)
    return {"model_id": MODEL_ID, "code_revision": SOURCE_REVISION,
            "config_sha256": CONFIG_SHA256,
            "runtime_sha256": _digest(json.dumps(inventory, sort_keys=True).encode()),
            "checkpoint_sha256": CHECKPOINT_SHA256}


def activate_runtime(*, root: Path | None = None) -> dict:
    identity = installed_runtime_identity(root=root)
    site = runtime_path(root=root).resolve()
    # Do not adopt an already imported SAM implementation from another install.
    for name, module in tuple(sys.modules.items()):
        if name == "sam2" or name.startswith("sam2."):
            location = getattr(module, "__file__", None)
            if not location or not Path(location).resolve().is_relative_to(site):
                raise ModelInstallError("Another SAM runtime is loaded; restart the engine")
    if str(site) not in sys.path:
        sys.path.insert(0, str(site))  # no .pth execution / no site.addsitedir
    return identity


def model_status(*, root: Path | None = None) -> dict:
    base = model_root(root=root)
    status = {"model_id": MODEL_ID, "installed": False, "state": "not-installed",
              "download_bytes": CHECKPOINT_SIZE_BYTES, "license": "Apache-2.0",
              "code_revision": SOURCE_REVISION, "checkpoint_sha256": CHECKPOINT_SHA256}
    if not base.exists():
        return status
    try:
        identity = installed_runtime_identity(root=root)
        # Status does not allocate/hash 156 MB. Inference always verifies bytes.
        if (base / CHECKPOINT_FILENAME).stat().st_size != CHECKPOINT_SIZE_BYTES:
            raise ModelInstallError("Checkpoint missing or truncated")
        status.update(identity, installed=True, state="installed")
    except (OSError, ValueError, ModelInstallError) as error:
        status.update(state="invalid", error=str(error))
    return status


def _cancel(cancelled: Cancel | None) -> None:
    if cancelled and cancelled():
        raise InstallCancelled("Optional model installation cancelled")


def _emit(progress: Progress | None, phase: str, **values) -> None:
    if progress:
        progress({"model_id": MODEL_ID, "phase": phase, **values})


def _run(command: list[str], cancelled: Cancel | None, log: Path,
         build_site: Path | None = None) -> None:
    environment = os.environ.copy()
    environment.update(SAM2_BUILD_CUDA="0", PIP_DISABLE_PIP_VERSION_CHECK="1",
                       PIP_NO_INPUT="1", PYTHONNOUSERSITE="1")
    if build_site is not None:
        # Build subprocesses see isolated tools, while Torch remains supplied by
        # the selected interpreter. Never install build requirements into base.
        environment["PYTHONPATH"] = str(build_site.resolve())
    # This cap is shared across pip invocations, not per subprocess.
    # Continue draining after reaching it so a verbose child cannot deadlock.
    log_limit = 1024 * 1024
    with log.open("a+b") as output:
        output.seek(0, os.SEEK_END)
        retained = min(output.tell(), log_limit)
        output.truncate(retained)
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, bufsize=0,
                                   env=environment, start_new_session=True)
        started = time.monotonic()
        completed = False
        try:
            assert process.stdout is not None
            os.set_blocking(process.stdout.fileno(), False)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                pipe_open = True
                while True:
                    _cancel(cancelled)
                    if time.monotonic() - started > 1800:
                        raise ModelInstallError("Optional runtime installer timed out")
                    exited = process.poll() is not None
                    events = selector.select(0 if exited else 0.2) if pipe_open else ()
                    if events:
                        # Bounded work per iteration keeps cancellation responsive
                        # even if the child writes stdout continuously.
                        try:
                            chunk = os.read(process.stdout.fileno(), 64 * 1024)
                        except BlockingIOError:
                            chunk = None
                        if chunk == b"":
                            selector.unregister(process.stdout)
                            pipe_open = False
                        elif chunk:
                            keep = chunk[:max(0, log_limit - retained)]
                            output.write(keep)
                            retained += len(keep)
                    elif exited:
                        # Do not wait indefinitely for an inherited pipe held by
                        # a descendant after the pip process has already exited.
                        break
                    elif not pipe_open:
                        time.sleep(0.2)
                if process.returncode:
                    raise ModelInstallError("Optional runtime installation failed (exit %s); check Python/pip and network" % process.returncode)
                completed = True
        finally:
            if not completed or process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
            if process.stdout is not None:
                process.stdout.close()


def _base_dependencies() -> None:
    for name, minimum in (("torch", (2, 5, 1)), ("torchvision", (0, 20, 1)),
                          ("numpy", (1, 24, 4)), ("Pillow", (9, 4, 0))):
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ModelInstallError("Install the explicitly chosen engine variant first; missing " + name) from error
        digits = tuple(int(part) for part in re.match(r"\d+(?:\.\d+)*", version).group().split("."))
        if digits < minimum:
            raise ModelInstallError("Existing engine dependency is too old: " + name + "; this installer never replaces it")


class _HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise ModelInstallError("Refusing non-HTTPS model redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def install_model(*, root: Path | None = None, cancelled: Cancel | None = None,
                  progress: Progress | None = None) -> dict:
    """Network/install side effects occur ONLY on an explicit call to this function.

    Call from a dedicated native-shell process, not the seccomp-offline engine.
    Existing good installation is immutable. Invalid installs need explicit user
    removal before retry; never delete someone else's runtime automatically.
    """
    if not _INSTALL_LOCK.acquire(blocking=False):
        raise ModelInstallError("Another optional-model install is in progress")
    staging = None
    lock = None
    try:
        _cancel(cancelled)
        base = model_root(root=root)
        if base.exists():
            status = model_status(root=root)
            if not status["installed"]:
                raise ModelInstallError("Existing optional model is invalid; remove it explicitly before reinstalling")
            verified_checkpoint_bytes(root=root)
            return status
        _base_dependencies()
        base.parent.mkdir(parents=True, exist_ok=True)
        lock_path = base.parent / (base.name + ".install-lock")
        try:
            lock_path.mkdir()
        except FileExistsError as error:
            raise ModelInstallError("Install already running or stale install lock; no changes made") from error
        lock = lock_path
        staging = Path(tempfile.mkdtemp(prefix=".sam2-install-", dir=base.parent))
        site = staging / "site-packages"
        log = staging / "install.log"
        _emit(progress, "runtime", message="Installing isolated SAM runtime; preserving engine Torch variant")
        pip = [sys.executable, "-m", "pip", "--isolated", "install", "--no-deps",
               "--no-compile", "--target", str(site), "--index-url", "https://pypi.org/simple"]
        _run(pip + ["--only-binary=:all:"] + list(BUILD_REQUIREMENTS), cancelled, log)
        _run(pip + ["--no-build-isolation"] + list(OPTIONAL_REQUIREMENTS),
             cancelled, log, build_site=site)
        _run(pip + ["--no-build-isolation", SOURCE_REQUIREMENT],
             cancelled, log, build_site=site)
        _check_source(site)
        _verified_file(site / CONFIG_RELATIVE_PATH, CONFIG_SIZE_BYTES, CONFIG_SHA256)
        _cancel(cancelled)
        _emit(progress, "checkpoint", downloaded_bytes=0, total_bytes=CHECKPOINT_SIZE_BYTES)
        digest = hashlib.sha256()
        count = 0
        target = staging / CHECKPOINT_FILENAME
        opener = urllib.request.build_opener(_HTTPSRedirect())
        with opener.open(CHECKPOINT_URL, timeout=30) as response, target.open("xb") as output:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) != CHECKPOINT_SIZE_BYTES:
                raise ModelInstallError("Checkpoint response length differs from reviewed metadata")
            download_started = time.monotonic()
            while True:
                if time.monotonic() - download_started > 3600:
                    raise ModelInstallError("Checkpoint download timed out")
                _cancel(cancelled)
                chunk = response.read(min(1024 * 1024, CHECKPOINT_SIZE_BYTES - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                if count > CHECKPOINT_SIZE_BYTES:
                    raise ModelInstallError("Checkpoint exceeds reviewed byte limit")
                output.write(chunk)
                digest.update(chunk)
                _emit(progress, "checkpoint", downloaded_bytes=count, total_bytes=CHECKPOINT_SIZE_BYTES)
            output.flush()
            os.fsync(output.fileno())
        if count != CHECKPOINT_SIZE_BYTES or digest.hexdigest() != CHECKPOINT_SHA256:
            raise ModelInstallError("Downloaded checkpoint failed size/SHA-256 verification")
        inventory = _inventory(site)
        receipt = {"model_id": MODEL_ID, "code_revision": SOURCE_REVISION,
                   "checkpoint_revision": CHECKPOINT_REVISION,
                   "checkpoint_sha256": CHECKPOINT_SHA256,
                   "runtime_files": inventory, "config_sha256": CONFIG_SHA256}
        (staging / "receipt.json").write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
        _cancel(cancelled)
        if base.exists():
            raise ModelInstallError("Optional model destination appeared during install")
        staging.rename(base)  # same filesystem; never publish a partial install
        staging = None
        _emit(progress, "complete", installed=True)
        return model_status(root=root)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        try:
            if lock is not None:
                lock.rmdir()
        finally:
            _INSTALL_LOCK.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicit optional SAM 2.1 Tiny installer")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--install", action="store_true")
    choice.add_argument("--status", action="store_true")
    args = parser.parse_args()
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    def emit(value: dict) -> None:
        print(json.dumps(value, ensure_ascii=False), flush=True)
    try:
        emit(install_model(cancelled=stopped.is_set, progress=emit) if args.install else model_status())
        return 0
    except Exception as error:
        emit({"model_id": MODEL_ID, "state": "cancelled" if isinstance(error, InstallCancelled) else "error", "error": str(error)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
