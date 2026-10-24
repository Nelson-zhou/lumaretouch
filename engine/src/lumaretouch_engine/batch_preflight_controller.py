"""Frozen batch review/commit policy, using explicit document/editor ports."""
from . import brow_shape_scope as BROW, nose_shape_scope as NOSE, eye_shape_scope as EYE, mouth_shape_scope as MOUTH
from dataclasses import dataclass
from typing import Callable
import json
from . import scope as SC, reference_color_scope as RC
from . import sky_replacement_scope as SKY, optics_auto_scope as OA, id_background_scope as ID_BACKGROUND
from . import optics_transfer_review as OR
from . import spill_transfer_review as SR
from . import original_shadow_transfer_review as SHR
from .body_scalar_transfer_review import select as body_family
from . import local_grade_layers as LG
from . import local_grade_runtime as LR
from .batch_preflight import PreflightStore,FrozenTarget,canonical,MAX_RESULT_BYTES,collarbone_required
from . import creative_derived_source as SOURCE, creative_derived_transfer as TRANSFER

@dataclass(frozen=True)
class PlanPorts:
    rows:Callable[[],list]
    current:Callable[[],int]
    remember:Callable[[],None]
    capture:Callable[[],dict]
    targets:Callable
    face_check:Callable
    commit:Callable
    prepare_optics:Callable|None=None
    prepare_reference:Callable|None=None
    capture_reference:Callable|None=None
    people_transfer:Callable|None=None
    prepare_crop:Callable|None=None
    verify_crop:Callable|None=None
    prepare_spill:Callable|None=None
    verify_spill:Callable|None=None
    prepare_shadow:Callable|None=None
    verify_shadow:Callable|None=None
    prepare_torso:Callable|None=None
    verify_torso:Callable|None=None
    prepare_waist:Callable|None=None
    verify_waist:Callable|None=None
    prepare_head:Callable|None=None
    verify_head:Callable|None=None

