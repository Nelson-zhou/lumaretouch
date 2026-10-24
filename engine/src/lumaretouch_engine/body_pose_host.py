"""Reachable source-owned body bank, common-map publication and existing history."""
from copy import deepcopy
from hashlib import sha256
from . import body_pose_project as D,body_pose_state as B,body_pose_evidence as E
from . import shoulder_shape_project as P,shoulder_shape_host as H,body_pose_render as R,leg_shape_host as L,arm_shape_host as A,waist_shape_host as W,leg_length_host as LL,neck_shape_host as N,torso_length_host as T,waist_length_host as WL,head_size_host as HS,body_pose_families as F
from .arm_shape_registered_host import ArmRegisteredHostMixin


class BodyPoseHostMixin(ArmRegisteredHostMixin):
    def _body_init(self):
        self._body_pose_bank=D.fields()[D.KEY];self._body_cursors={};self._body_candidates=None
        self._body_last_outcome={};self._body_authoritative={};self._body_authoritative_requests={};self._body_receipt_bytes=0;self._body_mutation_started=False;self._leg_receipts={};self._waist_receipts={};self._leg_length_receipts={};self._neck_receipts={};self._torso_length_receipts={};self._waist_length_receipts={};self._head_size_receipts={}

    def _body_fields(self,state=None):return D.fields(state)
    def _body_bank(self):return P.unpack(self._body_pose_bank)
    def _body_identity(self):return E.content_digest(self._body_bank())

    def _body_adapter(self,operation='shoulder_shape'):
        if operation=='head_size':return self._head_size_adapter()
        if operation=='arm_shape':return self._arm_adapter()
        if operation=='waist_length':return self._waist_length_adapter()
        if operation=='torso_length':return self._torso_length_adapter()
        if operation=='neck_shape':return self._neck_adapter()
        if operation=='leg_length':return self._leg_length_adapter()
        if operation=='waist_shape':return self._waist_adapter()
        if operation=='leg_shape':
            owner=self.__dict__.get('_leg_edit_owner')
            if owner is None:
                owner=L.LegHostAdapter(L.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),self._body_prepare,self._body_publish,self._leg_receipt_get,self._leg_receipt_put))
                self._leg_edit_owner=owner
            return owner
        owner=self.__dict__.get('_body_edit_owner')
        if owner is None:
            owner=H.ShoulderHostAdapter(H.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),self._body_prepare,self._body_publish))
            self._body_edit_owner=owner
        return owner

    def _leg_receipt_get(self,request_id):return deepcopy(self._leg_receipts.get(request_id))

    def _leg_receipt_put(self,request_id,digest,result):
        E.token(request_id);E.digest(digest)
        old=self._leg_receipts.get(request_id)
        if old is not None and old['digest']!=digest:raise ValueError('Body receipt identity changed')
        if old is None and len(self._leg_receipts)>=4096:raise ValueError('Leg receipt budget exhausted before mutation')
        self._leg_receipts[request_id]={'digest':digest,'result':deepcopy(result)}

    def _body_view(self,operation='shoulder_shape'):
        binding=self._people_binding();bank=self._body_bank();R.check_source(bank,R.source(self._people_source()))
        selected=self._body_cursors.get(binding['asset_sha256'])
        if selected is not None:
            try:B.target(bank,selected)
            except ValueError:selected=None;self._body_cursors.pop(binding['asset_sha256'],None)
        reason=getattr(self._vram,'people_suspended',None)
        presenter=F.presenter(operation)
        value=presenter.view(bank,binding,selected_body_ref=selected,people_state=self._people_owner().snapshot(),refusals=([{'body_ref':row['record']['body_ref'],'reason':reason} for row in bank['bodies'].values()] if reason else ()))
        value['last_outcome']=deepcopy(self._body_last_outcome.get(binding['asset_sha256']))
        return value

    def _body_report(self):
        return F.report(self)

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
        operation=F.request_family(request)
        wrapper=prepared if isinstance(prepared,A.Common.PreparedShoulders) else None
        if wrapper is not None:prepared=wrapper.people
        reason=prepared.reason if isinstance(prepared,H.UnappliedPreparation) else None
        if reason is None:
            try:
                pipeline.install(self._vram,prepared);self._vram.people_suspended=None
                source=self._people_source()
                self._vram.people_key=(source['sha256'],self._people_owner().fence,id(self._precompute),id(self._vram.src_f32),id(self._vram.repair_base),self._body_identity())
                frame=self._write_current_frame(operation)
            except Exception as error:
                reason='Body intent retained but edited output is suspended: '+str(error)
        if reason is not None:
            runtime.suspend(self._vram,reason)
            # If this actual fallback also fails, publication stays uncertain.
            # A stale edited frame is never described as the requested output.
            frame=self._write_current_frame(operation,original=True)
            frame.update(display_quality='original_unapplied',people_render_suspended=reason,suspended_effects=['body_geometry'])
        pixels=np.ascontiguousarray(self._vram.read_back()[:,:,:3]);source=self._people_source()
        frame_id=self.shm.instance_id.hex()+':'+str(frame['seq']);revision=self._people_binding()['document_revision']
        if reason is not None:
            outcome={'version':1,'request_id':request['request_id'],'published_frame_id':frame_id,'output_pixel_sha256':sha256(memoryview(pixels)).hexdigest(),'rendered':False,'applied':False,'retained_intent':True,'reason':reason,'runtime_quality_accepted':False}
        else:
            outcome=shoulder.outcome(prepared.body_fields,prepared.geometry,request_id=request['request_id'],render_revision=revision,original_dimensions=(source['width'],source['height']),rendered_pixels=pixels,published_frame_id=frame_id,sampling_passes=1)
        self._body_last_outcome[source['sha256']]=outcome
        receipt=None
        if wrapper is not None and reason is None:
            from .arm_shape_adapter import publication_receipt
            receipt=publication_receipt(wrapper,pixels,request_id=request['request_id'],published_frame_id=frame_id,render_revision=revision,sampling_passes=1)
        return frame,reason,receipt

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
        operation=F.request_family(request)
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
            frame,reason,render_receipt=self._body_publish_frame(prepared,request)
        finally:
            # The same history owner must retain partially published intent too,
            # even if allocation/render/hash fails after the first write.
            self._history_controller().record(operation+':gesture:'+request['gesture_id'],before_history,after=self._body_history_after(history_asset))
        view=self._body_view(operation)
        view['publication']={'request_id':request['request_id'],'rendered':reason is None,'unapplied_reason':reason}
        if operation=='arm_shape':view['render_receipt']=render_receipt
        result={'phase':'done','protocol':1,'request_id':request['request_id'],'success':True,'outcome_unknown':False,'rendered':reason is None,'unapplied_reason':reason,'view':view}
        self._body_authoritative[request['request_id']]=deepcopy(result)
        self._body_authoritative_requests[request['request_id']]={'operation':operation,'digest':E.content_digest(request)}
        self._body_receipt_bytes+=len(encoded(result))
        # Store the actual state/frame/history outcome before notifications.
        emit(frame);emit({'event':'params_set','mode':operation,'doc_state':self.doc_state()})
        return view

    def _body_status(self,request_id,operation='shoulder_shape'):
        owner=self._body_adapter(operation);result=owner.status(request_id)
        actual=self._body_authoritative.get(request_id)
        claim=owner.receipts.get(request_id);meta=self._body_authoritative_requests.get(request_id)
        same=claim is not None and meta=={'operation':operation,'digest':claim['digest']}
        if result.get('outcome_unknown') and not result.get('publication_invalid') and actual is not None and same:
            owner.resolve_publication(request_id,actual_result=actual);result=owner.status(request_id)
        return result

    def _body_history_restore(self,snapshot):
        from .body_pose_document_history import restore
        return {**snapshot,D.KEY:P.pack(restore(self._body_bank(),snapshot,current_state={'_creative_base':getattr(self,'_creative_base',None)}))}

    def cmd_shoulder_shape(self,message):
        from .body_pose_commands import BodyTransport
        from .server import emit
        owner=self.__dict__.setdefault('_body_transport',BodyTransport())
        owner.handle(self,message,emit)

    def cmd_leg_shape(self,message):
        from .body_pose_commands import BodyTransport
        from .server import emit
        owner=self.__dict__.setdefault('_leg_transport',BodyTransport('leg_shape'))
        owner.handle(self,message,emit)

    def _waist_adapter(self):
        owner=self.__dict__.get('_waist_edit_owner')
        if owner is None:
            owner=W.WaistHostAdapter(W.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),self._body_prepare,self._body_publish,self._waist_receipt_get,self._waist_receipt_put))
            self._waist_edit_owner=owner
        return owner

    def _waist_receipt_get(self,request_id):return deepcopy(self._waist_receipts.get(request_id))

    def _waist_receipt_put(self,request_id,digest,result):
        E.token(request_id);E.digest(digest)
        old=self._waist_receipts.get(request_id)
        if old is not None and old['digest']!=digest:raise ValueError('Waist receipt identity changed')
        if old is not None and old['result'].get('phase')=='done' and not old['result'].get('outcome_unknown') and old['result']!=result:
            raise ValueError('Terminal waist receipt is immutable')
        if old is None and len(self._waist_receipts)>=4096:raise ValueError('Waist receipt budget exhausted before mutation')
        self._waist_receipts[request_id]={'digest':digest,'result':deepcopy(result)}

    def cmd_waist_shape(self,message):
        from .body_pose_commands import BodyTransport
        from .server import emit
        owner=self.__dict__.setdefault('_waist_transport',BodyTransport('waist_shape'))
        owner.handle(self,message,emit)

    def _leg_length_adapter(self):
        owner=self.__dict__.get('_leg_length_edit_owner')
        if owner is None:
            owner=LL.LegLengthHostAdapter(LL.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),self._body_prepare,self._body_publish,self._leg_length_receipt_get,self._leg_length_receipt_put))
            self._leg_length_edit_owner=owner
        return owner

    def _leg_length_receipt_get(self,request_id):return deepcopy(self._leg_length_receipts.get(request_id))

    def _leg_length_receipt_put(self,request_id,digest,result):
        E.token(request_id);E.digest(digest)
        old=self._leg_length_receipts.get(request_id)
        if old is not None and old['digest']!=digest:raise ValueError('Leg length receipt identity changed')
        if old is not None and old['result'].get('phase')=='done' and not old['result'].get('outcome_unknown') and old['result']!=result:
            raise ValueError('Terminal leg length receipt is immutable')
        if old is None and len(self._leg_length_receipts)>=4096:raise ValueError('Leg length receipt budget exhausted before mutation')
        self._leg_length_receipts[request_id]={'digest':digest,'result':deepcopy(result)}

    def cmd_leg_length(self,message):
        from .body_pose_commands import BodyTransport
        from .server import emit
        owner=self.__dict__.setdefault('_leg_length_transport',BodyTransport('leg_length'))
        owner.handle(self,message,emit)
    def _neck_adapter(self):
        owner=self.__dict__.get('_neck_edit_owner')
        if owner is None:
            owner=N.NeckHostAdapter(N.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),self._body_prepare,self._body_publish,self._neck_receipt_get,self._neck_receipt_put))
            self._neck_edit_owner=owner
        return owner

    def _neck_receipt_get(self,request_id):return deepcopy(self._neck_receipts.get(request_id))

    def _neck_receipt_put(self,request_id,digest,result):
        E.token(request_id);E.digest(digest)
        old=self._neck_receipts.get(request_id)
        if old is not None and old['digest']!=digest:raise ValueError('Neck receipt identity changed')
        if old is not None and old['result'].get('phase')=='done' and not old['result'].get('outcome_unknown') and old['result']!=result:
            raise ValueError('Terminal neck receipt is immutable')
        if old is None and len(self._neck_receipts)>=4096:raise ValueError('Neck receipt budget exhausted before mutation')
        self._neck_receipts[request_id]={'digest':digest,'result':deepcopy(result)}

    def cmd_neck_shape(self,message):
        from .body_pose_commands import BodyTransport
        from .server import emit
        owner=self.__dict__.setdefault('_neck_transport',BodyTransport('neck_shape'))
        owner.handle(self,message,emit)

    def _torso_length_adapter(self):
        owner=self.__dict__.get('_torso_length_edit_owner')
        if owner is None:
            owner=T.TorsoLengthHostAdapter(T.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),self._body_prepare,self._body_publish,self._torso_length_receipt_get,self._torso_length_receipt_put))
            self._torso_length_edit_owner=owner
        return owner

    def _torso_length_receipt_get(self,request_id):return deepcopy(self._torso_length_receipts.get(request_id))

    def _torso_length_receipt_put(self,request_id,digest,result):
        E.token(request_id);E.digest(digest)
        old=self._torso_length_receipts.get(request_id)
        if old is not None and old['digest']!=digest:raise ValueError('Torso length receipt identity changed')
        if old is not None and old['result'].get('phase')=='done' and not old['result'].get('outcome_unknown') and old['result']!=result:
            raise ValueError('Terminal torso length receipt is immutable')
        if old is None and len(self._torso_length_receipts)>=4096:raise ValueError('Torso length receipt budget exhausted before mutation')
        self._torso_length_receipts[request_id]={'digest':digest,'result':deepcopy(result)}

    def cmd_torso_length(self,message):
        from .body_pose_commands import BodyTransport
        from .server import emit
        owner=self.__dict__.setdefault('_torso_length_transport',BodyTransport('torso_length'))
        owner.handle(self,message,emit)

    def _waist_length_adapter(self):
        owner=self.__dict__.get('_waist_length_edit_owner')
        if owner is None:
            owner=WL.WaistLengthHostAdapter(WL.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),self._body_prepare,self._body_publish,self._waist_length_receipt_get,self._waist_length_receipt_put))
            self._waist_length_edit_owner=owner
        return owner

    def _waist_length_receipt_get(self,request_id):return deepcopy(self._waist_length_receipts.get(request_id))

    def _waist_length_receipt_put(self,request_id,digest,result):
        E.token(request_id);E.digest(digest)
        old=self._waist_length_receipts.get(request_id)
        if old is not None and old['digest']!=digest:raise ValueError('Waist length receipt identity changed')
        if old is not None and old['result'].get('phase')=='done' and not old['result'].get('outcome_unknown') and old['result']!=result:
            raise ValueError('Terminal waist length receipt is immutable')
        if old is None and len(self._waist_length_receipts)>=4096:raise ValueError('Waist length receipt budget exhausted before mutation')
        self._waist_length_receipts[request_id]={'digest':digest,'result':deepcopy(result)}

    def cmd_waist_length(self,message):
        from .body_pose_commands import BodyTransport
        from .server import emit
        owner=self.__dict__.setdefault('_waist_length_transport',BodyTransport('waist_length'))
        owner.handle(self,message,emit)

    def _head_size_adapter(self):
        owner=self.__dict__.get('_head_size_edit_owner')
        if owner is None:
            owner=HS.HeadSizeHostAdapter(HS.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),self._body_prepare,self._body_publish,self._head_size_receipt_get,self._head_size_receipt_put))
            self._head_size_edit_owner=owner
        return owner

    def _head_size_receipt_get(self,request_id):return deepcopy(self._head_size_receipts.get(request_id))

    def _head_size_receipt_put(self,request_id,digest,result):
        E.token(request_id);E.digest(digest)
        old=self._head_size_receipts.get(request_id)
        if old is not None and old['digest']!=digest:raise ValueError('Head size receipt identity changed')
        if old is not None and old['result'].get('phase')=='done' and not old['result'].get('outcome_unknown') and old['result']!=result:
            raise ValueError('Terminal head size receipt is immutable')
        if old is None and len(self._head_size_receipts)>=4096:raise ValueError('Head size receipt budget exhausted before mutation')
        self._head_size_receipts[request_id]={'digest':digest,'result':deepcopy(result)}

    def cmd_head_size(self,message):
        from .body_pose_commands import BodyTransport
        from .server import emit
        owner=self.__dict__.setdefault('_head_size_transport',BodyTransport('head_size'))
        owner.handle(self,message,emit)
