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
        message = boundary['message']
        from .portrait_crop_recovery import observe as crop_observe
        if crop_observe(boundary, event): return
        if (message.get('cmd') == 'creative_selection' and event.get('event') == 'creative_selection_result'
                and event.get('request_id') == message.get('request_id') and event.get('action') == message.get('action')):
            boundary['selection_outcome'] = {key: event.get(key) for key in ('status', 'success', 'outcome_unknown', 'no_write')}
        if (event.get('event') == 'error' or event.get('success') is False
            or event.get('outcome_unknown') or event.get('requires_reload')
            or event.get('status') in ('failed', 'unknown', 'partial', 'blocked')
            or event.get('requires_readback')
            or (event.get('event') in ('light_glow_result', 'upscale_restore_result') and (event.get('receipt') or {}).get('outcome_unknown') is True)
            or (event.get('event')=='lens_blur_result' and (event.get('receipt') or {}).get('outcome_unknown') is True)
            or (event.get('event')=='expression_replacement_result' and (event.get('receipt') or {}).get('phase')=='unknown')):
            boundary['failed'] = True


def begin(engine, message, handler):
    boundary = {'failed': False, 'returned': False, 'started': False, 'message': message, 'engine': engine}
    _local.boundary = boundary
    if message.get('cmd') == 'hair_volume':
        boundary['hair_volume_before_fence'] = engine._people_owner().fence
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
    from .white_balance_auto_recovery import finish as auto_wb_finish
    if auto_wb_finish(engine, boundary, error): return
    from .final_canvas_flip_recovery import finish as flip_finish
    if flip_finish(engine, boundary): return
    from .portrait_crop_recovery import finish as crop_finish
    if crop_finish(engine, boundary, error): return
    from .hair_volume_recovery import finish as hair_volume_finish
    if hair_volume_finish(engine, boundary, error): return
    if message.get('cmd') in ('ingest_session', 'workflow_owner', 'background_material_library', 'background_material_library_cancel'):
        # The lease owns pending/unknown copy receipts. Only the existing atomic
        # managed transaction writes the saved project; readback cannot bless a
        # partial copy or taint a committed recipe on a rejected session request.
        return
    from .portrait_preset_delivery import command as delivery_command
    if delivery_command(message):
        # Scoped project CAS and canonical export jobs own their durable truth.
        # No recipe/history publication or unrelated autosave is authorized here.
        return
    from .creative_selection_host import read_only as selection_read_only
    from .portrait_preset_batch import read_only as portrait_preset_read_only
    if portrait_preset_read_only(message): return
    if selection_read_only(message): return
    from .light_glow_host import read_only as glow_read_only
    if glow_read_only(message):return
    from .upscale_restore_host import read_only as upscale_read_only
    if upscale_read_only(message):return
    from .lens_blur_host import read_only as lens_read_only
    if lens_read_only(message):return
    from .expression_replacement_host import read_only as expression_read_only
    if expression_read_only(message):return
    # Spill preview renders isolated candidates only. Even a rejected or failed
    # preview cannot dirty/taint committed project state or advance autosave.
    if message.get('cmd') == 'background' and message.get('action') in ('id_spill_preview', 'id_spill_paint_source', 'id_original_shadow_paint_source','id_original_shadow_preview'):
        return
    from .creative_transfer_host import inventory_read_only, head_preflight_read_only, face_style_image_read_only, face_style_preflight_read_only, portrait_cohort_image_read_only, portrait_cohort_preflight_read_only
    if inventory_read_only(message) or head_preflight_read_only(message):return
    if face_style_image_read_only(message):return  # Cached display failure is not a failed graph mutation.
    if face_style_preflight_read_only(message):return  # Named review may sync committed row snapshots, never publish edits.
    if portrait_cohort_image_read_only(message) or portrait_cohort_preflight_read_only(message):return
    from .eye_bag_cohort_store import read_only as eye_bag_cohort_read_only
    if eye_bag_cohort_read_only(message):return  # Source-plus-members review is not an association write.
    from .face_decoration_cohort_store import read_only as decoration_cohort_read_only
    if decoration_cohort_read_only(message):return
    from .face_decoration_batch_store import read_only as decoration_batch_read_only
    from .face_decoration_preset_store import read_only as decoration_preset_read_only
    if decoration_batch_read_only(message) or decoration_preset_read_only(message):return  # Includes exact paged mixed alias reads; no publication.
    from .eye_bag_batch_store import read_only as eye_bag_batch_read_only
    if eye_bag_batch_read_only(message):return  # Exact target review cannot publish or taint committed state.
    from .eye_bag_preset_store import read_only as eye_bag_preset_read_only
    if eye_bag_preset_read_only(message):return  # Dedicated preset read cannot publish or taint committed state.
    from .face_decoration_support_alias_review import read_only as decoration_support_read_only
    if decoration_support_read_only(message):return  # Staged graph/bank reads never publish or taint committed state.
    from .people_host_commands import face_style_read_only, eye_bag_read_only, facial_sculpt_read_only, eye_makeup_enhance_read_only
    if face_style_read_only(message) or eye_bag_read_only(message) or facial_sculpt_read_only(message) or eye_makeup_enhance_read_only(message):return  # Private read failures cannot taint committed project state.
    from .people_reference_dispatch import read_only as skin_reference_read_only
    if skin_reference_read_only(message): return
    from .hair_volume_controller import read_only as hair_volume_read_only
    if hair_volume_read_only(message): return
    from .hair_unification_controller import read_only as hair_unification_read_only
    if hair_unification_read_only(message): return
    if not boundary['started'] or message.get('cmd') in ('project_recovery', 'canvas_guides'):
        return
    runtime = engine.__dict__.get('_project_recovery_runtime')
    if runtime is None:
        return
    if message.get('cmd') == 'creative_selection':
        outcome = boundary.get('selection_outcome') or {}
        if not error and boundary['returned'] and outcome.get('outcome_unknown') is False:
            if outcome.get('status') == 'no_change' or outcome.get('no_write') is True: return
            if outcome.get('status') == 'applied' and outcome.get('success') is True:
                runtime.revision += 1
                return
    if message.get('cmd') == 'batch' and message.get('action') == 'portrait_preset_prepare':
        # Only the preparation owner can set this private boundary fact. A
        # known restored partial retains earlier analyses but is not an
        # uncertain project; an emitted JSON flag alone cannot settle it.
        outcome = boundary.get('portrait_preparation_outcome') or {}
        if (not error and boundary['returned'] and outcome.get('outcome_unknown') is False
                and outcome.get('editor_restored') is True and not runtime.tainted):
            if outcome.get('no_write') is not True:
                runtime.revision += 1
            return
    # Errors can occur after a partial mutation even if a handler returns. Keep
    # taint until a successful explicit project open/create establishes a base.
    if error or boundary['failed'] or not boundary['returned']:
        runtime.tainted = True
        runtime.reason = '上次命令未确认完整提交；请保存前检查，或重新打开已确认的工程'
    elif message.get('cmd') in engine.EDIT_CMDS or message.get('cmd') in (
        'final_canvas_flip','project','session','history','virtual_copy','managed_import','source_relocation',
        'people','hair_volume','batch','primary_calibration','colour_editor','selective_colour','colour_grading',
        'photo_grain','photo_detail','extended_tone','shoulder_shape','leg_shape','arm_shape',
        'waist_shape','leg_length','neck_shape','torso_length','waist_length','head_size','body_slim','custom_lut','semantic_colour','creative_document','common_background','expression_replacement','lens_blur','light_glow','upscale_restore'):
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
        self.__dict__.pop('_portrait_crop_taint', None)
        self.__dict__.pop('_portrait_crop_completed', None)
        self.scheduler.switch(self.project_id())
        self.revision += 1
        self.last_offered = -1
        self.tainted = False
        self.reason = None

    def guard(self):
        if self.tainted:
            raise RecoveryError(self.reason)
        e = self.engine
        if e.__dict__.get('_hair_volume_uncertain') is not None:
            raise RecoveryError('发量原提交尚未确认，请查询原请求或重新打开已确认的工程')
        for name, owner in tuple(e.__dict__.items()):
            if name.startswith('_project_recovery') or owner is None:
                continue
            # Every asynchronous owner is checked, including future owners that
            # implement the existing active/pending/uncertain/job conventions.
            if name in ('bench', '_export', '_thumbs', '_picks'):
                if owner.is_alive(): raise RecoveryError('后台任务尚未完成：' + name)
            if not (name.endswith(('_controller', '_owner', '_host')) or name in ('_batch_sync','_portrait_crop_service','_expression_replacement_service','_lens_blur_service','_light_glow_service','_upscale_restore_service')):
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
