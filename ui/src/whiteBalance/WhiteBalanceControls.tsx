import type {ReactNode} from 'react';
import {useState} from 'react';
import {confirm} from '@tauri-apps/plugin-dialog';
import type {DocState} from '../native';
import type {useWhiteBalanceWorkflow} from './useWhiteBalanceWorkflow';
import type {Algorithm} from './workflow';
import './whiteBalance.css';
export function WhiteBalanceAutoControl({owner,blocked}:{owner:ReturnType<typeof useWhiteBalanceWorkflow>;blocked:boolean}){
  const {workflow,context}=owner;
  return <section className="whiteBalanceControls" aria-label="自动白平衡">
    <button disabled={blocked||!context.enabled||!context.autoAvailable||!context.autoInput||workflow.busy()}
      onClick={()=>void workflow.start('auto',undefined,context.documentId,workflow.generation(),context.autoInput?.input_id)}>自动白平衡</button>
    <small>一次性经典统计估计，可正常撤销；不是 AI 校准、吸管或真实光源识别。主导色、混合光场景仍可能偏色。</small>
    <small>替换上次自动／吸管校正，保留手动色温、色调、参考白和曝光。预设仅复制固定结果，不会逐图重新估计。</small>
    {!context.autoAvailable&&<small>匹配的 Rust 自动白平衡核心未安装或不可用；不会使用替代算法。</small>}
    {context.autoAvailable&&!context.autoInput&&<small>当前预白平衡输入不可用；请结束检查、关闭画布翻转并刷新照片。</small>}
  </section>;
}
export function WhiteBalanceControls({owner,value,picker,pickerBusy=false}:{picker?:ReactNode;pickerBusy?:boolean;owner:ReturnType<typeof useWhiteBalanceWorkflow>;value:DocState['exposure']|undefined}){
  const {workflow,state,context}=owner;const algorithm=value?.options?.algorithm;
  const [confirming,setConfirming]=useState(false);
  const disabled=pickerBusy||confirming||!context.enabled||workflow.busy()||!algorithm;
  const change=async(next:Algorithm)=>{
    const document=context.documentId;const generation=workflow.generation();
    setConfirming(true);
    try{
    if(!await confirm('切换白平衡算法可能改变当前照片的颜色。原算法可通过撤销恢复，是否继续？',{title:'切换白平衡算法',kind:'warning'}))return;
    await workflow.start('set_algorithm',next,document,generation);
    }catch(error){workflow.reportUIError(error);}finally{setConfirming(false);}
  };
  return <section className="whiteBalanceControls" aria-label="白平衡算法与重置">
    <div>当前：{algorithm==='linear-srgb-d-white-ratio-v1'?'校正版白平衡':algorithm==='legacy-xyz-ratio-v1'?'旧版白平衡（保留原效果）':'等待照片状态'}</div>
    <div className="whiteBalanceButtons">
      <button disabled={disabled||algorithm==='linear-srgb-d-white-ratio-v1'} onClick={()=>void change('linear-srgb-d-white-ratio-v1')}>使用校正版</button>
      <button disabled={disabled||algorithm==='legacy-xyz-ratio-v1'} onClick={()=>void change('legacy-xyz-ratio-v1')}>使用旧版</button>
      <button disabled={disabled} onClick={()=>void workflow.start('reset',undefined,context.documentId)}>仅重置白平衡</button>
    </div>
    {picker}
    <button disabled={disabled} onClick={()=>void workflow.start('clear_pick',undefined,context.documentId)}>仅清除自动／吸管校正</button>
    {!context.enabled&&<small>{context.reason??'请等待引擎与照片就绪'}</small>}
    <small>重置仅清除色温、色调和自动／吸管校正，保留曝光、影调与参考白。</small>
    {state.message&&<p role="status">{state.message}</p>}
    {state.phase==='uncertain'&&<div>
      <p>{state.request?.action==='auto'?'自动结果未确认，不会重发。请查询原回执；仍未知时重启应用并重新打开已确认工程，不能仅切换照片解锁。':'结果未确认，不会自动重发。请先查询；仍无法确认时，重新打开照片后解除锁定。'}</p>
      <button onClick={()=>void workflow.check()}>查询原操作结果</button>
      {state.request?.action!=='auto'&&<button disabled={!context.enabled||context.documentId===state.request?.document_id} onClick={()=>workflow.acknowledgeAfterReload()}>已重新打开照片</button>}
    </div>}
  </section>;
}
