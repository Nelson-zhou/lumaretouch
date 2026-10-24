// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState, type PointerEvent} from 'react';
import {matchesSource, type SourceImage} from '../legShape/sourcePreview';
import {ridgeBrush, sourcePoint, type EyeSide, type RidgeBrush, type RidgeMask, type RidgeSource} from './support';

/** Local vectors only. Canonical support/feather pixels are shown by the host's frozen review. */
export function RidgeSourceEditor({context, image, source, side, masks, disabled, onChange, onLoaded, onDraftStart}: {
  context: string; image: SourceImage | null; source: RidgeSource; side: EyeSide; masks: Record<EyeSide, RidgeMask>; disabled: boolean;
  onChange: (side: EyeSide, value: RidgeMask) => void; onLoaded: (ready: boolean) => void; onDraftStart: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null), scroll = useRef<HTMLDivElement>(null), stroke = useRef<RidgeBrush | null>(null);
  const pointer = useRef<number | null>(null);
  const drag = useRef<{id: number; x: number; y: number; left: number; top: number} | null>(null);
  const [draft, setDraft] = useState<RidgeBrush | null>(null), [mode, setMode] = useState<'add' | 'subtract' | 'pan'>('add');
  const [radius, setRadius] = useState(Math.min(6, source.width / 2, source.height / 2)), [feather, setFeather] = useState(0), [zoom, setZoom] = useState(4), [loaded, setLoaded] = useState('');
  const valid = matchesSource(image, {...source, orientation: 'exif_normalized_once'});
  const imageKey = valid ? `${context}:${image.url}` : '';
  const available = valid && loaded === imageKey && !!imageKey && !disabled;
  const remaining = 4096 - Object.values(masks).reduce((sum, mask) => sum + mask.objects.reduce((n, b) => n + b.points.length, 0), 0);
  const live = useRef({context, available, side}); live.current = {context, available, side};
  useEffect(() => {stroke.current = null; pointer.current = null; drag.current = null; setDraft(null);}, [context, side, disabled]);
  useEffect(() => {setZoom(4); setMode('add'); setFeather(0);}, [imageKey]);
  useEffect(() => {
    const node = canvas.current, ctx = node?.getContext('2d'); if (!node || !ctx || !image) return;
    node.width = image.displayWidth; node.height = image.displayHeight; ctx.clearRect(0, 0, node.width, node.height);
    for (const eye of ['left', 'right'] as const) {
      const layer = document.createElement('canvas'); layer.width = node.width; layer.height = node.height;
      const pen = layer.getContext('2d'); if (!pen) continue;
      for (const b of [...masks[eye].objects, ...(eye === side && draft ? [draft] : [])]) {
        if (!b.enabled || !b.points.length) continue;
        const [[vx, vy], [wx, wy]] = b.axes, det = vx * wy - vy * wx; if (Math.abs(det) < 1e-12) continue;
        const points = b.points.map(([x, y]) => [(wy * x - wx * y) / det, (-vy * x + vx * y) / det]);
        pen.save(); pen.scale(node.width, node.height); pen.transform(vx, vy, wx, wy, 0, 0);
        pen.globalCompositeOperation = b.operation === 'subtract' ? 'destination-out' : 'source-over';
        pen.fillStyle = eye === 'left' ? '#20e5d5' : '#ffce55'; pen.strokeStyle = pen.fillStyle;
        pen.lineWidth = 2; pen.lineCap = 'round'; pen.lineJoin = 'round'; pen.beginPath();
        points.forEach((p, i) => i ? pen.lineTo(p[0], p[1]) : pen.moveTo(p[0], p[1]));
        if (points.length === 1) {pen.arc(points[0][0], points[0][1], 1, 0, Math.PI * 2); pen.fill();} else pen.stroke();
        pen.restore();
      }
      ctx.globalAlpha = .55; ctx.drawImage(layer, 0, 0);
    }
  }, [image, masks, side, draft]);
  const point = (e: PointerEvent<HTMLCanvasElement>) => sourcePoint(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect());
  const release = (e: PointerEvent<HTMLCanvasElement>) => {if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);};
  function end(e: PointerEvent<HTMLCanvasElement>, cancel = false) {
    if (pointer.current !== e.pointerId) return;
    const value = stroke.current; stroke.current = null; pointer.current = null; drag.current = null; setDraft(null); release(e);
    if (!cancel && value && live.current.available && live.current.context === context && live.current.side === side)
      onChange(side, {...masks[side], objects: [...masks[side].objects, value]});
  }
  return <section aria-label="逐眼卧蚕来源图画笔">
    <p>青色是人物左眼，黄色是人物右眼。先放大到可辨认卧蚕，再逐笔涂画；不是自动分割，也不要把眼袋整块当作卧蚕。擦除仅作用于当前眼，抬笔后不连接下一笔。</p>
    <div>{(['add', 'subtract', 'pan'] as const).map(m => <button type="button" key={m} disabled={disabled || !!draft} aria-pressed={mode === m} onClick={() => setMode(m)}>{m === 'add' ? '画保护范围' : m === 'subtract' ? '擦除当前眼' : '拖动平移'}</button>)}</div>
    <label>新笔迹半径（来源图像素）<input type="number" min={.5} max={Math.min(200, source.width / 2, source.height / 2)} step={.5} value={radius} disabled={disabled || !!draft}
      onChange={e => {const n = Number(e.target.value); if (Number.isFinite(n) && n >= .5 && n <= Math.min(200, source.width / 2, source.height / 2)) setRadius(n);}}/></label>
    <label>新笔迹羽化（默认 0）<input type="range" min={0} max={100} step={.1} value={feather} disabled={disabled || !!draft} onChange={e => setFeather(Number(e.target.value))}/>{feather}</label>
    <p>羽化 0 保留硬核满覆盖。羽化使用现有盒式滤波，数值 100 对应来源短边 5% 的滤波半径；羽化会减弱边缘保护，过大的羽化可能消灭全部满保护像素并被拒绝。几何草稿不模拟羽化，最终以引擎保护预览为准。</p>
    <div><button type="button" disabled={disabled || !!draft || zoom <= 1} onClick={() => setZoom(z => Math.max(1, z / 2))}>缩小</button>
      <button type="button" disabled={disabled || !!draft || zoom >= 32} onClick={() => setZoom(z => Math.min(32, z * 2))}>放大</button><span>{zoom * 100}%</span>
      <button type="button" disabled={disabled || !!draft || !masks[side].objects.length} onClick={() => onChange(side, {...masks[side], objects: masks[side].objects.slice(0, -1)})}>撤回当前眼一笔</button>
      <button type="button" disabled={disabled || !!draft || !masks[side].objects.length} onClick={() => onChange(side, {...masks[side], objects: []})}>清空当前眼</button></div>
    {valid && <div ref={scroll} style={{overflow: 'auto', maxHeight: 480, border: '1px solid #556', overscrollBehavior: 'contain'}}><div style={{position: 'relative', width: `${zoom * 100}%`, aspectRatio: `${image.displayWidth}/${image.displayHeight}`}}>
      <img key={imageKey} src={image.url} draggable={false} alt="当前不可变来源完整缩略参考，放大不补充图像细节" style={{display: 'block', width: '100%', height: '100%'}}
        onLoad={e => {const ready = e.currentTarget.naturalWidth === image.displayWidth && e.currentTarget.naturalHeight === image.displayHeight; setLoaded(ready ? imageKey : ''); onLoaded(ready);}}
        onError={() => {setLoaded(''); onLoaded(false);}}/>
      <canvas ref={canvas} aria-label="在当前来源图逐眼画保护范围、擦除或平移" style={{position: 'absolute', inset: 0, width: '100%', height: '100%', touchAction: 'none', cursor: mode === 'pan' ? 'grab' : 'crosshair'}}
        onPointerDown={e => {
          if (!available || e.button !== 0 || stroke.current || drag.current) return;
          if (mode === 'pan' && scroll.current) {e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); pointer.current = e.pointerId; drag.current = {id: e.pointerId, x: e.clientX, y: e.clientY, left: scroll.current.scrollLeft, top: scroll.current.scrollTop}; return;}
          if (mode === 'pan' || masks[side].objects.length >= 64 || remaining <= 0) return;
          const p = point(e); if (!p) return; e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); pointer.current = e.pointerId; onDraftStart();
          const b = ridgeBrush(side, mode, radius, feather, source, p); stroke.current = b; setDraft(b);
        }} onPointerMove={e => {
          if (pointer.current !== e.pointerId) return;
          if (drag.current && scroll.current) {scroll.current.scrollLeft = drag.current.left + drag.current.x - e.clientX; scroll.current.scrollTop = drag.current.top + drag.current.y - e.clientY; return;}
          const b = stroke.current, p = point(e); if (!available || !b || !p || b.points.length >= Math.min(1024, remaining)) return;
          const last = b.points[b.points.length - 1]; if (Math.hypot((p[0] - last[0]) * source.width, (p[1] - last[1]) * source.height) < .5) return;
          stroke.current = {...b, points: [...b.points, p]}; setDraft(stroke.current);
        }} onPointerUp={e => end(e)} onPointerCancel={e => end(e, true)} onLostPointerCapture={() => {stroke.current = null; pointer.current = null; drag.current = null; setDraft(null);}}/>
    </div></div>}
    {!available && <p role="status">等待匹配来源图加载或其他请求结束。没有可辨认细节时请停止，不要靠猜测标注。</p>}
    <p>最多每眼 64 笔、每笔 1024 点、双眼共 4096 点，剩余 {remaining} 点。原图来源、人物、分析或修复版本变化后必须重新审核；笔迹不会复制到其他来源。</p>
    {draft && draft.points.length >= Math.min(1024, remaining) && <p role="alert">本笔达到点数上限，后续移动未记录，请松开后分笔。</p>}
  </section>;
}
