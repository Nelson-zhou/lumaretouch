// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState, type PointerEvent} from 'react';
import {HAIR_SMOOTHING_LIMITS, sourcePoint, type HairSmoothingBrush, type HairSmoothingMask, type HairSmoothingSource} from './review';

export type HairSmoothingPaintImage = {url: string; width: number; height: number; sha256: string;
  /** Only an authenticated source crop belongs here, never a rendered-result crop. */
  rect?: [number, number, number, number]};
type Layer = 'target' | 'context' | 'protect';
type Stroke = {brush: HairSmoothingBrush; layer: Layer; pointer: number; binding: string};

/** Draft source vectors only. No semantic mask, inferred direction or second graph owner. */
export function HairSmoothingSourceEditor({binding, source, image, target, context, protect, disabled, onChange, onLoaded, onDraftStart}: {
  binding: string; source: HairSmoothingSource; image: HairSmoothingPaintImage | null;
  target: HairSmoothingMask; context: HairSmoothingMask; protect: HairSmoothingMask; disabled: boolean;
  onChange: (target: HairSmoothingMask, context: HairSmoothingMask, protect: HairSmoothingMask) => void;
  onLoaded: (ready: boolean) => void; onDraftStart: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null), stroke = useRef<Stroke | null>(null);
  const [draft, setDraft] = useState<Stroke | null>(null), [layer, setLayer] = useState<Layer>('target'), [subtract, setSubtract] = useState(false);
  const [radius, setRadius] = useState(1), [zoom, setZoom] = useState<'fit' | 'pixels'>('fit'), [pan, setPan] = useState(false);
  const [loaded, setLoaded] = useState('');
  const key = image ? `${binding}:${image.sha256}:${image.width}:${image.height}:${image.rect?.join(',') ?? 'full'}` : '';
  const available = !!image && loaded === key && !disabled;
  const mounted = useRef(false), current = useRef({binding, key, available, target, context, protect, onChange, onLoaded, onDraftStart});
  current.current = {binding, key, available, target, context, protect, onChange, onLoaded, onDraftStart};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; stroke.current = null;};}, []);
  useEffect(() => {stroke.current = null; setDraft(null);}, [key, disabled]);
  const total = [...target.objects, ...context.objects, ...protect.objects].reduce((n, brush) => n + brush.points.length, 0);
  const remaining = Math.max(0, HAIR_SMOOTHING_LIMITS.totalPoints - total);
  const stillCurrent = () => mounted.current && current.current.binding === binding && current.current.key === key;
  useEffect(() => {
    const node = canvas.current, ctx = node?.getContext('2d'); if (!node || !ctx || !image) return;
    node.width = image.width; node.height = image.height; ctx.clearRect(0, 0, node.width, node.height);
    const rows = [...context.objects.map(brush => ({brush, layer: 'context' as Layer})),
      ...target.objects.map(brush => ({brush, layer: 'target' as Layer})),
      ...protect.objects.map(brush => ({brush, layer: 'protect' as Layer})), ...(draft ? [draft] : [])];
    for (const row of rows) {
      const {brush} = row; if (!brush.enabled) continue;
      const [[vx, vy], [wx, wy]] = brush.axes, determinant = vx * wy - vy * wx;
      if (Math.abs(determinant) < 1e-12 || !brush.points.length) continue;
      const points = brush.points.map(([x, y]) => [(wy * x - wx * y) / determinant, (-vy * x + vx * y) / determinant]);
      const [x, y, width, height] = image.rect ?? [0, 0, source.width, source.height];
      ctx.save(); ctx.scale(node.width / width, node.height / height); ctx.translate(-x, -y);
      ctx.scale(source.width, source.height); ctx.transform(vx, vy, wx, wy, 0, 0);
      ctx.strokeStyle = row.layer === 'protect' ? 'rgba(255,50,130,.8)' : brush.operation === 'subtract' ? 'rgba(255,180,50,.7)'
        : row.layer === 'context' ? 'rgba(100,130,255,.45)' : 'rgba(20,220,225,.6)';
      ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.beginPath();
      points.forEach((point, index) => index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1]));
      if (points.length === 1) {ctx.arc(points[0][0], points[0][1], 1, 0, 2 * Math.PI); ctx.fill();} else ctx.stroke();
      ctx.restore();
    }
  }, [image, source.width, source.height, target, context, protect, draft]);
  const pointAt = (event: PointerEvent<HTMLCanvasElement>) => {
    const local = sourcePoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect());
    if (!local || !image) return null;
    const [x, y, width, height] = image.rect ?? [0, 0, source.width, source.height];
    return [(x + local[0] * width) / source.width, (y + local[1] * height) / source.height] as [number, number];
  };
  const cancel = (event?: PointerEvent<HTMLCanvasElement>) => {
    stroke.current = null; setDraft(null);
    if (event?.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const finish = (event: PointerEvent<HTMLCanvasElement>) => {
    const item = stroke.current; if (!item || item.pointer !== event.pointerId) return;
    cancel(event);
    if (!stillCurrent() || !current.current.available || item.binding !== binding) return;
    const state = current.current, next = state[item.layer];
    if (next.objects.length >= HAIR_SMOOTHING_LIMITS.strokes) return;
    const updated = {...next, objects: [...next.objects, item.brush]};
    state.onChange(item.layer === 'target' ? updated : state.target,
      item.layer === 'context' ? updated : state.context, item.layer === 'protect' ? updated : state.protect);
  };
  const edit = (nextTarget: HairSmoothingMask, nextContext: HairSmoothingMask, nextProtect: HairSmoothingMask) => {
    if (stillCurrent() && current.current.available && !stroke.current) current.current.onChange(nextTarget, nextContext, nextProtect);
  };
  const selectedMask = {target, context, protect}[layer];
  return <section aria-label="本人可见头发来源、目标、上下文及独立硬保护画笔">
    <p>青色标记要柔顺的可见纹理；蓝色独立标记足够宽的同人可见头发采样上下文，可覆盖目标。粉红硬保护独立否决全部采样，后来添加目标或上下文也不能覆盖它。</p>
    <div className="prow">{(['target', 'context', 'protect'] as const).map(value => <button key={value} type="button"
      disabled={!available || !!draft} aria-pressed={layer === value} onClick={() => {setLayer(value); setSubtract(false);}}>
      {value === 'target' ? '可见纹理目标' : value === 'context' ? '同人头发上下文' : '独立硬保护'}</button>)}</div>
    <label><input type="checkbox" checked={subtract && layer !== 'protect'} disabled={!available || !!draft || layer === 'protect'}
      onChange={event => setSubtract(event.target.checked)}/>从当前目标或上下文减去（橙色）；保护只能删除整笔修订</label>
    <label>画笔半径（来源短边百分比，不是纹理尺度）<input type="range" min="0.05" max="8" step="0.05" value={radius}
      disabled={!available || !!draft} onChange={event => setRadius(Number(event.target.value))}/>{radius}%</label>
    <div className="prow">
      <button type="button" disabled={!available || !!draft || !selectedMask.objects.length} onClick={() => {
        const next = {...selectedMask, objects: selectedMask.objects.slice(0, -1)};
        edit(layer === 'target' ? next : target, layer === 'context' ? next : context, layer === 'protect' ? next : protect);
      }}>移除当前类别最后一笔</button>
      <button type="button" disabled={!available || !!draft || !total} onClick={() => edit({...target, objects: []}, {...context, objects: []}, {...protect, objects: []})}>清空三类草稿，重新确认</button>
      <button type="button" disabled={!available || !!draft} aria-pressed={zoom === 'fit'} onClick={() => setZoom('fit')}>适合窗口</button>
      <button type="button" disabled={!available || !!draft} aria-pressed={zoom === 'pixels'} onClick={() => setZoom('pixels')}>参考像素 1:1</button>
      <button type="button" disabled={!available || !!draft} aria-pressed={pan} onClick={() => setPan(!pan)}>{pan ? '返回画笔' : '平移查看'}</button>
    </div>
    {image && <div style={{overflow: 'auto', maxHeight: 560}}><div style={{position: 'relative',
      width: zoom === 'pixels' ? image.width : '100%', aspectRatio: `${image.width}/${image.height}`}}>
      <img key={key} src={image.url} alt="当前真实来源，笔迹不代表自动头发或人物实例分割" draggable={false}
        style={{display: 'block', width: '100%', height: '100%'}} onLoad={event => {
          if (!stillCurrent()) return;
          const ready = event.currentTarget.naturalWidth === image.width && event.currentTarget.naturalHeight === image.height;
          setLoaded(ready ? key : ''); current.current.onLoaded(ready);
        }} onError={() => {if (stillCurrent()) {setLoaded(''); current.current.onLoaded(false);}}}/>
      <canvas ref={canvas} aria-label="本人可见头发目标、上下文和硬保护手绘画布" style={{position: 'absolute', inset: 0,
        width: '100%', height: '100%', touchAction: pan ? 'pan-x pan-y' : 'none', pointerEvents: pan ? 'none' : 'auto'}}
        onPointerDown={event => {
          if (!stillCurrent() || !current.current.available || pan || event.button !== 0 || stroke.current || remaining < 1
            || selectedMask.objects.length >= HAIR_SMOOTHING_LIMITS.strokes) return;
          const point = pointAt(event); if (!point) return;
          event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); current.current.onDraftStart();
          const pixels = radius / 100 * Math.min(source.width, source.height);
          const brush: HairSmoothingBrush = {id: crypto.randomUUID().replaceAll('-', ''),
            name: layer === 'protect' ? '可见头发硬保护' : layer === 'context' ? '同人可见头发上下文' : '可见头发柔顺目标',
            enabled: true, operation: layer !== 'protect' && subtract ? 'subtract' : 'add', kind: 'brush', opacity: 1, feather: 0,
            points: [point], axes: [[pixels / source.width, 0], [0, pixels / source.height]]};
          stroke.current = {brush, layer, pointer: event.pointerId, binding}; setDraft(stroke.current);
        }} onPointerMove={event => {
          const item = stroke.current;
          if (!stillCurrent() || !current.current.available || !item || item.pointer !== event.pointerId
            || item.brush.points.length >= Math.min(HAIR_SMOOTHING_LIMITS.pointsPerStroke, remaining)) return;
          const point = pointAt(event); if (!point) return;
          const last = item.brush.points[item.brush.points.length - 1];
          if (Math.hypot((point[0] - last[0]) * source.width, (point[1] - last[1]) * source.height) < .25) return;
          stroke.current = {...item, brush: {...item.brush, points: [...item.brush.points, point]}}; setDraft(stroke.current);
        }} onPointerUp={finish} onPointerCancel={event => {if (stroke.current?.pointer === event.pointerId) cancel(event);}}
        onLostPointerCapture={event => {if (stroke.current?.pointer === event.pointerId) cancel();}}/>
    </div></div>}
    {!available && <p role="status">等待当前真实来源图加载，或先结束现有人物请求。</p>}
    {image?.rect && <p>原生来源裁片：左 {image.rect[0]}，上 {image.rect[1]}，{image.rect[2]} × {image.rect[3]}；笔迹仍是完整来源坐标。</p>}
    {image && !image.rect && (image.width !== source.width || image.height !== source.height)
      && <p role="status">这是 {image.width} × {image.height} 定位缩略图，原来源 {source.width} × {source.height}。参考图 1:1 不等于来源 100%；不能据此猜纹理尺度。</p>}
    <p>这里只显示手工笔迹，不是最终准入。真实语义编辑权重、本人归属、硬保护及每个完整采样点的交集，以候选叠图为准。皮肤、头皮、耳朵、饰物、其他人和归属不清的接触边界需独立硬保护。</p>
    <p>每类最多 64 笔，每笔最多 1024 点，三类合计还可记录 {remaining} 点。达到上限停止记录，不自动简化；移除草稿不创建第二套撤销历史。</p>
  </section>;
}
