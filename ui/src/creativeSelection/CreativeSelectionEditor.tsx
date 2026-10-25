// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import {SELECTION_LIMITS, SELECTION_REFERENCE, SELECTION_REVIEW_IMAGES, selectionKey,
  type SelectionCombine, type SelectionImageRole, type SelectionMaskPolicy, type SelectionOperation, type SelectionPng,
  type SelectionPoint, type SelectionTool} from './model';
import {selectionImageUrl} from './imagery';
import {sameSelectionRect, selectionPoint, selectionShape, selectionTypingTarget, type SelectionConstraint, type SelectionRect} from './geometry';
import type {CreativeSelectionController} from './controller';
import './creativeSelection.css';

const toolNames: Record<SelectionTool, string> = {rectangle: '矩形 M', ellipse: '椭圆', lasso: '套索 L', brush: '画笔'};
const combineNames: Record<SelectionCombine, string> = {new: '新选区', add: '增加', subtract: '减去', intersect: '交集'};
const imageNames: Record<SelectionImageRole, string> = {before_composite: '应用前 · 完整合成', after_composite: '应用后 · 完整合成', before_mask: '之前 · 源像素蒙版', after_mask: '之后 · 源像素蒙版'};
const readRect = (node: HTMLElement): SelectionRect => {const r = node.getBoundingClientRect(); return {left: r.left, top: r.top, width: r.width, height: r.height};};

/** A load event alone does not prove that a hidden/zero-size image was presented. */
function PresentedImage({image, alt, onPresented}: {image: SelectionPng; alt: string;
  onPresented: (width: number, height: number, visible: boolean) => void}) {
  const node = useRef<HTMLImageElement>(null), callback = useRef(onPresented); callback.current = onPresented;
  const report = () => {
    const element = node.current; if (!element) return;
    const box = element.getBoundingClientRect();
    let ancestorsVisible = true, ancestor: HTMLElement | null = element;
    while (ancestor) {
      const style = getComputedStyle(ancestor);
      if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse' || Number(style.opacity) <= 0) {ancestorsVisible = false; break;}
      ancestor = ancestor.parentElement;
    }
    const visible = element.complete && element.naturalWidth === image.width && element.naturalHeight === image.height
      && box.width > 0 && box.height > 0 && element.getClientRects().length > 0 && document.visibilityState === 'visible'
      && ancestorsVisible;
    callback.current(element.naturalWidth, element.naturalHeight, visible);
  };
  useLayoutEffect(() => {
    const element = node.current; if (!element) return;
    let first = 0, second = 0;
    const schedule = () => {cancelAnimationFrame(first); cancelAnimationFrame(second); first = requestAnimationFrame(() => {second = requestAnimationFrame(report);});};
    const observer = new ResizeObserver(schedule); observer.observe(element);
    const visibilityObserver = new MutationObserver(schedule);
    for (let ancestor: HTMLElement | null = element; ancestor; ancestor = ancestor.parentElement)
      visibilityObserver.observe(ancestor, {attributes: true, attributeFilter: ['style', 'class', 'hidden']});
    document.addEventListener('visibilitychange', schedule); window.addEventListener('resize', schedule); schedule();
    return () => {observer.disconnect(); visibilityObserver.disconnect(); cancelAnimationFrame(first); cancelAnimationFrame(second);
      document.removeEventListener('visibilitychange', schedule); window.removeEventListener('resize', schedule); callback.current(0, 0, false);};
  }, [image.sha256, image.width, image.height]);
  return <img ref={node} src={selectionImageUrl(image)} alt={alt} draggable={false}
    onLoad={() => {requestAnimationFrame(() => requestAnimationFrame(report));}} onError={() => callback.current(0, 0, false)}/>;
}

