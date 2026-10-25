// SPDX-License-Identifier: GPL-3.0-or-later
import {initialLensRecipe, lensKey, lensReviewKey, lensRequestFits, validLensContext, validLensRecipe, validLensReview, validLensReceipt, validLensWriteCommand, validLensCapability, sameLensOwner, LENS_OPERATION, LENS_PROTOCOL,
  type LensBlurPort, type LensContext, type LensPoint, type LensPreviewCommand, type LensRecipe, type LensReview,
  type LensStroke, type LensWriteCommand, type LensReceipt, type LensCapability, type LensManualPlaneCommand} from './model';
import {decodeLensDepth, sampleLensDepth, verifyLensPng, type DecodedLensDepth} from './imagery';

export type LensPhase = 'empty' | 'loading' | 'editing' | 'previewing' | 'review' | 'applying' | 'cancelling' | 'pending' | 'unknown' | 'applied' | 'cancelled' | 'failed';
export interface LensState {
  capability: LensCapability;
  phase: LensPhase; context: LensContext | null; depth: DecodedLensDepth | null; recipe: LensRecipe | null;
  review: LensReview | null; source_verified: boolean; source_presented: boolean;
  before_presented: boolean; after_presented: boolean; acknowledged: boolean;
  stale: boolean; request: LensWriteCommand | null; checking: boolean; message: string;
  terminal_receipt: LensReceipt | null; terminal_refresh: 'none' | 'refreshing' | 'ready' | 'failed' | 'not-configured';
}
const empty = (): LensState => ({capability: {version: 1, operation_id: LENS_OPERATION, status: 'unavailable', kernels: [], reason: '尚未取得镜头虚化模块能力。'}, phase: 'empty', context: null, depth: null, recipe: null, review: null,
  source_verified: false, source_presented: false, before_presented: false, after_presented: false,
  acknowledged: false, stale: false, request: null, checking: false, message: '', terminal_receipt: null, terminal_refresh: 'none'});
const errorText = (error: unknown) => error instanceof Error ? error.message : '操作未完成。';
const contextKey = (v: LensContext) => lensKey([v.session_id, v.owner, v.source_image.sha256,
  v.depth_status, v.depth?.token, v.depth?.raster.sha256, v.depth?.provenance, v.depth?.subject_focus]);
function bounded<T>(promise: Promise<T>, timeout: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {timer = setTimeout(() => reject(Error('等待超时；已发送的修改不会重发。')), timeout);})])
    .finally(() => {if (timer !== undefined) clearTimeout(timer);});
}

