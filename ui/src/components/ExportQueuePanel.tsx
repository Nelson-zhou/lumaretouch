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
                  const d = strip?.docs.find((x) => x.path === p);
                  const done = status?.export?.images?.find((i) => i.path === p);
                  const now = status?.export_progress?.path === p;
                  const state = done ? (done.error ? "失败" : "已完成")
                    : now ? "导出中" : "待导出";
                  return (
                    <div className={"qRow" + (done ? (done.error ? " bad" : " ok") : "")}
                         key={p} title={done?.error}>
                      <span className="qName">{d?.name ?? p.split("/").pop() ?? p}</span>
                      <span className="qFmt">{exportBits16 ? "16-bit TIFF"
                        : exportFormat.toUpperCase()}</span>
                      <em>{state}</em>
                      <WatermarkReceipt outputs={done?.outputs}/>
                    </div>
                  );
                }) : <div className="qEmpty">先在底片条或图库选择要导出的照片</div>}
              </div>
            </div>);
}
