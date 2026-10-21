"""Frozen batch review/commit policy, using explicit document/editor ports."""
from dataclasses import dataclass
from typing import Callable
from . import scope as SC
from .batch_preflight import PreflightStore,FrozenTarget,canonical

@dataclass(frozen=True)
class PlanPorts:
    rows:Callable[[],list]
    current:Callable[[],int]
    remember:Callable[[],None]
    capture:Callable[[],dict]
    targets:Callable
    face_check:Callable
    commit:Callable

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
            if p['action']=='preflight':
                ops=SC.check_scope(p.get('module_scope'));policy=p.get('conflict_policy','skip_and_report')
                if policy not in ('skip_and_report','recheck'):raise SC.ScopeError(f'conflict_policy 未知：{policy!r}（可用：skip_and_report/recheck；没有 overwrite）')
                if p.get('preflight_token') is not None:raise SC.ScopeError('preflight does not accept an old token')
                indices,rejected=self.ports.targets(p.get('docs'));self.ports.remember()
                rows=self.ports.rows();index=self.ports.current()
                if not 0<=index<len(rows):raise SC.ScopeError('no active source document')
                source=self.ports.capture();source_row=rows[index];version=self.versions.version(source_row)
                targets=[];public=[]
                for i in indices:
                    row=rows[i];v=self.versions.version(row);live=i==index
                    before=SC.params_of(source if live else row['state'],ops);blocked=self._blocked(row,ops,live)
                    targets.append(FrozenTarget(v.document_id,v.revision,i,row['path'],blocked,canonical(before)))
                    public.append({'index':i,'path':row['path'],'live':live,'blocked':blocked,'before':before,
                                   'document_id':v.document_id,'revision':str(v.revision)})
                plan=self.store.create(self.versions.workspace,version.document_id,version.revision,source_row['path'],
                    ops,SC.params_of(source,ops),policy,targets,rejected)
                body={'event':'batch_preflight','success':True,'module_scope':ops,'source':'current',
                    'source_snapshot':self._source(plan),'applies':plan.params(),'policy':policy,'targets':public,
                    'rejected_docs':rejected,'ok':sum(not r['blocked'] for r in public),'blocked':sum(bool(r['blocked']) for r in public),
                    'preflight_token':plan.token,'workspace_generation':plan.workspace,'expires_ns':str(plan.expires_ns)}
                self.emit(body);self.emit_result(p,body);return
            if set(p)-{'cmd','action','preflight_token','request_id'}:
                raise SC.ScopeError('token commit cannot change source, targets, modules or policy; preflight again')
            token=p.get('preflight_token')
            if self.replay_completed(p):return
            plan=self.store.get(token,self.versions.workspace);self.ports.remember()
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
                    elif canonical(SC.params_of(live_state if index==current else row['state'],plan.modules))!=target.before_json:
                        blocked='target parameters changed outside the reviewed snapshot'
                    elif not blocked:blocked=self._blocked(row,plan.modules,index==current)
                resolved.append({'index':index,'path':target.path,'blocked':blocked,'document_id':target.document_id,
                    'reviewed_index':target.index,'expected_revision':str(target.revision),'current_revision':None if actual is None else str(actual)})
            source=by_id.get(plan.source_id)
            source_changed=source is None or self.versions.version(source[1]).revision!=plan.source_revision
            if plan.policy=='recheck' and any(r['blocked'] for r in resolved):
                raise SC.ScopeError('preflight conflicts require a new review; no target was written')
            self.store.claim(plan);commit_started=True
            body=self.ports.commit(list(plan.modules),plan.params(),resolved,plan.policy,plan.rejected(),source_snapshot=self._source(plan))
            result={k:v for k,v in body.items() if k not in ('event','doc_state','frame')}
            outcomes=[]
            for row in resolved:
                found=by_id.get(row['document_id'])
                after=None if found is None else str(self.versions.version(found[1]).revision)
                outcomes.append({**row,'result_revision':after,'outcome':'skipped' if row['blocked'] else 'applied'})
            result.update(success=True,target_outcomes=outcomes,preflight_token=plan.token,workspace_generation=plan.workspace,
                source_snapshot=self._source(plan),source_changed_since_preflight=source_changed,source_missing=source is None)
            result=self.store.finish(plan,result);self.emit_result(p,result)
        except Exception as error:
            result={'success':False,'error':str(error)[:2000],'requires_preflight':True,
                    'outcome_unknown':commit_started,
                    'target_outcomes':[{**r,'outcome':'conflict' if r['blocked'] else ('unknown' if commit_started else 'not_applied')} for r in resolved],
                    'preflight_token':p.get('preflight_token'),'workspace_generation':self.versions.workspace}
            if plan is not None and p.get('action')=='commit':result=self.store.finish(plan,result)
            self.emit({'event':'error','error':'batch '+str(p.get('action'))+' rejected: '+result['error']})
            self.emit_result(p,result)

    @staticmethod
    def _source(plan):
        return {'document_id':plan.source_id,'revision':str(plan.source_revision),'path':plan.source_path}
