// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState, type PointerEvent} from 'react';
import {NECK_WRINKLE_LIMITS, sourcePoint, type NeckBrush, type NeckMask, type NeckSource} from './review';

export type NeckPaintImage = {url: string; width: number; height: number; sha256: string;
  /** Trusted source crop only. Retouched output crops must NEVER enter this editor. */
  rect?: [number, number, number, number]};
type Mode = 'add' | 'subtract' | 'protect';
type Stroke = {brush: NeckBrush; mode: Mode; pointer: number; binding: string};

/** Draft vectors only: no sampling, segmentation, inferred neck contour or graph/history owner. */
export function NeckSourceEditor({binding, source, image, region, protect, disabled, onChange, onLoaded, onDraftStart}: {
  binding: string; source: NeckSource; image: NeckPaintImage | null; region: NeckMask; protect: NeckMask;
  disabled: boolean; onChange: (region: NeckMask, protect: NeckMask) => void;
  onLoaded: (ready: boolean) => void; onDraftStart: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null), stroke = useRef<Stroke | null>(null);
  const [draft, setDraft] = useState<Stroke | null>(null), [mode, setMode] = useState<Mode>('add');
  const [radius, setRadius] = useState(1), [zoom, setZoom] = useState<'fit' | 'pixels'>('fit'), [pan, setPan] = useState(false);
  const [loaded, setLoaded] = useState('');
  const key = image ? `${binding}:${image.sha256}:${image.width}:${image.height}:${image.rect?.join(',') ?? 'full'}` : '';
  const available = !!image && loaded === key && !disabled;
  const mounted = useRef(false), current = useRef({binding, key, available, region, protect, onChange, onLoaded, onDraftStart});
  current.current = {binding, key, available, region, protect, onChange, onLoaded, onDraftStart};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; stroke.current = null;};}, []);
  useEffect(() => {stroke.current = null; setDraft(null);}, [key, disabled]);
  const total = [...region.objects, ...protect.objects].reduce((n, brush) => n + brush.points.length, 0);
  const remaining = Math.max(0, NECK_WRINKLE_LIMITS.totalPoints - total);
  const stillCurrent = () => mounted.current && current.current.binding === binding && current.current.key === key;
  useEffect(() => {
    const node = canvas.current, ctx = node?.getContext('2d'); if (!node || !ctx || !image) return;
    // Display-only vectors may be drawn at the reference image's display extent.
    // These pixels never become a submitted mask or an analysis input.
    node.width = image.width; node.height = image.height; ctx.clearRect(0, 0, node.width, node.height);
    const rows = [...region.objects.map(brush => ({brush, protection: false})),
      ...protect.objects.map(brush => ({brush, protection: true})),
      ...(draft ? [{brush: draft.brush, protection: draft.mode === 'protect'}] : [])];
    for (const {brush, protection} of rows) {
      if (!brush.enabled) continue;
      const [[vx, vy], [wx, wy]] = brush.axes, determinant = vx * wy - vy * wx;
      if (Math.abs(determinant) < 1e-12 || !brush.points.length) continue;
      const points = brush.points.map(([x, y]) => [(wy * x - wx * y) / determinant, (-vy * x + vx * y) / determinant]);
      const [x, y, width, height] = image.rect ?? [0, 0, source.width, source.height];
      ctx.save(); ctx.scale(node.width / width, node.height / height); ctx.translate(-x, -y);
      ctx.scale(source.width, source.height); ctx.transform(vx, vy, wx, wy, 0, 0);
      ctx.strokeStyle = protection ? 'rgba(255,50,130,.8)' : brush.operation === 'subtract' ? 'rgba(255,180,50,.7)' : 'rgba(20,220,225,.5)';
      ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.beginPath();
      points.forEach((point, index) => index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1]));
      if (points.length === 1) {ctx.arc(points[0][0], points[0][1], 1, 0, 2 * Math.PI); ctx.fill();} else ctx.stroke();
      ctx.restore();
    }
  }, [image, source.width, source.height, region, protect, draft]);
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
    const item = stroke.current;
    if (!item || item.pointer !== event.pointerId) return;
    cancel(event);
    if (!stillCurrent() || !current.current.available || item.binding !== binding) return;
    const next = item.mode === 'protect' ? current.current.protect : current.current.region;
    if (next.objects.length >= NECK_WRINKLE_LIMITS.strokes) return;
    const updated = {...next, objects: [...next.objects, item.brush]};
    current.current.onChange(item.mode === 'protect' ? current.current.region : updated,
      item.mode === 'protect' ? updated : current.current.protect);
  };
  const edit = (nextRegion: NeckMask, nextProtect: NeckMask) => {
    if (stillCurrent() && current.current.available && !stroke.current) current.current.onChange(nextRegion, nextProtect);
  };
  return <section aria-label="颈部来源图与独立硬保护画笔">
    <p>在真实来源上画出可见颈部皮肤及足够的同人皮肤上下文。青色添加，橙色减去；粉红色是单独硬保护，后来添加皮肤也不能覆盖它。</p>
    <div className="prow">
      {(['add', 'subtract', 'protect'] as const).map(value => <button key={value} type="button" disabled={!available || !!draft}
        aria-pressed={mode === value} onClick={() => setMode(value)}>{value === 'add' ? '添加颈部与上下文' : value === 'subtract' ? '减去皮肤范围' : '绘制硬保护'}</button>)}
    </div>
    <label>画笔半径（来源短边百分比，不是细纹半宽）<input type="range" min="0.05" max="8" step="0.05" value={radius}
      disabled={!available || !!draft} onChange={event => setRadius(Number(event.target.value))}/>{radius}%</label>
    <div className="prow">
      <button type="button" disabled={!available || !!draft || !region.objects.length}
        onClick={() => edit({...region, objects: region.objects.slice(0, -1)}, protect)}>移除最后一笔皮肤草稿</button>
      <button type="button" disabled={!available || !!draft || !protect.objects.length}
        onClick={() => edit(region, {...protect, objects: protect.objects.slice(0, -1)})}>移除最后一笔保护草稿</button>
      <button type="button" disabled={!available || !!draft || !total}
        onClick={() => edit({...region, objects: []}, {...protect, objects: []})}>清空两类草稿，重新确认</button>
    </div>
    <div className="prow">
      <button type="button" disabled={!available || !!draft} aria-pressed={zoom === 'fit'} onClick={() => setZoom('fit')}>适合窗口</button>
      <button type="button" disabled={!available || !!draft} aria-pressed={zoom === 'pixels'} onClick={() => setZoom('pixels')}>参考图像素 1:1</button>
      <button type="button" disabled={!available || !!draft} aria-pressed={pan} onClick={() => setPan(!pan)}>{pan ? '返回画笔' : '平移查看'}</button>
    </div>
    {image && <div style={{overflow: 'auto', maxHeight: 560}}><div style={{position: 'relative',
      width: zoom === 'pixels' ? image.width : '100%', aspectRatio: `${image.width}/${image.height}`}}>
      <img key={key} src={image.url} alt="当前来源的完整真实颈部定位参考，尚未绘入任何自动颈部轮廓" draggable={false}
        style={{display: 'block', width: '100%', height: '100%'}} onLoad={event => {
          if (!stillCurrent()) return;
          const ready = event.currentTarget.naturalWidth === image.width && event.currentTarget.naturalHeight === image.height;
          setLoaded(ready ? key : ''); current.current.onLoaded(ready);
        }} onError={() => {if (stillCurrent()) {setLoaded(''); current.current.onLoaded(false);}}}/>
      <canvas ref={canvas} aria-label="当前人物颈部皮肤与硬保护手绘画布" style={{position: 'absolute', inset: 0,
        width: '100%', height: '100%', touchAction: pan ? 'pan-x pan-y' : 'none', pointerEvents: pan ? 'none' : 'auto'}}
        onPointerDown={event => {
          if (!stillCurrent() || !current.current.available || pan || event.button !== 0 || stroke.current || remaining < 1
            || (mode === 'protect' ? protect : region).objects.length >= NECK_WRINKLE_LIMITS.strokes) return;
          const point = pointAt(event); if (!point) return;
          event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); current.current.onDraftStart();
          const pixels = radius / 100 * Math.min(source.width, source.height);
          const brush: NeckBrush = {id: crypto.randomUUID().replaceAll('-', ''), name: mode === 'protect' ? '颈部硬保护' : '颈部皮肤上下文',
            enabled: true, operation: mode === 'subtract' ? 'subtract' : 'add', kind: 'brush', opacity: 1, feather: 0,
            points: [point], axes: [[pixels / source.width, 0], [0, pixels / source.height]]};
          stroke.current = {brush, mode, pointer: event.pointerId, binding}; setDraft(stroke.current);
        }} onPointerMove={event => {
          const item = stroke.current;
          if (!stillCurrent() || !current.current.available || !item || item.pointer !== event.pointerId
            || item.brush.points.length >= Math.min(NECK_WRINKLE_LIMITS.pointsPerStroke, remaining)) return;
          const point = pointAt(event); if (!point) return;
          const last = item.brush.points[item.brush.points.length - 1];
          if (Math.hypot((point[0] - last[0]) * source.width, (point[1] - last[1]) * source.height) < .25) return;
          stroke.current = {...item, brush: {...item.brush, points: [...item.brush.points, point]}}; setDraft(stroke.current);
        }} onPointerUp={finish} onPointerCancel={event => {if (stroke.current?.pointer === event.pointerId) cancel(event);}}
        onLostPointerCapture={event => {if (stroke.current?.pointer === event.pointerId) cancel();}}/>
    </div></div>}
    {!available && <p role="status">等待当前真实来源参考图加载完成，或先结束正在处理的请求。</p>}
    {image?.rect && <p>当前是来源像素裁片：左 {image.rect[0]}，上 {image.rect[1]}，{image.rect[2]} × {image.rect[3]}。笔迹仍保存为完整来源坐标，不转移到修图结果坐标。</p>}
    {image && !image.rect && (image.width !== source.width || image.height !== source.height)
      && <p role="status">这是 {image.width} × {image.height} 缩略参考，原来源 {source.width} × {source.height}。参考图 1:1 不是来源 100%，放大不会补充细纹细节。</p>}
    <p>此处只显示定位笔迹，不是最终准入范围。实际皮肤交集、硬保护与完整采样上下文排除，以引擎候选叠图为准。不会自动识别首饰或实例。</p>
    <p>每类至多 64 笔，每笔至多 1024 点，两类合计剩余 {remaining} 点。达到上限停止记录本笔，不自动简化点；松开后可清理草稿。草稿删除不创建第二套修图撤销历史。</p>
  </section>;
}