class FrozenBatchController:
    def __init__(self,ports,versions,emit,clock):
        self.ports=ports;self.versions=versions;self.emit=emit;self.store=PreflightStore(clock)
        # Session-only strong references, never serialized into a plan or receipt.
        # Copied public IDs are not authority to replace a reviewed document row.
        self._scalar_targets={}

    def _prune_scalar_targets(self):
        self.store._prune(self.store.clock())
        from .collarbone_visual_store import prune
        prune(self.store)
        self._scalar_targets={token:rows for token,rows in self._scalar_targets.items()
                              if token in self.store.pending}

    def _blocked(self,row,ops,live):
        if row.get('trashed'):return 'target is in the project trash'
        for op in ops:
            if SC.MODULES[op]['single_face']:
                verdict,reason=self.ports.face_check(row,live=live)
                if verdict!='ok':return f'{op}: {reason}'
        return None

    def emit_result(self,p,payload):
        # Result mailbox excludes full frames/snapshots; bounded crop/spill PNGs are review evidence.
        result={k:v for k,v in payload.items() if k not in ('event','doc_state','frame')}
        result.update(event='batch_result',action=p.get('action'),request_id=p.get('request_id'))
        if p.get('request_id') is not None:self.emit(result)
        return result

    def replay_completed(self,p):
        self._prune_scalar_targets()
        if set(p)-{'cmd','action','preflight_token','request_id','spill_review_ack','shadow_review_ack','torso_review_ack','waist_review_ack','head_review_ack','collarbone_review_ack'}:
            raise SC.ScopeError('token commit cannot change reviewed options')
        cached=self.store.completed(p.get('preflight_token'),self.versions.workspace)
        if cached is None:return False
        if 'spill_review_ack' in cached:
            if type(p.get('spill_review_ack')) is not list or canonical(p['spill_review_ack'])!=canonical(cached['spill_review_ack']):
                raise SC.ScopeError('Spill token replay requires its exact original visual acknowledgment')
        elif 'spill_review_ack' in p:
            raise SC.ScopeError('Spill acknowledgment cannot accompany a non-spill token')
        if 'shadow_review_ack' in cached:
            if type(p.get('shadow_review_ack')) is not list or canonical(p['shadow_review_ack'])!=canonical(cached['shadow_review_ack']):
                raise SC.ScopeError('Original-shadow token replay requires its exact original visual acknowledgment')
        elif 'shadow_review_ack' in p:
            raise SC.ScopeError('Original-shadow acknowledgment cannot accompany a non-shadow token')
        for key in ('torso_review_ack','waist_review_ack','head_review_ack'):
            if key in cached:
                if type(p.get(key)) is not list or canonical(p[key])!=canonical(cached[key]):
                    raise SC.ScopeError('Body-scalar token replay requires its exact original visual acknowledgment')
            elif key in p:
                raise SC.ScopeError('Body-scalar acknowledgment cannot accompany a different-family token')
        if 'collarbone_review_ack' in cached:
            if type(p.get('collarbone_review_ack')) is not list or canonical(p['collarbone_review_ack'])!=canonical(cached['collarbone_review_ack']):
                raise SC.ScopeError('Collarbone token replay requires its exact original visual acknowledgment')
        elif 'collarbone_review_ack' in p:
            raise SC.ScopeError('Collarbone acknowledgment cannot accompany another token')
        if p.get('request_id') is None:self.emit({**cached,'event':'batch_result','action':'commit','request_id':None,'replayed':True})
        else:self.emit_result(p,{**cached,'replayed':True})
        return True

    def handle(self,p):
        plan=None;resolved=[];commit_started=False;spill_ack=None;shadow_ack=None;scalar_ack=None;family=None
        try:
            self._prune_scalar_targets()
            if p['action']!='commit' and 'spill_review_ack' in p:
                raise SC.ScopeError('Spill visual acknowledgment is accepted only for a frozen commit')
            if p['action']!='commit' and 'shadow_review_ack' in p:
                raise SC.ScopeError('Original-shadow visual acknowledgment is accepted only for a frozen commit')
            if p['action']!='commit' and any(key in p for key in ('torso_review_ack','waist_review_ack','head_review_ack')):
                raise SC.ScopeError('Body-scalar visual acknowledgment is accepted only for a frozen commit')
            if p['action']!='commit' and 'collarbone_review_ack' in p:
                raise SC.ScopeError('Collarbone visual acknowledgment is accepted only for a frozen commit')
            if p['action']=='preflight' and p.get('people_transfer') is not None:
                if self.ports.people_transfer is None:raise ValueError('People transfer adapter unavailable')
                self.ports.people_transfer(self,p,None);return
            if p['action']=='commit':
                if self.replay_completed(p):return
                reviewed=self.store.get(p.get('preflight_token'),self.versions.workspace)
                if 'collarbone_review_ack' in p and not collarbone_required(reviewed):
                    raise SC.ScopeError('Collarbone acknowledgment requires its frozen people-transfer scope')
                if SC.SPILL_REMOVAL.OP in reviewed.modules:
                    if len(reviewed.targets)>SR.MAX_TARGETS:raise SC.ScopeError('Spill target count exceeds its reviewed display bound')
                    spill_records=[]
                    for target in reviewed.targets:
                        if target.blocked:continue
                        if target.spill_json is None:raise SC.ScopeError('Spill target lacks its frozen before/after review')
                        spill_records.append(SR.checked(json.loads(target.spill_json)))
                    # Bad/missing acknowledgment must fail before claim or a
                    # terminal receipt, so the actual reviewed token stays usable.
                    spill_ack=SR.acknowledgments(p.get('spill_review_ack'),spill_records)
                elif 'spill_review_ack' in p:
                    raise SC.ScopeError('Spill acknowledgment requires an explicitly selected spill module')
                if SC.ORIGINAL_SHADOW.OP in reviewed.modules:
                    if len(reviewed.targets)>SHR.MAX_TARGETS:raise SC.ScopeError('Original-shadow target count exceeds its reviewed display bound')
                    shadow_records=[]
                    for target in reviewed.targets:
                        if target.blocked:continue
                        if target.shadow_json is None:raise SC.ScopeError('Original-shadow target lacks its frozen before/after review')
                        shadow_records.append(SHR.checked(json.loads(target.shadow_json)))
                    # Bad/missing acknowledgment must fail before claim or a
                    # terminal receipt, so the actual reviewed token stays usable.
                    shadow_ack=SHR.acknowledgments(p.get('shadow_review_ack'),shadow_records)
                elif 'shadow_review_ack' in p:
                    raise SC.ScopeError('Original-shadow acknowledgment requires an explicitly selected shadow module')
                family=body_family(reviewed.modules)
                for key in ('torso_review_ack','waist_review_ack','head_review_ack'):
                    if key in p and (family is None or key!=family.ack_key):
                        raise SC.ScopeError('Body-scalar acknowledgment requires its explicitly selected family')
                if family is not None:
                    if len(reviewed.targets)>family.review.MAX_TARGETS:
                        raise SC.ScopeError('Body-scalar target count exceeds its reviewed display bound')
                    scalar_records=[]
                    for target in reviewed.targets:
                        if target.blocked:continue
                        value=getattr(target,family.frozen_key)
                        if value is None:raise SC.ScopeError('Body-scalar target lacks its frozen before/after review')
                        scalar_records.append(family.review.checked(json.loads(value)))
                    # Invalid acknowledgment never consumes an otherwise usable token.
                    scalar_ack=family.review.acknowledgments(p.get(family.ack_key),scalar_records)
                if '_semantic_colour_transfer' in reviewed.params():raise SC.ScopeError(SC.SEMANTIC.REASON)
                if '_people_transfer' in reviewed.params():
                    if self.ports.people_transfer is None:raise ValueError('People transfer adapter unavailable')
                    self.ports.people_transfer(self,p,reviewed);return
            if p['action']=='preflight' and SC.SEMANTIC.OP in (p.get('module_scope') or []):
                raise SC.ScopeError(SC.SEMANTIC.REASON)
            if p['action']=='preflight':
                ops=SC.check_scope(p.get('module_scope'));family=body_family(ops);policy=p.get('conflict_policy','skip_and_report')
                if 'lnx.collarbone.v1' in ops:raise SC.ScopeError('Collarbone batch requires confirmed or explicit target-owned people visual review')
                if policy not in ('skip_and_report','recheck'):raise SC.ScopeError(f'conflict_policy 未知：{policy!r}（可用：skip_and_report/recheck；没有 overwrite）')
                if p.get('preflight_token') is not None:raise SC.ScopeError('preflight does not accept an old token')
                indices,rejected=self.ports.targets(p.get('docs'))
                if SC.OP_CROP in ops and len(indices)>16:raise SC.ScopeError('Crop visual review supports at most sixteen targets; no target was omitted')
                if SC.SPILL_REMOVAL.OP in ops and len(indices)>SR.MAX_TARGETS:
                    raise SC.ScopeError('Spill visual review supports at most eight targets; no target was omitted')
                if SC.ORIGINAL_SHADOW.OP in ops and len(indices)>SHR.MAX_TARGETS:
                    raise SC.ScopeError('Original-shadow visual review supports at most eight targets; no target was omitted')
                if family is not None and len(indices)>family.review.MAX_TARGETS:
                    raise SC.ScopeError('Body-scalar visual review supports at most eight targets; no target was omitted')
                self.ports.remember()
                rows=self.ports.rows();index=self.ports.current()
                if not 0<=index<len(rows):raise SC.ScopeError('no active source document')
                source=self.ports.capture();source_row=rows[index];version=self.versions.version(source_row)
                mods=SC.params_of(source,ops)
                source_owned=family is not None or SC.ORIGINAL_SHADOW.OP in ops or SC.SPILL_REMOVAL.OP in ops or SC.OP_CROP in ops or SOURCE.record(source) is not None or any(SOURCE.record(rows[i].get('state') or {}) is not None for i in indices)
                source_proof=SOURCE.row_proof({**source_row,'state':source}) if source_owned else None
                TRANSFER.require_modules(source,mods,source_proof)
                reference_options=p.get('reference_color')
                if reference_options is not None:
                    if ops!=[RC.OP] or type(reference_options) is not dict or set(reference_options)!={'strength'}:
                        raise ValueError('新样片统一必须单独选择参考模块与程度')
                    if self.ports.capture_reference is None:raise ValueError('参考样片端口不可用')
                    mods[RC.OP]=self.ports.capture_reference(source_row,source,version.document_id,str(version.revision),reference_options['strength'])
                local_options=p.get('local_mask_transfer')
                if LG.OP in ops:
                    local_options=LG.options(local_options)
                    selected,_=LG.choose(mods[LG.OP]['groups'],local_options)
                    LG.portable({'version':1,'layers':selected})
                    LR.verify_original({'version':1,'layers':selected},source_row)
                elif local_options is not None:raise SC.ScopeError('局部蒙版选项需要明确选择独立局部调色模块')
                targets=[];public=[];scalar_targets={}
                for i in indices:
                    row=rows[i];v=self.versions.version(row);live=i==index
                    if family is not None:scalar_targets[v.document_id]=row
                    if family is not None:
                        blocked=self._blocked(row,ops,live)
                        try:before=OA.before_params(source if live else row['state'],ops)
                        except Exception as error:
                            # A missing/unreviewed body is an explicit blocked
                            # target, never a fabricated neutral dependency key.
                            before={};blocked=str(error)[:2000]
                    else:
                        before=OA.before_params(source if live else row['state'],ops);blocked=self._blocked(row,ops,live)
                    target_state=source if live else row['state'];target_proof=None
                    try:
                        if source_owned:target_proof=SOURCE.row_proof({**row,'state':target_state})
                        TRANSFER.require_modules(target_state,mods,source_proof)
                    except Exception as error:blocked=str(error)[:2000]
                    prepared=None;transfer=None;optics_record=None;optical_transfer=None;reference_record=None;crop_record=None;crop_transfer=None;spill_record=None;spill_transfer=None;shadow_record=None;shadow_transfer=None;scalar_record=None;scalar_transfer=None
                    if RC.OP in ops and live:blocked="参考图保持不变，不作为统一目标"
                    if not blocked and LG.OP in ops:
                        try:prepared,transfer=LR.prepare_modules(source if live else row['state'],mods,row,local_options,preview=len(public)<12)
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and (ID_BACKGROUND.OP in ops or SC.SPILL_REMOVAL.OP in ops or SC.ORIGINAL_SHADOW.OP in ops):
                        try:
                            candidate=OA.candidate(source if live else row['state'],prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            validator=SC.ORIGINAL_SHADOW if SC.ORIGINAL_SHADOW.OP in ops else SC.SPILL_REMOVAL if SC.SPILL_REMOVAL.OP in ops else ID_BACKGROUND
                            validator.validate_target(candidate,row['path'],(row['src_h'],row['src_w']))
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and SKY.OP in ops:
                        try:
                            candidate=OA.candidate(source if live else row["state"],prepared or mods,local_replace_legacy=bool(transfer and transfer["legacy_removed"]))
                            SKY.validate_target(candidate["_sky_replacement"],row["path"],(row["src_h"],row["src_w"]))
                        except Exception as error: blocked=str(error)[:2000]
                    if not blocked and (BROW.OP in ops or NOSE.OP in ops or EYE.OP in ops or MOUTH.OP in ops) and OA.OP not in ops:
                        try:
                            candidate=OA.candidate(source if live else row['state'],prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            if BROW.OP in ops: BROW.validate_target(candidate,row)
                            if NOSE.OP in ops: NOSE.validate_target(candidate,row)
                            if EYE.OP in ops: EYE.validate_target(candidate,row)
                            if MOUTH.OP in ops: MOUTH.validate_target(candidate,row)
                        except Exception as error: blocked=str(error)[:2000]
                    if not blocked and OA.OP in ops:
                        try:
                            if self.ports.prepare_optics is None:raise ValueError('本引擎缺少目标完整编辑预检端口')
                            original=source if live else row['state']
                            candidate=OA.candidate(original,prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            target_input=self.ports.prepare_optics(row,candidate,v.document_id,str(v.revision))
                            optics_record,optical_transfer=OR.prepare(mods[OA.OP],target_input,before_state=original,preview=len(public)<2)
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and RC.OP in ops:
                        try:
                            if self.ports.prepare_reference is None:raise ValueError('参考统一目标预检端口不可用')
                            candidate=OA.candidate(row['state'],prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            if optics_record is not None:candidate['_optics']=optics_record['recipe']
                            reference_record=self.ports.prepare_reference(row,candidate,v.document_id,str(v.revision),mods[RC.OP])
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and source_owned:
                        try:
                            candidate=OA.candidate(target_state,prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            TRANSFER.require_candidate(target_state,candidate,prepared or mods,source_proof)
                            if target_proof is not None:SOURCE.verify_row({**row,'state':self.ports.capture() if live else row['state']},target_proof)
                            if self.versions.version(row)!=v:raise ValueError('Target changed during parameter review')
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and SC.OP_CROP in ops:
                        try:
                            if self.ports.prepare_crop is None or self.ports.verify_crop is None:
                                raise ValueError('Crop requires an actual full edited target preview adapter')
                            candidate=OA.candidate(target_state,prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            if optics_record is not None:candidate['_optics']=optics_record['recipe']
                            if reference_record is not None:
                                RC.apply_verified(candidate,RC.verify_target(reference_record,target_state,candidate,row,v.document_id,v.revision,(prepared or mods)[RC.OP]))
                            crop_record,crop_transfer=self.ports.prepare_crop(row,candidate,v.document_id,str(v.revision))
                            self.ports.verify_crop(row,candidate,v.document_id,str(v.revision),crop_record)
                            SOURCE.verify_row({**row,'state':self.ports.capture() if live else row['state']},target_proof)
                            if self.versions.version(row)!=v:raise ValueError('Target changed during crop visual review')
                        except Exception as error:blocked=str(error)[:2000];crop_record=None;crop_transfer=None
                    if not blocked and SC.SPILL_REMOVAL.OP in ops:
                        try:
                            if self.ports.prepare_spill is None or self.ports.verify_spill is None:
                                raise ValueError('Spill requires actual full edited before/after target previews')
                            candidate=OA.candidate(target_state,prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            if optics_record is not None:candidate['_optics']=optics_record['recipe']
                            if reference_record is not None:
                                RC.apply_verified(candidate,RC.verify_target(reference_record,target_state,candidate,row,v.document_id,v.revision,(prepared or mods)[RC.OP]))
                            spill_record,spill_transfer=self.ports.prepare_spill(row,target_state,candidate,v.document_id,str(v.revision))
                            self.ports.verify_spill(row,target_state,candidate,v.document_id,str(v.revision),spill_record)
                            SOURCE.verify_row({**row,'state':self.ports.capture() if live else row['state']},target_proof)
                            if self.versions.version(row)!=v:raise ValueError('Target changed during spill visual review')
                        except Exception as error:blocked=str(error)[:2000];spill_record=None;spill_transfer=None;shadow_record=None;shadow_transfer=None
                    if not blocked and SC.ORIGINAL_SHADOW.OP in ops:
                        try:
                            if self.ports.prepare_shadow is None or self.ports.verify_shadow is None:
                                raise ValueError('Original-shadow requires actual full edited before/after target previews')
                            candidate=OA.candidate(target_state,prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            if optics_record is not None:candidate['_optics']=optics_record['recipe']
                            if reference_record is not None:
                                RC.apply_verified(candidate,RC.verify_target(reference_record,target_state,candidate,row,v.document_id,v.revision,(prepared or mods)[RC.OP]))
                            shadow_record,shadow_transfer=self.ports.prepare_shadow(row,target_state,candidate,v.document_id,str(v.revision))
                            self.ports.verify_shadow(row,target_state,candidate,v.document_id,str(v.revision),shadow_record)
                            SOURCE.verify_row({**row,'state':self.ports.capture() if live else row['state']},target_proof)
                            if self.versions.version(row)!=v:raise ValueError('Target changed during shadow visual review')
                        except Exception as error:blocked=str(error)[:2000];shadow_record=None;shadow_transfer=None
                    if not blocked and family is not None:
                        try:
                            prepare_scalar=getattr(self.ports,'prepare_'+family.port_name)
                            verify_scalar=getattr(self.ports,'verify_'+family.port_name)
                            if prepare_scalar is None or verify_scalar is None:
                                raise ValueError('Body-scalar requires actual full edited before/after target previews')
                            candidate=OA.candidate(target_state,prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            if optics_record is not None:candidate['_optics']=optics_record['recipe']
                            if reference_record is not None:
                                RC.apply_verified(candidate,RC.verify_target(reference_record,target_state,candidate,row,v.document_id,v.revision,(prepared or mods)[RC.OP]))
                            family.scope.validate_target(candidate,row['path'],(row['src_h'],row['src_w']))
                            scalar_record,scalar_transfer=prepare_scalar(row,target_state,candidate,v.document_id,str(v.revision))
                            verify_scalar(row,target_state,candidate,v.document_id,str(v.revision),scalar_record)
                            SOURCE.verify_row({**row,'state':self.ports.capture() if live else row['state']},target_proof)
                            if self.versions.version(row)!=v:raise ValueError('Target changed during body-scalar visual review')
                        except Exception as error:blocked=str(error)[:2000];scalar_record=None;scalar_transfer=None
                    private_transfer=None if transfer is None else {k:v for k,v in transfer.items() if k!='preview_jpeg'}
                    targets.append(FrozenTarget(v.document_id,v.revision,i,row['path'],blocked,canonical(before),
                        None if prepared is None else canonical(prepared),None if private_transfer is None else canonical(private_transfer),
                        None if optics_record is None else canonical(optics_record),None if reference_record is None else canonical(reference_record),
                        source_proof_json=None if target_proof is None else canonical(target_proof),
                        crop_json=None if crop_record is None else canonical(crop_record),
                        spill_json=None if spill_record is None else canonical(spill_record),
                        shadow_json=None if shadow_record is None else canonical(shadow_record),
                        **({family.frozen_key:None if scalar_record is None else canonical(scalar_record)} if family is not None else {})))
                    public.append({'index':i,'path':row['path'],'live':live,'blocked':blocked,'before':before,
                                   'document_id':v.document_id,'revision':str(v.revision),'local_mask_transfer':transfer,'optical_transfer':optical_transfer,'reference_color':reference_record,'crop_transfer':crop_transfer,'spill_transfer':spill_transfer,'shadow_transfer':shadow_transfer,'torso_transfer':None,
                                   **({family.wire_key:scalar_transfer} if family is not None else {}),
                                   **({'source_proof':target_proof} if source_owned else {})})
                if source_proof is not None:
                    SOURCE.verify_row({**source_row,'state':self.ports.capture()},source_proof)
                    if self.versions.version(source_row)!=version:raise ValueError('Source changed during parameter review')
                if family is not None:
                    current_rows=self.ports.rows()
                    for target in targets:
                        retained=scalar_targets[target.document_id]
                        found=self.versions.find(current_rows,target.document_id)
                        if (found is None or found[1] is not retained
                                or retained['path']!=target.path
                                or self.versions.version(retained).revision!=target.revision):
                            raise ValueError('Body-scalar target row was replaced or edited during preflight')
                plan=self.store.create(self.versions.workspace,version.document_id,version.revision,source_row['path'],
                    ops,mods,policy,targets,rejected,source_proof=source_proof)
                if family is not None:self._scalar_targets[plan.token]=scalar_targets
                self._prune_scalar_targets()
                body={'event':'batch_preflight','success':True,'outcome_unknown':False,'module_scope':ops,'source':'current',
                    'source_snapshot':self._source(plan),'applies':plan.params(),'policy':policy,'targets':public,
                    'rejected_docs':rejected,'ok':sum(not r['blocked'] for r in public),'blocked':sum(bool(r['blocked']) for r in public),
                    'preflight_token':plan.token,'workspace_generation':plan.workspace,'expires_ns':str(plan.expires_ns)}
                if LG.OP in ops:body['local_mask_transfer']=local_options
                # Every eligible crop/spill target has display evidence. Never let the native
                # mailbox silently lose an oversized otherwise-valid review.
                try:canonical(body,MAX_RESULT_BYTES-4096)
                except Exception:
                    self.store.pending.pop(plan.token,None)
                    raise
                self.emit(body);self.emit_result(p,body);return
            if set(p)-{'cmd','action','preflight_token','request_id','spill_review_ack','shadow_review_ack','torso_review_ack','waist_review_ack','head_review_ack','collarbone_review_ack'}:
                raise SC.ScopeError('token commit cannot change source, targets, modules or policy; preflight again')
            token=p.get('preflight_token')
            if self.replay_completed(p):return
            plan=self.store.get(token,self.versions.workspace);self.ports.remember()
            source_proof=None if plan.source_proof_json is None else SOURCE.check_row_proof(json.loads(plan.source_proof_json))
            all_rows=self.ports.rows();current=self.ports.current();live_state=self.ports.capture()
            by_id={self.versions.version(row).document_id:(i,row) for i,row in enumerate(all_rows)}
            resolved=[]
            for target in plan.targets:
                found=by_id.get(target.document_id)
                blocked=target.blocked;index=None;actual=None
                if found is None:blocked='target was removed or replaced'
                else:
                    index,row=found;actual=self.versions.version(row).revision
                    if family is not None and self._scalar_targets.get(plan.token,{}).get(target.document_id) is not row:
                        blocked='exact reviewed target row was removed or replaced; preflight again'
                    elif actual!=target.revision:blocked='target was edited after preflight; preflight again'
                    elif row['path']!=target.path:blocked='target source path changed after preflight; preflight again'
                    elif family is not None:
                        # Retain already blocked targets without trying to read
                        # nonexistent anatomy. Newly invalid body ownership is
                        # also a per-target conflict under skip-and-report.
                        if not blocked:
                            try:
                                if canonical(OA.before_params(live_state if index==current else row['state'],plan.modules))!=target.before_json:
                                    blocked='target parameters changed outside the reviewed snapshot'
                                else:blocked=self._blocked(row,plan.modules,index==current)
                            except Exception as error:blocked=str(error)[:2000]
                    elif canonical(OA.before_params(live_state if index==current else row['state'],plan.modules))!=target.before_json:
                        blocked='target parameters changed outside the reviewed snapshot'
                    elif not blocked:blocked=self._blocked(row,plan.modules,index==current)
                    if not blocked:
                        try:
                            state=live_state if index==current else row['state']
                            if source_proof is not None and target.source_proof_json is None:
                                raise ValueError('Reviewed target lacks its effective-source proof')
                            if target.source_proof_json is not None:
                                SOURCE.verify_row({**row,'state':state},json.loads(target.source_proof_json))
                            elif SOURCE.record(state) is not None:
                                raise ValueError('Legacy parameter review cannot authorize a derived target')
                            if source_proof is not None or target.source_proof_json is not None:
                                prepared=json.loads(target.prepared_json) if target.prepared_json is not None else plan.params()
                                TRANSFER.require_modules(state,prepared,source_proof)
                                candidate=OA.candidate(state,prepared,local_replace_legacy=bool(target.transfer_json and json.loads(target.transfer_json)['legacy_removed']))
                                TRANSFER.require_candidate(state,candidate,prepared,source_proof)
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and LG.OP in plan.modules:
                        try:LR.verify_modules(json.loads(target.prepared_json),row,json.loads(target.transfer_json))
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and (ID_BACKGROUND.OP in plan.modules or SC.SPILL_REMOVAL.OP in plan.modules or SC.ORIGINAL_SHADOW.OP in plan.modules):
                        try:
                            candidate=OA.candidate(live_state if index==current else row['state'],json.loads(target.prepared_json) if target.prepared_json is not None else plan.params(),local_replace_legacy=bool(target.transfer_json and json.loads(target.transfer_json)['legacy_removed']))
                            validator=SC.ORIGINAL_SHADOW if SC.ORIGINAL_SHADOW.OP in plan.modules else SC.SPILL_REMOVAL if SC.SPILL_REMOVAL.OP in plan.modules else ID_BACKGROUND
                            validator.validate_target(candidate,row['path'],(row['src_h'],row['src_w']))
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and SKY.OP in plan.modules:
                        try:
                            candidate=OA.candidate(live_state if index==current else row['state'],json.loads(target.prepared_json) if target.prepared_json is not None else plan.params(),local_replace_legacy=bool(target.transfer_json and json.loads(target.transfer_json)['legacy_removed']))
                            SKY.validate_target(candidate['_sky_replacement'],row['path'],(row['src_h'],row['src_w']))
                        except Exception as error: blocked=str(error)[:2000]
                    if not blocked and OA.OP in plan.modules:
                        try:
                            original=live_state if index==current else row['state']
                            prepared=json.loads(target.prepared_json) if target.prepared_json is not None else plan.params()
                            candidate=OA.candidate(original,prepared,local_replace_legacy=bool(target.transfer_json and json.loads(target.transfer_json)['legacy_removed']))
                            OA.verify_target(json.loads(target.optics_json),original,candidate,row,target.document_id,target.revision,prepared[OA.OP])
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and SC.OP_CROP in plan.modules:
                        try:
                            if target.crop_json is None or self.ports.verify_crop is None:
                                raise ValueError('Crop commit is missing its actual reviewed target preview')
                            original=live_state if index==current else row['state']
                            prepared=json.loads(target.prepared_json) if target.prepared_json is not None else plan.params()
                            candidate=OA.candidate(original,prepared,local_replace_legacy=bool(target.transfer_json and json.loads(target.transfer_json)['legacy_removed']))
                            if target.optics_json is not None:candidate['_optics']=json.loads(target.optics_json)['recipe']
                            if target.reference_json is not None:
                                RC.apply_verified(candidate,RC.verify_target(json.loads(target.reference_json),original,candidate,row,target.document_id,target.revision,prepared[RC.OP]))
                            self.ports.verify_crop(row,candidate,target.document_id,str(target.revision),json.loads(target.crop_json))
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and SC.SPILL_REMOVAL.OP in plan.modules:
                        try:
                            if target.spill_json is None or self.ports.verify_spill is None:
                                raise ValueError('Spill commit is missing its actual reviewed before/after target')
                            original=live_state if index==current else row['state']
                            prepared=json.loads(target.prepared_json) if target.prepared_json is not None else plan.params()
                            candidate=OA.candidate(original,prepared,local_replace_legacy=bool(target.transfer_json and json.loads(target.transfer_json)['legacy_removed']))
                            if target.optics_json is not None:candidate['_optics']=json.loads(target.optics_json)['recipe']
                            if target.reference_json is not None:
                                RC.apply_verified(candidate,RC.verify_target(json.loads(target.reference_json),original,candidate,row,target.document_id,target.revision,prepared[RC.OP]))
                            self.ports.verify_spill(row,original,candidate,target.document_id,str(target.revision),json.loads(target.spill_json))
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and SC.ORIGINAL_SHADOW.OP in plan.modules:
                        try:
                            if target.shadow_json is None or self.ports.verify_shadow is None:
                                raise ValueError('Original-shadow commit is missing its actual reviewed before/after target')
                            original=live_state if index==current else row['state']
                            prepared=json.loads(target.prepared_json) if target.prepared_json is not None else plan.params()
                            candidate=OA.candidate(original,prepared,local_replace_legacy=bool(target.transfer_json and json.loads(target.transfer_json)['legacy_removed']))
                            if target.optics_json is not None:candidate['_optics']=json.loads(target.optics_json)['recipe']
                            if target.reference_json is not None:
                                RC.apply_verified(candidate,RC.verify_target(json.loads(target.reference_json),original,candidate,row,target.document_id,target.revision,prepared[RC.OP]))
                            self.ports.verify_shadow(row,original,candidate,target.document_id,str(target.revision),json.loads(target.shadow_json))
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and family is not None:
                        try:
                            value=getattr(target,family.frozen_key);verify_scalar=getattr(self.ports,'verify_'+family.port_name)
                            if value is None or verify_scalar is None:
                                raise ValueError('Body-scalar commit is missing its actual reviewed before/after target')
                            original=live_state if index==current else row['state']
                            prepared=json.loads(target.prepared_json) if target.prepared_json is not None else plan.params()
                            candidate=OA.candidate(original,prepared,local_replace_legacy=bool(target.transfer_json and json.loads(target.transfer_json)['legacy_removed']))
                            if target.optics_json is not None:candidate['_optics']=json.loads(target.optics_json)['recipe']
                            if target.reference_json is not None:
                                RC.apply_verified(candidate,RC.verify_target(json.loads(target.reference_json),original,candidate,row,target.document_id,target.revision,prepared[RC.OP]))
                            family.scope.validate_target(candidate,row['path'],(row['src_h'],row['src_w']))
                            verify_scalar(row,original,candidate,target.document_id,str(target.revision),json.loads(value))
                        except Exception as error:blocked=str(error)[:2000]
                resolved.append({'index':index,'path':target.path,'blocked':blocked,'document_id':target.document_id,
                    **({'_reviewed_row':self._scalar_targets.get(plan.token,{}).get(target.document_id)} if family is not None else {}),
                    '_source_proof':None if target.source_proof_json is None else json.loads(target.source_proof_json),
                    '_crop_prepared':None if target.crop_json is None else json.loads(target.crop_json),
                    '_spill_prepared':None if target.spill_json is None else json.loads(target.spill_json),
                    '_shadow_prepared':None if target.shadow_json is None else json.loads(target.shadow_json),
                    **({family.prepared_key:None if getattr(target,family.frozen_key) is None else json.loads(getattr(target,family.frozen_key))} if family is not None else {}),
                    '_reference_prepared':None if target.reference_json is None else json.loads(target.reference_json),
                    '_optics_prepared':None if target.optics_json is None else json.loads(target.optics_json),
                    '_prepared_modules':None if target.prepared_json is None else json.loads(target.prepared_json),
                    '_local_replace_legacy':False if target.transfer_json is None else json.loads(target.transfer_json)['legacy_removed'],
                    'reviewed_index':target.index,'expected_revision':str(target.revision),'current_revision':None if actual is None else str(actual)})
            source=by_id.get(plan.source_id)
            source_changed=source is None or self.versions.version(source[1]).revision!=plan.source_revision
            if not source_changed and source_proof is not None:
                try:SOURCE.verify_row({**source[1],'state':live_state if source[0]==current else source[1]['state']},source_proof)
                except Exception:source_changed=True
            if RC.OP in plan.modules:
                if source_changed:raise SC.ScopeError('参考源图在预检后变化，请重新审核')
                # A newly captured current reference is source-file bound as well
                # as revision bound; an external file replacement is not an edit event.
                records=[json.loads(t.reference_json) for t in plan.targets if t.reference_json is not None]
                if any(r['reference']['document_id']==plan.source_id for r in records):
                    from .local_mask_state import verify_source
                    verify_source({'source':plan.params()[RC.OP]['reference']['source']},source[1]['path'])
            if plan.policy=='recheck' and any(r['blocked'] for r in resolved):
                raise SC.ScopeError('preflight conflicts require a new review; no target was written')
            self.store.claim(plan,request_id=p.get('request_id'),**({'spill_review_ack':spill_ack} if spill_ack is not None else {}),**({'shadow_review_ack':shadow_ack} if shadow_ack is not None else {}),**({family.ack_key:scalar_ack} if scalar_ack is not None else {}));commit_started=True
            body=self.ports.commit(list(plan.modules),plan.params(),resolved,plan.policy,plan.rejected(),source_snapshot=self._source(plan))
            result={k:v for k,v in body.items() if k not in ('event','doc_state','frame')}
            outcomes=[]
            for row in resolved:
                found=by_id.get(row['document_id'])
                after=None if found is None else str(self.versions.version(found[1]).revision)
                outcomes.append({**{k:v for k,v in row.items() if not k.startswith('_')},'result_revision':after,'outcome':'skipped' if row['blocked'] else 'applied'})
            result.update(success=True,outcome_unknown=False,target_outcomes=outcomes,preflight_token=plan.token,workspace_generation=plan.workspace,request_id=p.get('request_id'),
                source_snapshot=self._source(plan),source_changed_since_preflight=source_changed,source_missing=source is None)
            if spill_ack is not None:result['spill_review_ack']=spill_ack
            if shadow_ack is not None:result['shadow_review_ack']=shadow_ack
            if scalar_ack is not None:result[family.ack_key]=scalar_ack
            if scalar_ack is not None:result['module_scope']=list(plan.modules)
            result=self.store.finish(plan,result);self.emit_result(p,result)
        except Exception as error:
            result={'success':False,'error':str(error)[:2000],'requires_preflight':True,'request_id':p.get('request_id'),
                    'outcome_unknown':commit_started,
                    'target_outcomes':[{**{k:v for k,v in r.items() if not k.startswith('_')},'outcome':'conflict' if r['blocked'] else ('unknown' if commit_started else 'not_applied')} for r in resolved],
                    'preflight_token':p.get('preflight_token'),'workspace_generation':self.versions.workspace}
            if spill_ack is not None:result['spill_review_ack']=spill_ack
            if shadow_ack is not None:result['shadow_review_ack']=shadow_ack
            if scalar_ack is not None:result[family.ack_key]=scalar_ack
            if scalar_ack is not None:result['module_scope']=list((plan or reviewed).modules)
            if plan is not None and p.get('action')=='commit':result=self.store.finish(plan,result)
            self.emit({'event':'error','error':'batch '+str(p.get('action'))+' rejected: '+result['error']})
            self.emit_result(p,result)
        finally:
            self._prune_scalar_targets()

    @staticmethod
    def _source(plan):
        return {'document_id':plan.source_id,'revision':str(plan.source_revision),'path':plan.source_path,
                **({'source_proof':json.loads(plan.source_proof_json)} if plan.source_proof_json is not None else {})}
