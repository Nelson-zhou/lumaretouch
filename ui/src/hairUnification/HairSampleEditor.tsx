// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState, type PointerEvent} from 'react';
import {MAX_POINTS, MAX_STROKES, MAX_TOTAL_POINTS, type Reference, type ReferenceSide, type Sample, type SampleBrush, type SampleObject} from './model';

type Point = [number, number];
type Gesture = {pointer: number; imageKey: string; rect: DOMRect; brush: SampleBrush};
const position = (event: PointerEvent<HTMLDivElement>): Point | null => {
  const rect = event.currentTarget.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;
  const x = (event.clientX - rect.left) / rect.width, y = (event.clientY - rect.top) / rect.height;
  return x < 0 || x > 1 || y < 0 || y > 1 ? null : [x, y];
};

/** Complete immutable source only. No face-box expansion or mapping from the retouched canvas. */
export function HairSampleEditor({reference, side, value, disabled, onChange, onStroke, onError}: {
  reference: Reference; side: ReferenceSide; value: Sample; disabled: boolean;
  onChange: (value: Sample) => void; onStroke: (active: boolean) => void; onError: (message: string) => void;
}) {
  const gesture = useRef<Gesture | null>(null), owner = useRef({onStroke, onError, onChange});
  owner.current = {onStroke, onError, onChange};
  const [draft, setDraft] = useState<SampleBrush | null>(null), [loaded, setLoaded] = useState('');
  const [mode, setMode] = useState<'add' | 'subtract'>('add'), [radius, setRadius] = useState(1);
  const [zoom, setZoom] = useState(1), [pan, setPan] = useState(false);
  const imageKey = `${reference.source.sha256}:${reference.face_ref.face_instance_id}:${reference.source_png}`;
  const remaining = MAX_TOTAL_POINTS - value.objects.reduce((sum, item) => sum + (item.kind === 'brush' ? item.points.length : 0), 0);
  const available = !disabled && loaded === imageKey && remaining > 0 && value.objects.length < MAX_STROKES;
  function cancel() {
    const active = !!gesture.current;
    gesture.current = null; setDraft(null);
    if (active) owner.current.onStroke(false);
  }
  useEffect(() => {cancel();}, [imageKey, side, disabled, zoom, pan]);
  useEffect(() => {
    const blur = () => cancel(), visibility = () => {if (document.hidden) cancel();};
    window.addEventListener('blur', blur); document.addEventListener('visibilitychange', visibility);
    return () => {window.removeEventListener('blur', blur); document.removeEventListener('visibilitychange', visibility);
      if (gesture.current) {gesture.current = null; owner.current.onStroke(false);}};
  }, []);
  const {width, height} = reference.source;
  function append(event: PointerEvent<HTMLDivElement>): boolean {
    const active = gesture.current;
    if (!active || active.pointer !== event.pointerId || active.imageKey !== imageKey || !available) return false;
    const p = position(event), rect = event.currentTarget.getBoundingClientRect();
    if (!p || (['left', 'top', 'width', 'height'] as const).some(field => Math.abs(rect[field] - active.rect[field]) > .5)) {
      cancel(); owner.current.onError('源图视图位置或笔迹边界已改变，本笔已取消；之前草稿仍保留。'); return false;
    }
    const last = active.brush.points.at(-1)!;
    if (Math.hypot((p[0] - last[0]) * rect.width, (p[1] - last[1]) * rect.height) < 1) return true;
    if (active.brush.points.length >= Math.min(MAX_POINTS, remaining)) {
      cancel(); owner.current.onError('本笔超过样本路径预算，未保留本笔；请改用短笔划。'); return false;
    }
    active.brush = {...active.brush, points: [...active.brush.points, p]}; setDraft(active.brush); return true;
  }
  function vector(item: SampleObject, temporary = false) {
    if (!item.enabled) return null;
    const [[vx, vy], [wx, wy]] = item.axes, det = vx * wy - vy * wx;
    if (Math.abs(det) < 1e-12) return null;
    const color = item.operation === 'subtract' ? '#ff8b96' : side === 'roots' ? '#ffc76b' : '#5addd2';
    if (item.kind === 'radial') return <g key={item.id} transform={`matrix(${vx * width} ${vy * height} ${wx * width} ${wy * height} ${item.center[0] * width} ${item.center[1] * height})`}>
      <circle r={1} fill={color} opacity={.45}/></g>;
    const points = item.points.map(([x, y]) => [(wy * x - wx * y) / det, (-vy * x + vx * y) / det] as Point);
    return <g key={item.id} transform={`matrix(${vx * width} ${vy * height} ${wx * width} ${wy * height} 0 0)`}
      fill={color} stroke={color} opacity={temporary ? .7 : .45}>
      {points.length === 1 ? <circle cx={points[0][0]} cy={points[0][1]} r={1} stroke="none"/>
        : <polyline points={points.map(p => p.join(',')).join(' ')} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round"/>}</g>;
  }
  return <div className="hair-unification-samples">
    <p>只在未裁剪、未变形的源图画出本人的{side === 'roots' ? '发根' : '发尾'}参考样本。笔迹是采样指令，不是生效范围，也不是自动发根识别。</p>
    <div className="hair-unification-toolbar">
      <button type="button" disabled={disabled || !!draft} aria-pressed={mode === 'add'} onClick={() => setMode('add')}>添加样本</button>
      <button type="button" disabled={disabled || !!draft} aria-pressed={mode === 'subtract'} onClick={() => setMode('subtract')}>减去样本</button>
      <label>笔刷半径<input type="range" aria-label="参考样本笔刷半径" min={.2} max={5} step={.1} value={radius}
        disabled={disabled || !!draft} onChange={event => setRadius(Number(event.target.value))}/><output>{radius}% 源图短边</output></label>
      <button type="button" disabled={disabled || !!draft || !value.objects.length} onClick={() => onChange({...value, objects: value.objects.slice(0, -1)})}>撤回此样本最后一笔</button>
      <button type="button" disabled={disabled || !!draft || !value.objects.length} onClick={() => onChange({...value, objects: []})}>清空此样本草稿</button>
    </div>
    <div className="hair-unification-toolbar">
      <label>源图缩放<select aria-label="源图采样缩放" disabled={!!draft} value={zoom} onChange={event => setZoom(Number(event.target.value))}>
        {[1, 2, 4, 8].map(n => <option key={n} value={n}>{n === 1 ? '适应视图' : `${n * 100}% 缩小图`}</option>)}</select></label>
      <button type="button" aria-pressed={pan} disabled={!!draft} onClick={() => setPan(!pan)}>{pan ? '切换画笔' : '切换滚动平移'}</button>
    </div>
    <div className="hair-unification-source-viewport">
      <div className="hair-unification-source" style={{width: `${zoom * 100}%`, aspectRatio: `${reference.source_preview_width}/${reference.source_preview_height}`,
        touchAction: pan ? 'pan-x pan-y' : 'none'}}
        onPointerDown={event => {
          if (!available || pan || gesture.current || event.button !== 0) return;
          const p = position(event); if (!p) return;
          event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
          const sourceRadius = radius / 100 * Math.min(width, height);
          const brush: SampleBrush = {id: crypto.randomUUID().replaceAll('-', ''), name: side === 'roots' ? '本人发根样本' : '本人发尾样本',
            enabled: true, kind: 'brush', operation: mode, opacity: 1, feather: 1, points: [p], axes: [[sourceRadius / width, 0], [0, sourceRadius / height]]};
          gesture.current = {pointer: event.pointerId, imageKey, rect: event.currentTarget.getBoundingClientRect(), brush};
          setDraft(brush); onStroke(true);
        }}
        onPointerMove={event => {if (gesture.current?.pointer === event.pointerId) {event.preventDefault(); append(event);}}}
        onPointerUp={event => {
          if (gesture.current?.pointer !== event.pointerId) return;
          const valid = append(event), active = gesture.current; gesture.current = null; setDraft(null); onStroke(false);
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
          if (valid && active && available) onChange({...value, objects: [...value.objects, active.brush]});
        }}
        onPointerCancel={cancel} onLostPointerCapture={() => {if (gesture.current) cancel();}}>
        <img key={imageKey} src={reference.source_png} alt="未裁剪且未变形的完整源图，用于手绘本人头发参考样本" draggable={false}
          onLoad={event => {
            const img = event.currentTarget;
            if (img.currentSrc !== reference.source_png || img.naturalWidth !== reference.source_preview_width || img.naturalHeight !== reference.source_preview_height) {
              setLoaded(''); onError('参考源图尺寸不匹配，采样已禁用。'); return;
            }
            setLoaded(imageKey);
          }} onError={() => {setLoaded(''); onError('参考源图未完整加载，不能在占位图上采样。');}}/>
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
          {value.objects.map(item => vector(item))}{draft && vector(draft, true)}
        </svg>
      </div>
    </div>
    <p>每个样本最多 {MAX_STROKES} 笔、每笔 {MAX_POINTS} 点、总计 {MAX_TOTAL_POINTS} 点；还可保留 {Math.max(0, remaining)} 点。放大缩小图不会补充原片细节。红色为减去笔迹；最终样本以与实测头发相交后的审核图为准。</p>
  </div>;
}
