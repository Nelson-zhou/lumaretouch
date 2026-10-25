// SPDX-License-Identifier: GPL-3.0-or-later
import {GLOW_OPERATION, GLOW_PROTOCOL, freezeGlow, glowKey, glowPresetRecipe, glowRequestFits, glowReviewKey,
  unavailableGlowCapability, validGlowCapability, validGlowContext, validGlowRecipe, validGlowReceipt, validGlowReview, validGlowWriteCommand,
  type GlowCapability, type GlowContext, type GlowMode, type GlowPreset, type GlowPreviewCommand, type GlowRecipe,
  type GlowReceipt, type GlowReview, type GlowWriteCommand, type LightGlowPort} from './model';
import {verifyGlowCoverage, verifyGlowPng} from './imagery';

export type GlowPhase = 'empty' | 'verifying' | 'editing' | 'previewing' | 'review' | 'applying' | 'cancelling' | 'pending' | 'unknown' | 'applied' | 'cancelled' | 'failed';
export interface GlowState {
  capability: GlowCapability; context: GlowContext | null; recipe: GlowRecipe | null; review: GlowReview | null;
  phase: GlowPhase; stale: boolean; source_verified: boolean; source_loaded: boolean;
  before_loaded: boolean; after_loaded: boolean; coverage_loaded: boolean; reviewed: boolean;
  undo: GlowRecipe[]; redo: GlowRecipe[]; request: GlowWriteCommand | null; checking: boolean;
  terminal_receipt: GlowReceipt | null; terminal_refresh: 'none' | 'refreshing' | 'ready' | 'failed' | 'not-configured'; message: string;
}
const empty = (): GlowState => ({capability: unavailableGlowCapability('请先获取当前完整修图结果。'), context: null, recipe: null,
  review: null, phase: 'empty', stale: false, source_verified: false, source_loaded: false, before_loaded: false,
  after_loaded: false, coverage_loaded: false, reviewed: false, undo: [], redo: [], request: null, checking: false,
  terminal_receipt: null, terminal_refresh: 'none', message: '尚未获取真实来源，不显示占位效果。'});
const reason = (error: unknown): string => error instanceof Error ? error.message : String(error);
const invalidateReview = () => ({review: null, before_loaded: false, after_loaded: false, coverage_loaded: false, reviewed: false});
export function glowBounded<T>(promise: Promise<T>, timeout: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {timer = setTimeout(() => reject(Error('原请求尚未确认；只能查询，不会重发。')), timeout);})])
    .finally(() => {if (timer !== undefined) clearTimeout(timer);});
}

/** Instantiate above the modal. Source switching and hiding never discard an unresolved write. */
export class LightGlowController {
  private state: GlowState = freezeGlow(empty());
  private generation = 0;
  private readonly listeners = new Set<() => void>();
  private readonly drafts: Partial<Record<GlowMode, GlowRecipe>> = {};
  private terminal: {receipt: GlowReceipt; command: GlowWriteCommand} | null = null;
  private cancellingReads = false;
  private readonly id: () => string;
  private readonly timeout: number;
  constructor(readonly port: LightGlowPort, private readonly options: {
    requestId?: () => string; timeoutMs?: number;
    onTerminal?: (receipt: GlowReceipt, command: GlowWriteCommand) => Promise<void> | void;
  } = {}) {
    this.id = options.requestId ?? (() => crypto.randomUUID());
    this.timeout = options.timeoutMs ?? 145000;
  }
  snapshot = (): GlowState => this.state;
  subscribe = (listener: () => void): (() => void) => {this.listeners.add(listener); return () => {this.listeners.delete(listener);};};
  private publish(patch: Partial<GlowState>): void {this.state = freezeGlow({...this.state, ...patch}); this.listeners.forEach(listener => listener());}
  unresolved = (): boolean => this.state.request !== null;
  canDetach = (): boolean => !this.unresolved() && !this.port.pendingReads() && this.state.terminal_refresh !== 'refreshing'
    && !['verifying', 'previewing', 'applying', 'cancelling'].includes(this.state.phase);
  editable = (): boolean => this.port.protocol === GLOW_PROTOCOL && !!this.state.recipe && !!this.state.context
    && this.state.capability.status === 'available' && this.state.source_verified && this.state.source_loaded && !this.state.stale
    && !this.unresolved() && !this.port.pendingReads() && this.state.terminal_refresh !== 'refreshing'
    && !['verifying', 'previewing', 'applying', 'cancelling', 'pending', 'unknown', 'applied', 'cancelled'].includes(this.state.phase);
  canPreview = (): boolean => this.editable() && !!this.state.recipe && this.state.capability.modes.includes(this.state.recipe.mode);
  canApply = (): boolean => this.canPreview() && this.state.phase === 'review' && !!this.state.review && this.state.reviewed
    && this.state.before_loaded && this.state.after_loaded && this.state.coverage_loaded
    && glowKey(this.state.recipe) === glowKey(this.state.review.recipe);

