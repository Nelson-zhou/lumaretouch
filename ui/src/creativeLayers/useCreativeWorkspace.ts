// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState} from 'react';
import {notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {bindingFor, sameOwner, type CreativePorts, type CreativeReceipt, type CreativeRequest} from './model';
import {awaitCreativeNative, creativeFileFields, creativeNativeReceipt, creativeNativeState, submitCreativeNative,
  CreativeNativeRejected, type CreativeNativeState, type CreativePacket} from './nativePort';

export interface CreativeWorkspaceContext {
  sourceUid: string; loadId: string; engineKey: string; hostRevision: number;
  active: boolean; available: boolean; busy: boolean;
}
interface Pending {request: CreativeRequest; scope: string; engineKey: string; transition: boolean}
const scopeFor = (context: CreativeWorkspaceContext) => JSON.stringify([context.engineKey, context.sourceUid, context.loadId]);
const reason = (error: unknown) => error instanceof Error ? error.message : String(error);
const closedMessage = '历史已回到尚无创意文档的照片状态，旧图层和预览已关闭。可回到画布继续撤销/重做，或明确重新打开创意文档；不会自动重建图层。';

/** Mounted by App, so a view switch never discards an unresolved native operation. */
export function useCreativeWorkspace(context: CreativeWorkspaceContext, onChanged: () => Promise<void>) {
  const latest = useRef(context); latest.current = context;
  const changed = useRef(onChanged); changed.current = onChanged;
  const [value, setValue] = useState<CreativeNativeState | null>(null);
  const current = useRef<{scope: string; state: CreativeNativeState} | null>(null);
  const closedScope = useRef<string | null>(null), [reopenScope, setReopenScope] = useState<string | null>(null);
  const [message, setMessage] = useState(''), [working, setWorking] = useState(false), [unresolved, setUnresolved] = useState<CreativeRequest | null>(null);
  const pending = useRef<Pending | null>(null), reading = useRef(false), running = useRef(false), readGeneration = useRef(0);
  const querying = useRef(false), completed = useRef(new Map<string, CreativeReceipt>());
  const mounted = useRef(true);
  useEffect(() => {mounted.current = true; return () => {mounted.current = false; ++readGeneration.current;};}, []);
  const updateMessage = (text: string) => {if (mounted.current) setMessage(text);};

  function publish(packet: CreativePacket, scope: string, expected?: CreativeRequest, transition = false): boolean {
    if (scope !== scopeFor(latest.current) || packet.source_uid !== latest.current.sourceUid) return false;
    const before = current.current;
    if (packet.authority === null && (packet.status === 'ready' || (transition && (packet.status === 'applied' || packet.status === 'no_change')))) {
      if (expected && before?.scope === scope && !sameOwner(bindingFor(before.state.authority), expected)) return false;
      current.current = null; closedScope.current = scope;
      if (mounted.current) {setValue(null); setReopenScope(scope);}
      return true; // An explicitly absent document is authoritative, not a loading placeholder.
    }
    const next = creativeNativeState(packet); if (!next) return false;
    if (expected) {
      if (!transition && !sameOwner(bindingFor(next.authority), expected)) throw Error('普通图层操作不能替换其他文档的所有权。');
      if (before?.scope === scope && !sameOwner(bindingFor(before.state.authority), expected) &&
          !sameOwner(bindingFor(before.state.authority), bindingFor(next.authority))) return false;
    }
    if (before?.scope === scope && sameOwner(bindingFor(before.state.authority), bindingFor(next.authority)) &&
        before.state.authority.document.revision > next.authority.document.revision) throw Error('创意文档回读修订号倒退，保留较新状态。');
    current.current = {scope, state: next}; closedScope.current = null;
    if (mounted.current) {setValue(next); setReopenScope(null);} return true;
  }
  async function read(reopen = false) {
    const ctx = latest.current, scope = scopeFor(ctx);
    if (!mounted.current || reading.current || pending.current || (!reopen && closedScope.current === scope) ||
        !ctx.active || !ctx.available || !ctx.sourceUid || !ctx.loadId || ctx.busy) return;
    reading.current = true; const generation = ++readGeneration.current;
    setWorking(true); updateMessage('正在读取真实图层文档与渲染预览…');
    try {
      const request_id = crypto.randomUUID();
      await submitCreativeNative({action: !reopen && current.current?.scope === scope ? 'state' : 'open', request_id, source_uid: ctx.sourceUid});
      const packet = await awaitCreativeNative(request_id);
      if (!mounted.current || generation !== readGeneration.current || scope !== scopeFor(latest.current)) return;
      const published = publish(packet, scope);
      if (packet.status === 'rejected' || packet.status === 'unknown') throw Error(typeof packet.message === 'string' ? packet.message : '创意文档读取未确认。');
      if (!published) throw Error('宿主未提供真实图层文档，未创建示意图层。');
      updateMessage(closedScope.current === scope ? closedMessage : '已读取宿主确认的图层文档。');
    } catch (error) {if (mounted.current && generation === readGeneration.current && scope === scopeFor(latest.current)) updateMessage(reason(error));}
    finally {
      reading.current = false; if (mounted.current) setWorking(running.current);
      if (mounted.current && (scope !== scopeFor(latest.current) || generation !== readGeneration.current)) void read();
    }
  }
  function rejected(request: CreativeRequest, message: string): CreativeReceipt {return {...request, status: 'rejected', message};}
  function sameContext(request: CreativeRequest, scope: string): boolean {
    const state = current.current;
    return scope === scopeFor(latest.current) && !!state && state.scope === scope &&
      sameOwner(bindingFor(state.state.authority), request) && state.state.authority.document.revision === request.expected_revision;
  }
  async function accept(packet: CreativePacket, operation: Pending): Promise<CreativeReceipt> {
    const prior = completed.current.get(operation.request.request_id); if (prior) return prior;
    const receipt = creativeNativeReceipt(packet, operation.request);
    if (receipt.status === 'unknown') {updateMessage(receipt.message); return receipt;}
    // A history receipt may restore an older revision only under the new host owner.
    let published = false, stateError = '';
    try {published = publish(packet, operation.scope, operation.request, operation.transition);} catch (error) {stateError = reason(error);}
    completed.current.set(operation.request.request_id, receipt);
    if (completed.current.size > 64) completed.current.delete(completed.current.keys().next().value!);
    if (pending.current === operation) {pending.current = null; if (mounted.current) setUnresolved(null);}
    updateMessage(receipt.status === 'rejected' ? receipt.message : published && closedScope.current === operation.scope ? closedMessage :
      stateError ? `操作已确认，状态需重新读取：${stateError}` :
      typeof packet.preview_error === 'string' ? `操作已确认，预览未就绪：${packet.preview_error}` :
      receipt.status === 'no_change' ? '操作已确认，没有新增改动。' : '操作已由宿主确认。');
    if (receipt.status !== 'rejected') {
      try {await changed.current();} catch (error) {updateMessage(`操作已确认，但主工作区状态刷新失败：${reason(error)}`);}
    }
    if (!published) void read();
    return receipt;
  }
  async function submit(request: CreativeRequest, fields: Record<string, unknown> | (() => Promise<Record<string, unknown>>)): Promise<CreativeReceipt> {
    const ctx = latest.current, scope = scopeFor(ctx);
    if (pending.current || running.current || reading.current || ctx.busy) return rejected(request, '另一个操作尚未完成，未发送新操作。');
    if (!ctx.active || !ctx.available || !sameContext(request, scope)) return rejected(request, '图层文档或修订已变化，未发送旧操作。');
    const operation: Pending = {request, scope, engineKey: ctx.engineKey, transition: false};
    pending.current = operation; running.current = true; ++readGeneration.current;
    if (mounted.current) {setWorking(true); setUnresolved(request);}
    let sent = false;
    try {
      const payload = typeof fields === 'function' ? await fields() : fields;
      operation.transition = payload.action === 'history' || payload.action === 'return' || payload.action === 'fresh_current';
      await settleCurveEdit();
      if (!sameContext(request, scope) || latest.current.busy) {
        pending.current = null; if (mounted.current) setUnresolved(null);
        return rejected(request, '文件读取期间文档上下文已变化，未提交。');
      }
      notifyInspectionEditIntent(); sent = true;
      await submitCreativeNative({...request, ...payload});
      return await accept(await awaitCreativeNative(request.request_id), operation);
    } catch (error) {
      if (!sent || error instanceof CreativeNativeRejected) {
        if (pending.current === operation) pending.current = null;
        if (mounted.current) setUnresolved(null);
        updateMessage(reason(error)); return rejected(request, reason(error));
      }
      updateMessage(`${reason(error)} 原操作仍待核对，不会重发。`);
      return {...request, status: 'unknown', message: reason(error)};
    } finally {
      running.current = false; if (mounted.current) setWorking(reading.current || querying.current);
      if (!pending.current && scope !== scopeFor(latest.current)) void read();
    }
  }
  async function query(request = pending.current?.request): Promise<CreativeReceipt | null> {
    if (!request) return null;
    const known = completed.current.get(request.request_id); if (known) {void read(); return known;}
    if (querying.current) return {...request, status: 'unknown', message: '原操作正在核对，请稍候。'};
    const operation = pending.current?.request.request_id === request.request_id ? pending.current : null;
    if (!operation) return {...request, status: 'unknown', message: '原操作上下文已失效，不能将旧结果用于当前文档。'};
    querying.current = true; if (mounted.current) setWorking(true);
    try {return await accept(await awaitCreativeNative(request.request_id), operation);}
    catch (error) {updateMessage(reason(error)); return {...request, status: 'unknown', message: reason(error)};}
    finally {querying.current = false; if (mounted.current) setWorking(reading.current || running.current);}
  }
  const shown = current.current?.scope === scopeFor(context) ? value : null;
  const capabilities = shown?.capabilities;
  const ports: CreativePorts = {
    ...(capabilities?.command ? {command: ({command, ...request}: CreativeRequest & {command: import('./model').CreativeCommand}) => submit(request, {action: 'command', command})} : {}),
    ...(capabilities?.import_image ? {importImage: ({file, ...request}: CreativeRequest & {file: File}) => submit(request, async () => ({action: 'import_image', ...await creativeFileFields(file)}))} : {}),
    ...(capabilities?.attach_mask ? {attachMask: ({file, layer_id, ...request}: CreativeRequest & {file: File; layer_id: string}) => submit(request, async () => ({action: 'attach_mask', layer_id, ...await creativeFileFields(file)}))} : {}),
    ...(capabilities?.remove_mask ? {removeMask: ({layer_id, ...request}: CreativeRequest & {layer_id: string}) => submit(request, {action: 'remove_mask', layer_id})} : {}),
    ...(capabilities?.history ? {undo: (request: CreativeRequest) => submit(request, {action: 'history', direction: 'undo'}),
      redo: (request: CreativeRequest) => submit(request, {action: 'history', direction: 'redo'})} : {}),
    ...(capabilities?.return_new ? {returnNew: ({render_id, ...request}: CreativeRequest & {render_id: string}) => submit(request, {action: 'return', mode: 'new', render_id})} : {}),
    ...(capabilities?.update_original ? {updateOriginal: ({render_id, ...request}: CreativeRequest & {render_id: string}) => submit(request, {action: 'return', mode: 'update', render_id})} : {}),
    reconcile: async request => (await query(request)) ?? {...request, status: 'unknown', message: '没有可核对的原操作。'},
  };
  async function importPaths(paths: string[]): Promise<void> {
    if (paths.length !== 1) {updateMessage('创意工作区一次导入一张图片，请等待确认后再拖入下一张。'); return;}
    const state = current.current;
    if (!state || !state.state.capabilities.import_image || !latest.current.active) {updateMessage('创意图片导入尚未就绪，未替换原照片。'); return;}
    const path = paths[0], filename = path.split(/[\\/]/).pop() || path;
    const receipt = await submit({...bindingFor(state.state.authority), request_id: crypto.randomUUID()}, {action: 'import_image', path, filename});
    if (receipt.status === 'rejected' || receipt.status === 'unknown') updateMessage(receipt.message);
  }
  async function freshCurrent(): Promise<void> {
    const state = current.current?.state;
    if (!state?.capabilities.fresh_current || !state.history?.recoverable_delete) return;
    await submit({...bindingFor(state.authority), request_id: crypto.randomUUID()}, {action: 'fresh_current'});
  }
  async function acceptSelection(reply: import('../creativeSelection/model').SelectionReply, request: import('../creativeSelection/model').SelectionApplyRequest): Promise<void> {
    if (reply.status !== 'applied' && reply.status !== 'no_change') throw Error('选区修改尚未确认。');
    await changed.current();
    const scope = scopeFor(latest.current);
    if (latest.current.sourceUid !== request.source_uid) return; // Never publish into a different photo.
    const request_id = crypto.randomUUID();
    await submitCreativeNative({action: 'state', request_id, source_uid: request.source_uid});
    const packet = await awaitCreativeNative(request_id);
    if (scope !== scopeFor(latest.current)) return;
    const next = creativeNativeState(packet);
    if (!next || next.authority.document.document_id !== request.proof.document_id
      || next.authority.document.revision < Number(reply.revision)) throw Error('选区已应用，但完整图层状态尚未正确回读。');
    if (!publish(packet, scope)) throw Error('选区已应用，但当前图层所有权已变化。');
  }
  async function history(direction: 'undo' | 'redo'): Promise<void> {
    const state = current.current?.state;
    if (!state?.capabilities.history || !(direction === 'undo' ? state.history?.can_undo : state.history?.can_redo)) return;
    const receipt = await submit({...bindingFor(state.authority), request_id: crypto.randomUUID()}, {action: 'history', direction});
    if (receipt.status === 'rejected' || receipt.status === 'unknown') updateMessage(receipt.message);
  }
  useEffect(() => {
    if (pending.current && pending.current.engineKey !== context.engineKey) {
      pending.current = null; setUnresolved(null); updateMessage('引擎已更换，旧操作结果未知且不会重发。请核对工程状态。');
    }
    if (current.current?.scope !== scopeFor(context)) {current.current = null; setValue(null);}
    if (closedScope.current !== scopeFor(context)) {closedScope.current = null; setReopenScope(null);}
    if (context.active && context.available) void read();
  }, [context.active, context.available, context.sourceUid, context.loadId, context.engineKey, context.hostRevision, context.busy]);
  return {value: shown, ports, message, working, unresolved, pending: working || !!unresolved,
    busy: context.busy || working || !!unresolved || !!shown?.authority.busy,
    read: () => read(), reopen: () => read(true), needsReopen: reopenScope === scopeFor(context),
    query: () => query(), importPaths, history, freshCurrent, acceptSelection};
}
export type CreativeWorkspaceOwner = ReturnType<typeof useCreativeWorkspace>;
