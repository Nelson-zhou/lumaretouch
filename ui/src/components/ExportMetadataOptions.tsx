import {exportGpsForDepth, reconcileExportFormat} from '../exportModel';

export function ExportMetadataOptions({bits16,format,gps,onBits16,onGps,onFormat}:{bits16:boolean;format:string;gps:boolean;onBits16:(v:boolean)=>void;onGps:(v:boolean)=>void;onFormat:(v:string)=>void}) {
  return <>
                <label className="exCheck">
                  <input type="checkbox" checked={bits16}
                         onChange={(e) => {
                           onBits16(e.target.checked);
                           onFormat(reconcileExportFormat(e.target.checked, format));
                         }} />
                  16-bit PNG / TIFF（JPEG / WebP 开启时改用 TIFF）
                </label>
                <label className="exCheck">
                  <input type="checkbox" checked={exportGpsForDepth(bits16, gps)} disabled={bits16}
                         onChange={(e) => onGps(e.target.checked)} />
                  写入 GPS{bits16 && '（16-bit 暂不支持；保留 8-bit 时的选择）'}
                </label>
  </>;
}
