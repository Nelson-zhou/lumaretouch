import {useEffect,useState} from 'react';
import {useBatchWorkflow} from '../batch/useBatchWorkflow';
import {BatchReview} from '../batch/BatchReview';
export const REFERENCE_COLOR_OP='lnx.reference_color.v1';
export function ReferenceColorControls({sourceDocumentId,currentPath,targets,enabled,onComplete}:{sourceDocumentId:string;currentPath:string;targets:string[];enabled:boolean;onComplete:()=>void}){
  const [strength,setStrength]=useState(1),[last,setLast]=useState(''),[undone,setUndone]=useState(false);
  const selected=targets.filter(path=>path!==currentPath);
  const flow=useBatchWorkflow({docs:selected,moduleScope:[REFERENCE_COLOR_OP],conflictPolicy:'recheck',sourceDocumentId,
    enabled,referencePath:currentPath,label:'同场景参考白平衡/亮度',referenceColor:{strength}},onComplete);
  const busy=['preflighting','committing','uncertain'].includes(flow.ui.phase);
  useEffect(()=>{const result=flow.ui.result;if(result?.success&&result.batch_id){setLast(result.batch_id);setUndone(flow.ui.operation==='undo');}},[flow.ui.result,flow.ui.operation]);
  return <section className="referenceColorControls" aria-label="同场景参考统一">
    <strong>同场景色彩统一</strong>
    <span title={currentPath}> 参考：{currentPath.split(/[\\/]/).pop()||'请打开照片'}（保持不变）</span>
    <label>程度 {Math.round(strength*100)}% <input aria-label="参考统一程度" type="range" min="0" max="1" step="0.01" value={strength} disabled={busy} onChange={e=>setStrength(Number(e.target.value))}/></label>
    <button className="tb" disabled={!enabled||!selected.length||busy} onClick={flow.start}>预检已选 {selected.length} 张</button>
    <button className="tb" disabled={!last||busy||!enabled} onClick={()=>undone?flow.redo(last):flow.undo(last)}>{undone?'整组重做':'整组撤销'}</button>
    <small>以当前编辑成片为样片，逐图验证真实对应区域并计算白平衡/亮度。建议相近场景、后期调色最后使用；不是 AI 追色。换景、运动或混合光可能拒绝，必须检查成片。</small>
    <BatchReview state={flow.ui} onClose={flow.close} onCommit={flow.commit} onReview={flow.start} onQuery={flow.query} onAcknowledge={flow.acknowledgeInspection}/>
  </section>;
}
