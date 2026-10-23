"""Frozen batch review/commit policy, using explicit document/editor ports."""
from . import brow_shape_scope as BROW, nose_shape_scope as NOSE, eye_shape_scope as EYE, mouth_shape_scope as MOUTH
from dataclasses import dataclass
from typing import Callable
import json
from . import scope as SC, reference_color_scope as RC
from . import sky_replacement_scope as SKY, optics_auto_scope as OA, id_background_scope as ID_BACKGROUND
from . import optics_transfer_review as OR
from . import local_grade_layers as LG
from . import local_grade_runtime as LR
from .batch_preflight import PreflightStore,FrozenTarget,canonical
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

class FrozenBatchController:
    def __init__(self,ports,versions,emit,clock):
        self.ports=ports;self.versions=versions;self.emit=emit;self.store=PreflightStore(clock)

    def _blocked(self,row,ops,live):
        if row.get('trashed'):return 'target is in the project trash'
        for op in ops:
            if SC.MODULES[op]['single_face']:
                verdict,reason=self.ports.face_check(row,live=live)
                if verdict!='ok':return f'{op}: {reason}'
        return None

    def emit_result(self,p,payload):
        # Result mailbox has no render pixels or full document snapshot.
        result={k:v for k,v in payload.items() if k not in ('event','doc_state','frame')}
        result.update(event='batch_result',action=p.get('action'),request_id=p.get('request_id'))
        if p.get('request_id') is not None:self.emit(result)
        return result

    def replay_completed(self,p):
        if set(p)-{'cmd','action','preflight_token','request_id'}:
            raise SC.ScopeError('token commit cannot change reviewed options')
        cached=self.store.completed(p.get('preflight_token'),self.versions.workspace)
        if cached is None:return False
        if p.get('request_id') is None:self.emit({**cached,'event':'batch_result','action':'commit','request_id':None,'replayed':True})
        else:self.emit_result(p,{**cached,'replayed':True})
        return True

    def handle(self,p):
        plan=None;resolved=[];commit_started=False
        try:
            if p['action']=='preflight' and p.get('people_transfer') is not None:
                if self.ports.people_transfer is None:raise ValueError('People transfer adapter unavailable')
                self.ports.people_transfer(self,p,None);return
            if p['action']=='commit':
                if self.replay_completed(p):return
                reviewed=self.store.get(p.get('preflight_token'),self.versions.workspace)
                if '_semantic_colour_transfer' in reviewed.params():raise SC.ScopeError(SC.SEMANTIC.REASON)
                if '_people_transfer' in reviewed.params():
                    if self.ports.people_transfer is None:raise ValueError('People transfer adapter unavailable')
                    self.ports.people_transfer(self,p,reviewed);return
            if p['action']=='preflight' and SC.SEMANTIC.OP in (p.get('module_scope') or []):
                raise SC.ScopeError(SC.SEMANTIC.REASON)
            if p['action']=='preflight':
                ops=SC.check_scope(p.get('module_scope'));policy=p.get('conflict_policy','skip_and_report')
                if policy not in ('skip_and_report','recheck'):raise SC.ScopeError(f'conflict_policy 未知：{policy!r}（可用：skip_and_report/recheck；没有 overwrite）')
                if p.get('preflight_token') is not None:raise SC.ScopeError('preflight does not accept an old token')
                indices,rejected=self.ports.targets(p.get('docs'));self.ports.remember()
                rows=self.ports.rows();index=self.ports.current()
                if not 0<=index<len(rows):raise SC.ScopeError('no active source document')
                source=self.ports.capture();source_row=rows[index];version=self.versions.version(source_row)
                mods=SC.params_of(source,ops)
                source_owned=SOURCE.record(source) is not None or any(SOURCE.record(rows[i].get('state') or {}) is not None for i in indices)
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
                targets=[];public=[]
                for i in indices:
                    row=rows[i];v=self.versions.version(row);live=i==index
                    before=OA.before_params(source if live else row['state'],ops);blocked=self._blocked(row,ops,live)
                    target_state=source if live else row['state'];target_proof=None
                    try:
                        if source_owned:target_proof=SOURCE.row_proof({**row,'state':target_state})
                        TRANSFER.require_modules(target_state,mods,source_proof)
                    except Exception as error:blocked=str(error)[:2000]
                    prepared=None;transfer=None;optics_record=None;optical_transfer=None;reference_record=None
                    if RC.OP in ops and live:blocked="参考图保持不变，不作为统一目标"
                    if not blocked and LG.OP in ops:
                        try:prepared,transfer=LR.prepare_modules(source if live else row['state'],mods,row,local_options,preview=len(public)<12)
                        except Exception as error:blocked=str(error)[:2000]
                    if not blocked and ID_BACKGROUND.OP in ops:
                        try:
                            candidate=OA.candidate(source if live else row['state'],prepared or mods,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
                            ID_BACKGROUND.validate_target(candidate,row['path'],(row['src_h'],row['src_w']))
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
                    private_transfer=None if transfer is None else {k:v for k,v in transfer.items() if k!='preview_jpeg'}
                    targets.append(FrozenTarget(v.document_id,v.revision,i,row['path'],blocked,canonical(before),
                        None if prepared is None else canonical(prepared),None if private_transfer is None else canonical(private_transfer),
                        None if optics_record is None else canonical(optics_record),None if reference_record is None else canonical(reference_record),
                        source_proof_json=None if target_proof is None else canonical(target_proof)))
                    public.append({'index':i,'path':row['path'],'live':live,'blocked':blocked,'before':before,
                                   'document_id':v.document_id,'revision':str(v.revision),'local_mask_transfer':transfer,'optical_transfer':optical_transfer,'reference_color':reference_record,
                                   **({'source_proof':target_proof} if source_owned else {})})
                if source_proof is not None:
                    SOURCE.verify_row({**source_row,'state':self.ports.capture()},source_proof)
                    if self.versions.version(source_row)!=version:raise ValueError('Source changed during parameter review')
                plan=self.store.create(self.versions.workspace,version.document_id,version.revision,source_row['path'],
                    ops,mods,policy,targets,rejected,source_proof=source_proof)
                body={'event':'batch_preflight','success':True,'module_scope':ops,'source':'current',
                    'source_snapshot':self._source(plan),'applies':plan.params(),'policy':policy,'targets':public,
                    'rejected_docs':rejected,'ok':sum(not r['blocked'] for r in public),'blocked':sum(bool(r['blocked']) for r in public),
                    'preflight_token':plan.token,'workspace_generation':plan.workspace,'expires_ns':str(plan.expires_ns)}
                if LG.OP in ops:body['local_mask_transfer']=local_options
                self.emit(body);self.emit_result(p,body);return
            if set(p)-{'cmd','action','preflight_token','request_id'}:
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
                    if actual!=target.revision:blocked='target was edited after preflight; preflight again'
                    elif row['path']!=target.path:blocked='target source path changed after preflight; preflight again'
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
                    if not blocked and ID_BACKGROUND.OP in plan.modules:
                        try:
                            candidate=OA.candidate(live_state if index==current else row['state'],json.loads(target.prepared_json) if target.prepared_json is not None else plan.params(),local_replace_legacy=bool(target.transfer_json and json.loads(target.transfer_json)['legacy_removed']))
                            ID_BACKGROUND.validate_target(candidate,row['path'],(row['src_h'],row['src_w']))
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
                resolved.append({'index':index,'path':target.path,'blocked':blocked,'document_id':target.document_id,
                    '_source_proof':None if target.source_proof_json is None else json.loads(target.source_proof_json),
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
            self.store.claim(plan);commit_started=True
            body=self.ports.commit(list(plan.modules),plan.params(),resolved,plan.policy,plan.rejected(),source_snapshot=self._source(plan))
            result={k:v for k,v in body.items() if k not in ('event','doc_state','frame')}
            outcomes=[]
            for row in resolved:
                found=by_id.get(row['document_id'])
                after=None if found is None else str(self.versions.version(found[1]).revision)
                outcomes.append({**{k:v for k,v in row.items() if not k.startswith('_')},'result_revision':after,'outcome':'skipped' if row['blocked'] else 'applied'})
            result.update(success=True,target_outcomes=outcomes,preflight_token=plan.token,workspace_generation=plan.workspace,
                source_snapshot=self._source(plan),source_changed_since_preflight=source_changed,source_missing=source is None)
            result=self.store.finish(plan,result);self.emit_result(p,result)
        except Exception as error:
            result={'success':False,'error':str(error)[:2000],'requires_preflight':True,
                    'outcome_unknown':commit_started,
                    'target_outcomes':[{**{k:v for k,v in r.items() if not k.startswith('_')},'outcome':'conflict' if r['blocked'] else ('unknown' if commit_started else 'not_applied')} for r in resolved],
                    'preflight_token':p.get('preflight_token'),'workspace_generation':self.versions.workspace}
            if plan is not None and p.get('action')=='commit':result=self.store.finish(plan,result)
            self.emit({'event':'error','error':'batch '+str(p.get('action'))+' rejected: '+result['error']})
            self.emit_result(p,result)

    @staticmethod
    def _source(plan):
        return {'document_id':plan.source_id,'revision':str(plan.source_revision),'path':plan.source_path,
                **({'source_proof':json.loads(plan.source_proof_json)} if plan.source_proof_json is not None else {})}