/** Host-owned lifetime. Unmounting a panel MUST NOT destroy the original write receipt. */
export function createLensBlurWorkflow(port: LensBlurPort, options: {
  requestId?: () => string; timeoutMs?: number;
  /** Read-only authoritative refresh. For applied receipts, refresh result_document_id, not owner.document_id. */
  onTerminal?: (receipt: LensReceipt, command: LensWriteCommand) => Promise<void> | void;
} = {}) {
  let state = empty(), readGeneration = 0;
  let terminal: {receipt: LensReceipt; command: LensWriteCommand} | null = null;
  const listeners = new Set<() => void>();
  const id = options.requestId ?? (() => crypto.randomUUID().replaceAll('-', ''));
  const timeout = options.timeoutMs ?? 20000;
  const publish = (patch: Partial<LensState>) => {state = {...state, ...patch}; listeners.forEach(listener => listener());};
  const unresolved = () => state.request !== null && ['applying', 'cancelling', 'pending', 'unknown'].includes(state.phase);
  const editable = () => !unresolved() && state.terminal_refresh !== 'refreshing' && !state.stale && !['loading', 'previewing', 'applied', 'cancelled'].includes(state.phase);
  const renderingAvailable = () => port.protocol === LENS_PROTOCOL && state.capability.status === 'available' && !!state.recipe && state.capability.kernels.includes(state.recipe.aperture);
  const manualPlaneAvailable = () => port.protocol === LENS_PROTOCOL && !!port.prepareManualPlane && state.capability.status === 'available'
    && editable() && !!state.context && !state.depth && state.source_presented;
  const invalidate = () => ({review: null, acknowledged: false, before_presented: false, after_presented: false});
  function setCapability(value: unknown): void {
    const capability: LensCapability = validLensCapability(value) ? structuredClone(value)
      : {version: 1, operation_id: LENS_OPERATION, status: 'unavailable', kernels: [], reason: '模块能力协议无效。'};
    if (lensKey(capability) === lensKey(state.capability)) return;
    if (state.phase === 'previewing') ++readGeneration;
    // Disabling/replacing a module invalidates review only; it never deletes the recipe or an outstanding write.
    publish({capability, ...invalidate(), ...(state.phase === 'previewing' ? {phase: 'editing' as const} : {}),
      message: capability.status === 'available' ? '模块能力已更新，请重新生成效果。' : `${capability.reason} 已保存的配方不会被删除。`});
  }
  async function setContext(value: unknown): Promise<void> {
    // Refreshing the editor for a newly created copy must not erase its terminal receipt before exit.
    if (state.terminal_refresh === 'refreshing') return;
    if (!validLensContext(value)) {
      ++readGeneration;
      if (!unresolved()) terminal = null;
      publish(unresolved() ? {stale: true, ...invalidate(), source_presented: false, message: '当前来源协议无效；仍须查询原修改结果。'}
        : {...empty(), capability: state.capability, phase: 'failed', message: '当前照片、景深或来源协议无效；没有可编辑的来源。'});
      return;
    }
    // A terminal session exits; a host refresh must not silently turn it into a new edit before the UI observes it.
    if (state.context?.session_id === value.session_id && ['applied', 'cancelled'].includes(state.phase)) return;
    if (state.context && contextKey(value) === contextKey(state.context) && !state.stale) return;
    if (unresolved()) {
      ++readGeneration;
      publish({stale: true, ...invalidate(), source_presented: false, message: '照片或景深已变化；仍保留上一请求，只查询其回执，不重发。'});
      return;
    }
    const generation = ++readGeneration, context = structuredClone(value);
    terminal = null;
    publish({...empty(), capability: state.capability, phase: 'loading', context, message: '正在核对当前照片和真实景深数据…'});
    try {
      const [sourceOK, depth] = await Promise.all([verifyLensPng(context.source_image), context.depth ? decodeLensDepth(context.depth) : Promise.resolve(null)]);
      if (generation !== readGeneration) return;
      if (!sourceOK) throw Error('当前来源图校验失败，不能绘制选区或确认效果。');
      publish({phase: 'editing', source_verified: true, depth, recipe: depth ? initialLensRecipe(depth.asset) : null,
        message: context.message || (depth ? '当前照片已核对。点选焦点或调整清晰区间，再生成真实前后对比。' : '没有当前照片的可用景深。不会自动下载模型或生成占位景深。')});
    } catch (error) {if (generation === readGeneration) publish({phase: 'failed', source_verified: false, depth: null, recipe: null, message: errorText(error)});}
  }
  function sourcePresented(sha256: string, width: number, height: number, loaded: boolean): void {
    const image = state.context?.source_image;
    if (!image || image.sha256 !== sha256 || state.stale || !state.source_verified) return;
    const ready = loaded && width === image.width && height === image.height;
    if (state.source_presented !== ready) publish({source_presented: ready, acknowledged: false,
      ...(ready ? {} : {message: '来源图没有按声明尺寸成功显示，编辑与保存新副本已锁定。'})});
  }
  function releasePresentation(): void {
    // A panel disappearing is not a cancel and does not discard any in-flight request.
    publish({source_presented: false, before_presented: false, after_presented: false, acknowledged: false});
  }
  async function prepareManualPlane(): Promise<void> {
    if (!manualPlaneAvailable() || !port.prepareManualPlane || !state.context) return;
    const generation = ++readGeneration, context = state.context;
    const command: LensManualPlaneCommand = {version: LENS_PROTOCOL, action: 'prepare_manual_plane', request_id: id(), session_id: context.session_id,
      owner: structuredClone(context.owner), depth_value: .5, acknowledged_manual: true};
    publish({phase: 'loading', ...invalidate(), message: '正在准备你选择的人工散焦基准面，不进行 AI 景深分析；尚未修改文档。'});
    try {
      const result = await bounded(port.prepareManualPlane(command), timeout);
      if (generation !== readGeneration) return;
      if (!validLensContext(result) || result.session_id !== command.session_id || !sameLensOwner(result.owner, command.owner)
        || result.source_image.sha256 !== context.source_image.sha256 || !result.depth
        || result.depth.provenance.kind !== 'manual' || result.depth.provenance.method !== 'user_defined_plane'
        || result.depth.provenance.depth_value !== command.depth_value || result.depth.provenance.acknowledgement_id !== command.request_id)
        throw Error('人工散焦基准面未与本次明确选择和当前来源对应。');
      await setContext(result);
    } catch (error) {if (generation === readGeneration) publish({phase: 'failed', message: errorText(error)});}
  }
  function edit(value: LensRecipe): boolean {
    if (!editable() || state.capability.status !== 'available' || !state.depth || !state.source_presented || !validLensRecipe(value, state.depth.asset)) return false;
    ++readGeneration;
    terminal = null;
    publish({phase: 'editing', recipe: structuredClone(value), terminal_receipt: null, terminal_refresh: 'none', ...invalidate(), message: '参数已更改，之前的对比确认已作废。请重新生成效果。'});
    return true;
  }
  function focusPoint(point: LensPoint): boolean {
    if (!state.recipe || !state.depth) return false;
    const depth = sampleLensDepth(state.depth, point), half = (state.recipe.focus.far - state.recipe.focus.near) / 2;
    // The initial all-depth interval is neutral; first click narrows to an explicit 0.10 interval.
    const radius = half >= .5 ? .05 : half;
    return edit({...state.recipe, focus: {mode: 'point', point: {...point}, near: Math.max(0, depth - radius), far: Math.min(1, depth + radius)}});
  }
  function addStroke(stroke: LensStroke): boolean {
    return !!state.recipe && edit({...state.recipe, refinements: [...state.recipe.refinements, stroke]});
  }
  async function preview(): Promise<void> {
    if (!editable() || !renderingAvailable() || !state.context || !state.source_presented || !state.depth || !state.recipe
      || !validLensRecipe(state.recipe, state.depth.asset)) return;
    const generation = ++readGeneration;
    const command: LensPreviewCommand = {version: LENS_PROTOCOL, action: 'preview', request_id: id(), session_id: state.context.session_id,
      owner: structuredClone(state.context.owner), recipe: structuredClone(state.recipe)};
    if (!lensRequestFits(command)) {publish({phase: 'failed', ...invalidate(), message: '完整请求超过大小上限，未发送；请减少笔画。'}); return;}
    publish({phase: 'previewing', ...invalidate(), message: '正在请求当前照片的真实前后效果；尚未修改文档。'});
    try {
      const result = await bounded(port.preview(command), timeout);
      if (generation !== readGeneration) return;
      if (!validLensReview(result, command)) throw Error('前后对比与当前来源、景深或配方不匹配。');
      const review = structuredClone(result);
      if (!(await Promise.all([verifyLensPng(review.before), verifyLensPng(review.after)])).every(Boolean)) throw Error('前后对比图的内容或结构校验失败。');
      if (generation !== readGeneration) return;
      publish({phase: 'review', review, message: '请查看两张实际效果图，再确认保存为独立新副本；原文档和原片文件不会被覆盖。'});
    } catch (error) {if (generation === readGeneration) publish({phase: 'failed', ...invalidate(), message: errorText(error)});}
  }
  function presented(side: 'before' | 'after', key: string, width: number, height: number, loaded: boolean): void {
    if (state.phase !== 'review' || !state.review || lensReviewKey(state.review) !== key || state.stale) return;
    const image = state.review[side], ready = loaded && width === image.width && height === image.height;
    publish({[side === 'before' ? 'before_presented' : 'after_presented']: ready, acknowledged: false,
      ...(ready ? {} : {message: '效果图显示失败，确认和保存新副本已锁定。'})});
  }
  function acknowledge(value: boolean): void {
    publish({acknowledged: value && state.phase === 'review' && !!state.review && state.before_presented && state.after_presented
      && state.source_presented && !state.stale && !!state.recipe && lensKey(state.recipe) === lensKey(state.review.recipe)});
  }
  async function refreshTerminal(): Promise<void> {
    if (!terminal || !['none', 'failed'].includes(state.terminal_refresh)) return;
    if (!options.onTerminal) {
      publish({terminal_refresh: 'not-configured', message: `${state.message} 尚未配置编辑器刷新，请返回编辑器核对；不会重复提交。`});
      return;
    }
    const captured = terminal;
    publish({terminal_refresh: 'refreshing'});
    try {
      await bounded(Promise.resolve(options.onTerminal(structuredClone(captured.receipt), structuredClone(captured.command))), timeout);
      if (terminal === captured) publish({terminal_refresh: 'ready'});
    } catch {
      if (terminal === captured) publish({terminal_refresh: 'failed', message: '原请求已收到确定回执，但编辑器刷新未完成。可只重试刷新；不会重新保存或取消。'});
    }
  }
  async function receive(result: unknown, command: LensWriteCommand): Promise<void> {
    if (state.request?.request_id !== command.request_id) return;
    if (!validLensReceipt(result, command)) {
      publish({phase: 'unknown', checking: false, acknowledged: false, message: '原请求回执缺失、无效或不匹配。结果未知，禁止重新提交或假装取消。'});
      return;
    }
    if (result.phase !== 'done') {
      publish({phase: result.phase, checking: false, acknowledged: false,
        message: result.message || '原操作尚未终结；只能查询同一个请求。'});
      return;
    }
    const phase = result.outcome === 'applied' ? 'applied' : result.outcome === 'cancelled' ? 'cancelled' : 'failed';
    terminal = {receipt: structuredClone(result), command: structuredClone(command)};
    publish({phase, checking: false, request: null, terminal_receipt: structuredClone(result), terminal_refresh: 'none', ...invalidate(), message: result.message ||
      (phase === 'applied' ? '独立新副本已创建，原文档和原片文件未覆盖。' : phase === 'cancelled' ? '已确认取消，没有创建新副本。' : '原操作已明确拒绝，未执行。')});
    await refreshTerminal();
  }
  async function send(command: LensWriteCommand): Promise<void> {
    if (port.protocol !== LENS_PROTOCOL || !validLensWriteCommand(command)) {
      publish({phase: 'failed', message: '新副本请求协议无效，未发送。'}); return;
    }
    ++readGeneration;
    terminal = null;
    publish({phase: command.action === 'apply' ? 'applying' : 'cancelling', request: command, acknowledged: false,
      terminal_receipt: null, terminal_refresh: 'none',
      message: command.action === 'apply' ? '正在保存一次独立新副本，等待真实新文档回执；不覆盖原片…' : '正在取消本次编辑，等待确认…'});
    try {await receive(await bounded(port.submit(command), timeout), command);} catch (error) {
      if (state.request?.request_id === command.request_id) publish({phase: 'unknown', checking: false,
        message: `原请求结果未知：${errorText(error)} 仅可查询原请求，不重发。`});
    }
  }
  async function apply(): Promise<void> {
    if (unresolved() || !renderingAvailable() || state.phase !== 'review' || state.stale || !state.context || !state.review || !state.recipe
      || !state.depth || !validLensRecipe(state.recipe, state.depth.asset) || !state.acknowledged
      || !state.source_presented || !state.before_presented || !state.after_presented
      || lensKey(state.recipe) !== lensKey(state.review.recipe)) return;
    const r = state.review;
    await send({version: LENS_PROTOCOL, action: 'apply', request_id: id(), session_id: r.session_id, owner: structuredClone(r.owner),
      token: r.token, recipe_sha256: r.recipe_sha256, before_sha256: r.before.sha256, after_sha256: r.after.sha256, reviewed: true,
      return_mode: 'new_image', result_source_sha256: r.result_source_sha256});
  }
  async function cancel(): Promise<void> {
    if (unresolved() || state.terminal_refresh === 'refreshing' || !state.context || ['applied', 'cancelled'].includes(state.phase)) return;
    await send({version: LENS_PROTOCOL, action: 'cancel', request_id: id(), session_id: state.context.session_id,
      owner: structuredClone(state.context.owner), token: state.review?.token ?? null});
  }
  async function check(): Promise<void> {
    if (!unresolved() || state.checking || !state.request || ['applying', 'cancelling'].includes(state.phase)) return;
    const command = state.request;
    publish({checking: true, message: '正在查询原请求，不会重新应用或取消…'});
    try {await receive(await bounded(port.receipt(command), timeout), command);} catch (error) {
      if (state.request?.request_id === command.request_id) publish({phase: 'unknown', checking: false, message: `原请求仍待确认：${errorText(error)}`});
    }
  }
  return {snapshot: () => state, subscribe: (listener: () => void) => {listeners.add(listener); return () => {listeners.delete(listener);};},
    setContext, setCapability, sourcePresented, releasePresentation, prepareManualPlane, edit, focusPoint, addStroke, preview, presented, acknowledge, apply, cancel, check, refreshTerminal,
    unresolved, editable, renderingAvailable, manualPlaneAvailable};
}
export type LensBlurWorkflow = ReturnType<typeof createLensBlurWorkflow>;
