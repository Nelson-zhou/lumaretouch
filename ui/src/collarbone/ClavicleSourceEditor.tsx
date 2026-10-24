// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState, type PointerEvent} from 'react';
import {matchesSource, type SourceImage} from '../legShape/sourcePreview';
import {bodyMaskPoint, type SkinBodySource} from '../skinColour/bodyReviewModel';
import {clavicleReviewError, type ClavicleCurve, type ClavicleDraft, type ClaviclePoint} from './clavicleReview';

/** All anatomy points originate in explicit clicks on a proven whole-source image. */
export function ClavicleSourceEditor({context, image, source, value, disabled, onChange, onLoaded}: {
  context: string; image: SourceImage | null; source: SkinBodySource; value: ClavicleDraft; disabled: boolean;
  onChange: (value: ClavicleDraft) => void; onLoaded: (ready: boolean) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null), mounted = useRef(false);
  const [side, setSide] = useState<ClavicleCurve['id']>('left'), [mode, setMode] = useState<'add' | 'move'>('add');
  const [selectedPoint, setSelectedPoint] = useState<number | null>(null), [zoom, setZoom] = useState(1), [pan, setPan] = useState(false);
  const [loaded, setLoaded] = useState(''), [message, setMessage] = useState('');
  const validImage = matchesSource(image, {...source, orientation: 'exif_normalized_once'});
  const imageKey = validImage ? `${context}:${image.url}:${image.displayWidth}:${image.displayHeight}` : '';
  const draftKey = JSON.stringify(value), interactionKey = JSON.stringify([side, mode, selectedPoint, zoom, pan]);
  const live = useRef({context, imageKey, draftKey, interactionKey, disabled});
  live.current = {context, imageKey, draftKey, interactionKey, disabled};
  const imageCurrent = () => mounted.current && live.current.context === context && live.current.imageKey === imageKey;
  const current = () => imageCurrent() && !live.current.disabled && live.current.draftKey === draftKey && live.current.interactionKey === interactionKey;
  const available = validImage && !!imageKey && loaded === imageKey && !disabled;
  const curve = value.curves.find(item => item.id === side), shortSide = Math.min(source.width, source.height);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useEffect(() => {setSelectedPoint(null); setZoom(1); setPan(false); setMessage('');}, [context, imageKey]);
  useEffect(() => {
    const node = canvas.current, ctx = node?.getContext('2d'); if (!node || !ctx || !image) return;
    node.width = image.displayWidth; node.height = image.displayHeight; ctx.clearRect(0, 0, node.width, node.height);
    for (const item of value.curves) {
      const points = item.points.map(([x, y]) => [x * node.width, y * node.height]);
      if (!points.length) continue;
      // Elliptical scaling preserves half-width in original-source pixel units under thumbnail rounding.
      ctx.save(); ctx.scale(node.width / source.width, node.height / source.height);
      ctx.beginPath(); item.points.forEach(([x, y], index) => index ? ctx.lineTo(x * source.width, y * source.height) : ctx.moveTo(x * source.width, y * source.height));
      ctx.strokeStyle = item.id === 'left' ? 'rgba(255,195,35,.22)' : 'rgba(211,120,255,.22)';
      ctx.lineWidth = Math.max(0, 2 * item.width * shortSide); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      if (ctx.lineWidth > 0 && item.width > 0) ctx.stroke(); ctx.restore();
      ctx.beginPath(); points.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
      ctx.strokeStyle = item.id === 'left' ? '#ffd043' : '#dc94ff'; ctx.lineWidth = 2; ctx.stroke();
      points.forEach(([x, y], index) => {
        ctx.beginPath(); ctx.arc(x, y, side === item.id && selectedPoint === index ? 6 : 4, 0, Math.PI * 2);
        ctx.fillStyle = side === item.id && selectedPoint === index ? '#fff' : ctx.strokeStyle; ctx.fill();
        ctx.font = '13px sans-serif'; ctx.fillStyle = '#fff'; ctx.fillText(`${item.id === 'left' ? '左' : '右'}${index + 1}`, x + 7, y - 6);
      });
    }
  }, [value, image, side, selectedPoint, source.width, source.height, shortSide]);
  function edit(next: ClavicleDraft, resetVisibility = true) {
    if (!available || !current()) return;
    setMessage(''); onChange({...next, visible_anatomy_confirmed: resetVisibility ? false : next.visible_anatomy_confirmed});
  }
  function editCurve(points: ClaviclePoint[], width = curve?.width ?? 0) {
    const curves = value.curves.filter(item => item.id !== side);
    if (points.length) curves.push({id: side, points, width});
    edit({...value, curves: curves.sort((a, b) => a.id.localeCompare(b.id))});
  }
  function place(event: PointerEvent<HTMLCanvasElement>) {
    if (!available || !current() || pan || event.button !== 0) return;
    const point = bodyMaskPoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect());
    if (!point || point.some(n => n <= 0 || n >= 1)) {setMessage('请在来源图内部点击，不允许边界或图外控制点。'); return;}
    event.preventDefault();
    const points = curve?.points ?? [];
    if (mode === 'add') {
      if (points.length >= 8) {setMessage('本侧已达到 8 点上限，请移动、删除或清空，不会自动简化曲线。'); return;}
      editCurve([...points, point]); setSelectedPoint(points.length);
    } else {
      if (selectedPoint === null || !points[selectedPoint]) {setMessage('请先选择需要移动的控制点，再点击来源图中的新位置。'); return;}
      editCurve(points.map((old, index) => index === selectedPoint ? point : old));
    }
  }
  const validation = clavicleReviewError(value, source);
  return <section aria-label="来源图手工锁骨曲线审核">
    <p>请只沿来源中已经看得见的锁骨逐点标记。没有预置点、自动检测或另一侧补全；一侧可见时仅画这一侧。下方曲线定位独立于身体皮肤画笔，二者都必须审核。</p>
    <label>明确选择官方适用类别<select value={value.category} disabled={!available} onChange={event => {
      const category = event.target.value; if (category !== '' && category !== 'female' && category !== 'elder_female') return;
      edit({...value, category, eligibility_confirmed: false});
    }}><option value="">请选择，不自动分类</option><option value="female">女</option><option value="elder_female">长辈女</option></select></label>
    <label style={{display: 'block'}}><input type="checkbox" checked={value.eligibility_confirmed} disabled={!available || !value.category}
      onChange={event => edit({...value, eligibility_confirmed: event.target.checked}, false)}/>我确认本人物适用我选择的类别；这不是系统对性别或年龄的判断</label>
    <div className="prow">{(['left', 'right'] as const).map(id => <button key={id} type="button" disabled={!available} aria-pressed={side === id}
      onClick={() => {setSide(id); setSelectedPoint(null); setMode('add');}}>{id === 'left' ? '图像左侧' : '图像右侧'}（{value.curves.find(item => item.id === id)?.points.length ?? 0} 点）</button>)}</div>
    <p>“左/右”是屏幕中的图像左右，不是人物自身的左右；每条曲线需 3 至 8 点，点按你的点击顺序连接；相邻点至少相距原始来源 2 像素，转向须小于 90 度。</p>
    <div className="prow"><button type="button" disabled={!available} aria-pressed={mode === 'add'} onClick={() => setMode('add')}>点击添加控制点</button>
      <button type="button" disabled={!available || !curve?.points.length} aria-pressed={mode === 'move'} onClick={() => setMode('move')}>移动选中控制点</button></div>
    <label>控制点<select value={selectedPoint ?? ''} disabled={!available || !curve?.points.length}
      onChange={event => {setSelectedPoint(event.target.value === '' ? null : Number(event.target.value)); setMode('move');}}>
      <option value="">选择要移动或删除的点</option>{curve?.points.map((_, index) => <option key={index} value={index}>第 {index + 1} 点</option>)}</select></label>
    <button type="button" disabled={!available || selectedPoint === null || !curve?.points[selectedPoint]}
      onClick={() => {if (selectedPoint !== null && curve) {editCurve(curve.points.filter((_, index) => index !== selectedPoint)); setSelectedPoint(null);}}}>删除所选点</button>
    {selectedPoint !== null && curve?.points[selectedPoint] && <p className="muted">所选点来源坐标：x = {(curve.points[selectedPoint][0] * source.width).toFixed(2)}，y = {(curve.points[selectedPoint][1] * source.height).toFixed(2)} 像素（完整画布像素边界坐标）；在图中点击移动，不用文本推断坐标。</p>}
    <label>本侧横向半宽（原始来源图像素，4 至 256）<input type="number" min={4} max={256} step="any" value={curve?.width ? Number((curve.width * shortSide).toFixed(6)) : ''}
      disabled={!available || !curve?.points.length} aria-label="锁骨曲线来源像素半宽" onChange={event => {
        const text = event.target.value, pixels = Number(text); if (!curve) return;
        if (text === '' || Number.isFinite(pixels)) editCurve(curve.points, text === '' ? 0 : pixels / shortSide);
      }}/></label>
    <p>半宽是中心线两侧各自的范围，不是整条带宽；曲线总长须至少为两倍半宽。需先放点再明确填写，不会默认选择。来源中没有足够空间或真实明暗时请缩窄、重画或放弃，不能猜测补全。</p>
    <div className="prow"><button type="button" disabled={!available || !curve} onClick={() => {editCurve([]); setSelectedPoint(null);}}>清空本侧曲线</button>
      <button type="button" disabled={!available || !value.curves.length} onClick={() => {edit({...value, curves: []}); setSelectedPoint(null);}}>清空全部曲线</button>
      <button type="button" disabled={!available || zoom <= 1} onClick={() => setZoom(old => Math.max(1, old / 2))}>缩小</button>
      <button type="button" disabled={!available || zoom >= 8} onClick={() => setZoom(old => Math.min(8, old * 2))}>放大</button>
      <button type="button" disabled={!available} aria-pressed={pan} onClick={() => setPan(old => !old)}>{pan ? '切换标点' : '切换平移'}</button><span>{Math.round(zoom * 100)}%</span></div>
    {validImage && <div style={{overflow: 'auto', maxHeight: 440}}><div style={{position: 'relative', width: `${zoom * 100}%`, aspectRatio: `${image.displayWidth}/${image.displayHeight}`}}>
      <img key={imageKey} src={image.url} alt="锁骨标记所用的完整有效来源缩略参考，未按脸框或修图结果推断" draggable={false} style={{display: 'block', width: '100%', height: '100%'}}
        onLoad={event => {if (!imageCurrent()) return; const ready = event.currentTarget.naturalWidth === image.displayWidth && event.currentTarget.naturalHeight === image.displayHeight; setLoaded(ready ? imageKey : ''); onLoaded(ready);}}
        onError={() => {if (!imageCurrent()) return; setLoaded(''); onLoaded(false);}}/>
      <canvas ref={canvas} aria-label="点击来源图手工添加或移动锁骨控制点" onPointerDown={place}
        style={{position: 'absolute', inset: 0, width: '100%', height: '100%', touchAction: pan ? 'pan-x pan-y' : 'none', pointerEvents: pan ? 'none' : 'auto'}}/>
    </div></div>}
    {!available && <p role="status">请等待匹配当前来源与人物的图像实际加载，并结束其他编辑。</p>}
    <label style={{display: 'block'}}><input type="checkbox" checked={value.visible_anatomy_confirmed} disabled={!available || !value.curves.length}
      onChange={event => edit({...value, visible_anatomy_confirmed: event.target.checked}, false)}/>我确认每个点与半宽只沿真实可见锁骨，未推测衣物下、遮挡处、裁切外或另一侧的解剖结构</label>
    {(message || validation) && <p role="status">{message || validation}</p>}
    <p>这是手工定位草稿，不是检测结果、最终支持范围或效果图。曲线点不会自动插入、补齐或删除；缩略图放大不能证明原图细节。较小的真实渲染网格仍可能因点距或半宽不足而拒绝，不会替你夹取数值或补画。确认前必须检查引擎返回的真实前后对比和范围叠图。</p>
  </section>;
}
