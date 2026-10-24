// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useId, useRef, useState, type KeyboardEvent, type PointerEvent} from 'react';
import {sourceViewport, type SourceImage} from '../legShape/sourcePreview';
import {verifiedImage, type FaceDecorationView} from './model';
import {LIMITS, region, stroke, totalPoints, type Point, type Region, type Stroke} from './review';
const emptyFlags = () => ({visible: false, unoccluded: false, owner: false});
/** Mounted only for one exact reference request. No source support or consent is borrowed from another tool/person. */
export function FaceDecorationSupportEditor({report, faceBox, disabled, onReview}: {
  report: FaceDecorationView; faceBox: [number, number, number, number]; disabled: boolean; onReview: (region: Region) => Promise<void>;
}) {
  const id = useId(), [image, setImage] = useState<SourceImage | null>(null), [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(''), [strokes, setStrokes] = useState<Stroke[]>([]), [draft, setDraft] = useState<Stroke | null>(null);
  const [mode, setMode] = useState<'add' | 'subtract'>('add'), [radius, setRadius] = useState(Math.min(20, report.source.width - 1, report.source.height - 1));
  const [flags, setFlags] = useState(emptyFlags), [saving, setSaving] = useState(false), [zoom, setZoom] = useState(1), [cursor, setCursor] = useState<Point>([.5, .5]);
  const drawing = useRef<Stroke | null>(null), alive = useRef(true), savingRef = useRef(false);
  const proof = report.reference_proof!, source = report.source;
  const key = `${proof.reference_request_id}:${proof.preview_sha256}`;
  useEffect(() => {
    let active = true; alive.current = true;
    setImage(null); setLoaded(false); setStrokes([]); setDraft(null); drawing.current = null; setFlags(emptyFlags()); setError('');
    void verifiedImage(report.source_preview, proof).then(value => {if (active) setImage(value);}, cause => {if (active) setError(String(cause));});
    return () => {active = false; alive.current = false; drawing.current = null;};
  }, [key]);
  useEffect(() => {if (disabled) {drawing.current = null; setDraft(null);}}, [disabled]);
  const available = !disabled && !saving && loaded && !!image;
  const hasRoom = strokes.length < LIMITS.strokes && totalPoints(strokes) < LIMITS.totalPoints;
  const current = useRef({available, hasRoom}); current.current = {available, hasRoom};
  function replace(next: Stroke[]) {setStrokes(next); setFlags(emptyFlags()); setError('');}
  function at(event: PointerEvent<SVGSVGElement>): Point | null {
    const matrix = event.currentTarget.getScreenCTM(); if (!matrix) return null;
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    const point: Point = [p.x / (source.width - 1), p.y / (source.height - 1)];
    return point.every(n => Number.isFinite(n) && n >= 0 && n <= 1) ? point : null;
  }
  function start(event: PointerEvent<SVGSVGElement>) {
    if (!current.current.available || !current.current.hasRoom || drawing.current || event.button !== 0) return;
    const point = at(event); if (!point) return;
    event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId);
    const next = stroke(source, mode, radius, point, crypto.randomUUID()); drawing.current = next; setDraft(next); setCursor(point); setFlags(emptyFlags());
  }
  function move(event: PointerEvent<SVGSVGElement>) {
    const old = drawing.current; if (!old || !current.current.available) return;
    const point = at(event); if (!point) return;
    if (old.points.length >= Math.min(LIMITS.pointsPerStroke, LIMITS.totalPoints - totalPoints(strokes))) return;
    const last = old.points.at(-1)!;
    if (Math.hypot((point[0] - last[0]) * (source.width - 1), (point[1] - last[1]) * (source.height - 1)) < Math.max(1, radius / 4)) return;
    const next = {...old, points: [...old.points, point]}; drawing.current = next; setDraft(next); setCursor(point);
  }
  function finish(event: PointerEvent<SVGSVGElement>, cancel = false) {
    const next = drawing.current; drawing.current = null; setDraft(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (next && !cancel && current.current.available) replace([...strokes, next]);
  }
  function keyboard(event: KeyboardEvent<SVGSVGElement>) {
    if (!available || drawing.current) return;
    const step = event.shiftKey ? 25 : 5;
    const offsets: Record<string, [number, number]> = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step]};
    const move = offsets[event.key];
    if (move) {event.preventDefault(); setCursor(p => [Math.max(0, Math.min(1, p[0] + move[0] / (source.width - 1))), Math.max(0, Math.min(1, p[1] + move[1] / (source.height - 1)))]);}
    if ((event.key === 'Enter' || event.key === ' ') && hasRoom) {event.preventDefault(); replace([...strokes, stroke(source, mode, radius, cursor, crypto.randomUUID())]);}
  }
  async function save() {
    if (!current.current.available || savingRef.current || drawing.current) return;
    try {
      const value = region(strokes, loaded && !!image, flags); savingRef.current = true; setSaving(true);
      await onReview(value);
      if (alive.current) setError('');
    } catch (cause) {if (alive.current) setError(String(cause));}
    finally {savingRef.current = false; if (alive.current) setSaving(false);}
  }
  function renderStroke(item: Stroke) {
    const colour = item.operation === 'add' ? '#22d3c5' : '#ff776c', r = item.axes[0][0] * (source.width - 1);
    return <g key={item.id} fill={colour} stroke={colour} strokeWidth={r * 2} opacity=".45" strokeLinecap="round" strokeLinejoin="round">
      <polyline fill="none" points={item.points.map(p => `${p[0] * (source.width - 1)},${p[1] * (source.height - 1)}`).join(' ')}/>
      {item.points.length === 1 && <circle cx={item.points[0][0] * (source.width - 1)} cy={item.points[0][1] * (source.height - 1)} r={r} stroke="none"/>}
    </g>;
  }
  return <fieldset className="decorationReview" disabled={disabled || saving}>
    <legend>仅此人物的脸部装饰范围审核</legend>
    <p>这是真实来源的全图参考缩图，不是效果图或全分辨率验收图。请涂选可见面部皮肤，并擦除眼、眉、唇、发丝、饰物和其他人物；不会自动识别所有遮挡。</p>
    <p id={`${id}-instructions`}>黄色框标记当前人物检测位置，不是皮肤或遮挡证明。青色为添加笔迹，红色为排除笔迹，不代表最终精确蒙版。拖动画笔；也可聚焦图像，用方向键移动 5 个源像素（Shift 为 25），Enter 或空格点涂。新一笔不会跨越上一笔的间隙。</p>
    {!loaded && <p role="status">正在校验并加载本次来源图像，确认项尚不可用。</p>}
    <div className="decorationSourceScroll">{image && <div className="decorationSource" style={{width: `${zoom * 100}%`, aspectRatio: `${image.displayWidth}/${image.displayHeight}`}}>
      <img key={key} src={image.url} alt="当前人物脸部装饰审核的真实未修饰来源参考缩图" draggable={false}
        onLoad={event => {if (event.currentTarget.naturalWidth === image.displayWidth && event.currentTarget.naturalHeight === image.displayHeight) setLoaded(true); else {setLoaded(false); setError('来源图像实际解码尺寸不匹配。');}}}
        onError={() => {setLoaded(false); setFlags(emptyFlags()); setError('来源图像加载失败，不能审核。');}}/>
      <svg viewBox={sourceViewport(image)} preserveAspectRatio="none" tabIndex={0} role="img" aria-label="脸部装饰可见皮肤画布" aria-describedby={`${id}-instructions`}
        aria-disabled={!available} onPointerDown={start} onPointerMove={move} onPointerUp={finish} onPointerCancel={e => finish(e, true)} onLostPointerCapture={e => {if (drawing.current) finish(e, true);}} onKeyDown={keyboard}>
        <rect x={faceBox[0] * (source.width - 1)} y={faceBox[1] * (source.height - 1)}
          width={(faceBox[2] - faceBox[0]) * (source.width - 1)} height={(faceBox[3] - faceBox[1]) * (source.height - 1)}
          fill="none" stroke="#ffd96c" strokeWidth={Math.max(1, source.width / 600)} strokeDasharray="6 4"/>
        {[...strokes, ...(draft ? [draft] : [])].map(renderStroke)}
        <circle cx={cursor[0] * (source.width - 1)} cy={cursor[1] * (source.height - 1)} r={radius} fill="none" stroke="white" strokeWidth={Math.max(1, source.width / 800)} strokeDasharray="4 3"/>
      </svg>
    </div>}</div>
    <div className="decorationReviewTools">
      <button type="button" disabled={!available || !!draft} aria-pressed={mode === 'add'} onClick={() => setMode('add')}>添加可见皮肤</button>
      <button type="button" disabled={!available || !!draft} aria-pressed={mode === 'subtract'} onClick={() => setMode('subtract')}>排除遮挡 / 非皮肤</button>
      <label>画笔半径（源像素）<input type="number" min={1} max={Math.min(500, source.width - 1, source.height - 1)} value={radius} disabled={!available || !!draft} onChange={e => {const v = e.currentTarget.valueAsNumber; if (Number.isFinite(v) && v >= 1 && v <= Math.min(500, source.width - 1, source.height - 1)) setRadius(v);}}/></label>
      <label>参考图放大<input type="range" min={1} max={4} step={.25} value={zoom} onChange={e => setZoom(Number(e.currentTarget.value))}/><output>{zoom}×</output></label>
      <button type="button" disabled={!available || !strokes.length || !!draft} onClick={() => replace(strokes.slice(0, -1))}>撤销一笔</button>
      <button type="button" disabled={!available || !strokes.length || !!draft} onClick={() => replace([])}>清空本次笔迹</button>
    </div>
    <p role="status">{strokes.length}/{LIMITS.strokes} 笔，{totalPoints(strokes)}/{LIMITS.totalPoints} 个点。{!hasRoom && '已达到笔迹上限，请撤销或清理后继续。'}</p>
    <label><input type="checkbox" disabled={!available || !strokes.length || !!draft} checked={flags.visible} onChange={e => setFlags(f => ({...f, visible: e.target.checked}))}/>我已查看本次来源图：脸部装饰只添加在所画的清晰可见皮肤上。</label>
    <label><input type="checkbox" disabled={!available || !strokes.length || !!draft} checked={flags.unoccluded} onChange={e => setFlags(f => ({...f, unoccluded: e.target.checked}))}/>我已从本次脸部装饰范围排除遮挡物、眼眉唇和头发。</label>
    <label><input type="checkbox" disabled={!available || !strokes.length || !!draft} checked={flags.owner} onChange={e => setFlags(f => ({...f, owner: e.target.checked}))}/>我确认本次脸部装饰范围仅属于当前选中人物，不是其他人物，也不沿用腮红或其他工具的审核。</label>
    <button type="button" disabled={!available || !!draft || !strokes.some(s => s.operation === 'add') || !flags.visible || !flags.unoccluded || !flags.owner} onClick={() => void save()}>保存此人物的装饰范围审核</button>
    {error && <p role="alert">{error}</p>}
    <small>笔迹、原图及审核不会随预设或批量参数复制。关键点、皮肤支持、侧脸或分辨率不可靠时，引擎仍会拒绝，手动确认不能解除限制。</small>
  </fieldset>;
}
