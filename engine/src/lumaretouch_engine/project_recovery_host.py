"""Opt-in engine host. Shared dispatcher wiring is deliberately a separate gate.

capture_committed() must run at the serialized command boundary and return
(project, proof). proof supplies revision, original_path, native_receipts and
transaction_open, including every native mutation owner, not just history.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

from .project_recovery_store import RecoveryError


class RecoveryHost:
    def __init__(self, store, scheduler, *, current_project_id, capture_committed, emit):
        self.store = store
        self.scheduler = scheduler
        self.current_project_id = current_project_id
        self.capture_committed = capture_committed
        self.emit = emit
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='recovery-review')
        self.slots = threading.BoundedSemaphore(4)
        self.lock = threading.Lock()
        self.receipts = {}
        self.closed = False
        self.active = 0
        self.cancel = threading.Event()
        self.store.cancelled = self.cancel.is_set

    def blocks(self, name, payload):
        with self.lock:
            return self.active > 0 and name not in ('project_recovery', 'hello', 'ping', 'status', 'shutdown')

    def handle(self, request):
        request = dict(request)
        rid, pid = request.get('request_id'), request.get('project_id')
        action = request.get('action')
        if not isinstance(rid, str) or not 1 <= len(rid) <= 128:
            raise RecoveryError('Invalid recovery request identity')
        if action not in ('list', 'inspect', 'restore', 'discard', 'status', 'cancel', 'snapshot', 'relink', 'trash_list', 'restore_trash'):
            raise RecoveryError('Unknown recovery action')
        if not pid or pid != (self.current_project_id() or '__recovery__'):
            raise RecoveryError('Project changed; recovery request rejected')
        with self.lock:
            if rid in self.receipts:
                prior, result = self.receipts[rid]
                if prior != request:
                    raise RecoveryError('Recovery request identity conflict')
                if result is not None:
                    self.emit(result)
                return
            if self.closed or len(self.receipts) >= 256:
                raise RecoveryError('Recovery receipt capacity exhausted or host closed')
            if not self.slots.acquire(blocking=False):
                raise RecoveryError('Recovery work queue full')
            self.receipts = {key:value for key,value in self.receipts.items() if value[1] is None or value[0]['action'] in ('restore','restore_trash','discard','snapshot','relink')}
            if self.active == 0: self.cancel.clear()
            self.receipts[rid] = (request, None)
            self.active += 1
        # Snapshot capture must stay on the engine command owner, never the I/O
        # worker. Only encoded immutable bytes are handed to AutosaveScheduler.
        try:
            snapshot = None
            if action == 'snapshot':
                project, proof = self.capture_committed()
                snapshot = self.scheduler.offer(project, project_id=pid, kind='version_snapshot', **proof)
        except Exception as error:
            self._finish(request, {'success': False, 'error': str(error)})
            return
        if action == 'cancel':
            self.cancel.set()
            self.scheduler.cancel()
            self._finish(request, {'success':True, 'phase':'cancel_requested'})
            return
        self.pool.submit(self._work, request, snapshot)

    def _finish(self, request, outcome):
        result = {**outcome, 'event': 'project_recovery_result',
                  'request_id': request['request_id'], 'project_id': request['project_id'],
                  'action': request['action']}
        with self.lock:
            self.receipts[request['request_id']] = (request, result)
            self.active -= 1
        self.slots.release()
        self.emit(result)

    def _work(self, request, snapshot):
        mutation = request['action'] in ('restore','restore_trash','discard','relink')
        started = False
        try:
            if self.closed or self.cancel.is_set():
                raise InterruptedError('恢复操作已取消，候选保留')
            action, pid = request['action'], request['project_id']
            if pid != (self.current_project_id() or '__recovery__'):
                raise RecoveryError('Project switched before operation began')
            if action in ('inspect', 'restore', 'discard', 'restore_trash', 'relink'):
                review = self.store.inspect(request.get('candidate_id', ''), area=request.get('area', 'candidates'))
                if pid != '__recovery__' and review['receipt']['project_id'] != pid:
                    raise RecoveryError('Candidate belongs to another project')
            if mutation:
                if self.closed or self.cancel.is_set(): raise InterruptedError('恢复操作已取消')
                self.store.operation_started(request)
                started = True
            if action in ('list', 'trash_list'):
                area = 'trash' if action == 'trash_list' else 'candidates'
                result = {'candidates': self.store.list_candidates(None if pid == '__recovery__' else pid, area=area), 'usage': self.store.usage(), 'area':area, 'operations':self.store.operations(None if pid == '__recovery__' else pid)}
            elif action == 'inspect':
                result = {'review': review}
            elif action in ('restore', 'restore_trash'):
                result = self.store.restore_copy(request['candidate_id'], request['destination'],
                    confirmed=request.get('confirmed') is True,
                    reviewed_sha256=request.get('reviewed_sha256', ''), area=request.get('area', 'candidates'))
            elif action == 'relink':
                result = self.store.relink(request['candidate_id'], request['source_asset_id'], request['path'],
                    reviewed_sha256=request.get('reviewed_sha256', ''), confirmed=request.get('confirmed') is True,
                    area=request.get('area', 'candidates'))
            elif action == 'discard':
                result = self.store.discard(request['candidate_id'], confirmed=request.get('confirmed') is True)
            elif action == 'snapshot':
                result = snapshot
                # This receipt acknowledges enqueue only. UI must query status;
                # it must not present queued as a durable saved version.
            elif action == 'cancel':
                self.scheduler.cancel()
                result = self.scheduler.status()
            else:
                result = self.scheduler.status()
            outcome = {'success': True, **result}
        except Exception as error:
            outcome = {'success': False, 'error': str(error),
                'outcome_unknown': bool(started and isinstance(error, OSError)),
                'destination': request.get('destination')}
        if started:
            try: self.store.operation_finished(request, outcome)
            except Exception as error:
                outcome = {'success':False,'outcome_unknown':True,'error':'操作记录未确认：'+str(error),
                           'destination':request.get('destination')}
        self._finish(request, outcome)

    def close(self):
        with self.lock:
            self.closed = True
            self.cancel.set()
        self.pool.shutdown(wait=False, cancel_futures=False)
        return self.scheduler.shutdown()
