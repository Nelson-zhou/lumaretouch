import {useState} from 'react';
import {needsAnalysis,neutralControls,validControls,validRevision} from './model';
import type {ProtectionControls,ProtectionReport,ProtectedRegion} from './model';
import {abandonProtection,queryProtection,showProtectionMessage,submitProtection,useProtectionOperation} from './owner';

type Props={report?:ProtectionReport;disabled:boolean;onChanged:()=>Promise<void>};
/** Key drafts to canonical revision; never transplant one photo's draft onto another. */
export function PortraitProtectionControls(props:Props) {
  const r=props.report;
  const valid=!!r&&validControls(r.controls)&&validRevision(r.revision)&&typeof r.document_id==='string'
    &&typeof r.active==='boolean'&&typeof r.analysis_available==='boolean';
  return <section aria-label="人像保护">
    <p>单人 P0：仅使用实际验证的人脸与面部皮肤证据。不是身份识别，也不保证去除所有瑕疵。</p>
    {valid?<Editor key={`${r!.document_id}:${r!.revision}`} {...props} report={r!}/>:<p role="status">当前文档未提供有效的人像保护状态；不能编辑。</p>}
    <ReceiptActions onChanged={props.onChanged}/>
  </section>;
}
function ReceiptActions({onChanged}:{onChanged:()=>Promise<void>}) {
  const op=useProtectionOperation();
  async function refresh(action:Promise<boolean>){if(await action){try{await onChanged();}catch(e){showProtectionMessage(`原操作已核实，但当前状态刷新失败：${String(e)}`);}}}
  return <>
    {op.pending&&<p>原操作绑定文档 {op.pending.document_id}，版本 {op.pending.revision}；等待期间不能提交新的保护设置。</p>}
    {op.pending&&<button type="button" disabled={op.busy} onClick={()=>void refresh(queryProtection())}>查询原保护操作（不重发）</button>}
    {op.pending&&op.recoveryAvailable&&<button type="button" disabled={op.busy} onClick={()=>void refresh(abandonProtection())}>按已验证的新工作区放弃旧等待（旧结果仍未知）</button>}
    {op.message&&<p role="status" aria-live="polite">{op.message}</p>}
  </>;
}
function Editor({report,disabled,onChanged}:Props&{report:ProtectionReport}) {
  const op=useProtectionOperation();
  const [draft,setDraft]=useState<ProtectionControls>(()=>structuredClone(report.controls));
  const [region,setRegion]=useState(['0','0','1','1']);
  const [error,setError]=useState('');
  const locked=disabled||op.busy||!!op.pending||op.storageBlocked;
  function change<K extends keyof ProtectionControls>(key:K,value:ProtectionControls[K]){setDraft(d=>({...d,[key]:value}));}
  async function apply(controls:ProtectionControls){
    if(locked)return;
    if(await submitProtection(report,controls)){try{await onChanged();}catch(e){showProtectionMessage(`保护配方已提交，但当前状态刷新失败：${String(e)}`);}}
  }
  function addRegion(){
    const box=region.map(s=>s.trim()===''?NaN:Number(s)) as ProtectedRegion;
    const next={...draft,protected_regions:[...draft.protected_regions,box]};
    if(!validControls(next)){setError('矩形需为 0–1 的原图坐标，左<右、上<下；最多 64 个。');return;}
    setDraft(next);setError('');
  }
  return <>
    <p>当前已提交：{report.active?'有界小瑕疵校正启用':'校正未启用'}；实际分析证据：{report.analysis_available?'可用':'不可用'}。</p>
    {report.reason&&<p role="status">{report.reason}</p>}
    <details><summary>查看当前已提交配方（不是下方草稿）</summary><pre>{JSON.stringify(report.controls,null,2)}</pre></details>
    <fieldset disabled={locked}>
      <legend>待提交设置</legend>
      <label><input type="checkbox" checked={draft.enabled} onChange={e=>change('enabled',e.target.checked)}/>启用有界小瑕疵校正</label>
      <label>强度 <input type="range" min="0" max="1" step="0.01" value={draft.strength} onChange={e=>change('strength',Number(e.target.value))}/><output>{Math.round(draft.strength*100)}%</output></label>
      <label><input type="checkbox" checked={draft.protect_identity_marks} onChange={e=>change('protect_identity_marks',e.target.checked)}/>保守保护深色标记（非痣、疤痕或纹身分类器）</label>
      <label><input type="checkbox" checked={draft.analysis_enabled} onChange={e=>change('analysis_enabled',e.target.checked)}/>保留实际单人分析证据</label>
      <label><input type="checkbox" checked={draft.overlay_visible} onChange={e=>change('overlay_visible',e.target.checked)}/>显示分析叠层（仅预览，不写入导出）</label>
      <label>保护羽化（原图像素，0–256）<input type="number" min="0" max="256" step="1" value={draft.feather} onChange={e=>change('feather',e.target.valueAsNumber)}/></label>
      <fieldset><legend>手工保护矩形（{draft.protected_regions.length}/64）</legend>
        <p>使用未裁剪、未翻转原图的归一化坐标：左上角 (0,0)，右下角 (1,1)。不是当前画布坐标；叠层不代表所有自动保护区域。</p>
        {['左','上','右','下'].map((label,i)=><label key={label}>{label}<input type="number" min="0" max="1" step="0.001" value={region[i]} onChange={e=>setRegion(old=>old.map((v,j)=>i===j?e.target.value:v))}/></label>)}
        <button type="button" disabled={draft.protected_regions.length>=64} onClick={addRegion}>添加保护矩形</button>
        <ol>{draft.protected_regions.map((box,i)=><li key={i}>{box.join(', ')} <button type="button" aria-label={`移除保护矩形 ${i+1}`} onClick={()=>change('protected_regions',draft.protected_regions.filter((_,j)=>i!==j))}>移除</button></li>)}</ol>
        {error&&<p role="alert">{error}</p>}
      </fieldset>
      {!report.analysis_available&&<p>当前无可用分析证据；需先取得实际单人分析。可关闭校正与分析，不能以多人、推断或整图皮肤替代。</p>}
      <button type="button" disabled={!validControls(draft)||(needsAnalysis(draft)&&!report.analysis_available)} onClick={()=>void apply(draft)}>提交保护设置</button>
      <button type="button" onClick={()=>setDraft(structuredClone(report.controls))}>还原草稿</button>
      <button type="button" onClick={()=>void apply(neutralControls())}>清除保护配方</button>
    </fieldset>
  </>;
}
