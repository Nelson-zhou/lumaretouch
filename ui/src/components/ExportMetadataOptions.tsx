import {exportGpsForIntent, isOriginalExportFormat, reconcileExportFormat} from '../exportModel';

export function ExportMetadataOptions({bits16,format,gps,onBits16,onGps,onFormat}:{bits16:boolean;format:string;gps:boolean;onBits16:(v:boolean)=>void;onGps:(v:boolean)=>void;onFormat:(v:string)=>void}) {
  const original = isOriginalExportFormat(format);
  return <>
    <label className="exCheck">
      <input type="checkbox" checked={!original && bits16} disabled={original}
        onChange={(e) => {
          onBits16(e.target.checked);
          onFormat(reconcileExportFormat(e.target.checked, format));
        }} />
      {original ? 'Original：位深由每张源文件确定（保留手动格式的位深偏好）'
        : '16-bit PNG / TIFF（JPEG / WebP 开启时改用 TIFF）'}
    </label>
    <label className="exCheck">
      <input type="checkbox" checked={exportGpsForIntent(bits16, format, gps)} disabled={!original && bits16}
        onChange={(e) => onGps(e.target.checked)} />
      写入 GPS{original ? '（整批若含 16-bit，预览将明确拒绝；不会自动关闭）'
        : bits16 ? '（16-bit 暂不支持；保留 8-bit 时的选择）' : ''}
    </label>
  </>;
}
