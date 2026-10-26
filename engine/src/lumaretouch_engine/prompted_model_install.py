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


def _base_identity() -> dict:
    _base_dependencies()
    executable = Path(sys.executable).resolve()
    info = executable.stat()
    return {"python":str(executable), "prefix":sys.prefix, "version":sys.version,
            "executable_stamp":[info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns],
            "packages":{name:{"version":importlib.metadata.version(name),
                              "location":str(importlib.metadata.distribution(name).locate_file("")),
                              "record_sha256":_digest((importlib.metadata.distribution(name).read_text("RECORD") or "").encode())}
                        for name in ("torch","torchvision","numpy","Pillow")}}


def _disclosure() -> dict:
    return {"extension_id":"id-background-prompted-v1", "model_id":MODEL_ID,
            "download_bytes":CHECKPOINT_SIZE_BYTES, "runtime_download_separate":True,
            "disk_free_floor_bytes":1024**3, "cpu_probe_address_space_limit_bytes":8*1024**3,
            "cpu_probe_available_memory_floor_bytes":4*1024**3,
            "license":"Apache-2.0", "code_revision":SOURCE_REVISION,
            "checkpoint_sha256":CHECKPOINT_SHA256, "ready":False,
            "readiness":"unchecked", "checkpoint_verified":False,
            "automatic_base_runtime_setup":False, "tested_devices":[],
            "readiness_scope":"bounded CPU fixture only; not portrait quality, performance or GPU acceptance"}


def model_status(*, root: Path | None = None) -> dict:
    """Offline status: hash actual bytes, never download, import SAM, or infer."""
    from .curated_extension_download import partial_size
    from .curated_extension_probe import PROBE
    base = model_root(root=root)
    status = {**_disclosure(), "installed":False, "state":"not-installed"}
    try:
        status["resume_bytes"] = partial_size(base)
        base_identity = _base_identity()
    except (OSError, ValueError, ModelInstallError) as error:
        status.update(state="unsupported", error=str(error))
        return status
    if not base.exists():
        return status
    try:
        identity = installed_runtime_identity(root=root)
        verified_checkpoint_bytes(root=root)
        status.update(identity, installed=True, state="installed", checkpoint_verified=True)
        proof_path = base / "readiness.json"
        if proof_path.exists():
            with proof_path.open("rb") as stream:
                raw = stream.read(65537)
            if len(raw)>65536:
                raise ModelInstallError("Readiness receipt exceeds its budget")
            proof = json.loads(raw)
            if proof == {"probe":PROBE,"runtime":identity,"base":base_identity}:
                status.update(ready=True, readiness="cpu-probe-passed")
            else:
                status.update(readiness="stale", error="Runtime changed; explicitly recheck CPU readiness")
    except (OSError, ValueError, ModelInstallError) as error:
        status.update(state="invalid", ready=False, error=str(error))
    return status


def check_readiness(*, root: Path | None = None, cancelled=None, progress=None, _owner_held=False) -> dict:
    """Explicit bounded CPU self-check. No user photo, GPU fallback, or downloads."""
    from .curated_extension_probe import PROBE
    base = model_root(root=root)
    if not _owner_held:
        _base_dependencies()
        lock = _lock_model(base)
        try:
            return check_readiness(root=root,cancelled=cancelled,progress=progress,_owner_held=True)
        finally:
            lock.close()
    identity = installed_runtime_identity(root=root)
    base_identity = _base_identity()
    verified_checkpoint_bytes(root=root)
    _cancel(cancelled)
    # A failed recheck must not leave an older passing receipt advertised.
    (base/"readiness.json").unlink(missing_ok=True)
    _emit(progress,"readiness",installed=True,ready=False,readiness="checking-cpu")
    with tempfile.TemporaryDirectory(prefix=".sam-readiness-", dir=base.parent) as directory:
        output = Path(directory)/"result.json"
        _run([sys.executable,"-m","lumaretouch_engine.curated_extension_probe",
              "--root",str(base.resolve()),"--output",str(output),"--parent-pid",str(os.getpid())],
             cancelled,Path(directory)/"probe.log",timeout=240)
        with output.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw)>65536 or json.loads(raw) != {"probe":PROBE,"runtime":identity}:
            raise ModelInstallError("CPU readiness result does not match the verified runtime")
        _cancel(cancelled)
        if installed_runtime_identity(root=root) != identity or _base_identity()!=base_identity:
            raise ModelInstallError("Runtime changed during CPU readiness check")
        verified_checkpoint_bytes(root=root)
        receipt = Path(directory)/"readiness.json"
        receipt.write_text(json.dumps({"probe":PROBE,"runtime":identity,"base":base_identity},sort_keys=True))
        os.replace(receipt,base/"readiness.json")
    return model_status(root=root)


def _cancel(cancelled: Cancel | None) -> None:
    if cancelled and cancelled():
        raise InstallCancelled("Optional model installation cancelled")


def _emit(progress: Progress | None, phase: str, **values) -> None:
    if progress:
        progress({"model_id": MODEL_ID, "phase": phase, **values})


def _run(command: list[str], cancelled: Cancel | None, log: Path,
         build_site: Path | None = None, *, timeout=1800) -> None:
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
                    if time.monotonic() - started > timeout:
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
                    output.flush()
                    output.seek(max(0,retained-2000))
                    detail = output.read(2000).decode("utf-8",errors="replace")
                    raise ModelInstallError("Optional runtime operation failed (exit %s): %s" % (process.returncode,detail))
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
    if sys.platform != "linux" or sys.version_info < (3,10):
        raise ModelInstallError("Curated setup currently supports Linux Python 3.10+ only; no base runtime auto-install")
    for name, minimum in (("torch", (2, 5, 1)), ("torchvision", (0, 20, 1)),
                          ("numpy", (1, 24, 4)), ("Pillow", (9, 4, 0))):
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ModelInstallError("Install the explicitly chosen engine variant first; missing " + name) from error
        match = re.match(r"\d+(?:\.\d+)*", version)
        if not match:
            raise ModelInstallError("Unrecognized engine dependency version: "+name)
        digits = tuple(int(part) for part in match.group().split("."))
        if digits < minimum:
            raise ModelInstallError("Existing engine dependency is too old: " + name + "; this installer never replaces it")


