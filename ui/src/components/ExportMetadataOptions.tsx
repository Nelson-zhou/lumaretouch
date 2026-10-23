export function ExportMetadataOptions({bits16,gps,onBits16,onGps,onFormat}:{bits16:boolean;gps:boolean;onBits16:(v:boolean)=>void;onGps:(v:boolean)=>void;onFormat:(v:string)=>void}) {
  return <>
                <label className="exCheck">
                  <input type="checkbox" checked={bits16}
                         onChange={(e) => {
                           onBits16(e.target.checked);
                           // 切 16-bit 同时把面板格式收到 TIFF，不让控件停在会被后端拒的 jpg
                           if (e.target.checked) onFormat("tif");
                         }} />
                  16-bit TIFF
                </label>
                <label className="exCheck">
                  <input type="checkbox" checked={gps}
                         onChange={(e) => onGps(e.target.checked)} />
                  写入 GPS
                </label>
  </>;
}
