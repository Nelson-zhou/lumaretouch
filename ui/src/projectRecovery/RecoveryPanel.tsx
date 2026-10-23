import {useEffect, useState, useSyncExternalStore} from 'react';
import type {createRecoveryWorkflow, RecoveryCandidate, Review} from './model';
type Workflow=ReturnType<typeof createRecoveryWorkflow>;
export function RecoveryPanel({workflow, autosave, chooseNewDirectory, chooseSource, openRestored}: {
  workflow:Workflow; autosave:ReturnType<Workflow['snapshot']>;
  chooseNewDirectory:()=>Promise<string|null>; chooseSource:()=>Promise<string|null>;
  openRestored:(path:string)=>Promise<void>;
}) {
  const state=useSyncExternalStore(workflow.subscribe,workflow.snapshot,workflow.snapshot);
  const [candidates,setCandidates]=useState<RecoveryCandidate[]>([]);
  const [area,setArea]=useState<'candidates'|'trash'>('candidates');
  const [selected,setSelected]=useState<RecoveryCandidate|null>(null);
  const [review,setReview]=useState<Review|null>(null);
  const [confirm,setConfirm]=useState<'restore'|'discard'|null>(null);
  const [notice,setNotice]=useState('');
  useEffect(()=>{
    if(state.phase==='idle'){setCandidates([]);setSelected(null);setReview(null);setConfirm(null);}
    if(state.reply?.candidates){setCandidates(state.reply.candidates);setArea(state.reply.area??'candidates');}
    if(state.reply?.review)setReview(state.reply.review);
  },[state]);
  const locked=state.phase==='working'||state.phase==='uncertain';
  async function relink(source_asset_id:string){
    if(!selected||!review)return;
    const path=await chooseSource();if(!path)return;
    if(!window.confirm(`只接受完整 SHA256 相同的原图，将创建新的恢复候选，保留旧候选。\n${path}`))return;
    await workflow.run('relink',{candidate_id:selected.candidate_id,source_asset_id,path,area,
      reviewed_sha256:review.receipt.project_sha256,confirmed:true});
    setNotice('请刷新候选并检查新版本，原候选未覆盖。');
  }
  async function restore(){
    if(!selected||!review)return;
    const destination=await chooseNewDirectory();if(!destination)return;
    await workflow.run(area==='trash'?'restore_trash':'restore',{candidate_id:selected.candidate_id,area,
      reviewed_sha256:review.receipt.project_sha256,destination,confirmed:true});
    setConfirm(null);
  }
  return <section aria-label="项目崩溃恢复与版本快照">
    <h3>本机自动保存与恢复</h3>
    <p>自动保存不替代手动保存。只创建完整恢复候选，不覆盖原工程，不上传。失败或未知事务会暂停自动保存。</p>
    <p role="status">自动保存：{autosave.error??autosave.reply?.phase??autosave.phase}</p>
    {autosave.reply?.usage&&<p>恢复资料占用 {Math.ceil(autosave.reply.usage.bytes/1e6)} / {Math.floor(autosave.reply.usage.budget_bytes/1e6)} MB（含回收站；不会自动永久删除）</p>}
    <button disabled={locked} onClick={()=>{setSelected(null);setReview(null);void workflow.run('list');}}>恢复候选</button>
    <button disabled={locked} onClick={()=>{setSelected(null);setReview(null);void workflow.run('trash_list');}}>可恢复回收站</button>
    <button disabled={locked} onClick={()=>void workflow.run('snapshot')}>保存完整版本快照</button>
    {locked&&<button onClick={()=>void workflow.read()}>查询原操作结果（不重发）</button>}
    <p role="status">{state.error??state.reply?.phase??state.phase} {notice}</p>
    {state.reply?.path&&<button onClick={()=>void openRestored(state.reply!.path!)}>打开新恢复副本（原工程不变）</button>}
    {state.reply?.operations?.length ? <details><summary>本机恢复操作记录（含中断操作）</summary><ul>
      {state.reply.operations.map(operation=><li key={operation.request.request_id}>
        {operation.request.action}：{operation.phase} · {operation.request.destination??operation.request.request_id}
        {operation.phase==='started'||operation.phase==='unknown'?<span>结果待核对，禁止直接重试覆盖；原候选保留。</span>:null}
        {operation.result?.success&&operation.result.path&&<button onClick={()=>void openRestored(operation.result!.path!)}>打开已完成副本</button>}
      </li>)}
    </ul></details>:null}
    <ul>{candidates.map(candidate=><li key={candidate.candidate_id}>
      {candidate.kind==='version_snapshot'?'版本快照':'自动保存'} · {candidate.revision??'未知版本'} · {candidate.project_bytes??0} 字节
      {candidate.phase==='damaged'?<span>损坏：{candidate.reason}，原文件保留</span>:<button disabled={locked} onClick={()=>{setSelected(candidate);setReview(null);setConfirm(null);void workflow.run('inspect',{candidate_id:candidate.candidate_id,area});}}>核对来源</button>}
    </li>)}</ul>
    {selected&&review?.receipt.candidate_id===selected.candidate_id&&<div>
      <ul>{review.sources.map(source=><li key={source.document_id}>{source.path}：{source.status}
        {source.status!=='matched'&&<button disabled={locked} onClick={()=>void relink(source.source_asset_id)}>选择并核对原图</button>}
      </li>)}</ul>
      {review.source_reconciliation_required&&<p role="alert">来源尚未核对，禁止使用旧蒙版处理变化后的图片。可选择完整哈希相同的原图创建新候选。</p>}
      <button disabled={locked||review.source_reconciliation_required} onClick={()=>setConfirm('restore')}>恢复为新工程副本</button>
      {area==='candidates'&&<button disabled={locked} onClick={()=>setConfirm('discard')}>移入可恢复回收站</button>}
    </div>}
    {confirm&&<div role="alertdialog" aria-label="确认恢复操作">
      <p>{confirm==='restore'?'只写入新目录，原工程与候选保留。继续？':'移入本机恢复回收站，不永久删除，也不释放磁盘空间。继续？'}</p>
      <button disabled={locked} onClick={()=>{if(confirm==='restore')void restore();else if(selected){void workflow.run('discard',{candidate_id:selected.candidate_id,confirmed:true});setConfirm(null);}}}>确认</button>
      <button disabled={locked} onClick={()=>setConfirm(null)}>取消</button>
    </div>}
  </section>;
}
