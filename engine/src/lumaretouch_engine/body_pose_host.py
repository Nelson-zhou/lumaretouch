"""Reachable source-owned body bank, common-map publication and existing history."""
from copy import deepcopy
from hashlib import sha256
from . import body_pose_project as D,body_pose_state as B,body_pose_evidence as E
from . import shoulder_shape_project as P,shoulder_shape_host as H,body_pose_render as R


class BodyPoseHostMixin:
    def _body_init(self):
        self._body_pose_bank=D.fields()[D.KEY];self._body_cursors={};self._body_candidates=None
        self._body_last_outcome={};self._body_authoritative={};self._body_receipt_bytes=0;self._body_mutation_started=False

    def _body_fields(self,state=None):return D.fields(state)
    def _body_bank(self):return P.unpack(self._body_pose_bank)
    def _body_identity(self):return E.content_digest(self._body_bank())

    def _body_adapter(self):
        owner=self.__dict__.get('_body_edit_owner')
        if owner is None:
            owner=H.ShoulderHostAdapter(H.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),self._body_prepare,self._body_publish))
            self._body_edit_owner=owner
        return owner

    def _body_view(self):
        binding=self._people_binding();bank=self._body_bank();R.check_source(bank,R.source(self._people_source()))
        selected=self._body_cursors.get(binding['asset_sha256'])
        if selected is not None:
            try:B.target(bank,selected)
            except ValueError:selected=None;self._body_cursors.pop(binding['asset_sha256'],None)
        reason=getattr(self._vram,'people_suspended',None)
        value=H.view(bank,binding,selected_body_ref=selected,people_state=self._people_owner().snapshot(),refusals=([{'body_ref':row['record']['body_ref'],'reason':reason} for row in bank['bodies'].values()] if reason else ()))
        value['last_outcome']=deepcopy(self._body_last_outcome.get(binding['asset_sha256']))
        return value

    def _body_report(self):
        if not self._image_loaded or self._doc_index<0:return {}
        try:return {'shoulder_shape':self._body_view()}
        except (ValueError,RuntimeError,OSError,KeyError) as error:return {'shoulder_shape':None,'shoulder_shape_error':str(error)}

    def _body_prepare(self,candidate):
        from . import people_engine_runtime as runtime,people_support_assets as support
        from .cpu_memory_budget import available_estimate
        frame,people,analyses=self._people_bind();R.check_source(candidate,R.source(frame))
        recovery=support.raster(people,self._people_support,frame['sha256'],(self._vram.h,self._vram.w))
        from .people_owned_inputs import preview as owned_inputs
        return runtime.prepare_preview(self._vram,people,frame['sha256'],analyses,byte_budget=available_estimate(),recovery_assets=recovery,**owned_inputs(self,people,body_bank=candidate,body_source=frame))

    def _body_publish_frame(self,prepared,request):
        from . import people_pipeline as pipeline,people_engine_runtime as runtime,shoulder_shape_runtime as shoulder
        import numpy as np
        reason=prepared.reason if isinstance(prepared,H.UnappliedPreparation) else None
        if reason is None:
            try:
                pipeline.install(self._vram,prepared);self._vram.people_suspended=None
                source=self._people_source()
                self._vram.people_key=(source['sha256'],self._people_owner().fence,id(self._precompute),id(self._vram.src_f32),id(self._vram.repair_base),self._body_identity())
                frame=self._write_current_frame('shoulder_shape')
            except Exception as error:
                reason='Body intent retained but edited output is suspended: '+str(error)
        if reason is not None:
            runtime.suspend(self._vram,reason)
            # If this actual fallback also fails, publication stays uncertain.
            # A stale edited frame is never described as the requested output.
            frame=self._write_current_frame('shoulder_shape',original=True)
            frame.update(display_quality='original_unapplied',people_render_suspended=reason,suspended_effects=['body_geometry'])
        pixels=np.ascontiguousarray(self._vram.read_back()[:,:,:3]);source=self._people_source()
        frame_id=self.shm.instance_id.hex()+':'+str(frame['seq']);revision=self._people_binding()['document_revision']
        if reason is not None:
            outcome={'version':1,'request_id':request['request_id'],'published_frame_id':frame_id,'output_pixel_sha256':sha256(memoryview(pixels)).hexdigest(),'rendered':False,'applied':False,'retained_intent':True,'reason':reason,'runtime_quality_accepted':False}
        else:
            outcome=shoulder.outcome(prepared.body_fields,prepared.geometry,request_id=request['request_id'],render_revision=revision,original_dimensions=(source['width'],source['height']),rendered_pixels=pixels,published_frame_id=frame_id,sampling_passes=1)
        self._body_last_outcome[source['sha256']]=outcome
        return frame,reason

    def _body_history_after(self,asset):
        # Pre-bound by this serialized transaction before mutation. File loss
        # cannot erase the undo entry for already-retained in-memory intent.
        E.digest(asset);after=self._capture_state()
        for key in self.HISTORY_SKIP:del after[key]
        after['_people_history']=self._people_owner().capture_document(asset) if self._people_managed() else None
        return after

    def _body_publish(self,before,candidate,prepared,patch,request):
        from .server import emit
        from .body_pose_commands import encoded
        try:
            before_history=self._history_capture();history_asset=self._people_source()['sha256'];packed=P.pack(candidate)
            estimate=len(encoded(candidate))+len(encoded(self._people_owner().snapshot()['persons']))+32768
            if not isinstance(prepared,H.UnappliedPreparation):estimate+=sum(len(encoded(field.facts)) for field in prepared.body_fields)
            if len(self._body_authoritative)>=4096 or self._body_receipt_bytes+estimate>128*1024*1024:raise ValueError('Body authoritative receipt budget exhausted before publication; no old identity becomes replayable')
            if request['request_id'] in self._body_authoritative:raise ValueError('Body request identity was already published in another operation')
            self._document_versions().check_advance(self._docs[self._doc_index])
        except (ValueError,RuntimeError,OSError) as error:raise H.PublicationNotStarted(str(error)) from error
        self._body_mutation_started=True
        try:
            self._body_pose_bank=packed;self._project_dirty=True;self._fence_current_document()
            self._people_render_enabled=True;self._people_path=self._doc_path
            frame,reason=self._body_publish_frame(prepared,request)
        finally:
            # The same history owner must retain partially published intent too,
            # even if allocation/render/hash fails after the first write.
            self._history_controller().record('shoulder_shape:gesture:'+request['gesture_id'],before_history,after=self._body_history_after(history_asset))
        view=self._body_view()
        view['publication']={'request_id':request['request_id'],'rendered':reason is None,'unapplied_reason':reason}
        result={'phase':'done','protocol':1,'request_id':request['request_id'],'success':True,'outcome_unknown':False,'rendered':reason is None,'unapplied_reason':reason,'view':view}
        self._body_authoritative[request['request_id']]=deepcopy(result);self._body_receipt_bytes+=len(encoded(result))
        # Store the actual state/frame/history outcome before notifications.
        emit(frame);emit({'event':'params_set','mode':'shoulder_shape','doc_state':self.doc_state()})
        return view

    def _body_status(self,request_id):
        owner=self._body_adapter();result=owner.status(request_id)
        actual=self._body_authoritative.get(request_id)
        if result.get('outcome_unknown') and actual is not None:owner.resolve_publication(request_id,actual_result=actual);result=owner.status(request_id)
        return result

    def _body_history_restore(self,snapshot):
        from .body_pose_document_history import restore
        return {**snapshot,D.KEY:P.pack(restore(self._body_bank(),snapshot))}

    def cmd_shoulder_shape(self,message):
        from .body_pose_commands import BodyTransport
        from .server import emit
        owner=self.__dict__.setdefault('_body_transport',BodyTransport())
        owner.handle(self,message,emit)
