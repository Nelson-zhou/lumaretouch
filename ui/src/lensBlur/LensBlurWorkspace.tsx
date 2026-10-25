// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState, useSyncExternalStore, type PointerEvent} from 'react';
import {LENS_APERTURES, LENS_APERTURE_LABELS, LENS_LIMITS, lensReviewKey,
  type LensAperture, type LensPoint, type LensRecipe, type LensStroke} from './model';
import {lensDisplayToSource, lensImageUrl, paintLensDepth} from './imagery';
import type {LensBlurWorkflow} from './workflow';
import './lensBlur.css';

type PaintMode = 'focus' | 'clear' | 'blur';
const percentage = (value: number) => `${Math.round(value * 100)}%`;

/** Purely modular review surface; a mounted parent supplies the persistent workflow/host port. */
export function LensBlurWorkspace({workflow, onExit, disabled = false}: {
  workflow: LensBlurWorkflow; onExit: () => void; disabled?: boolean;
}) {
  const state = useSyncExternalStore(workflow.subscribe, workflow.snapshot, workflow.snapshot);
  const [mode, setMode] = useState<PaintMode>('focus'), [visualize, setVisualize] = useState(false);
  const [brush, setBrush] = useState({amount: 1, flow: .5, feather: .5, radius: .025});
  const [draft, setDraft] = useState<LensStroke | null>(null), [paintError, setPaintError] = useState('');
  const [focusCoordinates, setFocusCoordinates] = useState({x: .5, y: .5});
  const stroke = useRef<LensStroke | null>(null), pointer = useRef<number | null>(null);
  const drawingSurface = useRef<SVGSVGElement>(null), depthCanvas = useRef<HTMLCanvasElement>(null);
  const closedSession = useRef<string | null>(null);
  const context = state.context, recipe = state.recipe, source = context?.owner.source;
  const manualPlane = state.depth?.asset.provenance.kind === 'manual' && state.depth.asset.provenance.method === 'user_defined_plane';
  const locked = disabled || !workflow.editable() || state.capability.status !== 'available' || !state.source_presented || !state.depth || !recipe;
  const unresolved = workflow.unresolved();
  const contextIdentity = context ? `${context.session_id}:${context.owner.document_id}:${context.owner.document_epoch}:${context.owner.document_revision}:${context.depth?.token ?? ''}` : '';
  const dropStroke = () => {
    if (pointer.current !== null && drawingSurface.current?.hasPointerCapture(pointer.current)) drawingSurface.current.releasePointerCapture(pointer.current);
    pointer.current = null; stroke.current = null; setDraft(null);
  };
  useEffect(() => {dropStroke(); setPaintError(''); setMode(manualPlane ? 'blur' : 'focus'); setFocusCoordinates({x: .5, y: .5});}, [contextIdentity, manualPlane]);
  useEffect(() => () => workflow.releasePresentation(), [workflow]);
  useEffect(() => {
    if ((state.phase === 'applied' || state.phase === 'cancelled') && state.terminal_refresh === 'ready'
      && context && closedSession.current !== context.session_id) {
      closedSession.current = context.session_id; onExit();
    }
  }, [state.phase, state.terminal_refresh, context?.session_id, onExit]);
  useEffect(() => {if (locked) dropStroke();}, [locked]);
  useEffect(() => {
    if (visualize && state.depth && recipe && depthCanvas.current
      && !paintLensDepth(depthCanvas.current, state.depth, recipe.focus.near, recipe.focus.far)) setPaintError('景深图无法显示；不会以示意图替代。');
  }, [visualize, state.depth, recipe?.focus.near, recipe?.focus.far]);
  const edit = (patch: Partial<LensRecipe>) => {dropStroke(); if (recipe) workflow.edit({...recipe, ...patch});};
  const pointFromEvent = (event: PointerEvent<SVGSVGElement>): LensPoint | null => {
    if (!source) return null;
    const rect = event.currentTarget.getBoundingClientRect();
    return lensDisplayToSource(event.clientX, event.clientY, rect, source);
  };
  const start = (event: PointerEvent<SVGSVGElement>) => {
    if (locked || !event.isPrimary || event.button !== 0 || pointer.current !== null) return;
    const point = pointFromEvent(event);
    if (!point) return;
    event.preventDefault(); setPaintError('');
    if (mode === 'focus') {workflow.focusPoint(point); setFocusCoordinates(point); return;}
    if ((recipe?.refinements.length ?? 0) >= LENS_LIMITS.strokes) {setPaintError('已达到笔画上限，请撤销一笔；不会静默截断笔画。'); return;}
    const next: LensStroke = {id: crypto.randomUUID().replaceAll('-', ''), mode, ...brush, points: [point]};
    stroke.current = next; pointer.current = event.pointerId; setDraft(next);
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const move = (event: PointerEvent<SVGSVGElement>) => {
    const current = stroke.current;
    if (locked || !current || pointer.current !== event.pointerId) return;
    const point = pointFromEvent(event);
    if (!point) return;
    const last = current.points[current.points.length - 1];
    if (point.x === last.x && point.y === last.y) return;
    const count = (recipe?.refinements.reduce((sum, s) => sum + s.points.length, 0) ?? 0) + current.points.length;
    if (current.points.length >= LENS_LIMITS.pointsPerStroke || count >= LENS_LIMITS.points) {
      dropStroke(); setPaintError('本笔超过点数上限，整笔已取消；已有笔画保留，没有抽稀或截断。'); return;
    }
    const next = {...current, points: [...current.points, point]};
    stroke.current = next; setDraft(next);
  };
  const finish = (event: PointerEvent<SVGSVGElement>) => {
    if (pointer.current !== event.pointerId || !stroke.current) return;
    move(event);
    const value = stroke.current;
    dropStroke();
    if (value && !workflow.addStroke(value)) setPaintError('笔画来源或参数已失效，本笔未保存。');
  };
  const cancelPointer = (event: PointerEvent<SVGSVGElement>) => {if (pointer.current === event.pointerId) {dropStroke(); setPaintError('绘制被中断，本笔未保存。');}};
  const strokes = [...(recipe?.refinements ?? []), ...(draft ? [draft] : [])];
  const review = state.review, reviewKey = review ? lensReviewKey(review) : '';
  const canExit = !unresolved && state.terminal_refresh !== 'refreshing' && (state.phase === 'applied' || state.phase === 'cancelled' || !context);
  const setIntervalBound = (side: 'near' | 'far', value: number) => {
    if (!recipe) return;
    const near = side === 'near' ? Math.min(value, recipe.focus.far) : recipe.focus.near;
    const far = side === 'far' ? Math.max(value, recipe.focus.near) : recipe.focus.far;
    edit({focus: {mode: 'interval', near, far, point: null}});
  };
  return <section className="lensBlurWorkspace" role="dialog" aria-modal="true" aria-label="镜头虚化 · 当前照片景深与效果复核">
    <header className="lensBlurHeader"><div><h2>镜头虚化</h2><p>当前照片 · 相对景深 · 原创光斑核</p></div>
      {canExit ? <button type="button" onClick={onExit}>关闭</button>
        : <button type="button" disabled={disabled || unresolved || state.terminal_refresh === 'refreshing'} onClick={() => {dropStroke(); void workflow.cancel();}}>取消本次编辑</button>}
    </header>
    <p className="lensBlurBoundary">不代表真实镜头焦距、光圈值或专有算法等效。模型未就绪时不会下载模型，也不会用渐变或人物轮廓冒充景深。</p>
    <p className="lensBlurBoundary">确认后仅在当前项目中新建独立照片副本，不覆盖原文档或原片文件；写出图片文件需另行导出。</p>
    {context && !state.depth && <div className="lensBlurManual"><p>也可明确选择人工散焦：使用恒定编辑基准面，靠清晰/虚化笔画控制效果。这不是照片景深分析。</p>
      <button type="button" disabled={disabled || !workflow.manualPlaneAvailable()} onClick={() => void workflow.prepareManualPlane()}>人工散焦编辑（不做 AI 景深分析）</button></div>}
    {manualPlane && <p className="lensBlurBoundary">人工散焦模式：下方平面是你选择的恒定编辑基准，不反映照片远近。先调大虚化半径，再用橙色“虚化”笔画添加效果；青色“清晰”笔画保护区域。</p>}
    {state.capability.status !== 'available' && <p role="status">{state.capability.reason} 现有配方不会被删除；替换模块后须重新复核。</p>}
    <p className="lensBlurStatus" role={state.phase === 'unknown' || state.phase === 'failed' ? 'alert' : 'status'} aria-live="polite">{state.message}</p>
    {context && <div className="lensBlurProvenance"><span>{state.stale ? '原请求的旧来源' : '来源'} {context.owner.source.sha256.slice(0, 12)} · {source!.width} × {source!.height} · 已统一 EXIF 方向</span>
      {state.depth ? <span>{state.depth.asset.provenance.kind === 'manual' ? manualPlane ? '人工散焦恒定基准面，不是实测景深' : '手动深度输入，不是 AI 分析' : `已提供模型深度：${state.depth.asset.provenance.model_id}`}
        {' · '}{state.depth.asset.raster.width} × {state.depth.asset.raster.height} · {state.depth.asset.raster.sha256.slice(0, 12)}</span>
        : <span>{context.depth_status === 'missing-model' ? '缺少已验证的本地深度模型' : context.depth_status === 'pending' ? '等待实际景深分析' : '没有可用的当前照片景深'}</span>}
    </div>}
    <div className="lensBlurLayout">
      <div className="lensBlurCanvasColumn">
        {source && context && state.source_verified && !state.stale ? <>
          <div className="lensBlurSource" style={{aspectRatio: `${source.width} / ${source.height}`}}>
            <img key={`${contextIdentity}:${context.source_image.sha256}`} src={lensImageUrl(context.source_image)} alt="当前完整来源照片，未叠加本次镜头虚化"
              draggable={false} onLoad={e => workflow.sourcePresented(context.source_image.sha256, e.currentTarget.naturalWidth, e.currentTarget.naturalHeight, true)}
              onError={() => workflow.sourcePresented(context.source_image.sha256, 0, 0, false)}/>
            {visualize && state.depth && <canvas ref={depthCanvas} className="lensBlurDepth" role="img" aria-label={manualPlane ? '用户明确选择的人工散焦恒定基准面，不是照片景深' : '当前照片的实际相对景深栅格：浅黄近，深紫远；高亮为清晰区间'}/>}
            <svg ref={drawingSurface} className="lensBlurPaint" viewBox={`-.5 -.5 ${source.width} ${source.height}`} preserveAspectRatio="none"
              aria-label={mode === 'focus' ? '点击照片设置焦点，或使用下方坐标输入' : `${mode === 'clear' ? '清晰' : '虚化'}优化绘制区域`}
              onPointerDown={start} onPointerMove={move} onPointerUp={finish} onPointerCancel={cancelPointer}
              onLostPointerCapture={cancelPointer} onContextMenu={event => event.preventDefault()}>
              {strokes.map(s => <g key={s.id} opacity={.30 + s.amount * .35} fill={s.mode === 'clear' ? '#59ecd2' : '#ffae69'} stroke={s.mode === 'clear' ? '#59ecd2' : '#ffae69'}>
                {s.points.length === 1 ? <circle cx={s.points[0].x * (source.width - 1)} cy={s.points[0].y * (source.height - 1)} r={s.radius * Math.min(source.width, source.height)} stroke="none"/>
                  : <polyline points={s.points.map(p => `${p.x * (source.width - 1)},${p.y * (source.height - 1)}`).join(' ')} fill="none"
                    strokeWidth={2 * s.radius * Math.min(source.width, source.height)} strokeLinecap="round" strokeLinejoin="round"/>}
              </g>)}
              {recipe?.focus.point && <circle cx={recipe.focus.point.x * (source.width - 1)} cy={recipe.focus.point.y * (source.height - 1)}
                r={Math.min(source.width, source.height) * .014} stroke="white" strokeWidth={Math.min(source.width, source.height) * .003} fill="none"/>}
            </svg>
          </div>
          <p className="lensBlurCaption">完整来源图，不是虚化效果。彩色笔画只表示编辑范围，不模拟羽化或最终效果。</p>
        </> : <p className="lensBlurEmpty">等待校验成功的当前来源图。没有占位效果图。</p>}
        <label className="lensBlurToggle"><input type="checkbox" checked={visualize} disabled={!state.depth || state.stale} onChange={e => setVisualize(e.target.checked)}/>{manualPlane ? '显示人工编辑基准面（非景深）' : '显示真实景深数据'}</label>
        {visualize && state.depth && <p className="lensBlurLegend">{manualPlane ? '均匀色块只表示恒定的人工编辑基准，不表达照片远近。' : '浅黄：相对近景 0 → 深紫：相对远景 1。亮区是当前清晰区间；不是米数或置信度。'}</p>}
        {paintError && <p role="alert">{paintError}</p>}
      </div>
      <fieldset className="lensBlurControls" disabled={locked}>
        <legend>当前照片配方</legend>
        <label>光斑核<select value={recipe?.aperture ?? 'circular_disk'} onChange={e => edit({aperture: e.target.value as LensAperture})}>
          {LENS_APERTURES.map(value => <option key={value} value={value} disabled={!state.capability.kernels.includes(value)}>{LENS_APERTURE_LABELS[value]}</option>)}
        </select></label>
        <label>虚化半径 {recipe?.max_radius_px ?? 0} 源像素<input type="range" min="0" max="128" step=".5" value={recipe?.max_radius_px ?? 0}
          onChange={e => edit({max_radius_px: Number(e.target.value)})}/></label>
        <p>0 为中性，不等同于 f 值。效果必须在真实前后图中确认。</p>
        <label>焦点模式<select value={recipe?.focus.mode ?? 'interval'} onChange={e => {
          if (!recipe) return;
          if (e.target.value === 'subject' && state.depth?.asset.subject_focus) {
            const f = state.depth.asset.subject_focus; edit({focus: {mode: 'subject', near: f.near, far: f.far, point: null}});
          } else if (e.target.value === 'point') {setMode('focus'); workflow.focusPoint(focusCoordinates);}
          else edit({focus: {mode: 'interval', near: recipe.focus.near, far: recipe.focus.far, point: null}});
        }}><option value="interval">手动清晰区间</option><option value="point">点击照片设置焦点</option>
          <option value="subject" disabled={!state.depth?.asset.subject_focus}>已测量主体范围{!state.depth?.asset.subject_focus ? '（未提供）' : ''}</option></select></label>
        <label>近端 {percentage(recipe?.focus.near ?? 0)}<input type="range" min="0" max="1" step=".001" value={recipe?.focus.near ?? 0} onChange={e => setIntervalBound('near', Number(e.target.value))}/></label>
        <label>远端 {percentage(recipe?.focus.far ?? 1)}<input type="range" min="0" max="1" step=".001" value={recipe?.focus.far ?? 1} onChange={e => setIntervalBound('far', Number(e.target.value))}/></label>
        <div className="lensBlurCoordinates"><label>焦点 X<input type="number" min="0" max="1" step=".01" value={focusCoordinates.x} onChange={e => setFocusCoordinates({...focusCoordinates, x: Number(e.target.value)})}/></label>
          <label>焦点 Y<input type="number" min="0" max="1" step=".01" value={focusCoordinates.y} onChange={e => setFocusCoordinates({...focusCoordinates, y: Number(e.target.value)})}/></label>
          <button type="button" onClick={() => workflow.focusPoint(focusCoordinates)}>按坐标对焦</button></div>
        <label>景深过渡 {percentage(recipe?.depth_falloff ?? .2)}<input type="range" min=".001" max="1" step=".001" value={recipe?.depth_falloff ?? .2} onChange={e => edit({depth_falloff: Number(e.target.value)})}/></label>
        <label>遮挡容差 {percentage(recipe?.occlusion_tolerance ?? .02)}<input type="range" min="0" max="1" step=".001" value={recipe?.occlusion_tolerance ?? .02} onChange={e => edit({occlusion_tolerance: Number(e.target.value)})}/></label>
        <label>光斑旋转 {Math.round((recipe?.rotation_radians ?? 0) * 180 / Math.PI)}°<input type="range" min="-180" max="180" step="1" value={(recipe?.rotation_radians ?? 0) * 180 / Math.PI} onChange={e => edit({rotation_radians: Number(e.target.value) * Math.PI / 180})}/></label>
        <fieldset><legend>源图涂抹优化</legend>
          <div className="lensBlurModes">{(['focus', 'clear', 'blur'] as const).map(value => <button key={value} type="button" aria-pressed={mode === value}
            onClick={() => {dropStroke(); setMode(value);}}>{value === 'focus' ? '点选焦点' : value === 'clear' ? '清晰' : '虚化'}</button>)}</div>
          {(['amount', 'radius', 'flow', 'feather'] as const).map(name => <label key={name}>{({amount: '程度', radius: '大小（源图短边半径）', flow: '流量', feather: '羽化'})[name]} {percentage(brush[name])}
            <input type="range" min={name === 'radius' ? '.002' : '0'} max={name === 'radius' ? '.25' : '1'} step=".001" value={brush[name]}
              onChange={e => {dropStroke(); setBrush({...brush, [name]: Number(e.target.value)});}}/></label>)}
          <p>青色保清晰，橙色加虚化。笔画仅属于当前来源；0 半径时不会制造虚化。</p>
          <button type="button" disabled={!recipe?.refinements.length} onClick={() => edit({refinements: recipe!.refinements.slice(0, -1)})}>撤销最后一笔</button>
          <button type="button" disabled={!recipe?.refinements.length} onClick={() => edit({refinements: []})}>清空本次笔画</button>
        </fieldset>
      </fieldset>
    </div>
    <div className="lensBlurActions"><button type="button" disabled={locked || !workflow.renderingAvailable() || !!draft} onClick={() => void workflow.preview()}>生成真实前后对比</button>
      {unresolved && <button type="button" disabled={state.checking || ['applying', 'cancelling'].includes(state.phase)} onClick={() => void workflow.check()}>{state.checking ? '正在查询…' : '查询原请求，不重发'}</button>}
    </div>
    {review && <section className="lensBlurReview" aria-label="实际渲染的前后效果复核">
      <div className="lensBlurCompare">{(['before', 'after'] as const).map(side => <figure key={`${reviewKey}:${side}`}>
        <figcaption>{side === 'before' ? '原文档（实际渲染，不覆盖）' : '新副本候选（当前配方实际渲染）'}</figcaption>
        <img src={lensImageUrl(review[side])} alt={side === 'before' ? '原文档完整效果' : '镜头虚化新副本候选完整效果'}
          onLoad={e => workflow.presented(side, reviewKey, e.currentTarget.naturalWidth, e.currentTarget.naturalHeight, true)}
          onError={() => workflow.presented(side, reviewKey, 0, 0, false)}/>
      </figure>)}</div>
      {review.notes.length > 0 && <ul>{review.notes.map((note, index) => <li key={index}>{note}</li>)}</ul>}
      <label className="lensBlurToggle"><input type="checkbox" checked={state.acknowledged}
        disabled={disabled || !state.before_presented || !state.after_presented || state.phase !== 'review' || state.stale || !state.source_presented}
        onChange={e => workflow.acknowledge(e.target.checked)}/>我已查看这两张实际效果图，确认当前照片、焦点范围和涂抹效果，并保存为独立新副本</label>
      <button type="button" disabled={disabled || state.phase !== 'review' || !state.acknowledged || !workflow.renderingAvailable() || unresolved || !!draft}
        onClick={() => void workflow.apply()}>保存为新副本</button>
    </section>}
    {unresolved && <p className="lensBlurBoundary">请求 {state.request?.request_id} 尚未终结。不能宣称“未创建副本”、重复保存或撤销未知结果。切换照片也不会重发。</p>}
    {state.terminal_refresh === 'refreshing' && <p role="status">原请求结果已确认，正在刷新编辑器；不会再次保存。</p>}
    {state.terminal_refresh === 'failed' && <button type="button" disabled={disabled} onClick={() => void workflow.refreshTerminal()}>只重试刷新编辑器</button>}
    {(state.phase === 'applied' || state.phase === 'cancelled') && <button type="button" disabled={state.terminal_refresh === 'refreshing'} onClick={onExit}>返回编辑器</button>}
  </section>;
}
