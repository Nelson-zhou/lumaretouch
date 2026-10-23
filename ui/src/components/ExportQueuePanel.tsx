import {TargetSizeResult} from '../exportTargetSize/TargetSizeControls';
import type {EngineStatus,SessionState} from '../native';
import {WatermarkReceipt} from '../watermark/WatermarkControls';
export function ExportQueuePanel({exportTargets,exporting,status,strip,exportBits16,exportFormat}:{exportTargets:string[];exporting:boolean;status:EngineStatus|null;strip:SessionState|null;exportBits16:boolean;exportFormat:string}){
 return (<div className="exportQueue">
              <div className="qHead">
                <h2>批量导出</h2>
                <span>{exportTargets.length} 张 · {exporting
                  ? `导出中 ${(status?.export_progress?.index ?? 0) + 1}/${status?.export_progress?.total ?? 0}`
                  : status?.export
                    ? `上一批 ${status.export.total} 张 · 失败 ${status.export.failed}`
                    : "空闲"}</span>
              </div>
              {exporting && (
                <div className="qBar"><i style={{ width: `${Math.round(
                  ((status?.export_progress?.index ?? 0) + 1)
                  / Math.max(1, status?.export_progress?.total ?? 1) * 100)}%` }} /></div>
              )}
              <div className="qList">
                {exportTargets.length ? exportTargets.map((p) => {
                  const d = strip?.docs.find((x) => x.document_id === p);
                  const done = status?.export?.images?.find((i) => i.document_id === p);
                  const now = status?.export_progress?.document_id === p;
                  const targetWarning = !!done && (!!done.target_size && done.target_size.status !== 'skipped' && !done.target_size.within_tolerance || !!done.outputs?.some(o => o.target_size && o.target_size.status !== 'skipped' && !o.target_size.within_tolerance));
                  const state = done ? (done.error ? "失败" : done.out_skipped ? "已跳过" : targetWarning ? "已写入（目标未达）" : "已完成")
                    : now ? "导出中" : "待导出";
                  return (
                    <div className={"qRow" + (done ? (done.error || targetWarning ? " bad" : " ok") : "")}
                         key={p} title={done?.error ?? done?.skip_reason ?? done?.out}>
                      <span className="qName">{d ? `${d.name}${d.copy_number ? ` · 副本 ${d.copy_number}` : ""}` : p}</span>
                      <span className="qFmt">{done?.format ? done.format.toUpperCase() : exportBits16 ? "16-bit TIFF"
                        : exportFormat.toUpperCase()}</span>
                      <em>{state}</em>
                      {done?.out && <small title={done.renamed_from ? `原目标：${done.renamed_from}` : undefined}>{done.out}</small>}
                      <WatermarkReceipt outputs={done?.outputs}/>
                      {done?.target_size && <TargetSizeResult receipt={done.target_size}/>}
                      {done?.outputs?.map((output, index) => output.target_size && <small key={`${output.variant}-${index}`}>
                        {output.variant === 'clean' ? '无水印副本：' : '水印副本：'}<TargetSizeResult receipt={output.target_size}/>{output.directory_fsync === false && !output.skipped && ' · 目录持久化同步未确认'}
                      </small>)}
                      {done?.directory_fsync === false && !done.out_skipped && <small role="status">文件已写入，目录持久化同步未确认</small>}
                    </div>
                  );
                }) : <div className="qEmpty">先在底片条或图库选择要导出的照片</div>}
              </div>
            </div>);
}
