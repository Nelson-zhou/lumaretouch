"""Owns inspection preparation/worker lifecycle, independent from Engine command routing.

Dependencies are narrow callbacks: document metadata, heavy-work busy state,
owned export snapshot creation, and protocol event emission. This module never
owns the command reader, history, project/session state, or renderer pipeline.
"""
import os
from typing import Callable

class InspectionController:
    def __init__(self, *, document: Callable[[], str | None],
                 proxy_dimensions: Callable[[], tuple[int, int]], busy: Callable[[], bool],
                 capture_snapshot: Callable[[], dict], emit: Callable[[dict], None]):
        self._document = document
        self._proxy_dimensions = proxy_dimensions
        self._busy = busy
        self._capture_snapshot = capture_snapshot
        self._emit = emit
        self.tick_bytes = 1024 * 1024
        self.max_asset_bytes = 512 * 1024 * 1024
        self.tx = self.result = self.request_id = self.request = self.job = None
        self.render_config = self.error = None
        self.last_id = 0
        self.state = "idle"

    @property
    def worker_running(self):
        return self.job is not None and self.job.running

    def fail_tick(self, error):
        self.cancel(notify=False)
        self.state = "failed"
        self.emit_status(str(error))

    def emit_status(self, error=None):
        tx = getattr(self, "tx", None)
        result = getattr(self, "result", None)
        job = getattr(self, "job", None)
        detail = error or (job.error if job is not None else None)
        if detail is not None:
            self.error = detail
        asset_bytes = tx.asset_bytes if tx is not None else (result.asset_bytes if result else (job.asset_bytes if job is not None else 0))
        config = getattr(self, "render_config", None) or {}
        self._emit({"event": "inspection_snapshot", "preparation_only": getattr(self, "render_config", None) is None,
              "epoch": config.get("epoch"), "ticket": config.get("ticket"),
              "request_id": getattr(self, "request_id", None),
              "state": getattr(self, "state", "idle"),
              "asset_bytes": asset_bytes,
              "copied_bytes": tx.copied_bytes if tx is not None else asset_bytes,
              "result_path": os.path.join(job.directory, "result.lrif") if job is not None and job.state == "ready" else None,
              "error": getattr(self, "error", None)})

    def cancel(self, reason="invalidated", *, notify=True):
        tx = getattr(self, "tx", None)
        job = getattr(self, "job", None)
        active = tx is not None or getattr(self, "result", None) is not None or job is not None
        if job is not None:
            job.cancel()
            if not job.running:
                job.cleanup()
                self.job = None
        if tx is not None:
            tx.cancel()
        self.tx = None
        self.result = None
        self.request = None
        if active:
            self.state = "cancelling" if job is not None and job.running else "cancelled"
            if notify:
                self.emit_status(reason)

    def tick(self):
        job = getattr(self, "job", None)
        if job is not None:
            before = job.state
            job.tick(self.tick_bytes)
            self.state = job.state
            if job.state != before:
                self.emit_status()
            if job.state in ("cancelled", "failed") and not job.running:
                self.job = None
            return
        tx = getattr(self, "tx", None)
        if tx is None:
            return
        if tx.advance(self.tick_bytes):
            self.result = tx.take_result()
            self.tx = None
            config = getattr(self, "render_config", None)
            if config is not None:
                from .inspection_job import InspectionJob
                request = self.request
                self.job = InspectionJob(self.result,
                    request["path"], request["source_identity"], config, request["max_asset_bytes"])
                self.result = None
                self.state = "spooling"
            else:
                self.state = "ready"
            self.emit_status()

    def pending(self):
        job = getattr(self, "job", None)
        return (getattr(self, "tx", None) is not None or
                (job is not None and job.state in ("spooling", "rendering", "cancelling")))

    def shutdown(self):
        self.cancel("engine_exit", notify=False)
        job = getattr(self, "job", None)
        if job is not None:
            if job.process is not None:
                job.process.wait()  # SIGKILL sent by cancel; never abandon child/lease.
            job.cleanup()
            self.job = None

    def handle_command(self, p: dict):
        try:
            return self._handle(p)
        except Exception as exc:
            if p.get("action", "status") == "start":
                # Rejection belongs to the submitted identity, not the previous
                # active job. The host must release a never-started reservation
                # even when export/benchmark/validation rejects before registration.
                config = p.get("render") if type(p.get("render")) is dict else {}
                epoch = config.get("epoch")
                ticket = config.get("ticket")
                request = p.get("request_id")
                self._emit({"event": "inspection_snapshot", "state": "failed", "rejected": True,
                      "preparation_only": not bool(config),
                      "request_id": request if type(request) is str and len(request) <= 20 else None,
                      "epoch": epoch if type(epoch) is str and len(epoch) == 32 else None,
                      "ticket": ticket if type(ticket) is list and len(ticket) == 5 and
                          all(type(v) is str and len(v) <= 20 for v in ticket) else None,
                      "asset_bytes": 0, "copied_bytes": 0, "result_path": None,
                      "error": str(exc)[:2000]})
            raise

    def _handle(self, p: dict):
        unknown = set(p) - {"cmd", "action", "request_id", "max_asset_bytes", "render"}
        if unknown:
            raise ValueError(f"inspection_snapshot unknown fields: {sorted(unknown)}")
        action = p.get("action", "status")
        if action == "status":
            self.emit_status()
            return
        request_id = p.get("request_id")
        if (not isinstance(request_id, str) or not request_id.isascii() or
            not request_id.isdecimal() or len(request_id) > 20 or
            request_id.startswith("0") or not 0 < int(request_id) < 2**64):
            raise ValueError("inspection_snapshot requires a canonical nonzero u64 request_id string")
        if action in ("cancel", "release"):
            if request_id != getattr(self, "request_id", None):
                raise ValueError("inspection_snapshot request identity mismatch")
            self.cancel(action, notify=False)
            if getattr(self, "job", None) is None:
                self.state = "cancelled" if action == "cancel" else "released"
            self.emit_status()
            return
        if action != "start":
            raise ValueError("inspection_snapshot action must be start/status/cancel/release")
        limit = p.get("max_asset_bytes")
        if type(limit) is not int or not 0 <= limit <= self.max_asset_bytes:
            raise ValueError("inspection_snapshot needs an admitted asset budget <=512MiB")
        document = self._document()
        if document is None:
            raise ValueError("inspection_snapshot requires a loaded document")
        if self._busy():
            raise ValueError("inspection_snapshot is busy with export/benchmark")
        if int(request_id) <= getattr(self, "last_id", 0):
            raise ValueError("inspection_snapshot request IDs must increase")
        config = p.get("render")
        if config is not None:
            from .inspection_job import validate_config
            config = validate_config(config)
            if config["ticket"][0] != request_id:
                raise ValueError("Inspection render ticket differs from request ID")
        self.cancel("superseded")
        if getattr(self, "job", None) is not None:
            raise ValueError("Previous inspection worker is still exiting; retry after cancellation")
        self.render_config = config
        self.error = None
        self.last_id = int(request_id)
        self.request_id = request_id
        self.request = {"path": document,
            "proxy_hw": self._proxy_dimensions(), "request_id": request_id}
        try:
            if config is not None:
                from .inspection_worker import source_identity
                self.request.update(source_identity=source_identity(document),
                                                         max_asset_bytes=limit)
            from .render_snapshot import SnapshotTransaction
            snap = self._capture_snapshot()
            self.tx = SnapshotTransaction(snap, max_asset_bytes=limit)
        except Exception as exc:
            self.state = "failed"
            self.error = str(exc)
            raise
        self.state = "copying"
        self.emit_status()