function VectorOutline({operation, live = false}: {operation: SelectionOperation; live?: boolean}) {
  if (operation.kind === 'invert') return null;
  const color = operation.combine === 'subtract' ? '#ff8e8e' : operation.combine === 'intersect' ? '#dab0ff' : '#81f0d0';
  if (operation.kind === 'rectangle') return <rect x={operation.x0} y={operation.y0} width={operation.x1 - operation.x0} height={operation.y1 - operation.y0}
    fill="none" stroke={color} vectorEffect="non-scaling-stroke" strokeWidth={live ? 2 : 1} strokeDasharray={live ? undefined : '5 4'}/>;
  if (operation.kind === 'ellipse') return <ellipse cx={(operation.x0 + operation.x1) / 2} cy={(operation.y0 + operation.y1) / 2}
    rx={(operation.x1 - operation.x0) / 2} ry={(operation.y1 - operation.y0) / 2} fill="none" stroke={color}
    vectorEffect="non-scaling-stroke" strokeWidth={live ? 2 : 1} strokeDasharray={live ? undefined : '5 4'}/>;
  const points = operation.points.map(point => point.join(',')).join(' ');
  if (operation.kind === 'brush') return operation.points.length === 1
    ? <circle cx={operation.points[0][0]} cy={operation.points[0][1]} r={operation.diameter / 2} fill={color} opacity={.2}/>
    : <polyline points={points} stroke={color} strokeWidth={operation.diameter} strokeOpacity={.2} strokeLinecap="round" strokeLinejoin="round" fill="none"/>;
  return live ? <polyline points={points} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke"/>
    : <polygon points={points} fill="none" stroke={color} strokeWidth={1} strokeDasharray="5 4" vectorEffect="non-scaling-stroke"/>;
}

