// SPDX-License-Identifier: GPL-3.0-or-later
/** App integration only. AUTHORED / UNRUN; mounting does not acquire, render or write. */
import {useLayoutEffect, useRef, useState} from 'react';
import {settleCurveEdit} from '../curveEditBarrier';
import {glowBounded, type LightGlowController} from './controller';
import {glowKey, sameGlowOwner, type GlowContext, type GlowPreviewCommand, type GlowWriteCommand} from './model';
import {createLightGlowNativePort, type LightGlowNativePort} from './nativePort';
import {useLightGlow, type GlowRefresh, type LightGlowWorkspaceContext} from './useLightGlow';

type SourceCommand = GlowPreviewCommand | GlowWriteCommand;
interface SourceBinding {key: string; scope: string; engineKey: string}
const scope = (context: LightGlowWorkspaceContext): string =>
  glowKey([context.engineKey, context.sourceUid, context.loadId, context.hostRevision]);
const sourceKey = (context: GlowContext): string => glowKey([context.session_id, context.owner, context.source_evidence]);
const admission = (context: LightGlowWorkspaceContext): boolean => !!context.sourceUid && !!context.loadId && !!context.engineKey
  && Number.isSafeInteger(context.hostRevision) && context.hostRevision >= 0
  && context.active && context.available && !context.externalBusy && !context.queueBusy;
const reason = (error: unknown): string => error instanceof Error ? error.message : String(error);

/** Call once, unconditionally in App. The existing owner owns all source/request identities.
 * Neither a modal close nor a context change replaces the native port or replays a write. */
export function useGlowWorkspaceBinding(context: LightGlowWorkspaceContext, onChanged: GlowRefresh) {
  const current = useRef({...context});
  const engineKey = useRef(context.engineKey);
  const controller = useRef<LightGlowController | null>(null);
  const source = useRef<SourceBinding | null>(null);
  const port = useRef<LightGlowNativePort | null>(null);
  const mounted = useRef(false);
  const generation = useRef(0);
  const acquiring = useRef(false);
  const [preparing, setPreparing] = useState(false);
  const key = scope(context);

  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  // Commit the live identity before useLightGlow updates its owner. Never bind to an
  // abandoned concurrent render, a filename, or a reconstructed canonical revision.
  useLayoutEffect(() => {
    if (scope(current.current) !== key || (admission(current.current) && !admission(context))) ++generation.current;
    current.current = {...context}; engineKey.current = context.engineKey;
  }, [key, context.active, context.available, context.externalBusy, context.queueBusy]);

  if (!port.current) {
    const requireSource = (command: SourceCommand, cancelling = false): void => {
      const state = controller.current?.snapshot(), retained = state?.context, bound = source.current, live = current.current;
      if (!mounted.current || !state || !retained || !bound || bound.key !== sourceKey(retained)
        || bound.engineKey !== engineKey.current || retained.session_id !== command.session_id
        || !sameGlowOwner(retained.owner, command.owner)) throw Error('原发光来源、会话或引擎身份不匹配，未发送新操作。');
      if (command.action !== 'preview' && (!state.request || glowKey(state.request) !== glowKey(command)))
        throw Error('发光写入不属于控制器保留的原请求，未发送。');
      // Same-engine Cancel may release its old source after a photo/workspace switch.
      // It must never send an old session to a replacement engine or require new edits.
      if (cancelling) return;
      if (!admission(live) || bound.scope !== scope(live) || state.stale || !state.source_verified || !state.source_loaded
        || retained.owner.document_id !== live.sourceUid || retained.source_evidence.load_id !== live.loadId)
        throw Error('当前照片或其他编辑尚未稳定，旧发光来源不可用；未发送新操作。');
      if (command.action === 'preview' && glowKey(state.recipe) !== glowKey(command.recipe))
        throw Error('发光配方已变化，未发送旧预览。');
      // Do not check pendingReads here: nativePort has already reserved this read.
      // queueBusy is admission-only and must not feed back into externalBusy.
    };
    const preflight = async (command: SourceCommand): Promise<void> => {
      requireSource(command);
      const expected = generation.current;
      await glowBounded(settleCurveEdit(), 10000);
      if (expected !== generation.current) throw Error('等待编辑完成时照片或工作区已变化，未发送旧发光操作。');
      requireSource(command);
    };
    port.current = createLightGlowNativePort({engineKey: () => engineKey.current,
      beforeRead: preflight,
      beforeWrite: command => command.action === 'cancel' ? requireSource(command, true) : preflight(command)});
  }

  const owner = useLightGlow(context, port.current, onChanged);
  useLayoutEffect(() => {
    controller.current = owner.controller;
    const state = owner.controller.snapshot(), retained = state.context;
    if (!retained || state.stale) return;
    const nextKey = sourceKey(retained);
    if (source.current?.key === nextKey) return;
    if (retained.owner.document_id !== current.current.sourceUid || retained.source_evidence.load_id !== current.current.loadId) return;
    // Record only the real context the existing owner accepted. No new capture,
    // candidate, document store or request ledger is introduced by this binding.
    source.current = {key: nextKey, scope: scope(current.current), engineKey: engineKey.current};
  }, [owner.controller, owner.state.context, key]);

  const acquireCurrent = async (): Promise<void> => {
    if (acquiring.current || !owner.canAcquire || !admission(current.current)) return;
    acquiring.current = true; setPreparing(true);
    const expected = generation.current, expectedScope = scope(current.current);
    try {
      try {
        await glowBounded(settleCurveEdit(), 10000);
        if (!mounted.current || expected !== generation.current || expectedScope !== scope(current.current) || !admission(current.current))
          throw Error('照片、引擎或其他编辑状态已变化，请在稳定后重新获取。');
      } catch (error) {
        // This gate precedes request reservation. A failure is a real no-send
        // result, not a fabricated terminal reply for an admitted native request.
        owner.controller.markStale(`未发送新的来源获取请求：${reason(error)}`); return;
      }
      if (mounted.current) setPreparing(false);
      await owner.acquireCurrent();
    } finally {
      acquiring.current = false;
      if (mounted.current) setPreparing(false);
    }
  };

  return {...owner, acquireCurrent, canAcquire: owner.canAcquire && !preparing, busy: owner.busy || preparing,
    message: preparing ? '正在等待已有曲线编辑完成；尚未发送新的来源获取。' : owner.message};
}
