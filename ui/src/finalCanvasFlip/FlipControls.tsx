import type {FlipReport} from './model';
import {abandonFlip,queryFlip,showFlipMessage,submitFlip,useFlipOperation} from './owner';

export function FlipControls({report,disabled,onChanged,axis,label}: {report?:FlipReport;disabled:boolean;onChanged:()=>Promise<void>;axis?:'horizontal'|'vertical';label?:string}) {
  const operation=useFlipOperation();
  const locked=disabled||operation.busy||!!operation.pending;
  async function refreshAfter(action:Promise<boolean>){if(await action){try{await onChanged();}catch(e){showFlipMessage(`翻转已提交，但刷新失败：${String(e)}`);}}}
  if(!report)return <p role="status">当前引擎未提供原图翻转，请更新匹配版本。</p>;
  function button(direction:'horizontal'|'vertical'){
    const checked=report![direction];
    return <button type="button" className={axis?'specBtn':undefined} data-control-id={direction==='horizontal'?'control:PC-32478:21':'control:PC-32478:22'}
      disabled={locked||(!report!.available&&!checked)} aria-pressed={checked}
      onClick={()=>void refreshAfter(submitFlip(report!,direction==='horizontal'?!report!.horizontal:report!.horizontal,direction==='vertical'?!report!.vertical:report!.vertical))}>
      {label??(direction==='horizontal'?'水平翻转':'垂直翻转')} {checked?'开':'关'}</button>;
  }
  return <section aria-label="原图水平与垂直翻转">
    <div className="cropRow">{axis?button(axis):<>{button('horizontal')}{button('vertical')}<button type="button" disabled={locked||!report.active} onClick={()=>void refreshAfter(submitFlip(report,false,false))}>清除翻转</button></>}</div>
    {!axis&&<small>非破坏编辑：裁剪及全部处理之后翻转，导出同步；原图对比不翻转。</small>}
    {!report.available&&<p role="status">翻转原生模块未安装；已有配方保留，可清除翻转恢复中性。</p>}
    {report.reason&&<p role="status">{report.reason}</p>}
    {operation.pending&&<button type="button" disabled={operation.busy} onClick={()=>void refreshAfter(queryFlip())}>查询原翻转操作结果</button>}
    {operation.pending&&operation.recoveryAvailable&&<button type="button" disabled={operation.busy} onClick={()=>void (async()=>{if(await abandonFlip()){try{await onChanged();}catch(e){showFlipMessage(`旧结果仍未知，新工作区刷新失败：${String(e)}`);}}})()}>按已验证的新工作区放弃旧等待（不重发）</button>}
    {operation.message&&<p role="status" aria-live="polite">{operation.message}</p>}
  </section>;
}