interface Gesture {pointer: number; key: string; rect: SelectionRect; points: SelectionPoint[]; operation: SelectionOperation | null}
export function CreativeSelectionEditor({controller, disabled = false, unavailableReason}: {
  controller: CreativeSelectionController; disabled?: boolean; unavailableReason?: string;
}) {
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  const [tool, setTool] = useState<SelectionTool>('rectangle'), [combine, setCombine] = useState<SelectionCombine>('new');
  const [brushMode, setBrushMode] = useState<'add' | 'subtract'>('add'), [mode, setMode] = useState<'free' | 'ratio' | 'size'>('free');
  const [shapeWidth, setShapeWidth] = useState(1), [shapeHeight, setShapeHeight] = useState(1);
  const [diameter, setDiameter] = useState(80), [hardness, setHardness] = useState(.8), [opacity, setOpacity] = useState(1);
  const [live, setLive] = useState<SelectionOperation | null>(null), [hover, setHover] = useState<SelectionPoint | null>(null);
  const stage = useRef<HTMLDivElement>(null), gesture = useRef<Gesture | null>(null);
  const context = state.context, proof = context?.proof, recipe = state.recipe, review = state.review;
  const editable = !disabled && controller.editable(), draftKey = selectionKey([proof, tool, combine, brushMode, mode, shapeWidth, shapeHeight, diameter, hardness, opacity, editable, recipe]);
  const constraint: SelectionConstraint = mode === 'free' ? {mode} : {mode, width: shapeWidth, height: shapeHeight};
  const abandon = (message?: string) => {
    const old = gesture.current; gesture.current = null; setLive(null); setHover(null);
    if (old && stage.current?.hasPointerCapture(old.pointer)) stage.current.releasePointerCapture(old.pointer);
    if (old && message) controller.notice(message);
  };
  useLayoutEffect(() => {if (gesture.current && gesture.current.key !== draftKey) abandon('工具、来源或画布状态已变化，未完成的整笔已取消。');}, [draftKey]);
  useEffect(() => {
    const blur = () => abandon('窗口失焦，未完成的整笔已取消。');
    const visibility = () => {if (document.visibilityState !== 'visible') blur();};
    window.addEventListener('blur', blur); document.addEventListener('visibilitychange', visibility);
    return () => {window.removeEventListener('blur', blur); document.removeEventListener('visibilitychange', visibility); gesture.current = null; controller.releasePresentation();};
  }, [controller]);
  useEffect(() => {setTool('rectangle'); setCombine('new'); setBrushMode('add'); setMode('free'); setLive(null); setHover(null);}, [context?.proof.source_sha256, context?.proof.layer_id]);
  const pointFor = (event: ReactPointerEvent<HTMLDivElement>) => proof ? selectionPoint(event.clientX, event.clientY, readRect(event.currentTarget), proof.canvas) : null;
  const createOperation = (points: SelectionPoint[]): SelectionOperation | null => {
    if (!proof) return null;
    if (tool === 'rectangle' || tool === 'ellipse') return selectionShape(tool, combine, points[0], points[points.length - 1], proof.canvas, constraint);
    if (tool === 'lasso') return {kind: 'lasso', combine, points};
    return {kind: 'brush', combine: brushMode, points, diameter, hardness, opacity};
  };
  const advance = (event: ReactPointerEvent<HTMLDivElement>): Gesture | null => {
    const down = gesture.current, point = pointFor(event); setHover(point);
    if (!down || down.pointer !== event.pointerId) return null;
    if (!editable || down.key !== draftKey || !sameSelectionRect(down.rect, readRect(event.currentTarget)) || !point) {
      abandon('画布位置或尺寸改变，或指针离开画布；未完成的整笔已取消。'); return null;
    }
    const last = down.points[down.points.length - 1];
    if (Math.hypot(point[0] - last[0], point[1] - last[1]) >= .25) {
      if (tool === 'rectangle' || tool === 'ellipse') down.points = [down.points[0], point];
      else {
        if (down.points.length >= SELECTION_LIMITS.pointsPerGesture) {abandon('单笔点数超过安全上限，整笔未提交；请分段绘制。'); return null;}
        down.points = [...down.points, point];
      }
    }
    down.operation = createOperation(down.points); setLive(down.operation); return down;
  };
  const stop = (event: ReactPointerEvent<HTMLDivElement>) => {event.preventDefault(); event.stopPropagation();};
  const setDimension = (value: string, setter: (number: number) => void) => {const number = Number(value); if (Number.isFinite(number) && number > 0) setter(number);};
  return <section className="creative-selection" aria-label="创意选区编辑器" onKeyDown={event => {
    if (!editable || event.isDefaultPrevented() || event.nativeEvent.isComposing || event.ctrlKey || event.metaKey || event.altKey || selectionTypingTarget(event.target)) return;
    if (event.key === 'Escape') {event.preventDefault(); event.stopPropagation(); abandon('未完成的手势已取消；已完成草稿未删除。');}
    else if (event.key.toLowerCase() === 'm' || event.key.toLowerCase() === 'l') {
      event.preventDefault(); event.stopPropagation(); abandon(); setTool(event.key.toLowerCase() === 'm' ? 'rectangle' : 'lasso');
    }
  }}>
    <header className="creative-selection-header"><div><h3>规则 / 自由选区</h3><p>真实蒙版 · 仅当前选中图片图层</p></div>
      <button type="button" disabled={disabled || !controller.canAcquire()} onClick={() => void controller.acquire()}>{context ? '重新获取当前画布并清空草稿' : '获取当前图层画布'}</button></header>
    <p className="creative-selection-status" role={state.phase === 'unknown' || state.phase === 'failed' ? 'alert' : 'status'} aria-live="polite">{unavailableReason || state.message}</p>
    {proof && <p className="creative-selection-evidence">冻结画布 {proof.canvas.width} × {proof.canvas.height} px · 图层来源 {proof.source.width} × {proof.source.height} px
      {' · '}修订 {proof.expected_revision} · 来源摘要 {proof.source_sha256.slice(0, 12)}{state.stale ? ' · 已失效' : ''}</p>}
    <div className="creative-selection-layout">
      <div>
        {context && recipe && state.source_verified && !state.stale ? <>
          <div ref={stage} className={`creative-selection-stage${editable ? ' editable' : ''}`} style={{aspectRatio: `${proof!.canvas.width} / ${proof!.canvas.height}`}}
            tabIndex={0} role="application" aria-label="选区画布，M 矩形、L 套索；松手完成，Esc 取消当前手势"
            onPointerDown={event => {
              stop(event); if (!editable || event.button !== 0 || !event.isPrimary || gesture.current) return;
              const point = pointFor(event); if (!point) return;
              event.currentTarget.focus({preventScroll: true});
              const operation = createOperation([point]);
              gesture.current = {pointer: event.pointerId, key: draftKey, rect: readRect(event.currentTarget), points: [point], operation};
              setLive(operation); setHover(point);
              try {event.currentTarget.setPointerCapture(event.pointerId);} catch {abandon('无法取得指针控制，整笔未提交。');}
            }} onPointerMove={event => {stop(event); if (editable) advance(event);}}
            onPointerLeave={() => {if (!gesture.current) setHover(null);}}
            onPointerUp={event => {
              stop(event); if (gesture.current?.pointer !== event.pointerId) return;
              const completed = advance(event); const operation = completed?.operation; abandon();
              if (!operation) {controller.notice('选区尺寸无效或过小，未提交。固定尺寸不能超过画布。'); return;}
              if (operation.kind === 'lasso' && operation.points.length < 3) {controller.notice('套索至少需要三个不同位置；未提交。'); return;}
              // Native even-odd rasterization closes the final point to the first, only after pointerup.
              controller.append(operation);
            }} onPointerCancel={event => {stop(event); if (gesture.current?.pointer === event.pointerId) abandon('指针手势中断，整笔未提交。');}}
            onLostPointerCapture={event => {if (gesture.current?.pointer === event.pointerId) abandon('指针控制中断，整笔未提交。');}}>
            <PresentedImage image={context.canvas_image} alt="冻结的真实完整创意画布" onPresented={(width, height, visible) => controller.sourcePresented(context.canvas_image.sha256, width, height, visible)}/>
            <svg aria-hidden="true" viewBox={`0 0 ${proof!.canvas.width} ${proof!.canvas.height}`} preserveAspectRatio="none">
              {recipe.operations.map((operation, index) => <VectorOutline key={index} operation={operation}/>)}
              {live && <VectorOutline operation={live} live/>}
              {hover && tool === 'brush' && <g fill="none" stroke="#fff" strokeWidth={1}>
                <circle cx={hover[0]} cy={hover[1]} r={diameter / 2} vectorEffect="non-scaling-stroke"/>
                <circle cx={hover[0]} cy={hover[1]} r={diameter * hardness / 2} strokeDasharray="3 3" vectorEffect="non-scaling-stroke"/>
              </g>}
            </svg>
          </div>
          <p className="creative-selection-hint">轮廓和笔迹仅表示矢量操作路径，不是最终选区或蒙版。最终覆盖率以真实预览为准。画布适配显示，不冒充 100% 检视。</p>
          <p className="creative-selection-hint">套索松手自动闭合；离开画布、视图变化、窗口失焦或 Esc 都会取消未完成的整笔。M / L 仅在本编辑区焦点内有效，不拦截输入框。</p>
        </> : <div className="creative-selection-empty">{state.stale ? '旧画布已失效。不会把选区带到新照片。' : '没有已验证的真实画布，不显示占位图片。'}</div>}
      </div>
      <fieldset className="creative-selection-controls" disabled={!editable}><legend>本地选区草稿</legend>
        <div className="creative-selection-buttons" role="group" aria-label="选区工具">{(Object.keys(toolNames) as SelectionTool[]).map(value =>
          <button type="button" key={value} aria-pressed={tool === value} onClick={() => {abandon(); setTool(value);}}>{toolNames[value]}</button>)}</div>
        {tool !== 'brush' && <label>组合方式<select value={combine} onChange={event => setCombine(event.target.value as SelectionCombine)}>
          {(Object.keys(combineNames) as SelectionCombine[]).map(value => <option key={value} value={value}>{combineNames[value]}</option>)}</select></label>}
        {(tool === 'rectangle' || tool === 'ellipse') && <>
          <label>形状约束<select value={mode} onChange={event => {setMode(event.target.value as typeof mode); setShapeWidth(event.target.value === 'size' ? Math.min(200, proof?.canvas.width ?? 200) : 1); setShapeHeight(event.target.value === 'size' ? Math.min(200, proof?.canvas.height ?? 200) : 1);}}>
            <option value="free">自由</option><option value="ratio">固定比例</option><option value="size">固定源像素尺寸</option></select></label>
          {mode !== 'free' && <div className="creative-selection-dimensions"><label>{mode === 'ratio' ? '宽比' : '宽 px'}<input type="number" value={shapeWidth} min={mode === 'ratio' ? .001 : 1} step={mode === 'ratio' ? .1 : 1}
            onChange={event => setDimension(event.target.value, setShapeWidth)}/></label><label>{mode === 'ratio' ? '高比' : '高 px'}<input type="number" value={shapeHeight} min={mode === 'ratio' ? .001 : 1} step={mode === 'ratio' ? .1 : 1}
            onChange={event => setDimension(event.target.value, setShapeHeight)}/></label></div>}
          {mode === 'size' && <p className="creative-selection-hint">尺寸使用冻结创意画布的真实像素，非屏幕像素；点击定位。靠近边缘会平移完整形状，不缩小尺寸。</p>}
        </>}
        {tool === 'brush' && <>
          <label>笔刷模式<select value={brushMode} onChange={event => setBrushMode(event.target.value as typeof brushMode)}><option value="add">增加</option><option value="subtract">减去</option></select></label>
          <label>直径（源画布 px）<input type="number" value={diameter} min={1} max={262144} step={1} onChange={event => {const value = Number(event.target.value); if (Number.isFinite(value) && value >= 1 && value <= 262144) setDiameter(value);}}/></label>
          <label>硬度 {Math.round(hardness * 100)}%<input type="range" value={hardness} min={0} max={1} step={.01} onChange={event => setHardness(Number(event.target.value))}/></label>
          <label>不透明度 {Math.round(opacity * 100)}%<input type="range" value={opacity} min={0} max={1} step={.01} onChange={event => setOpacity(Number(event.target.value))}/></label>
        </>}
        <label>羽化半径 {recipe?.feather_radius ?? 0} px<input type="range" min={0} max={256} step={1} value={recipe?.feather_radius ?? 0} onChange={event => controller.feather(Number(event.target.value))}/></label>
        <p className="creative-selection-hint">羽化作用于合并后的整个选区。范围和覆盖率算法是本地实现，不宣称复刻专有算法。</p>
        <div className="creative-selection-buttons"><button type="button" onClick={() => controller.append({kind: 'invert'})}>反选</button>
          <button type="button" disabled={!recipe?.operations.length} onClick={() => controller.deselect()}>取消选区</button>
          <button type="button" disabled={!state.undo.length} onClick={() => controller.undo()}>撤销草稿</button><button type="button" disabled={!state.redo.length} onClick={() => controller.redo()}>重做草稿</button></div>
        <p className="creative-selection-hint">{recipe?.operations.length ?? 0} 个操作。草稿撤销与图层历史分离；“取消选区”不删除已有蒙版。</p>
        <label>现有图层蒙版<select value={state.mask_policy ?? ''} onChange={event => controller.policy((event.target.value || null) as SelectionMaskPolicy | null)}>
          {proof?.existing_mask_id ? <><option value="">请明确选择，不默认替换</option><option value="replace">替换现有蒙版</option><option value="union">并集：max(原蒙版, 新选区)</option>
            <option value="subtract">相减：max(原蒙版 − 新选区, 0)</option><option value="intersect">交集：min(原蒙版, 新选区)</option></> : <option value="create">创建新蒙版</option>}
        </select></label>
      </fieldset>
    </div>
    <div className="creative-selection-buttons"><button type="button" disabled={disabled || !controller.canPreview()} onClick={() => void controller.preview()}>生成真实前后图与蒙版</button>
      <button type="button" disabled={disabled || !!state.cancel_request || (!state.context && !state.request) || state.phase === 'applied'} onClick={() => {abandon(); void controller.cancel();}}>放弃本次草稿 / 请求取消原任务</button>
      {controller.unresolved() && <button type="button" disabled={state.checking || !controller.port.receipt} onClick={() => void controller.check()}>核对原操作结果</button>}</div>
    {controller.canDismissRetiredWorkspace() && <button type="button" onClick={() => controller.dismissRetiredWorkspace()}>已核对重开工程，关闭旧会话待核对状态</button>}
    {review && state.phase === 'review' && <section className="creative-selection-review" aria-label="真实完整前后图和蒙版审核">
      <h4>先审核真实合成结果，再应用蒙版</h4>
      <div className="creative-selection-review-grid">{(['before_composite', 'after_composite', 'before_mask', 'after_mask'] as SelectionImageRole[]).map(role =>
        <figure key={`${review.preview_token}:${role}`}><div className="creative-selection-image" style={{aspectRatio: `${review[role].width} / ${review[role].height}`}}>
          <PresentedImage image={review[role]} alt={imageNames[role]} onPresented={(width, height, visible) => controller.presented(role, review.preview_token, width, height, visible)}/>
        </div><figcaption>{imageNames[role]} · {review[role].width} × {review[role].height} 显示采样</figcaption></figure>)}</div>
      <p className="creative-selection-hint">蒙版为真实源栅格的覆盖率显示：白色保留，黑色隐藏，灰色部分保留。这里的 PNG 仅供复核，应用的是不可变的全分辨率数值蒙版，不将预览图回写成源资产。</p>
      <label className="creative-selection-confirm"><input type="checkbox" checked={state.reviewed} disabled={disabled || !controller.editable() || !SELECTION_REVIEW_IMAGES.every(role => state.images_presented[role])}
        onChange={event => controller.acknowledge(event.target.checked)}/>我已查看完整前后图与蒙版，确认按上方方式应用到当前选中的图片图层。</label>
    </section>}
    <footer className="creative-selection-footer"><button type="button" disabled={disabled || !controller.canApply()} onClick={() => void controller.apply()}>应用真实蒙版到图层历史</button>
      {state.refresh === 'failed' && <button type="button" onClick={() => void controller.refresh()}>仅重试宿主状态回读</button>}
      <a href={SELECTION_REFERENCE} target="_blank" rel="noreferrer">规则 / 自由选区参考</a>
      <p className="creative-selection-hint">仅当前来源的未锁定图片叶图层。组与不支持的能力明确不可用；应用前后不改动原照片文件。</p></footer>
  </section>;
}
