// SPDX-License-Identifier: GPL-3.0-or-later
import {eyeBagPresetAliasHistoryClass,eyeBagPresetAliasWritePending,subscribeEyeBagPresetAliasWrites,sameEyeBagPresetAliasMarker} from '../eyeBagPreserve/presetAliasHistoryRegistry';
import {recoveryAliasHistoryClass,recoveryAliasWritePending,subscribeRecoveryAliasWrites,sameRecoveryAliasMarker,setRecoveryAliasWritePending,subscribeRecoveryAliasWorkspace,recoveryAliasWorkspace,type RecoveryAliasMarker} from '../effectRecovery/aliasHistoryRegistry';
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
  const recoveryReadback=useRef<{id:string;epoch:string;batchId:string;action:'undo'|'redo';marker:RecoveryAliasMarker;terminalKnown:boolean}|null>(null);
  const [recoveryNeedsRefresh,setRecoveryNeedsRefresh]=useState(false);
  useLayoutEffect(()=>subscribeRecoveryAliasWorkspace(replacement=>{if(recoveryReadback.current?.epoch===replacement.previous){recoveryReadback.current=null;setRecoveryNeedsRefresh(false);}}),[]);
  const [historyKind, setHistoryKind] = useState<'face_style' | 'eye_bag' | 'eye_bag_preset' | 'eye_bag_recovery' | null>(null);
  async function refreshHistory() {
    const recoveryAtStart=recoveryReadback.current,terminalAtStart=recoveryAtStart?.terminalKnown===true;
    setHistoryRefreshing(true);
    try {await refreshRef.current(); setHistoryRefreshError('');
      if(terminalAtStart&&recoveryAtStart&&recoveryReadback.current===recoveryAtStart&&recoveryAtStart.terminalKnown&&recoveryAliasWorkspace()===recoveryAtStart.epoch){setRecoveryAliasWritePending(recoveryAtStart.id,false);recoveryReadback.current=null;setRecoveryNeedsRefresh(false);}}
    catch (cause) {setHistoryRefreshError(recoveryAtStart&&!terminalAtStart
      ?`原恢复批次结果仍未确认，状态刷新也失败：${String(cause)}。刷新不能解除原请求保护，请查询原请求，不要重复提交。`
      :`批次结果已确认，但状态刷新失败：${String(cause)}。请刷新，不要重复提交。`);}
    finally {setHistoryRefreshing(false);}
  }
  const value = doc?.people ?? null;
  const supported = status?.ready_caps?.people_protocol === 1;
  const enabled = !!status?.engine_alive && supported && !!value && !status?.export_progress;
  // This controller reuses the engine's scoped batch ledger. It stores no local undo snapshots.
  // It lives with the people queue, so collapsing a review cannot abandon an uncertain undo.
  const history = useBatchWorkflow({docs: [], moduleScope: [], conflictPolicy: 'recheck',
    sourceDocumentId: value?.binding.document_id ?? '', enabled: false, label: '共享来源人物受保护批次历史'}, completed => {
      const readback=recoveryReadback.current,result=completed.result;
      if(readback&&result&&['done','error'].includes(completed.phase)&&result.outcome_unknown===false
        &&completed.operation===readback.action&&result.batch_id===readback.batchId&&recoveryAliasWorkspace()===readback.epoch
        &&sameRecoveryAliasMarker(result.eye_bag_recovery_alias_review,readback.marker))readback.terminalKnown=true;
      void refreshHistory();
    });
  const presetAliasPending=useSyncExternalStore(subscribeEyeBagPresetAliasWrites,eyeBagPresetAliasWritePending,eyeBagPresetAliasWritePending);
  const recoveryAliasPending=useSyncExternalStore(subscribeRecoveryAliasWrites,recoveryAliasWritePending,recoveryAliasWritePending);
  const historyBusy = recoveryAliasPending || presetAliasPending || historyRefreshing || ['preflighting', 'committing', 'uncertain'].includes(history.ui.phase);
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
  // Reopened composite entries come from the exact ledger marker, not a guessed preset name or an in-memory success receipt.
  const presetAliasBatches=(status?.session?.sync?.batches??[]).filter(batch=>Object.hasOwn(batch,'eye_bag_preset_alias_review'));
  const canPresetAliasHistory=(batchId:string,action:'undo'|'redo')=>{
    const batch=presetAliasBatches.find(row=>row.batch_id===batchId),classification=eyeBagPresetAliasHistoryClass(batchId);
    return enabled&&status?.ready_caps?.batch_preflight_protocol===1&&!!batch&&!!classification?.marker
      &&status.session?.sync?.workspace_generation===value?.binding.document_epoch
      &&sameEyeBagPresetAliasMarker(batch.eye_bag_preset_alias_review,classification.marker)
      &&batch.targets===classification.memberCount&&JSON.stringify(batch.module_scope)===JSON.stringify(['lnx.people_graph.v1'])
      &&!state.pending&&!state.uncertain&&!historyBusy&&!historyRefreshError&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending
      &&(action==='undo'?!batch.undone&&!!status.session?.sync?.undoable.includes(batchId):batch.undone);
  };
  function restorePresetAlias(batchId:string,action:'undo'|'redo'){
    if(!canPresetAliasHistory(batchId,action))return;
    setHistoryKind('eye_bag_preset');setHistoryRefreshError('');workflow.update(value,false);
    return action==='undo'?history.undo(batchId):history.redo(batchId);
  }
  // A distinct marker restores only the shared recovery vector, never preset state or scalar intent.
  const recoveryAliasBatches=(status?.session?.sync?.batches??[]).filter(batch=>Object.hasOwn(batch,'eye_bag_recovery_alias_review'));
  const canRecoveryAliasHistory=(batchId:string,action:'undo'|'redo')=>{
    const batch=recoveryAliasBatches.find(row=>row.batch_id===batchId),classification=recoveryAliasHistoryClass(batchId);
    return enabled&&status?.ready_caps?.batch_preflight_protocol===1&&!!batch&&!!classification?.marker
      &&status.session?.sync?.workspace_generation===value?.binding.document_epoch
      &&sameRecoveryAliasMarker(batch.eye_bag_recovery_alias_review,classification.marker)
      &&batch.targets===classification.memberCount&&JSON.stringify(batch.module_scope)===JSON.stringify(['lnx.people_graph.v1'])
      &&!state.pending&&!state.uncertain&&!historyBusy&&!historyRefreshError&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending
      &&(action==='undo'?!batch.undone&&!!status.session?.sync?.undoable.includes(batchId):batch.undone);
  };
  function restoreRecoveryAlias(batchId:string,action:'undo'|'redo'){
    if(recoveryReadback.current||recoveryAliasWritePending()||!canRecoveryAliasHistory(batchId,action))return;
    setHistoryKind('eye_bag_recovery');setHistoryRefreshError('');workflow.update(value,false);
    // Start through the sole batch controller before erecting its global readback fence.
    // A definitive rollback may advance member versions, so refresh must finish before a new review.
    const work=action==='undo'?history.undo(batchId):history.redo(batchId);
    if(work&&value){const id=`recovery-history-${crypto.randomUUID()}`,epoch=value.binding.document_epoch;
      recoveryReadback.current={id,epoch,batchId,action,marker:structuredClone(recoveryAliasHistoryClass(batchId)!.marker!),terminalKnown:false};setRecoveryNeedsRefresh(true);setRecoveryAliasWritePending(id,true,epoch);}
    return work;
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
    presetEyeBagAliasHistory:{batches:presetAliasBatches,
      state:historyKind==='eye_bag_preset'?history.ui:{...history.ui,phase:'closed' as const,result:null},
      writePending:presetAliasPending,canUndo:(id:string)=>canPresetAliasHistory(id,'undo'),canRedo:(id:string)=>canPresetAliasHistory(id,'redo'),
      undo:(id:string)=>restorePresetAlias(id,'undo'),redo:(id:string)=>restorePresetAlias(id,'redo'),query:history.query,
      refreshError:historyRefreshError,refreshing:historyRefreshing,refresh:refreshHistory},
    recoveryEyeBagAliasHistory:{batches:recoveryAliasBatches,
      state:historyKind==='eye_bag_recovery'?history.ui:{...history.ui,phase:'closed' as const,result:null},
      writePending:recoveryAliasPending&&!recoveryNeedsRefresh,needsRefresh:recoveryNeedsRefresh,canUndo:(id:string)=>canRecoveryAliasHistory(id,'undo'),canRedo:(id:string)=>canRecoveryAliasHistory(id,'redo'),
      undo:(id:string)=>restoreRecoveryAlias(id,'undo'),redo:(id:string)=>restoreRecoveryAlias(id,'redo'),query:history.query,
      refreshError:historyRefreshError,refreshing:historyRefreshing,refresh:refreshHistory},
    eyeBagAliasHistory: {receipt: eyeSameEpoch ? eyeReceipt : null,
      state: historyKind === 'eye_bag' ? history.ui : {...history.ui, phase: 'closed' as const, result: null},
      ledger: eyeLedger, refreshError: historyRefreshError,
      canUndo: canEyeHistory && !eyeLedger!.undone && !!status?.session?.sync?.undoable.includes(eyeReceipt!.batchId),
      canRedo: canEyeHistory && !!eyeLedger!.undone,
      undo: () => restoreEyeAlias('undo'), redo: () => restoreEyeAlias('redo'), query: history.query,
      refreshing: historyRefreshing, refresh: refreshHistory}};
}
export type PeopleOwner = ReturnType<typeof usePeopleWorkflow>;