  setCapability(value: unknown): void {
    const capability = validGlowCapability(value) ? value : unavailableGlowCapability('发光模块能力协议无效。');
    if (glowKey(capability) === glowKey(this.state.capability)) return;
    ++this.generation;
    this.publish({capability, ...invalidateReview(), ...(this.state.phase === 'previewing' ? {phase: 'editing' as const} : {}),
      ...(this.state.phase === 'verifying' ? {phase: 'editing' as const, stale: true, source_verified: false, source_loaded: false} : {}),
      message: capability.status === 'available' ? '模块能力已确认；已有配方保留，请重新生成实际效果。' : `${capability.reason ?? '模块不可用。'} 已有配方与未决请求保留。`});
  }
  markStale(message = '当前照片、加载会话或修订已变化；旧来源不能继续预览或保存。'): void {
    ++this.generation;
    this.publish({stale: true, source_loaded: false, ...invalidateReview(),
      ...(this.state.phase === 'previewing' || this.state.phase === 'verifying' ? {phase: 'editing' as const} : {}),
      message: `${message}${this.unresolved() ? ' 仍保留原修改请求，必须查询其真实结果。' : ''}`});
  }
  async setContext(value: unknown): Promise<void> {
    if (this.unresolved() || this.state.terminal_refresh === 'refreshing') {this.markStale(); return;}
    if (!validGlowContext(value)) {this.markStale('来源协议或完整图像范围无效。'); return;}
    if (this.state.context && glowKey(value) === glowKey(this.state.context) && !this.state.stale) return;
    const context = freezeGlow(value), generation = ++this.generation;
    this.terminal = null;
    for (const mode of Object.keys(this.drafts) as GlowMode[]) delete this.drafts[mode];
    this.publish({...empty(), capability: context.capability, context, phase: 'verifying', message: '正在核对完整当前来源的图像内容与归属；不修改历史。'});
    const verified = await verifyGlowPng(context.before);
    if (generation !== this.generation) return;
    if (!verified) {this.publish({phase: 'failed', message: '完整来源 PNG 的结构或摘要校验失败，编辑已锁定。'}); return;}
    // Default black mist is a local choice, not a claim about the vendor's initially selected mode.
    const mode = context.capability.modes.includes('black_mist') ? 'black_mist' : context.capability.modes[0];
    const recipe = mode ? glowPresetRecipe(mode) : null;
    if (recipe) this.drafts[recipe.mode] = recipe;
    this.publish({phase: 'editing', source_verified: true, recipe, message: context.message || '完整来源已校验。请选择模式与程度，再生成真实效果。'});
  }
  sourceLoaded(sha256: string, width: number, height: number, loaded: boolean): void {
    const source = this.state.context?.before;
    if (!source || !this.state.source_verified || this.state.stale || source.sha256 !== sha256) return;
    const ready = loaded && width === source.width && height === source.height;
    if (ready === this.state.source_loaded) return;
    this.publish({source_loaded: ready, reviewed: false, ...(ready ? {} : {message: '完整来源没有按声明尺寸解码，编辑与应用已锁定。'})});
  }
  /** A browser load is not a claim that the user saw or approved the image. */
  presented(side: 'before' | 'after' | 'coverage', key: string, width: number, height: number, loaded: boolean): void {
    const review = this.state.review;
    if (!review || this.state.phase !== 'review' || this.state.stale || glowReviewKey(review) !== key) return;
    const image = review[side], ready = loaded && width === image.width && height === image.height;
    const property = side === 'before' ? 'before_loaded' : side === 'after' ? 'after_loaded' : 'coverage_loaded';
    if (this.state[property] === ready) return;
    this.publish({[property]: ready, reviewed: false, ...(ready ? {} : {message: '前后图或真实作用范围没有正确解码，应用已锁定。'})});
  }
  releasePresentation(): void {this.publish({source_loaded: false, before_loaded: false, after_loaded: false, coverage_loaded: false, reviewed: false});}
  acknowledge(value: boolean): void {
    this.publish({reviewed: value && this.canPreview() && this.state.phase === 'review' && !!this.state.review
      && this.state.before_loaded && this.state.after_loaded && this.state.coverage_loaded && glowKey(this.state.recipe) === glowKey(this.state.review.recipe)});
  }
  private replaceRecipe(recipe: GlowRecipe, history: 'push' | 'undo' | 'redo'): boolean {
    if (!this.editable() || !validGlowRecipe(recipe) || !this.state.capability.modes.includes(recipe.mode) || !this.state.recipe) return false;
    if (glowKey(recipe) === glowKey(this.state.recipe)) return true;
    ++this.generation; this.terminal = null; this.drafts[recipe.mode] = freezeGlow(recipe);
    const undo = history === 'undo' ? this.state.undo.slice(0, -1) : [...this.state.undo, this.state.recipe].slice(-128);
    const redo = history === 'undo' ? [...this.state.redo, this.state.recipe].slice(-128) : history === 'redo' ? this.state.redo.slice(0, -1) : [];
    this.publish({recipe, undo, redo, phase: 'editing', terminal_receipt: null, terminal_refresh: 'none', ...invalidateReview(),
      message: '配方已更改；旧对比与确认已作废。原照片和历史未写入，请重新生成效果。'});
    return true;
  }
  edit(recipe: GlowRecipe): boolean {return !!this.state.recipe && recipe.mode === this.state.recipe.mode && this.replaceRecipe(recipe, 'push');}
  selectMode(mode: GlowMode): boolean {
    const recipe = this.drafts[mode] ?? glowPresetRecipe(mode);
    return !!recipe && this.replaceRecipe(recipe, 'push');
  }
  selectPreset(preset: GlowPreset): boolean {
    const recipe = this.state.recipe && glowPresetRecipe(this.state.recipe.mode, preset);
    return !!recipe && this.replaceRecipe(recipe, 'push');
  }
  undo(): boolean {const recipe = this.state.undo.at(-1); return !!recipe && this.replaceRecipe(recipe, 'undo');}
  redo(): boolean {const recipe = this.state.redo.at(-1); return !!recipe && this.replaceRecipe(recipe, 'redo');}
  async preview(): Promise<void> {
    if (!this.canPreview() || !this.state.context || !this.state.recipe) return;
    const context = this.state.context, generation = ++this.generation;
    const command: GlowPreviewCommand = freezeGlow({version: 1, operation_id: GLOW_OPERATION, action: 'preview', request_id: this.id(),
      session_id: context.session_id, owner: context.owner, recipe: this.state.recipe});
    if (!glowRequestFits(command)) {this.publish({message: '配方请求超过边界，未发送。'}); return;}
    this.publish({phase: 'previewing', ...invalidateReview(), message: '正在计算真实完整前后图与像素变化范围；没有写入文档。'});
    try {
      const result = await glowBounded(this.port.preview(command), this.timeout);
      if (generation !== this.generation) return;
      if (!validGlowReview(result, command, context)) throw Error('效果回执与保留来源、配方或范围不匹配。');
      const review = freezeGlow(result);
      if (!(await Promise.all([verifyGlowPng(review.before), verifyGlowPng(review.after), verifyGlowCoverage(review.coverage)])).every(Boolean)) throw Error('真实效果图或作用范围图的内容校验失败。');
      if (generation !== this.generation) return;
      this.publish({phase: 'review', review, message: review.no_change ? '此配方没有改变来源像素。应用仍会创建独立新图，不会写入原图。'
        : '请查看完整前后图，并可开启绿色实际变化范围；确认后才可新建独立图片。'});
    } catch (error) {if (generation === this.generation) this.publish({phase: 'failed', ...invalidateReview(), message: reason(error)});}
  }
  private async receive(value: unknown, command: GlowWriteCommand): Promise<void> {
    if (this.state.request?.request_id !== command.request_id) return;
    if (!validGlowReceipt(value, command)) {
      this.publish({phase: 'unknown', checking: false, reviewed: false, message: '修改回执无效或缺失。结果未知，只能查询原请求，不能重发或假装取消。'}); return;
    }
    if (value.phase !== 'done') {this.publish({phase: value.phase, checking: false, reviewed: false, message: value.message}); return;}
    const phase = value.outcome === 'applied' ? 'applied' : value.outcome === 'cancelled' ? 'cancelled' : 'failed';
    this.terminal = freezeGlow({receipt: value, command});
    this.publish({phase, request: null, checking: false, terminal_receipt: value, terminal_refresh: 'none', ...invalidateReview(),
      message: value.message || (phase === 'applied' ? '独立新图已确认创建，原照片历史未覆盖。' : phase === 'cancelled' ? '会话已确认取消，没有创建新图。' : '原请求已明确拒绝。')});
    await this.refreshTerminal();
  }
  private async send(command: GlowWriteCommand): Promise<void> {
    if (this.unresolved() || this.port.protocol !== GLOW_PROTOCOL || !validGlowWriteCommand(command)) return;
    ++this.generation; this.terminal = null;
    const retained = freezeGlow(command);
    this.publish({phase: command.action === 'apply' ? 'applying' : 'cancelling', request: retained, reviewed: false,
      terminal_receipt: null, terminal_refresh: 'none', message: '已保留原修改请求身份，等待确定回执；不会因超时重新提交。'});
    try {await this.receive(await glowBounded(this.port.submit(retained), this.timeout), retained);}
    catch (error) {if (this.state.request?.request_id === retained.request_id) this.publish({phase: 'unknown', checking: false, message: `结果未知：${reason(error)} 请查询原请求。`});}
  }
  async apply(): Promise<void> {
    if (!this.canApply() || !this.state.review) return;
    const review = this.state.review;
    await this.send({version: 1, operation_id: GLOW_OPERATION, action: 'apply', request_id: this.id(), session_id: review.session_id,
      owner: review.owner, token: review.token, recipe_sha256: review.recipe_sha256, result_source_sha256: review.result_source_sha256,
      coverage_sha256: review.coverage_sha256, before_sha256: review.before.sha256, after_sha256: review.after.sha256,
      coverage_image_sha256: review.coverage.sha256, reviewed: true, return_mode: 'new_image'});
  }
  async cancel(): Promise<void> {
    if (this.cancellingReads || this.unresolved() || !this.state.context || this.state.terminal_refresh === 'refreshing' || ['applied', 'cancelled'].includes(this.state.phase)) return;
    const context = this.state.context;
    // The session cancellation owns its exact outcome; read cancellation acceptance is not completion.
    ++this.generation; this.cancellingReads = true;
    this.publish({phase: 'cancelling', reviewed: false, message: '正在请求停止原读取；等待会话取消回执，尚不能确认已退出。'});
    try {
      try {await glowBounded(this.port.cancelReads(), 10000);} catch { /* Submit exact session cancellation; never claim read unwind. */ }
      await this.send({version: 1, operation_id: GLOW_OPERATION, action: 'cancel', request_id: this.id(), session_id: context.session_id, owner: context.owner, token: null});
    } finally {this.cancellingReads = false;}
  }
  async check(explicit = true): Promise<void> {
    if (!this.state.request || this.state.checking || ['applying', 'cancelling'].includes(this.state.phase)) return;
    const command = this.state.request;
    if (explicit) this.port.requestReconciliation?.(command);
    this.publish({checking: true});
    try {await this.receive(await glowBounded(this.port.receipt(command), this.timeout), command);}
    catch (error) {if (this.state.request?.request_id === command.request_id) this.publish({phase: 'unknown', checking: false, message: `原请求仍未确认：${reason(error)}`});}
  }
  async refreshTerminal(): Promise<void> {
    const terminal = this.terminal;
    if (!terminal || !['none', 'failed'].includes(this.state.terminal_refresh)) return;
    if (!this.options.onTerminal) {this.publish({terminal_refresh: 'not-configured', message: `${this.state.message} 尚未配置编辑器刷新；不要重复应用。`}); return;}
    this.publish({terminal_refresh: 'refreshing'});
    try {
      await glowBounded(Promise.resolve(this.options.onTerminal(terminal.receipt, terminal.command)), this.timeout);
      if (this.terminal === terminal) this.publish({terminal_refresh: 'ready'});
    } catch (error) {if (this.terminal === terminal) this.publish({terminal_refresh: 'failed', message: `已有确定回执，但编辑器刷新未完成：${reason(error)}。只能重试刷新，不会重复应用。`});}
  }
}
