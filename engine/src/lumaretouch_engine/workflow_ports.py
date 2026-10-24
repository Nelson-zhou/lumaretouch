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
        from .face_decoration_scope import capture as capture_decoration
        from .blush_makeup_scope import capture as capture_blush
        from .lipstick_scope import capture as capture_lipstick
        from .eyeliner_scope import capture as capture_eyeliner
        from .eyelash_scope import capture as capture_eyelash
        from .brow_makeup_scope import capture as capture_brow_makeup
        from .iris_makeup_scope import capture as capture_iris
        from .skin_colour_scope import capture as capture_skin_colour
        from .skin_finish_scope import capture as capture_skin_finish
        from .skin_gloss_scope import capture as capture_skin_gloss
        from .skin_texture_scope import capture as capture_skin_texture
        from .skin_evenness_scope import capture as capture_skin_evenness
        from .body_skin_evenness_scope import capture as capture_body_skin_evenness
        from .collarbone_scope import capture as capture_collarbone
        from .body_face_match_scope import capture as capture_body_face_match
        from .face_contour_scope import capture as capture_face_contour
        from .slim_face_scope import capture as capture_slim_face
        from .face_size_scope import capture as capture_face_size
        from .lower_face_scope import capture as capture_lower_face
        from .mid_face_scope import capture as capture_mid_face
        from .chin_shape_scope import capture as capture_chin_shape
        from .chin_length_scope import capture as capture_chin_length
        from .philtrum_scope import capture as capture_philtrum
        from .eye_symmetry_scope import capture as capture_eye_symmetry
        from .brow_enhance_scope import capture as capture_brow_enhance
        from .lip_texture_scope import capture as capture_lip_texture
        from .eye_bag_preserve_scope import capture as capture_eye_bag_preserve
        state = capture_skin_finish(self,capture_skin_colour(self,capture_iris(self,capture_eyelash(self,capture_brow_makeup(self,capture_eyeliner(self,capture_lipstick(self,capture_blush(self,capture(self)))))))))
        state = capture_face_size(self,capture_slim_face(self,capture_face_contour(self,capture_skin_texture(self,capture_skin_gloss(self,state)))))
        state = capture_collarbone(self,capture_body_skin_evenness(self,capture_skin_evenness(self,state)))
        state = capture_body_face_match(self,state)
        state = capture_decoration(self,state)
        state = capture_philtrum(self,capture_chin_length(self,capture_chin_shape(self,capture_mid_face(self,capture_lower_face(self,state)))))
        return capture_eye_bag_preserve(self,capture_lip_texture(self,capture_brow_enhance(self,capture_eye_symmetry(self,state))))

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

    def _prepare_crop_target(self,row,candidate,document_id,revision):
        from .crop_transfer_review import prepare
        return prepare(self,row,candidate,document_id,revision)

    def _verify_crop_target(self,row,candidate,document_id,revision,record):
        from .crop_transfer_review import verify
        return verify(self,row,candidate,document_id,revision,record)


    def _prepare_spill_target(self,row,before,candidate,document_id,revision):
        from .spill_transfer_review import prepare
        return prepare(self,row,before,candidate,document_id,revision)

    def _verify_spill_target(self,row,before,candidate,document_id,revision,record):
        from .spill_transfer_review import verify
        return verify(self,row,before,candidate,document_id,revision,record)

    def _prepare_xmp_target(self,row,before,candidate,document_id,revision,xmp_sha256):
        from .xmp_target_review import prepare
        return prepare(self,row,before,candidate,document_id,revision,xmp_sha256)

    def _verify_xmp_target(self,row,before,candidate,document_id,revision,xmp_sha256,record):
        from .xmp_target_review import verify
        return verify(self,row,before,candidate,document_id,revision,xmp_sha256,record)

    def _prepare_shadow_target(self,row,before,candidate,document_id,revision):
        from .original_shadow_transfer_review import prepare
        return prepare(self,row,before,candidate,document_id,revision)

    def _verify_shadow_target(self,row,before,candidate,document_id,revision,record):
        from .original_shadow_transfer_review import verify
        return verify(self,row,before,candidate,document_id,revision,record)

    def _prepare_torso_target(self,row,before,candidate,document_id,revision):
        from .torso_length_transfer_review import prepare
        return prepare(self,row,before,candidate,document_id,revision)

    def _verify_torso_target(self,row,before,candidate,document_id,revision,record):
        from .torso_length_transfer_review import verify
        return verify(self,row,before,candidate,document_id,revision,record)

    def _prepare_waist_target(self,row,before,candidate,document_id,revision):
        from .waist_length_transfer_review import prepare
        return prepare(self,row,before,candidate,document_id,revision)

    def _verify_waist_target(self,row,before,candidate,document_id,revision,record):
        from .waist_length_transfer_review import verify
        return verify(self,row,before,candidate,document_id,revision,record)

    def _prepare_head_target(self,row,before,candidate,document_id,revision):
        from .head_size_transfer_review import prepare
        return prepare(self,row,before,candidate,document_id,revision)

    def _verify_head_target(self,row,before,candidate,document_id,revision,record):
        from .head_size_transfer_review import verify
        return verify(self,row,before,candidate,document_id,revision,record)

    def _head_history_identity(self,row,state,document_id,revision):
        from .head_size_transfer_review import history_identity
        return history_identity(self,row,state,document_id,str(revision))

    def _batch_history_identity(self,row,state,document_id,revision):
        from .full_candidate_render import identity
        proof,_,_=identity(self,row,state,document_id,str(revision))
        return proof

    def _torso_history_identity(self,row,state,document_id,revision):
        from .torso_length_transfer_review import history_identity
        return history_identity(self,row,state,document_id,str(revision))

    def _waist_history_identity(self,row,state,document_id,revision):
        from .waist_length_transfer_review import history_identity
        return history_identity(self,row,state,document_id,str(revision))

    def _prepare_face_decoration_preset(self,row,before,candidate,document_id,revision,preset,modules):
        from .face_decoration_preset_review import prepare
        return prepare(self,row,before,candidate,document_id,str(revision),preset,modules)

    def _verify_face_decoration_preset(self,row,before,candidate,document_id,revision,record):
        from .face_decoration_preset_review import verify
        return verify(self,row,before,candidate,document_id,str(revision),record)

    def _replay_face_decoration_preset(self,row,state,document_id,revision,record,**kwargs):
        from .face_decoration_preset_review import replay
        return replay(self,row,state,document_id,str(revision),record,**kwargs)

    def _verify_face_decoration_preset_applied(self,row,state,document_id,revision,record,**kwargs):
        from .face_decoration_preset_review import verify_applied
        return verify_applied(self,row,state,document_id,str(revision),record,**kwargs)

    def _prepare_collarbone_preset(self,row,before,candidate,document_id,revision,preset,modules):
        from .collarbone_preset_review import prepare
        return prepare(self,row,before,candidate,document_id,str(revision),preset,modules)

    def _verify_collarbone_preset(self,row,before,candidate,document_id,revision,record):
        from .collarbone_preset_review import verify
        return verify(self,row,before,candidate,document_id,str(revision),record)

    def _replay_collarbone_preset(self,row,state,document_id,revision,record,**kwargs):
        from .collarbone_preset_review import replay
        return replay(self,row,state,document_id,str(revision),record,**kwargs)

    def _verify_collarbone_preset_applied(self,row,state,document_id,revision,record,**kwargs):
        from .collarbone_preset_review import verify_applied
        return verify_applied(self,row,state,document_id,str(revision),record,**kwargs)

    def _prepare_eye_bag_preset(self,row,before,candidate,document_id,revision,preset,modules,*,replace_legacy=False):
        from .eye_bag_preset_review import prepare
        return prepare(self,row,before,candidate,document_id,str(revision),preset,modules,replace_legacy=replace_legacy)

    def _verify_eye_bag_preset(self,row,before,candidate,document_id,revision,record):
        from .eye_bag_preset_review import verify
        return verify(self,row,before,candidate,document_id,str(revision),record)

    def _replay_eye_bag_preset(self,row,state,document_id,revision,record,**kwargs):
        from .eye_bag_preset_review import replay
        return replay(self,row,state,document_id,str(revision),record,**kwargs)

    def _verify_eye_bag_preset_applied(self,row,state,document_id,revision,record,**kwargs):
        from .eye_bag_preset_review import verify_applied
        return verify_applied(self,row,state,document_id,str(revision),record,**kwargs)

    def _verify_eye_bag_preset_alias(self,record):
        from .eye_bag_preset_alias_review import verify_live
        return verify_live(self,record)

    def _publish_eye_bag_preset_alias(self,row,before,candidate,document_id,revision,record,modules,request_id,**kwargs):
        from .eye_bag_preset_alias_review import publish
        return publish(self,row,before,candidate,document_id,str(revision),record,modules,request_id,**kwargs)

    def _verify_face_decoration_preset_alias(self,record):
        from .face_decoration_preset_alias_review import verify_live
        return verify_live(self,record)

    def _publish_face_decoration_preset_alias(self,row,before,candidate,document_id,revision,record,modules,request_id,**kwargs):
        from .face_decoration_preset_alias_review import publish
        return publish(self,row,before,candidate,document_id,str(revision),record,modules,request_id,**kwargs)

    def _preset_controller(self):
        controller = self.__dict__.get("_live_presets")
        if controller is None:
            controller = PRS.PresetController(PRS.PresetPorts(
                prepare_eye_bag=self._prepare_eye_bag_preset,verify_eye_bag=self._verify_eye_bag_preset,
                eye_bag_replay=self._replay_eye_bag_preset,verify_eye_bag_applied=self._verify_eye_bag_preset_applied,
                verify_eye_bag_alias=self._verify_eye_bag_preset_alias,publish_eye_bag_alias=self._publish_eye_bag_preset_alias,
                verify_face_decoration_alias=self._verify_face_decoration_preset_alias,publish_face_decoration_alias=self._publish_face_decoration_preset_alias,
                prepare_face_decoration=self._prepare_face_decoration_preset,verify_face_decoration=self._verify_face_decoration_preset,
                face_decoration_replay=self._replay_face_decoration_preset,verify_face_decoration_applied=self._verify_face_decoration_preset_applied,
                prepare_collarbone=self._prepare_collarbone_preset,verify_collarbone=self._verify_collarbone_preset,
                collarbone_replay=self._replay_collarbone_preset,verify_collarbone_applied=self._verify_collarbone_preset_applied,
                prepare_optics=self._prepare_optics_target, prepare_reference=self._prepare_reference_target,
                prepare_crop=self._prepare_crop_target, verify_crop=self._verify_crop_target,
                prepare_spill=self._prepare_spill_target, verify_spill=self._verify_spill_target,
                prepare_shadow=self._prepare_shadow_target, verify_shadow=self._verify_shadow_target,
                prepare_torso=self._prepare_torso_target, verify_torso=self._verify_torso_target,
                prepare_waist=self._prepare_waist_target, verify_waist=self._verify_waist_target,
                prepare_head=self._prepare_head_target, verify_head=self._verify_head_target,
                head_history_identity=self._head_history_identity,
                torso_history_identity=self._torso_history_identity, waist_history_identity=self._waist_history_identity,
                prepare_xmp=self._prepare_xmp_target, verify_xmp=self._verify_xmp_target,
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
        from .face_decoration_batch_plan import require_generic_safe as decoration_guard
        controller = self.__dict__.get("_batch_sync")
        if controller is None:
            controller = BS.BatchSyncController(
                BS.BatchDocuments(rows=lambda: self._docs,
                    current_index=lambda: self._doc_index,
                    remember_current=lambda: self._remember_current(),
                    index_of=lambda path: self._index_of(path)),
                BS.BatchEditor(decoration_guard=lambda row: decoration_guard(self,row),
                prepare_crop=self._prepare_crop_target, verify_crop=self._verify_crop_target,
                prepare_spill=self._prepare_spill_target, verify_spill=self._verify_spill_target,
                prepare_shadow=self._prepare_shadow_target, verify_shadow=self._verify_shadow_target,
                prepare_torso=self._prepare_torso_target, verify_torso=self._verify_torso_target,
                prepare_waist=self._prepare_waist_target, verify_waist=self._verify_waist_target,
                prepare_head=self._prepare_head_target, verify_head=self._verify_head_target,
                head_history_identity=self._head_history_identity,
                waist_history_identity=self._waist_history_identity,
                torso_history_identity=self._torso_history_identity, history_identity=self._batch_history_identity, people_transfer=self._people_transfer_batch, people_restore=self._people_restore_batch, capture_reference=self._capture_reference, prepare_optics=self._prepare_optics_target, prepare_reference=self._prepare_reference_target, guard=lambda label: self._guard_editable(label),
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
