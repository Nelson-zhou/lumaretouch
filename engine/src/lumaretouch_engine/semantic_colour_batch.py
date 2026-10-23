# SPDX-License-Identifier: GPL-3.0-or-later
"""Semantic colour adapter for the existing FrozenBatch and scoped batch ledger.

No second transaction scheduler, history stack or document identity. Preparation
performs real independent renders/inference/fits. Host wiring remains explicit.
"""
from copy import deepcopy
import json
from . import semantic_colour_state as S, semantic_colour_portable as P, semantic_colour_batch_target as T
from .semantic_colour_project import BUNDLE
from .semantic_colour_batch_assets import ProposalAssets
from .batch_preflight import FrozenTarget,canonical
MARKER='_semantic_colour_transfer'
MAX_TARGETS=128


class SemanticColourBatch:
    def __init__(self,engine):self.engine=engine;self.assets=ProposalAssets()
    def close(self):self.assets.close()

    def preflight(self,controller,request,*,cancelled=lambda:False,progress=lambda value:None,intent=None,bundle=None,include_current=False):
        """Private intent/bundle override is exclusively for checked preset import."""
        if set(request)-{'cmd','action','request_id','docs','module_scope','conflict_policy','semantic_colour'}:
            raise ValueError('语义追色不能混合其它批量选项')
        if request.get('module_scope')!=[S.OP] or request.get('semantic_colour')!={'source':'current'}:
            raise ValueError('必须明确选择单独的语义追色模块和当前已审核配方')
        policy=request.get('conflict_policy','skip_and_report')
        if policy not in ('skip_and_report','recheck'):raise ValueError('无效的批量冲突策略')
        e=self.engine;batch=e._batch_controller();batch.documents.remember_current();self.assets.prune(controller.store)
        rows=batch.documents.rows();source_index=batch.documents.current_index()
        if not 0<=source_index<len(rows):raise ValueError('没有可用的追色来源文档')
        source_row=rows[source_index];source_state=batch.editor.capture();source_version=batch.versions.version(source_row)
        from . import local_mask_state as LM
        if intent is None:
            intent=P.extract(source_state.get(S.KEY));bundle=source_state.get(BUNDLE)
            original=S.check(source_state.get(S.KEY))['target']['source'];LM.verify_source({'source':original},source_row['path'])
            source_key=T.owned_key(source_state);origin='document'
        else:
            intent=P.check(intent);original={'sha256':LM.source_digest(source_row['path']),'width':source_row['src_w'],'height':source_row['src_h']}
            source_key=None;origin='explicit-reference-preset'
        indices,rejected=batch.target_indices(request.get('docs'))
        if len(indices)>MAX_TARGETS:raise ValueError('一次冻结最多审核 128 张目标，请按组分批；未悄悄丢弃任何目标')
        if cancelled():raise InterruptedError('追色批量预检已取消')
        progress({'stage':'reference_analysis','targets':len(indices)})
        cache=T.reference_analysis(intent,bundle,cancelled=cancelled)
        targets=[];public=[];descriptors=[];plan=None
        try:
            for position,index in enumerate(indices):
                if cancelled():raise InterruptedError('追色批量预检已取消，未发布部分方案')
                row=rows[index];v=batch.versions.version(row);blocked=None;descriptor=None;summary=None;before_key=None
                try:
                    if row.get('trashed'):raise ValueError('目标在项目回收站')
                    if index==source_index and not include_current:raise ValueError('当前已编辑来源保持不变，不作为本次批量目标')
                    self.assets.admit();state=source_state if index==source_index else row['state'];before_key=T.owned_key(state)
                    progress({'stage':'target_fit','position':position+1,'targets':len(indices),'document_id':v.document_id,'path':row['path']})
                    record=T.prepare(e,row,state,v.document_id,v.revision,intent,cache,cancelled=cancelled)
                    summary=T.public(record);descriptor=self.assets.put(record);descriptors.append(descriptor)
                except InterruptedError:raise
                except Exception as error:blocked=str(error)[:2000]
                targets.append(FrozenTarget(v.document_id,v.revision,index,row['path'],blocked,
                    canonical({'owned_key':before_key}),prepared_json=None if descriptor is None else canonical(descriptor)))
                public.append({'index':index,'path':row['path'],'live':index==source_index,'document_id':v.document_id,
                    'revision':str(v.revision),'blocked':blocked,'semantic_colour':summary})
            current=batch.versions.version(source_row)
            if current!=source_version or LM.source_digest(source_row['path'])!=original['sha256']:
                raise ValueError('来源文档在预检期间改变，未发布方案')
            if source_key is not None and T.owned_key(batch.editor.capture())!=source_key:raise ValueError('来源追色意图在预检期间改变')
            if cancelled():raise InterruptedError('追色批量预检已取消')
            params={MARKER:{'intent':intent,'source_owned_key':source_key,'source_source':original,
                'reference_analysis_proof':cache['proof'],'origin':origin}}
            plan=controller.store.create(batch.versions.workspace,source_version.document_id,source_version.revision,
                source_row['path'],[S.OP],params,policy,targets,rejected)
            self.assets.bind(plan.token,descriptors);self.assets.prune(controller.store)
            body={'event':'batch_preflight','success':True,'module_scope':[S.OP],'source':'current',
                'source_snapshot':controller._source(plan),'applies':intent,'policy':policy,'targets':public,'rejected_docs':rejected,
                'ok':sum(not x['blocked'] for x in public),'blocked':sum(bool(x['blocked']) for x in public),
                'preflight_token':plan.token,'workspace_generation':plan.workspace,'expires_ns':str(plan.expires_ns),
                'semantic_colour':True,'quality_acceptance':'UNRUN'}
            canonical(body,limit=8*1024*1024)
            controller.emit(body);controller.emit_result(request,body);return body
        except BaseException:
            if plan is not None:
                controller.store.pending.pop(plan.token,None);self.assets.release(plan.token)
            for descriptor in descriptors:self.assets.drop(descriptor['id'])
            raise

    def preview(self,controller,token,document_id):
        """Lazy selected-target preview; no image grids in the frozen-plan receipt."""
        plan=controller.store.get(token,self.engine._document_versions().workspace)
        if MARKER not in plan.params():raise ValueError('不是语义追色方案')
        target=next((t for t in plan.targets if t.document_id==document_id),None)
        if target is None or target.blocked or target.prepared_json is None:raise ValueError('目标没有可审核的拟合结果')
        record=self.assets.get(json.loads(target.prepared_json));batch=self.engine._batch_controller()
        found=batch.versions.find(batch.documents.rows(),document_id)
        if found is None:raise ValueError('审核目标已移除')
        index,row=found;state=batch.editor.capture() if index==batch.documents.current_index() else row['state']
        T.verify(self.engine,row,state,document_id,target.revision,plan.params()[MARKER]['intent'],record)
        return {'preflight_token':token,'document_id':document_id,'proof':record['proof'],'preview':deepcopy(record['preview']),
            'semantic_colour':T.public(record)}

    def commit(self,controller,request,plan,*,cancelled=lambda:False,before_write=lambda:None,record_live_history=False):
        if set(request)-{'cmd','action','request_id','preflight_token'}:raise ValueError('提交只能使用原冻结 token，不能修改意图或目标')
        params=plan.params().get(MARKER)
        if params is None:raise ValueError('不是语义追色冻结方案')
        intent=P.check(params['intent']);e=self.engine;batch=e._batch_controller();batch.documents.remember_current()
        source=batch.versions.find(batch.documents.rows(),plan.source_id)
        from . import local_mask_state as LM,reference_color_assets as A
        if source is None or source[1]['path']!=plan.source_path or batch.versions.version(source[1]).revision!=plan.source_revision:
            raise ValueError('来源文档在审核后改变')
        LM.verify_source({'source':params['source_source']},source[1]['path'])
        if params['source_owned_key'] is not None and T.owned_key(source[1]['state'])!=params['source_owned_key']:
            raise ValueError('来源追色贡献在审核后改变')
        from .semantic_colour_canvas import reference_admission
        reference_admission(intent['reference'],include_bundle=True);bundle=A.bundle(intent['reference'])
        planned=[];outcomes=[]
        for target in plan.targets:
            if cancelled():raise InterruptedError('批量追色提交前已取消，没有目标被写入')
            found=batch.versions.find(batch.documents.rows(),target.document_id);blocked=target.blocked
            try:
                if blocked:raise ValueError(blocked)
                if found is None:raise ValueError('目标已移除')
                index,row=found;v=batch.versions.version(row)
                if row.get('trashed') or row['path']!=target.path or v.revision!=target.revision:raise ValueError('目标在审核后改变')
                before=batch.editor.capture() if index==batch.documents.current_index() else row['state']
                if T.owned_key(before)!=json.loads(target.before_json)['owned_key']:raise ValueError('目标追色贡献在审核后改变')
                record=self.assets.get(json.loads(target.prepared_json))
                if record.get('reference_analysis_proof')!=params['reference_analysis_proof']:raise ValueError('目标不是本次样片分析产生')
                T.verify(e,row,before,target.document_id,target.revision,intent,record)
                from .cpu_memory_budget import available_estimate
                if available_estimate()<2*24*1024*1024+128*1024*1024:raise ValueError('目标保留蒙版的提交内存不足，未替换为低分辨率输出')
                after=T.install(before,record,bundle);planned.append((index,row,before,after))
            except Exception as error:blocked=str(error)[:2000]
            outcomes.append({'index':None if found is None else found[0],'document_id':target.document_id,'path':target.path,
                'expected_revision':str(target.revision),'blocked':blocked,'outcome':'skipped' if blocked else 'prepared'})
        if plan.policy=='recheck' and any(x['blocked'] for x in outcomes):raise ValueError('有目标冲突，整组未修改；请重新审核')
        if not planned:raise ValueError('没有合格的冻结目标，整组未修改')
        if cancelled():raise InterruptedError('批量追色提交前已取消')
        # Revalidate all source bytes after potentially lengthy artifact/mask
        # preparation. External file replacement does not advance editor fences.
        LM.verify_source({'source':params['source_source']},source[1]['path'])
        for index,row,before,after in planned:
            LM.verify_source({'source':after[S.KEY]['target']['source']},row['path'])
        path=A.cache_root()/(intent['reference']['asset_id']+'.npz')
        if path.is_symlink() or not path.is_file() or A._hash(path)!=intent['reference']['asset_id']:
            raise ValueError('样片资源在提交准备期间变化，整批未写入')
        if cancelled():raise InterruptedError('批量追色写入前已取消')
        # Claim existing FrozenBatch token before the first editor write.
        history_before=e._history_capture() if record_live_history and any(x[0]==batch.documents.current_index() for x in planned) else None
        controller.store.claim(plan);before_write()
        try:
            from .semantic_colour_batch_ledger import publish
            bid,frame=publish(batch,planned,policy=plan.policy,source_snapshot=controller._source(plan),review_token=plan.token)
            if history_before is not None:e._history_record('AI 追色逐目标应用',history_before,coalesce=False)
            for outcome in outcomes:
                if not outcome['blocked']:
                    outcome['outcome']='applied';outcome['result_revision']=str(batch.versions.version(batch.documents.rows()[outcome['index']]).revision)
            body={'event':'batch_committed','success':True,'batch_id':bid,'module_scope':[S.OP],'semantic_colour':True,
                'applied':[x[0] for x in planned],'skipped':[x for x in outcomes if x['blocked']],'target_outcomes':outcomes,
                'preflight_token':plan.token,'workspace_generation':plan.workspace,'source_snapshot':controller._source(plan),
                'source_changed_since_preflight':False,'source_missing':False}
            batch.last_result['skipped']=body['skipped'];controller.emit(body)
            if frame is not None:controller.emit(frame)
        except Exception as error:
            body={'success':False,'outcome_unknown':True,'error':str(error)[:2000],'preflight_token':plan.token,
                'workspace_generation':plan.workspace,'requires_preflight':True}
        result=controller.store.finish(plan,body);self.assets.release(plan.token);controller.emit_result(request,result);return result


def owner(engine):
    value=engine.__dict__.get('_semantic_colour_batch_owner')
    if value is None:value=engine._semantic_colour_batch_owner=SemanticColourBatch(engine)
    return value


def handle(engine,controller,request,plan,*,cancelled=lambda:False,progress=lambda value:None):
    service=owner(engine)
    return service.preflight(controller,request,cancelled=cancelled,progress=progress) if plan is None else service.commit(controller,request,plan,cancelled=cancelled)
