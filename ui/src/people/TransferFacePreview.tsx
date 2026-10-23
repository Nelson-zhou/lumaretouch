import {useState} from 'react';
import type {FaceRef} from './model';
import {sameFace} from './transferProof';
import {selectableFace, type InventoryEntry} from './transferInventory';
import './transferFaces.css';

/** Uses the provided effective-source PNG, not the edited filmstrip thumbnail. */
export function TransferFacePreview({entry, selected, label, disabled = false, readOnly = false, onChange, onPreviewStatus}: {
  entry: InventoryEntry; selected: FaceRef[]; label: string; disabled?: boolean; readOnly?: boolean;
  onChange?: (refs: FaceRef[]) => void; onPreviewStatus?: (documentId: string, ready: boolean) => void;
}) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const preview = entry.source_preview;
  const selectedFace = (ref: FaceRef) => selected.some(item => sameFace(item, ref));
  const shown = readOnly ? entry.faces.filter(face => selectedFace(face.face_ref)) : entry.faces;
  const report = (ready: boolean) => {setStatus(ready ? 'ready' : 'error'); onPreviewStatus?.(entry.document.document_id, ready);};
  const toggle = (ref: FaceRef) => onChange?.(selectedFace(ref) ? selected.filter(item => !sameFace(item, ref)) : [...selected, ref]);
  return <section className="transferFacePreview" aria-label={label}>
    <p className="transferFaceTitle">{label}</p>
    <div className="transferSourceImage" style={{width: preview.width, maxWidth: '100%'}}>
      <img src={`data:${preview.mime};base64,${preview.base64}`} alt={`${label}的未编辑实际源图；编号对应下方人脸`}
        width={preview.width} height={preview.height}
        onLoad={event => report(event.currentTarget.naturalWidth === preview.width && event.currentTarget.naturalHeight === preview.height)}
        onError={() => report(false)}/>
      {status === 'ready' && shown.map(face => {
        const index = entry.faces.indexOf(face), [x0, y0, x1, y1] = face.box, checked = selectedFace(face.face_ref);
        const style = {left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%`};
        return readOnly ? <span key={face.face_ref.face_instance_id} className="transferFaceBox chosen" style={style} aria-hidden="true"><b>{index + 1}</b></span>
          : <button type="button" key={face.face_ref.face_instance_id} className={`transferFaceBox${checked ? ' chosen' : ''}`} style={style}
            disabled={disabled || !selectableFace(face)} aria-pressed={checked} aria-label={`${label}：${checked ? '取消' : '选择'}人脸 ${index + 1}`}
            onClick={() => toggle(face.face_ref)}><b>{index + 1}</b></button>;
      })}
    </div>
    {status !== 'ready' && <p role="status">{status === 'error' ? '实际源图预览未能验证，请重新读取；不能凭空选择人脸。' : '正在载入实际源图预览…'}</p>}
    <p className="transferFaceIdentity">文档 {entry.document.document_id} · 文档版本 {entry.document.revision} · 人物版本 {entry.state_revision}</p>
    {readOnly ? <p>已指定人脸：{shown.map(face => entry.faces.indexOf(face) + 1).join('、') || '无'}</p>
      : <fieldset disabled={disabled || status !== 'ready'}><legend>手动勾选本张接收参数的人脸</legend>
        {entry.faces.map((face, index) => <label key={face.face_ref.face_instance_id} className="transferFaceOption">
          <input type="checkbox" checked={selectedFace(face.face_ref)} disabled={!selectableFace(face)} onChange={() => toggle(face.face_ref)}/>
          人脸 {index + 1}{!face.enabled ? '（已禁用）' : face.analysis_status !== 'verified' ? '（未验证分析，不可同步）' : ''}
          <small> · 分析版本 {face.face_ref.analysis_revision}</small>
        </label>)}
      </fieldset>}
  </section>;
}
