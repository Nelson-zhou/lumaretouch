"""Explicit batch/preset engine ports, extracted from the capped command host."""
import time
from . import batch_sync as BS, preset_controller as PRS
from .shm import monotonic_ns
def emit(event):
    from .server import emit as send
    send(event)

class WorkflowPortsMixin:
    def _people_preset_capture(self):
        from .eye_light_scope import capture
        from .blush_makeup_scope import capture as capture_blush
        from .lipstick_scope import capture as capture_lipstick
        from .eyeliner_scope import capture as capture_eyeliner
        from .brow_makeup_scope import capture as capture_brow_makeup
        return capture_brow_makeup(self,capture_eyeliner(self,capture_lipstick(self,capture_blush(self,capture(self)))))

    def _people_preset_replay(self,state,**kwargs):
        from .people_scope import replay_preset
        return replay_preset(self,state,**kwargs)

    def _people_batch_face_check(self,row,**kwargs):
        from .people_scope import legacy_batch_face_check
        return legacy_batch_face_check(self,row,**kwargs)

    def _people_transfer_batch(self,controller,p,plan):
        from .people_batch_transfer import handle
        return handle(self,controller,p,plan)

    def _prepare_reference_target(self,row,state,document_id,revision,params):
        from .reference_color_engine import prepare_target
        return prepare_target(self,row,state,document_id,revision,params)

    def _capture_reference(self,row,state,document_id,revision,strength):
        from .reference_color_engine import reference_intent
        return reference_intent(self,row,state,document_id,revision,strength)

    def _prepare_optics_target(self, row, candidate, document_id, revision):
        from .optics_transfer_engine import prepare_target
        return prepare_target(self, row, candidate, document_id, revision)


    def _preset_controller(self):
        controller = self.__dict__.get("_live_presets")
        if controller is None:
            controller = PRS.PresetController(PRS.PresetPorts(
                prepare_optics=self._prepare_optics_target, prepare_reference=self._prepare_reference_target,
                guard=lambda label: self._guard_editable(label), document_id=lambda: self._load_id,
                capture=lambda: self._people_preset_capture(), replay=lambda state, **kw: self._people_preset_replay(state, **kw),
                face_check=lambda: self._face_known_single(None, live=True), status=lambda: self.doc_state(),
                invalidate=lambda: setattr(self, "_vram", None), target_row=lambda: self._docs[self._doc_index],
                revision=lambda: str(self._document_versions().version(self._docs[self._doc_index]).revision),
                advance=lambda: self._fence_current_document()), emit=lambda event: emit(event))
            self._live_presets = controller
        return controller


    def cmd_preset(self, p: dict): self._preset_controller().handle_command(p)


    def _preset_apply(self, p: dict): return self._preset_controller().apply(p)


    def _preset_save(self, p: dict): return self._preset_controller().save(p)


    def _batch_controller(self):
        controller = self.__dict__.get("_batch_sync")
        if controller is None:
            controller = BS.BatchSyncController(
                BS.BatchDocuments(rows=lambda: self._docs,
                    current_index=lambda: self._doc_index,
                    remember_current=lambda: self._remember_current(),
                    index_of=lambda path: self._index_of(path)),
                BS.BatchEditor(people_transfer=self._people_transfer_batch, people_restore=self._people_restore_batch, capture_reference=self._capture_reference, prepare_optics=self._prepare_optics_target, prepare_reference=self._prepare_reference_target, guard=lambda label: self._guard_editable(label),
                    capture=lambda: self._capture_state(),
                    replay=lambda state, **kw: self._replay_state(state, **kw),
                    face_known_single=lambda row, **kw: self._people_batch_face_check(row, **kw),
                    status=lambda: self.doc_state(),mark_dirty=lambda:setattr(self,"_project_dirty",True),
                    invalidate=lambda:setattr(self,"_vram",None)),
                emit=lambda event: emit(event), clock=lambda: time.time(),
                monotonic=lambda: monotonic_ns(), history_limit=self.HISTORY_MAX, versions=self._document_versions())
            self._batch_sync = controller
        controller.history_limit = self.HISTORY_MAX
        return controller


    def cmd_batch(self, p: dict):
        return self._batch_controller().handle_command(p)


