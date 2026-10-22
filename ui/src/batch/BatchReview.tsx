import {MaskTransferEvidenceView} from '../localMasks/transfer';
import {useEffect,useRef} from 'react';
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
export function BatchReview({state,onCommit,onReview,onQuery,onAcknowledge,onClose}:{state:BatchUi;onCommit:()=>unknown;
  onReview:()=>unknown;onQuery:()=>unknown;onAcknowledge:()=>void;onClose:()=>void}){
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
  const title=state.operation==='undo'?'撤销批量同步':'批量同步预检';
  return <div className="batchReviewBackdrop">
    <section ref={dialog} tabIndex={-1} className="batchReview" role="dialog" aria-modal="true" aria-labelledby="batchReviewTitle">
      <header><h2 id="batchReviewTitle">{title}</h2><button className="tb" disabled={busy} onClick={onClose}>{state.phase==='uncertain'?'暂时收起':'关闭'}</button></header>
      <div aria-live="polite">
        {state.phase==='preflighting'&&<p>正在冻结源图配方并检查目标照片，尚未修改任何照片。</p>}
        {busy&&<p>正在等待引擎的实际结果，请勿重复提交。入队不代表已经完成。</p>}
        {state.message&&<p className="batchWarning">{state.message}</p>}
        {(state.phase==='uncertain'||result?.outcome_unknown)&&<p className="batchWarning">部分改动可能已经生效。关闭此窗口不会撤销已发送的任务，收起后仍保留本次任务；请再次查询，或检查照片后明确结束跟踪，勿盲目重复同步。</p>}
        {result?.success&&<p>{state.operation==='undo'?`已恢复 ${result.restored?.length??0} 张，冲突 ${result.conflicts?.length??0} 张。`:
          `已同步 ${result.target_outcomes?.filter(t=>t.outcome==='applied').length??0} 张，跳过 ${result.target_outcomes?.filter(t=>t.outcome==='skipped').length??0} 张。`}</p>}
      </div>
      {plan&&<>
        <p title={plan.source_snapshot.path}>源图：{file(plan.source_snapshot.path)} · 预检版本 {plan.source_snapshot.revision}</p>
        <p>{state.scopeLabel} · {plan.module_scope.length} 个模块</p>
        <p>固定使用预检时的配方；后续修改源图不会改变本次提交。目标照片若在预检后修改，不会被覆盖。</p>
        <p>预检可同步 {plan.ok} 张 · 受阻 {plan.blocked} 张 · 无效选择 {plan.rejected_docs?.length??0} 张</p>
        <p>冲突处理：{plan.policy==='recheck'?'任一目标变化则整批不写入，重新预检':'跳过有变化的目标，并逐张报告'}</p>
        {result?.source_changed_since_preflight&&<p>源图在预检后已变化，本次仍使用已确认的旧版本配方。</p>}
        <details><summary>查看冻结的模块与参数</summary><pre>{JSON.stringify(plan.applies,null,2)}</pre></details>
      </>}
      {!!targets.length&&<ul className="batchTargets">{targets.map(t=><li key={t.document_id} title={t.path}>
        <span>{file(t.path)}</span><span>{t.outcome==='applied'?'已同步':t.outcome==='unknown'?'结果未确认':t.outcome==='not_applied'?'未执行':reason(t.blocked)}</span>
        {t.local_mask_transfer&&<MaskTransferEvidenceView value={t.local_mask_transfer}/>}
      </li>)}</ul>}
      {!!plan?.rejected_docs?.length&&<ul>{plan.rejected_docs.map((r,i)=><li key={i}>{String(r.doc)}：{r.error}</li>)}</ul>}
      {!!result?.conflicts?.length&&<ul>{result.conflicts.map((r,i)=><li key={i}>{file(r.path)}：{r.reason}</li>)}</ul>}
      <footer>
        {state.phase==='review'&&<button className="tb primary" disabled={!plan?.ok||(plan.policy==='recheck'&&plan.blocked>0)} onClick={onCommit}>确认本次配方并同步</button>}
        {['review','error','done'].includes(state.phase)&&state.operation!=='undo'&&<button className="tb" onClick={onReview}>重新预检</button>}
        {state.phase==='uncertain'&&<><button className="tb" onClick={onAcknowledge}>我已检查照片，结束本次跟踪</button><button className="tb primary" onClick={onQuery}>再次查询这次任务</button></>}
      </footer>
    </section>
  </div>;
}
