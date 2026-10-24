// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState, type PointerEvent} from 'react';
import {matchesSource, type SourceImage} from '../legShape/sourcePreview';
import {bodyMaskPoint, type SkinBodyMask, type SkinBodySource} from './bodyReviewModel';
type Brush = SkinBodyMask['objects'][number];
type Point = [number, number];

/** Uses the existing source canvas brush convention, never inverse-maps retouched pixels. */
export function SkinBodySourceEditor({context, image, source, value, disabled, onChange, onLoaded, onDraftStart}: {
  context: string; image: SourceImage | null; source: SkinBodySource; value: SkinBodyMask; disabled: boolean;
  onChange: (value: SkinBodyMask) => void; onLoaded: (ready: boolean) => void;
  onDraftStart: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null), stroke = useRef<Brush | null>(null);
  const [draft, setDraft] = useState<Brush | null>(null), [mode, setMode] = useState<'add' | 'subtract'>('add');
  const [radius, setRadius] = useState(2), [feather, setFeather] = useState(10), [zoom, setZoom] = useState(1), [pan, setPan] = useState(false);
  const [loaded, setLoaded] = useState('');
  const validImage = matchesSource(image, {...source, orientation: 'exif_normalized_once'});
  const imageKey = validImage ? `${context}:${image.url}:${image.displayWidth}:${image.displayHeight}` : '';
  const available = validImage && loaded === imageKey && !!imageKey && !disabled;
  const remaining = Math.max(0, 4096 - value.objects.reduce((sum, object) => sum + object.points.length, 0));
  const live = useRef({context, available}); live.current = {context, available};
  useEffect(() => {stroke.current = null; setDraft(null);}, [context, disabled]);
  // Readiness is keyed to the actual load event. Do not clear a cached image's
  // newer onLoad result from a later passive effect.
  useEffect(() => {stroke.current = null; setDraft(null); setZoom(1); setPan(false);}, [imageKey]);
  useEffect(() => {
    const node = canvas.current, ctx = node?.getContext('2d'); if (!node || !ctx || !image) return;
    node.width = image.displayWidth; node.height = image.displayHeight; ctx.clearRect(0, 0, node.width, node.height);
    for (const object of [...value.objects, ...(draft ? [draft] : [])]) {
      if (!object.enabled) continue;
      const [[vx, vy], [wx, wy]] = object.axes, determinant = vx * wy - vy * wx;
      if (Math.abs(determinant) < 1e-12 || !object.points.length) continue;
      const points = object.points.map(([x, y]) => [(wy * x - wx * y) / determinant, (-vy * x + vx * y) / determinant]);
      ctx.save(); ctx.scale(node.width, node.height); ctx.transform(vx, vy, wx, wy, 0, 0);
      ctx.strokeStyle = object.operation === 'subtract' ? 'rgba(255,105,100,.72)' : 'rgba(30,220,225,.6)';
      ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.beginPath();
      points.forEach((p, index) => index ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
      if (points.length === 1) {ctx.arc(points[0][0], points[0][1], 1, 0, Math.PI * 2); ctx.fill();} else ctx.stroke();
      ctx.restore();
    }
  }, [value, draft, image]);
  const point = (event: PointerEvent<HTMLCanvasElement>): Point | null => bodyMaskPoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect());
  const release = (event: PointerEvent<HTMLCanvasElement>) => {if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);};
  const cancel = (event: PointerEvent<HTMLCanvasElement>) => {stroke.current = null; setDraft(null); release(event);};
  const finish = (event: PointerEvent<HTMLCanvasElement>) => {
    const object = stroke.current; stroke.current = null; setDraft(null); release(event);
    if (!object || !live.current.available || live.current.context !== context) return;
    onChange({...value, objects: [...value.objects, object]});
  };
  return <section aria-label="身体皮肤来源图画笔">
    <p>青色添加，红色减去；笔迹按当前有效来源图像的完整像素边界定位，不按脸框推断身体，也不从修图结果反算范围。</p>
    <div className="prow"><button type="button" disabled={!available} aria-pressed={mode === 'add'} onClick={() => setMode('add')}>添加皮肤范围</button>
      <button type="button" disabled={!available} aria-pressed={mode === 'subtract'} onClick={() => setMode('subtract')}>减去范围</button></div>
    <label>新笔迹半径（来源图短边 %）<input type="range" min=".1" max="10" step=".1" value={radius} disabled={!available || !!draft} onChange={event => setRadius(Number(event.target.value))}/>{radius}%</label>
    <label>新笔迹羽化（本产品 0–100）<input type="range" min="0" max="100" step="1" value={feather} disabled={!available || !!draft} onChange={event => setFeather(Number(event.target.value))}/>{feather}</label>
    <div className="prow"><button type="button" disabled={!available || !value.objects.length} onClick={() => onChange({...value, objects: value.objects.slice(0, -1)})}>撤回一笔</button>
      <button type="button" disabled={!available || !value.objects.length} onClick={() => onChange({...value, objects: []})}>清空草稿</button></div>
    <div className="prow"><button type="button" disabled={!available || zoom <= 1} onClick={() => setZoom(old => Math.max(1, old / 2))}>缩小</button>
      <button type="button" disabled={!available || zoom >= 8} onClick={() => setZoom(old => Math.min(8, old * 2))}>放大</button>
      <button type="button" disabled={!available || !!draft} aria-pressed={pan} onClick={() => setPan(old => !old)}>{pan ? '切换画笔' : '切换平移'}</button><span>{Math.round(zoom * 100)}%</span></div>
    {validImage && <div style={{overflow: 'auto', maxHeight: 440}}><div style={{position: 'relative', width: `${zoom * 100}%`, aspectRatio: `${image.displayWidth}/${image.displayHeight}`}}>
      <img key={imageKey} src={image.url} alt="当前有效来源图像的完整缩略参考，不是修图结果" draggable={false} style={{display: 'block', width: '100%', height: '100%'}}
        onLoad={event => {const ready = event.currentTarget.naturalWidth === image.displayWidth && event.currentTarget.naturalHeight === image.displayHeight; setLoaded(ready ? imageKey : ''); onLoaded(ready);}}
        onError={() => {setLoaded(''); onLoaded(false);}}/>
      <canvas ref={canvas} aria-label="在来源图添加或减去可见身体皮肤笔迹" style={{position: 'absolute', inset: 0, width: '100%', height: '100%', touchAction: pan ? 'pan-x pan-y' : 'none', pointerEvents: pan ? 'none' : 'auto'}}
        onPointerDown={event => {
          if (!available || pan || event.button !== 0 || stroke.current || value.objects.length >= 64 || remaining < 1) return;
          const p = point(event); if (!p) return; event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
          onDraftStart();
          const pixels = radius / 100 * Math.min(source.width, source.height);
          const object: Brush = {id: crypto.randomUUID().replaceAll('-', ''), name: mode === 'add' ? '身体皮肤添加' : '身体皮肤减去', enabled: true,
            operation: mode, kind: 'brush', opacity: 1, feather, points: [p], axes: [[pixels / source.width, 0], [0, pixels / source.height]]};
          stroke.current = object; setDraft(object);
        }} onPointerMove={event => {
          const object = stroke.current, p = point(event); if (!available || !object || !p || object.points.length >= Math.min(1024, remaining)) return;
          const last = object.points[object.points.length - 1]; if (Math.hypot(p[0] - last[0], p[1] - last[1]) < .0005) return;
          stroke.current = {...object, points: [...object.points, p]}; setDraft(stroke.current);
        }} onPointerUp={finish} onPointerCancel={cancel} onLostPointerCapture={() => {stroke.current = null; setDraft(null);}}/>
    </div></div>}
    {!available && <p role="status">请等待匹配当前人物与来源图的参考图加载，并结束其他编辑。</p>}
    {draft && draft.points.length >= Math.min(1024, remaining) && <p role="status">本笔已达到记录上限，后续移动不会加入；请松开后分笔，或撤回清理。已有几何点不会自动删减。</p>}
    <p>这是笔迹定位草稿，不是最终蒙版或真实效果；羽化与排除区以引擎审核图为准。缩略图放大不补充来源细节。最多 64 笔，每笔 1024 点，总计 4096 点，剩余 {remaining} 点；达到上限请分笔、撤回或清理。</p>
  </section>;
}
