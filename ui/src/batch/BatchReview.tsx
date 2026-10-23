import {PeopleTransferEvidence} from '../people/transferReview';
import {ReferenceColorReview} from '../referenceColor/ReferenceColorReview';
import {AutomaticTransferReview} from '../optics/AutomaticTransferReview';
import {MaskTransferEvidenceView} from '../localMasks/transfer';
import {useEffect,useRef,type ReactNode} from 'react';
import type {BatchUi,BatchTarget} from './batchWorkflow';
import './batchReview.css';
const file=(path:string)=>path.split('/').pop()||path;
function reason(text:string|null|undefined){
  if(!text)return '可同步';
  const known:Record<string,string>={
    'target is in the project trash':'照片已移入项目回收站',
    'target was removed or replaced':'照片已移除或被替换',
    'target was edited after preflight; preflight again':'预检后已编辑，已保护，需重新预检',
    'target parameters changed outside the reviewed snapshot':'参数与预检快照不同，已保护',
  };return known[text]??text;
}
export function BatchReview({state,onCommit,onReview,onQuery,onAcknowledge,onClose,peoplePreview,commitBlockedReason}:{state:BatchUi;onCommit:()=>unknown;
  onReview:()=>unknown;onQuery:()=>unknown;onAcknowledge:()=>void;onClose:()=>void;peoplePreview?:ReactNode;commitBlockedReason?:string}){
  const dialog=useRef<HTMLElement>(null),close=useRef(onClose);close.current=onClose;
  const open=state.phase!=='closed'&&!state.hidden,busy=state.phase==='committing';
  useEffect(()=>{
    if(!open)return;
    const previous=document.activeElement as HTMLElement|null;dialog.current?.focus();
    const key=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close.current();}
      if(event.key==='Tab'){
        const items=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),summary,[tabindex="0"]')??[]);
        if(!items.length){event.preventDefault();return;}
        const first=items[0],last=items[items.length-1];
        if(event.shiftKey&&(document.activeElement===first||document.activeElement===dialog.current)){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&(document.activeElement===last||document.activeElement===dialog.current)){event.preventDefault();first.focus();}
      }
    };
    window.addEventListener('keydown',key,true);
    return()=>{window.removeEventListener('keydown',key,true);previous?.focus();};
  },[open]);
  if(!open)return state.phase==='uncertain'?<button className="batchPending tb" onClick={onReview}>查看未确认的批量任务</button>:null;
  const plan=state.plan,result=state.result;
  const targets:BatchTarget[]=result?.target_outcomes??plan?.targets??[];
  const title=state.operation==='redo'?'重做批量同步':state.operation==='undo'?'撤销批量同步':'批量同步预检';
  return <div className="batchReviewBackdrop">
    <section ref={dialog} tabIndex={-1} className="batchReview" role="dialog" aria-modal="true" aria-labelledby="batchReviewTitle">
      <header><h2 id="batchReviewTitle">{title}</h2><button className="tb" disabled={busy} onClick={onClose}>{state.phase==='uncertain'?'暂时收起':'关闭'}</button></header>
      <div aria-live="polite">
        {state.phase==='preflighting'&&<p>正在冻结源图配方并检查目标照片，尚未修改任何照片。</p>}
        {busy&&<p>正在等待引擎的实际结果，请勿重复提交。入队不代表已经完成。</p>}
        {state.message&&<p className="batchWarning">{state.message}</p>}
        {(state.phase==='uncertain'||result?.outcome_unknown)&&<p className="batchWarning">{state.operation==='preflight'?'只读预检尚未确认完成，尚未修改照片；收起后保留同一任务，请继续查询，不会重复解算。':'部分改动可能已经生效。关闭此窗口不会撤销已发送的任务，收起后仍保留本次任务；请再次查询，或检查照片后明确结束跟踪，勿盲目重复同步。'}</p>}
        {result?.success&&<p>{['undo','redo'].includes(state.operation)?`已恢复 ${result.restored?.length??0} 张，冲突 ${result.conflicts?.length??0} 张。`:
          `已同步 ${result.target_outcomes?.filter(t=>t.outcome==='applied').length??0} 张，跳过 ${result.target_outcomes?.filter(t=>t.outcome==='skipped').length??0} 张。`}</p>}
      </div>
      {plan&&<>
        <p title={plan.source_snapshot.path}>源图：{file(plan.source_snapshot.path)} · 预检版本 {plan.source_snapshot.revision}</p>
        <p>{state.scopeLabel} · {plan.module_scope.length} 个模块</p>
        <p>{plan.people_transfer?(plan.applies.target_policy==='explicit_face_map'?'只向本次手动指定的人脸同步勾选参数；不建立持久人物关联。源图、目标、人物状态或关联改变后必须重新预检。':'只向明确确认的同一人物同步勾选参数；源图、目标或关联改变后必须重新预检。'):plan.module_scope.includes('lnx.reference_color.v1')?'参考或目标在预检后修改则拒绝，必须重新审核。样片保持不变，整组撤销/重做保留其他手动编辑。':'固定使用预检时的配方；目标照片若在预检后修改，不会被覆盖。'}</p>
        <p>预检可同步 {plan.ok} 张 · 受阻 {plan.blocked} 张 · 无效选择 {plan.rejected_docs?.length??0} 张</p>
        <p>冲突处理：{plan.policy==='recheck'?'任一目标变化则整批不写入，重新预检':'跳过有变化的目标，并逐张报告'}</p>
        {result?.source_changed_since_preflight&&<p>源图在预检后已变化，本次仍使用已确认的旧版本配方。</p>}
        <details><summary>查看冻结的模块与参数</summary><pre>{JSON.stringify(plan.applies,null,2)}</pre></details>
        {peoplePreview}
      </>}
      {!!targets.length&&<ul className="batchTargets">{targets.map(t=><li key={t.document_id} title={t.path}>
        <span>{file(t.path)}</span><span>{t.outcome==='applied'?'已同步':t.outcome==='unknown'?'结果未确认':t.outcome==='not_applied'?'未执行':reason(t.blocked)}</span>
        {t.people_transfer&&<PeopleTransferEvidence value={t.people_transfer}/>}
        {t.local_mask_transfer&&<MaskTransferEvidenceView value={t.local_mask_transfer}/>}
        {t.reference_color&&<ReferenceColorReview value={t.reference_color}/>}
        {t.optical_transfer&&<AutomaticTransferReview report={t.optical_transfer}/>}
      </li>)}</ul>}
      {!!plan?.rejected_docs?.length&&<ul>{plan.rejected_docs.map((r,i)=><li key={i}>{String(r.doc)}：{r.error}</li>)}</ul>}
      {!!result?.conflicts?.length&&<ul>{result.conflicts.map((r,i)=><li key={i}>{file(r.path)}：{r.reason}</li>)}</ul>}
      <footer>
        {state.phase==='review'&&commitBlockedReason&&<p role="status">{commitBlockedReason}</p>}
        {state.phase==='review'&&<button className="tb primary" disabled={!!commitBlockedReason||!plan?.ok||(plan.policy==='recheck'&&plan.blocked>0)} onClick={onCommit}>{plan?.applies.target_policy==='explicit_face_map'?'仅确认本次人脸配对与参数并同步':'确认本次配方并同步'}</button>}
        {['review','error','done'].includes(state.phase)&&!['undo','redo'].includes(state.operation)&&<button className="tb" onClick={onReview}>重新预检</button>}
        {state.phase==='uncertain'&&<><button className="tb" onClick={onAcknowledge}>我已检查照片，结束本次跟踪</button><button className="tb primary" onClick={onQuery}>再次查询这次任务</button></>}
      </footer>
    </section>
  </div>;
}
