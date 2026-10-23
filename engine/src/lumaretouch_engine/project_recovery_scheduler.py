"""One writer + one coalesced pending snapshot, independent of preview rendering.

Only the serialized engine command boundary may call offer(). It must supply a
complete encoded project, committed history revision and native receipt fence.
This class never reads the live engine graph on its background worker.
"""
from __future__ import annotations

import contextlib
import json
import threading
import time

from .project_recovery_store import RecoveryError, no_dropped
from . import creative_document_storage as CS


class AutosaveScheduler:
    def __init__(self, store, *, interval_seconds=30.0, snapshot_bytes=64_000_000):
        if interval_seconds < 1 or snapshot_bytes < 1:
            raise RecoveryError('Invalid autosave limits')
        self.store = store
        self.interval = float(interval_seconds)
        self.snapshot_bytes = int(snapshot_bytes)
        self.cv = threading.Condition(threading.RLock())
        self.epoch = 0
        self.project_id = None
        self.pending = None
        self.closed = False
        self.busy = False
        self.last_write = 0.0
        self.revision = -1
        self.state = {'phase': 'idle', 'notice': '尚无已提交编辑需要自动保存'}
        self.thread = threading.Thread(target=self._run, name='project-autosave', daemon=True)
        self.thread.start()

    def switch(self, project_id):
        """Invalidate queued/inflight old work; keep existing disk candidates."""
        with self.cv:
            if self.closed:
                raise RecoveryError('Autosave scheduler is shut down')
            self.epoch += 1
            self.project_id = project_id
            self.pending = None
            self.revision = -1
            self.last_write = 0.0
            self.state = {'phase': 'idle', 'project_id': project_id}
            self.cv.notify_all()

    def offer(self, project: dict, *, project_id: str, revision: int,
              original_path: str | None, native_receipts: list,
              transaction_open: bool, kind='autosave') -> dict:
        """Caller owns serialization lock until this returns.

        Encoding happens on the engine command owner, never the renderer/UI
        event thread. Frozen bytes sever all aliases before worker admission.
        Coalescing replaces only queued complete snapshots, never history entries.
        """
        if kind not in ('autosave', 'version_snapshot'):
            raise RecoveryError('Invalid snapshot kind')
        if transaction_open or any(r.get('phase') not in ('committed', 'rejected', 'cancelled')
                                   for r in native_receipts):
            raise RecoveryError('Autosave fenced by unfinished/unknown edit transaction')
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise RecoveryError('Committed history revision required')
        if project.get('project_id') != project_id:
            raise RecoveryError('Project capture identity mismatch')
        with self.cv:
            capture_epoch = self.epoch
            if self.closed or project_id != self.project_id:
                raise RecoveryError('Project is not active')
        no_dropped(project)
        # The existing limit governs the manifest, not base64-expanded float
        # pixels. Immutable byte chunks travel out of band under the unchanged
        # creative-store and recovery disk budgets, never a lossy codec.
        try:
            frozen = CS.freeze(project, self.snapshot_bytes)
        except ValueError as error:
            raise RecoveryError(f'Autosave snapshot unavailable: {error}') from error
        # Freeze request receipts too. They are evidence, not commands to replay.
        receipts = json.loads(json.dumps(native_receipts, allow_nan=False))
        metadata = {'revision': revision, 'original_path': original_path,
                    'native_receipts': receipts, 'kind': kind,
                    'receipt_policy': 'never_replay', 'capture_complete': True}
        with self.cv:
            if self.closed or project_id != self.project_id or capture_epoch != self.epoch:
                raise RecoveryError('Project switched or scheduler stopped during capture')
            if revision < self.revision:
                raise RecoveryError('Stale committed revision')
            if self.pending is not None and (kind == 'version_snapshot' or self.pending[2]['kind'] == 'version_snapshot'):
                raise RecoveryError('Named snapshot backpressure: wait for existing write')
            self.revision = revision
            self.pending = (self.epoch, frozen, metadata)
            self.state = {'phase': 'queued', 'project_id': project_id, 'revision': revision}
            self.cv.notify_all()
            return dict(self.state)

    @contextlib.contextmanager
    def _guard(self, epoch):
        with self.cv:
            if self.closed or epoch != self.epoch:
                raise RecoveryError('Autosave cancelled before commit; original untouched')
            yield

    def _run(self):
        while True:
            with self.cv:
                while not self.closed:
                    if self.pending is None:
                        self.cv.wait()
                        continue
                    delay = self.interval - (time.monotonic() - self.last_write)
                    if delay > 0 and self.pending[2]['kind'] == 'autosave':
                        self.cv.wait(delay)
                        continue
                    break
                if self.closed:
                    return
                epoch, frozen, metadata = self.pending
                self.pending = None
                self.busy = True
                self.state = {'phase': 'writing', 'project_id': self.project_id,
                              'revision': metadata['revision']}
            try:
                receipt = self.store.publish(frozen, metadata, lambda: self._guard(epoch))
                outcome = {'phase': 'saved', 'receipt': receipt}
            except Exception as error:
                # Includes post-rename fsync failure: never report durable success
                # or retry this write automatically; inspect candidates on reopen.
                outcome = {'phase': 'blocked', 'reason': str(error),
                           'notice': '自动保存未确认，原工程与已有恢复版本保留；请检查磁盘候选'}
            with self.cv:
                self.busy = False
                self.last_write = time.monotonic()
                if epoch == self.epoch:
                    self.state = outcome
                self.cv.notify_all()

    def status(self):
        with self.cv:
            return {**self.state, 'pending': self.pending is not None, 'writing': self.busy,
                    'closed': self.closed, 'epoch': self.epoch}

    def cancel(self):
        with self.cv:
            self.epoch += 1
            self.pending = None
            self.state = {'phase': 'cancelled', 'notice': '已提交恢复版本仍保留'}
            self.cv.notify_all()

    def shutdown(self, *, timeout_seconds=2.0):
        """Bounded stop, not a claim that dirty work was saved. Caller prompts.

        A write already inside atomic commit finishes before close admission;
        another write is fenced and its incomplete staging is never a candidate.
        """
        with self.cv:
            self.closed = True
            self.epoch += 1
            self.pending = None
            self.cv.notify_all()
        self.thread.join(timeout=max(0.0, timeout_seconds))
        return {'stopped': not self.thread.is_alive(), 'flushed': False,
                'notice': '退出不等于保存；仍有未保存编辑时必须保留关闭确认'}
