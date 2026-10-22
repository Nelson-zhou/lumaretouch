import type {WhiteBalancePickerOwner} from './useWhiteBalancePicker';
export function WhiteBalancePickerControls({owner,onStart}:{owner:WhiteBalancePickerOwner;onStart:()=>void}){
  const {workflow,state,context}=owner;
  return <div className="whiteBalancePickerControls">
    <button disabled={!context.enabled||context.canStart===false||owner.active||owner.pending} onClick={onStart}>中性灰吸管</button>
    <button disabled={!owner.active} onClick={()=>workflow.cancel()}>取消取样</button>
    <small>先显示冻结的白平衡前输入，再点击应为中性的灰白处。取样最多 25 像素，过暗、过曝或旋转补边会拒绝；保留手动色温、色调与影调。</small>
    {!context.enabled&&<small>{context.reason}</small>}
    {state.message&&<p role="status">{state.message}</p>}
    {state.phase==='uncertain'&&<div><p>结果未确认，不要再次取样；仅查询原操作。</p>
      <button onClick={()=>void workflow.check()}>查询原操作结果</button>
      <button disabled={!context.enabled||context.documentId===state.request?.document_id} onClick={()=>workflow.acknowledgeAfterReload()}>已重新打开照片</button></div>}
  </div>;
}
export function WhiteBalancePickerStatus({owner}:{owner:WhiteBalancePickerOwner}){
  if(!['sending','waiting','uncertain','success','failure'].includes(owner.state.phase)||!owner.state.message)return null;
  return <div className="sourcePatchStatus" role="status"><span>{owner.state.message}</span>
    {owner.state.phase==='uncertain'&&<button onClick={()=>void owner.workflow.check()}>查询原白平衡结果</button>}</div>;
}
