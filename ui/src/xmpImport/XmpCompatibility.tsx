import {useEffect, useRef, useState} from 'react';
import {XMP_MODE, type XmpAck, type XmpAdaptationId, type XmpReport, type XmpSummary} from './model';

const statusLabel = {adaptable: '可选择本机参数适配', unsupported: '不支持，不会应用', metadata: '仅保留元数据', invalid: '无效，不会应用'};
function displayValue(value: unknown): string {
  const result = JSON.stringify(value);
  return result === undefined ? '无值' : result;
}
/** Individual decoded properties only. Never mount or execute an XML document. */
export function XmpReportView({report}: {report: XmpReport}) {
  return <div className="xmpReport">
    <p><strong>{report.filename}</strong> · {report.byte_length.toLocaleString()} 字节</p>
    <p>ProcessVersion：{report.process_version ?? '未提供'}；Camera Raw 版本：{report.camera_raw_version ?? '未提供'}。</p>
    <p>这是有限的参数语法适配，不是 Adobe 渲染兼容。即使数值相同，结果也可能不同；不支持的项目会保留在报告中，但不会参与修图。</p>
    {report.warnings.length > 0 && <ul>{report.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
    <details><summary>逐项兼容报告（{report.properties.length} 项，含不支持项）</summary>
      <dl>{report.properties.map((property, index) => <div key={index} className={`xmpProperty xmpProperty-${property.status}`}>
        <dt>{property.name} · {statusLabel[property.status]}</dt>
        <dd>{displayValue(property.value)}</dd><dd>{property.reason}</dd>
      </div>)}</dl>
    </details>
    <small>源文件 SHA-256：{report.source_sha256}<br/>报告 SHA-256：{report.report_sha256}</small>
  </div>;
}
export function XmpSummaryView({value}: {value: XmpSummary}) {
  return <details><summary>XMP 来源与只读兼容报告</summary>
    <p>已选择：{value.selected.map(id => value.report.adaptations.find(a => a.id === id)?.title ?? id).join('、')}。应用前必须逐张查看真实前后预览。</p>
    <XmpReportView report={value.report}/>
  </details>;
}
export function XmpCompatibilityDialog({report, busy, error, onCancel, onImport}: {
  report: XmpReport; busy: boolean; error?: string; onCancel: () => void; onImport: (ack: XmpAck) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [selected, setSelected] = useState<XmpAdaptationId[]>([]), [acknowledged, setAcknowledged] = useState(false);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => {if (element?.open) element.close();};
  }, []);
  return <dialog ref={dialog} className="xmpCompatibilityDialog" aria-label="XMP 兼容性检查与导入确认"
    onKeyDown={event => event.stopPropagation()}
    onCancel={event => {event.preventDefault(); if (!busy) onCancel();}}>
    <h3>XMP 兼容性检查，尚未导入</h3>
    <XmpReportView report={report}/>
    <fieldset disabled={busy || !report.can_import}><legend>明确选择要适配的参数组（默认不选）</legend>
      {report.adaptations.map(adaptation => <label key={adaptation.id}>
        <input type="checkbox" checked={selected.includes(adaptation.id)} onChange={event => {
          setSelected(previous => event.target.checked ? [...previous, adaptation.id] : previous.filter(id => id !== adaptation.id));
          setAcknowledged(false);
        }}/><span>{adaptation.title}<small>{adaptation.reason}</small></span>
      </label>)}
    </fieldset>
    {selected.includes('point_curves') && <p>点曲线适配会替换完整的本机 v1 曲线组，包括原有亮度曲线和参数曲线扩展；不会补齐源文件缺失的通道。</p>}
    {!report.can_import && <p role="alert">此文件目前没有可安全适配的参数组合。可以查看报告，但不能导入；不会把不支持内容伪装成已完成。</p>}
    <label><input type="checkbox" checked={acknowledged} disabled={busy || !report.can_import || !selected.length}
      onChange={event => setAcknowledged(event.target.checked)}/>
      我已查看兼容报告，同意仅适配勾选参数；白平衡、相机配置文件及所有标记不支持的项目不会被应用，效果不保证与 Adobe 一致。</label>
    <p>导入只创建预设，不会改变当前照片。之后应用时还须查看当前照片的真实前后像素并再次确认。</p>
    {error && <p role="alert">{error}</p>}
    <div className="presetButtons"><button autoFocus disabled={busy} onClick={onCancel}>取消</button>
      <button disabled={busy || !report.can_import || !selected.length || !acknowledged} onClick={() => onImport({
        source_sha256: report.source_sha256, report_sha256: report.report_sha256, mode: XMP_MODE, selected: [...selected],
      })}>{busy ? '等待本次导入回执…' : '确认选择并导入'}</button></div>
  </dialog>;
}
