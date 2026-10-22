import {MaskTransferControls,type MaskTransferOptions,type TransferGroupChoice} from '../localMasks/transfer';
/** A real, reachable photo-recipe workflow, separate from file-export controls. */
export function BatchActions(props:{count:number;scopes:Array<{label:string;ops:string[]}>;scope:string;policy:string;
  onScope:(value:string)=>void;onPolicy:(value:string)=>void;ready:boolean;busy:boolean;unresolved:boolean;
  groups?:TransferGroupChoice[];localMaskTransfer?:MaskTransferOptions;onLocalMaskTransfer?:(v:MaskTransferOptions)=>void;canUndo:boolean;note:string;onReview:()=>unknown;onUndo:()=>unknown}){
  const hasScope = props.scopes.some(s => s.label === props.scope && s.ops.length > 0);
  return <section className="batchActions" aria-label="批量配方同步">
    <div><strong>配方同步</strong><span>底片条已选 {props.count} 张（Ctrl / Shift 多选）</span></div>
    <div><button className="tb primary" disabled={!props.unresolved&&(!props.ready||!props.count||!hasScope||props.busy)} onClick={props.onReview}>
      {props.unresolved?'查看未确认任务':'预检并同步配方'}</button>
      <button className="tb" disabled={!props.ready||!props.canUndo||props.busy||props.unresolved} onClick={props.onUndo}>撤销上一批同步</button></div>
    <details className="batchSettings"><summary>范围与冲突</summary><div>
    <label>同步范围<select value={props.scope} disabled={props.busy||props.unresolved} onChange={e=>props.onScope(e.target.value)}>
      {props.scopes.map(s=><option key={s.label} value={s.label}>{s.label}</option>)}</select></label>
    <label>目标变化时<select value={props.policy} disabled={props.busy||props.unresolved} onChange={e=>props.onPolicy(e.target.value)}>
      <option value="skip_and_report">跳过并逐张报告</option><option value="recheck">整批不写入，重新预检</option></select></label>
      <small>{props.note}</small>
      {props.localMaskTransfer&&props.onLocalMaskTransfer&&<MaskTransferControls groups={props.groups} value={props.localMaskTransfer} onChange={props.onLocalMaskTransfer} disabled={props.busy||props.unresolved}/>}
    </div></details>
    {!props.ready&&<small>需要已打开照片及支持批量预检的配套引擎。</small>}
  </section>;
}
