"""Serialized committed-boundary adapter; never blesses history-finally state."""
import os
import threading
import time
from .project_recovery_store import RecoveryStore, RecoveryError
from .project_recovery_scheduler import AutosaveScheduler
from .project_recovery_host import RecoveryHost
from .project_recovery_capture import capture

_local = threading.local()


def observe(event):
    boundary = getattr(_local, 'boundary', None)
    if boundary is not None:
        if (event.get('event') == 'error' or event.get('success') is False
            or event.get('outcome_unknown') or event.get('requires_reload')
            or event.get('status') in ('failed', 'unknown', 'partial', 'blocked')
            or event.get('requires_readback')):
            boundary['failed'] = True


def begin(engine, message, handler):
    boundary = {'failed': False, 'returned': False, 'started': False, 'message': message}
    _local.boundary = boundary
    def wrapped(payload):
        boundary['started'] = True
        value = handler(payload)
        boundary['returned'] = True
        return value
    return boundary, wrapped


def finish(engine, boundary, error=None):
    _local.boundary = None
    if boundary is None:
        return
    message = boundary['message']
    # Spill preview renders isolated candidates only. Even a rejected or failed
    # preview cannot dirty/taint committed project state or advance autosave.
    if message.get('cmd') == 'background' and message.get('action') in ('id_spill_preview', 'id_spill_paint_source', 'id_original_shadow_paint_source','id_original_shadow_preview'):
        return
    from .creative_transfer_host import inventory_read_only
    if inventory_read_only(message):return
    if not boundary['started'] or message.get('cmd') in ('project_recovery', 'canvas_guides'):
        return
    runtime = engine.__dict__.get('_project_recovery_runtime')
    if runtime is None:
        return
    # Errors can occur after a partial mutation even if a handler returns. Keep
    # taint until a successful explicit project open/create establishes a base.
    if error or boundary['failed'] or not boundary['returned']:
        runtime.tainted = True
        runtime.reason = '上次命令未确认完整提交；请保存前检查，或重新打开已确认的工程'
    elif message.get('cmd') in engine.EDIT_CMDS or message.get('cmd') in (
        'project','session','history','virtual_copy','managed_import','source_relocation',
        'people','batch','primary_calibration','colour_editor','selective_colour','colour_grading',
        'photo_grain','photo_detail','extended_tone','shoulder_shape','leg_shape','arm_shape',
        'waist_shape','leg_length','neck_shape','torso_length','waist_length','custom_lut','semantic_colour','creative_document','common_background'):
        if message.get('action') not in ('state','query','status','receipt','list','context'):
            runtime.revision += 1


class Runtime:
    def __init__(self, engine, emit):
        self.engine = engine
        self.store = RecoveryStore(os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'), 'lumaretouch', 'recovery'))
        self.scheduler = AutosaveScheduler(self.store)
        self.revision = 0
        self.last_offered = -1
        self.last_checkpoint = 0.0
        self.tainted = False
        self.reason = None
        self.native_receipts = []
        self.host = RecoveryHost(self.store, self.scheduler, current_project_id=self.project_id,
            capture_committed=self.capture, emit=emit)
        self.switch()

    def project_id(self):
        return (self.engine._project or {}).get('project_id')

    def switch(self):
        self.scheduler.switch(self.project_id())
        self.revision += 1
        self.last_offered = -1
        self.tainted = False
        self.reason = None

    def guard(self):
        if self.tainted:
            raise RecoveryError(self.reason)
        e = self.engine
        for name, owner in tuple(e.__dict__.items()):
            if name.startswith('_project_recovery') or owner is None:
                continue
            # Every asynchronous owner is checked, including future owners that
            # implement the existing active/pending/uncertain/job conventions.
            if name in ('bench', '_export', '_thumbs', '_picks'):
                if owner.is_alive(): raise RecoveryError('后台任务尚未完成：' + name)
            if not (name.endswith(('_controller', '_owner', '_host')) or name == '_batch_sync'):
                continue
            for field in ('active', 'uncertain', 'pending', 'job', 'worker_running'):
                value = getattr(owner, field, None)
                if not callable(value) and value:
                    raise RecoveryError('等待操作边界或回执：' + name + '.' + field)
            if name.endswith('_preview_owner') or name in ('_local_grade_live_owner','_semantic_colour_owner'):
                if getattr(owner,'latest',None) is not None or getattr(owner,'session',None) is not None:
                    raise RecoveryError('请先接受或取消当前预览：'+name)
            worker = getattr(owner, 'worker', None)
            if worker is not None and hasattr(worker, 'is_alive') and worker.is_alive():
                raise RecoveryError('等待工作线程：' + name)
        # History group is a coalescing identity, not an open transaction.
        # UI checkpoint polling pauses during pointer/composition interaction;
        # native queue drain and serialized handler completion prove graph safety.

    def capture(self):
        self.guard()
        return capture(self.engine, revision=self.revision,
            native_receipts=self.native_receipts, transaction_open=False)

    def checkpoint(self, request):
        if request.get('project_id') != self.project_id():
            raise RecoveryError('工程已切换，旧自动保存请求失效')
        if request.get('native_settled') is not True:
            raise RecoveryError('缺少宿主队列与全部请求回执屏障')
        if self.host.active == 0 and not self.host.closed:
            self.host.cancel.clear()
        self.native_receipts = request.get('native_receipts', [])
        self.guard()
        if self.project_id() != self.scheduler.project_id:
            raise RecoveryError('工程身份尚未建立恢复边界')
        now = time.monotonic()
        if (self.engine._project_dirty and self.revision != self.last_offered
            and now - self.last_checkpoint >= 30):
            project, proof = self.capture()
            self.scheduler.offer(project, project_id=self.project_id(), **proof)
            self.last_offered = self.revision
            self.last_checkpoint = now
        return {**self.scheduler.status(), 'usage': self.store.usage()}


def owner(engine, emit):
    runtime = engine.__dict__.get('_project_recovery_runtime')
    if runtime is None:
        runtime = Runtime(engine, emit)
        engine._project_recovery_runtime = runtime
    return runtime
