// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore} from 'react';
import {runPeopleRequest, type DocState, type EngineStatus} from '../native';
import {createPeopleWorkflow} from './workflow';
import {type PeopleAction, type PeopleMailbox, type PeopleTarget} from './model';
import {useBatchWorkflow} from '../batch/useBatchWorkflow';

/** App lifetime keeps the original request queryable when the panel is collapsed. */
export function usePeopleWorkflow(status: EngineStatus | null, doc: DocState | null, refresh: () => Promise<void>) {
  const refreshRef = useRef(refresh); refreshRef.current = refresh;
  const workflow = useMemo(() => createPeopleWorkflow({
    send: command => runPeopleRequest(command),
    recoverEyeBagRead: request_id => runPeopleRequest({action: 'recover_eye_bag_read', request_id}),
    cancelEyeBagRead: request_id => runPeopleRequest({action: 'cancel_eye_bag_read', request_id}),
    read: request_id => runPeopleRequest({action: 'status', request_id}) as Promise<PeopleMailbox>,
    refresh: () => refreshRef.current(),
  }), []);
  const state = useSyncExternalStore(workflow.subscribe, workflow.snapshot, workflow.snapshot);
  const [historyRefreshError, setHistoryRefreshError] = useState(''), [historyRefreshing, setHistoryRefreshing] = useState(false);
  const [historyKind, setHistoryKind] = useState<'face_style' | 'eye_bag' | null>(null);
  async function refreshHistory() {
    setHistoryRefreshing(true);
    try {await refreshRef.current(); setHistoryRefreshError('');}
    catch (cause) {setHistoryRefreshError(`批次结果已确认，但状态刷新失败：${String(cause)}。请刷新，不要重复提交。`);}
    finally {setHistoryRefreshing(false);}
  }
  const value = doc?.people ?? null;
  const supported = status?.ready_caps?.people_protocol === 1;
  const enabled = !!status?.engine_alive && supported && !!value && !status?.export_progress;
  // This controller reuses the engine's scoped batch ledger. It stores no local undo snapshots.
  // It lives with the people queue, so collapsing a review cannot abandon an uncertain undo.
  const history = useBatchWorkflow({docs: [], moduleScope: [], conflictPolicy: 'recheck',
    sourceDocumentId: value?.binding.document_id ?? '', enabled: false, label: '共享来源人物受保护批次历史'}, () => {void refreshHistory();});
  const historyBusy = historyRefreshing || ['preflighting', 'committing', 'uncertain'].includes(history.ui.phase);
  useLayoutEffect(() => {workflow.update(value, enabled && !historyBusy);}, [workflow, value, enabled, historyBusy]);
  const receipt = state.lastAliasCommit;
  useLayoutEffect(() => {if (receipt) history.protectFaceStyleAlias(receipt);}, [receipt]);
  const eyeReceipt = state.lastEyeBagAliasCommit;
  useLayoutEffect(() => {if (eyeReceipt) history.protectEyeBagAlias(eyeReceipt);}, [eyeReceipt]);
  const sameEpoch = !!receipt && receipt.documentEpoch === value?.binding.document_epoch;
  const ledger = sameEpoch && receipt ? status?.session?.sync?.batches.find(batch => batch.batch_id === receipt.batchId
    && batch.targets === receipt.review.members.length && batch.module_scope.length === 1 && batch.module_scope[0] === 'lnx.people_graph.v1') : undefined;
  const canHistory = enabled && status?.ready_caps?.batch_preflight_protocol === 1 && !!ledger
    && !state.pending && !state.uncertain && !historyBusy && !historyRefreshError && !status?.edit_queue?.in_flight && !status?.edit_queue?.pending;
  function restoreAlias(action: 'undo' | 'redo') {
    if (!receipt || !ledger || !canHistory || (action === 'undo' ? ledger.undone : !ledger.undone)
      || action === 'undo' && !status?.session?.sync?.undoable.includes(receipt.batchId)
      || !history.protectFaceStyleAlias(receipt)) return;
    setHistoryKind('face_style'); setHistoryRefreshError(''); setHistoryRefreshing(true);
    workflow.update(value, false);
    return action === 'undo' ? history.undo(receipt.batchId) : history.redo(receipt.batchId);
  }
  const eyeSameEpoch = !!eyeReceipt && eyeReceipt.documentEpoch === value?.binding.document_epoch;
  const eyeLedger = eyeSameEpoch && eyeReceipt ? status?.session?.sync?.batches.find(batch => batch.batch_id === eyeReceipt.batchId
    && batch.targets === eyeReceipt.review.members.length && batch.module_scope.length === 1 && batch.module_scope[0] === 'lnx.people_graph.v1') : undefined;
  const canEyeHistory = enabled && status?.ready_caps?.batch_preflight_protocol === 1 && !!eyeLedger
    && !state.pending && !state.uncertain && !historyBusy && !historyRefreshError && !status?.edit_queue?.in_flight && !status?.edit_queue?.pending;
  function restoreEyeAlias(action: 'undo' | 'redo') {
    if (!eyeReceipt || !eyeLedger || !canEyeHistory || (action === 'undo' ? eyeLedger.undone : !eyeLedger.undone)
      || action === 'undo' && !status?.session?.sync?.undoable.includes(eyeReceipt.batchId)
      || !history.protectEyeBagAlias(eyeReceipt)) return;
    setHistoryKind('eye_bag'); setHistoryRefreshError(''); setHistoryRefreshing(true);
    workflow.update(value, false);
    return action === 'undo' ? history.undo(eyeReceipt.batchId) : history.redo(eyeReceipt.batchId);
  }
  const guard = () => {
    if (historyBusy) throw Error('共享来源批次历史仍在处理或查询中，不能重发修改。');
  };
  async function submit(action: PeopleAction['action'], payload: Record<string, unknown>, target: PeopleTarget): Promise<void> {
    guard();
    if (!value) return Promise.reject(Error('当前照片尚未提供人物状态。'));
    const {document_id, document_epoch, document_revision} = value.binding;
    return workflow.submit({document_id, document_epoch, document_revision,
      state_revision: value.revision, association_revision: value.association_revision,
      request_id: crypto.randomUUID(), target, action, payload});
  }
  return {value, state: {...state, pending: state.pending || historyBusy,
    uncertain: state.uncertain || history.ui.phase === 'uncertain'}, supported, enabled, submit,
    submitCaptured: async (command: PeopleAction) => {guard(); return workflow.submit(command);},
    patch: (patches: Parameters<typeof workflow.patch>[0]) => {guard(); return workflow.patch(patches);},
    cancelEyeBagRead: workflow.cancelEyeBagRead,
    recoverEyeBagRead: workflow.recoverEyeBagRead,
    eyeBagDraft: workflow.eyeBagDraft, saveEyeBagDraft: workflow.saveEyeBagDraft,
    check: async () => {if (history.ui.phase === 'uncertain') await history.query(); else await workflow.check();},
    aliasHistory: {receipt: sameEpoch ? receipt : null, state: historyKind === 'face_style' ? history.ui : {...history.ui, phase: 'closed' as const, result: null}, ledger, refreshError: historyRefreshError,
      canUndo: canHistory && !ledger!.undone && !!status?.session?.sync?.undoable.includes(receipt!.batchId),
      canRedo: canHistory && !!ledger!.undone,
      undo: () => restoreAlias('undo'), redo: () => restoreAlias('redo'), query: history.query,
      refreshing: historyRefreshing, refresh: refreshHistory},
    eyeBagAliasHistory: {receipt: eyeSameEpoch ? eyeReceipt : null,
      state: historyKind === 'eye_bag' ? history.ui : {...history.ui, phase: 'closed' as const, result: null},
      ledger: eyeLedger, refreshError: historyRefreshError,
      canUndo: canEyeHistory && !eyeLedger!.undone && !!status?.session?.sync?.undoable.includes(eyeReceipt!.batchId),
      canRedo: canEyeHistory && !!eyeLedger!.undone,
      undo: () => restoreEyeAlias('undo'), redo: () => restoreEyeAlias('redo'), query: history.query,
      refreshing: historyRefreshing, refresh: refreshHistory}};
}
export type PeopleOwner = ReturnType<typeof usePeopleWorkflow>;