def _lock_model(base):
    """Shared by explicit install and check; status remains read-only."""
    import fcntl
    base.parent.mkdir(parents=True,exist_ok=True)
    if (base.parent/(base.name+".install-lock")).exists():
        raise ModelInstallError("Legacy installer lock exists; verify the older installer has exited before removing its lock")
    fd = os.open(base.parent/(base.name+".install-owner"),
                 os.O_CREAT|os.O_RDWR|getattr(os,"O_NOFOLLOW",0),0o600)
    lock = os.fdopen(fd,"a+b")
    try:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except Exception as error:
        lock.close()
        raise ModelInstallError("Another optional-model operation owns this version") from error
    return lock


def install_model(*, root: Path | None = None, cancelled: Cancel | None = None,
                  progress: Progress | None = None) -> dict:
    """Explicit install/retry, preserving old bytes until candidate CPU readiness.

    The single reviewed checkpoint is shared with the existing prompted runtime;
    partial transfers survive cancellation. Runtime staging is discarded on error.
    An invalid old version is retained as a backup, never recursively removed.
    """
    from .curated_extension_download import acquire
    if not _INSTALL_LOCK.acquire(blocking=False):
        raise ModelInstallError("Another optional-model install is in progress")
    staging = None
    lock = None
    try:
        _cancel(cancelled)
        base = model_root(root=root)
        _base_dependencies()
        lock = _lock_model(base)
        if base.is_symlink():
            raise ModelInstallError("Optional model destination cannot be a symlink")
        if base.exists():
            status = model_status(root=root)
            if status["installed"] and status["state"]=="installed":
                return check_readiness(root=root,cancelled=cancelled,progress=progress,_owner_held=True)
        if shutil.disk_usage(base.parent).free < 1024**3:
            raise ModelInstallError("Curated setup needs at least 1 GiB free staging space; existing models retained")
        checkpoint = acquire(base,emit=lambda phase,**values:_emit(progress,phase,**values),
                             cancelled=lambda:_cancel(cancelled))
        _cancel(cancelled)
        staging = Path(tempfile.mkdtemp(prefix=".sam2-install-", dir=base.parent))
        site = staging / "site-packages"
        log = staging / "install.log"
        _emit(progress, "runtime", checkpoint_verified=True,
              message="Preparing isolated SAM components; existing engine Torch variant is unchanged")
        pip = [sys.executable, "-m", "pip", "--isolated", "install", "--no-deps",
               "--no-compile", "--target", str(site), "--index-url", "https://pypi.org/simple"]
        _run(pip + ["--only-binary=:all:"] + list(BUILD_REQUIREMENTS), cancelled, log)
        _run(pip + ["--no-build-isolation"] + list(OPTIONAL_REQUIREMENTS),
             cancelled, log, build_site=site)
        _run(pip + ["--no-build-isolation", SOURCE_REQUIREMENT],
             cancelled, log, build_site=site)
        _check_source(site)
        _verified_file(site / CONFIG_RELATIVE_PATH, CONFIG_SIZE_BYTES, CONFIG_SHA256)
        shutil.copyfile(checkpoint,staging/CHECKPOINT_FILENAME)
        _verified_file(staging/CHECKPOINT_FILENAME,CHECKPOINT_SIZE_BYTES,CHECKPOINT_SHA256)
        receipt = {"model_id": MODEL_ID, "code_revision": SOURCE_REVISION,
                   "checkpoint_revision": CHECKPOINT_REVISION,
                   "checkpoint_sha256": CHECKPOINT_SHA256,
                   "runtime_files": _inventory(site), "config_sha256": CONFIG_SHA256}
        (staging / "receipt.json").write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
        # Probe the candidate in its own process BEFORE publishing any replacement.
        candidate = check_readiness(root=staging,cancelled=cancelled,progress=progress,_owner_held=True)
        if not candidate.get("ready"):
            raise ModelInstallError("Candidate runtime did not pass bounded CPU readiness")
        _cancel(cancelled)
        backup = None
        if base.exists():
            backup = base.parent/(base.name+".retained-"+str(time.time_ns()))
            base.rename(backup)
        try:
            staging.rename(base)
        except Exception:
            if backup is not None and not base.exists():
                backup.rename(base)
            raise
        staging = None
        result = model_status(root=root)
        if backup is not None:
            result["retained_previous_version"] = str(backup)
        _emit(progress,"complete",installed=True,ready=result.get("ready",False))
        return result
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        if lock is not None:
            lock.close()
        _INSTALL_LOCK.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicit optional SAM 2.1 Tiny installer")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--install", action="store_true")
    choice.add_argument("--status", action="store_true")
    choice.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    def emit(value: dict) -> None:
        print(json.dumps(value, ensure_ascii=False), flush=True)
    try:
        if args.install:
            result = install_model(cancelled=stopped.is_set, progress=emit)
        elif args.check:
            result = check_readiness(cancelled=stopped.is_set, progress=emit)
        else:
            result = model_status()
        emit(result)
        return 0
    except Exception as error:
        emit({"model_id": MODEL_ID, "state": "cancelled" if isinstance(error, InstallCancelled) else "error", "error": str(error)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
