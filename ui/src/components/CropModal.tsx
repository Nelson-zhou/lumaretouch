/**
 * 裁剪 / 旋转模态（P0 lnx.crop.v1）。
 *
 * 直连 `cmd_crop`：比例只在本地换算成归一化 rect，提交后以引擎回的
 * `crop_rect / rotation_degrees / crop_out / out_full` 为准——预览里看到的那块
 * 与文件里写的像素数是同一份数（引擎报，前端不自己乘）。
 */
import { useEffect, useMemo, useState } from "react";

export interface CropState {
  rect: number[];
  rotation_degrees: number;
  neutral: boolean;
  lit: boolean;
  crop_out?: [number, number] | null;
  out_full?: [number, number] | null;
}

const RATIOS: { id: string; label: string; a: number | null }[] = [
  { id: "orig", label: "原比例", a: null },
  { id: "free", label: "自由", a: 0 },
  { id: "1:1", label: "1:1", a: 1 },
  { id: "3:2", label: "3:2", a: 3 / 2 },
  { id: "4:3", label: "4:3", a: 4 / 3 },
  { id: "16:9", label: "16:9", a: 16 / 9 },
];

export default function CropModal(props: {
  open: boolean;
  imgW: number;
  imgH: number;
  crop: CropState | null;
  onClose: () => void;
  onApply: (rect: number[], rotation: number) => void;
  onClear: () => void;
}) {
  const { open, imgW, imgH, crop } = props;
  const [ratio, setRatio] = useState("orig");
  const [zoom, setZoom] = useState(90);
  const [rot, setRot] = useState(0);

  useEffect(() => {
    if (!open) return;
    setRatio(crop?.neutral === false ? "free" : "orig");
    setZoom(90);
    setRot(crop?.rotation_degrees ?? 0);
  }, [open, crop?.neutral, crop?.rotation_degrees]);

  const imageAspect = imgW > 0 && imgH > 0 ? imgW / imgH : 3 / 2;

  const rect = useMemo(() => {
    if (ratio === "free" && crop && !crop.neutral) {
      return crop.rect;
    }
    const a = ratio === "orig" || ratio === "free" ? imageAspect
      : (RATIOS.find((r) => r.id === ratio)?.a || imageAspect);
    const z = Math.max(0.2, Math.min(1, zoom / 100));
    let w = z, h = z;
    // 目标比例 a = 像素宽/像素高 = (w*imgW)/(h*imgH) → w/h = a/(imgW/imgH)
    const k = a / imageAspect;
    if (k >= 1) w = Math.min(1, z); else h = Math.min(1, z);
    if (k >= 1) h = w / k; else w = h * k;
    return [(1 - w) / 2, (1 - h) / 2, (1 + w) / 2, (1 + h) / 2];
  }, [ratio, zoom, crop, imageAspect, imgW, imgH]);

  if (!open) return null;

  const pxW = imgW > 0 ? Math.max(1, Math.round((rect[2] - rect[0]) * imgW)) : 0;
  const pxH = imgH > 0 ? Math.max(1, Math.round((rect[3] - rect[1]) * imgH)) : 0;
  const out = crop?.out_full ?? crop?.crop_out ?? null;

  return (
    <div className="cropOverlay" role="dialog" aria-label="裁剪与旋转">
      <div className="cropCard">
        <div className="cropHead">
          <b>裁剪与旋转</b>
          <em>lnx.crop.v1 · 正角顺时针</em>
          <button className="cropX" onClick={props.onClose} title="关闭">✕</button>
        </div>

        <div className="cropRatios">
          {RATIOS.map((r) => (
            <button key={r.id} className={ratio === r.id ? "on" : ""}
              onClick={() => setRatio(r.id)}>{r.label}</button>
          ))}
        </div>

        <div className="cropFrame">
          <div className="cropSrc">
            <div className="cropRect"
              style={{
                left: `${rect[0] * 100}%`, top: `${rect[1] * 100}%`,
                width: `${(rect[2] - rect[0]) * 100}%`,
                height: `${(rect[3] - rect[1]) * 100}%`,
                transform: `rotate(${rot * 0.06}deg)`,
              }} />
            <span className="cropPx">{pxW} × {pxH}</span>
          </div>
        </div>

        <div className="cropRow">
          <span>裁剪范围</span>
          <input type="range" min={40} max={100} value={zoom}
            disabled={ratio === "free" && !!crop && !crop.neutral}
            onChange={(e) => setZoom(+e.target.value)} />
          <em>{zoom}%</em>
        </div>
        <div className="cropRow">
          <span>旋转</span>
          <button onClick={() => setRot((r) => r - 90)} title="逆时针 90°">↺ 90°</button>
          <button onClick={() => setRot((r) => r + 90)} title="顺时针 90°">↻ 90°</button>
          <input type="range" min={-45} max={45} step={1}
            value={((rot % 90) + 90) % 90 > 45 ? ((rot % 90) + 90) % 90 - 90 : ((rot % 90) + 90) % 90}
            onChange={(e) => {
              const base = Math.round(rot / 90) * 90;
              setRot(base + +e.target.value);
            }} />
          <em>{rot}°</em>
        </div>

        <div className="cropFoot">
          <span>
            {out ? `输出：${out[0]} × ${out[1]} px` : "应用后由引擎回报输出尺寸"}
          </span>
          <span className="cropSpacer" />
          <button onClick={() => { setRatio("orig"); setZoom(90); setRot(0); }}
            title="比例与旋转回到原样">重置</button>
          <button onClick={props.onClear} title="关闭裁剪层（不剪不转）">清除裁剪</button>
          <button className="primary" onClick={() => props.onApply(rect, rot)}>
            应用裁剪
          </button>
        </div>
      </div>
    </div>
  );
}
