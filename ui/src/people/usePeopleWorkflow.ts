// SPDX-License-Identifier: GPL-3.0-or-later
import {decorationHistoryReadback,beginDecorationHistoryReadback,observeDecorationHistoryTerminal,settleDecorationHistoryReadback} from './decorationPresetReadback';
import {decorationPresetAliasHistoryClass,decorationPresetAliasWritePending,subscribeDecorationPresetAliasWrites,sameDecorationPresetAliasMarker} from '../faceDecoration/presetAliasHistoryRegistry';
import {supportAliasHistoryClass,sameSupportAliasMarker,supportAliasWritePending,subscribeSupportAliasWrites,subscribeSupportAliasWorkspace} from '../faceDecoration/supportAliasHistoryRegistry';
import {decorationMultiHistory} from '../faceDecoration/multiHistory';
import {eyeBagPresetAliasHistoryClass,eyeBagPresetAliasWritePending,subscribeEyeBagPresetAliasWrites,sameEyeBagPresetAliasMarker} from '../eyeBagPreserve/presetAliasHistoryRegistry';
import {recoveryAliasHistoryClass,recoveryAliasWritePending,subscribeRecoveryAliasWrites,sameRecoveryAliasMarker,setRecoveryAliasWritePending,subscribeRecoveryAliasWorkspace,recoveryAliasWorkspace,type RecoveryAliasMarker} from '../effectRecovery/aliasHistoryRegistry';
import {useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore} from 'react';
import {runPeopleRequest, type DocState, type EngineStatus} from '../native';
import {createPeopleWorkflow} from './workflow';
import {type PeopleAction, type PeopleMailbox, type PeopleTarget} from './model';
import {useBatchWorkflow} from '../batch/useBatchWorkflow';
import {isSkinReferenceAction} from '../skinReferenceMatch/model';
import {isSkinReferenceBodyAction} from '../skinReferenceBody/model';

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
  useLayoutEffect(() => {
    if (status?.engine_alive === true) workflow.observeHairSmoothingRecovery(status.hair_smoothing_recovery);
  }, [workflow, status?.engine_alive, status?.hair_smoothing_recovery?.engine_epoch, status?.hair_smoothing_recovery?.replacement_serial]);
  useLayoutEffect(()=>subscribeSupportAliasWorkspace(value=>workflow.retireDecorationSupportWorkspace(value)),[workflow]);
  const [historyRefreshError, setHistoryRefreshError] = useState(''), [historyRefreshing, setHistoryRefreshing] = useState(false);
  const recoveryReadback=useRef<{id:string;epoch:string;batchId:string;action:'undo'|'redo';marker:RecoveryAliasMarker;terminalKnown:boolean}|null>(null);
  const [recoveryNeedsRefresh,setRecoveryNeedsRefresh]=useState(false);
  useLayoutEffect(()=>subscribeRecoveryAliasWorkspace(replacement=>{if(recoveryReadback.current?.epoch===replacement.previous){recoveryReadback.current=null;setRecoveryNeedsRefresh(false);}}),[]);
  const [historyKind, setHistoryKind] = useState<'face_style' | 'eye_bag' | 'eye_bag_preset' | 'eye_bag_recovery' | 'face_decoration_alias' | 'face_decoration_support_alias' | 'face_decoration_preset_alias' | null>(null);
  async function refreshHistory() {
    const decorationAtStart=decorationHistoryReadback(),decorationTerminalAtStart=decorationAtStart?.terminalKnown===true;
    const recoveryAtStart=recoveryReadback.current,terminalAtStart=recoveryAtStart?.terminalKnown===true;
    setHistoryRefreshing(true);
    try {await refreshRef.current(); await settleDecorationHistoryReadback(decorationAtStart,decorationTerminalAtStart); setHistoryRefreshError('');
      if(terminalAtStart&&recoveryAtStart&&recoveryReadback.current===recoveryAtStart&&recoveryAtStart.terminalKnown&&recoveryAliasWorkspace()===recoveryAtStart.epoch){setRecoveryAliasWritePending(recoveryAtStart.id,false);recoveryReadback.current=null;setRecoveryNeedsRefresh(false);}}
    catch (cause) {setHistoryRefreshError(decorationAtStart&&!decorationTerminalAtStart?'原装饰预设历史结果仍未确认；刷新不能解除保护，请查询原请求。':recoveryAtStart&&!terminalAtStart
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
      observeDecorationHistoryTerminal(completed);
      const readback=recoveryReadback.current,result=completed.result;
      if(readback&&result&&['done','error'].includes(completed.phase)&&result.outcome_unknown===false
        &&completed.operation===readback.action&&result.batch_id===readback.batchId&&recoveryAliasWorkspace()===readback.epoch
        &&sameRecoveryAliasMarker(result.eye_bag_recovery_alias_review,readback.marker))readback.terminalKnown=true;
      void refreshHistory();
    });
  const presetAliasPending=useSyncExternalStore(subscribeEyeBagPresetAliasWrites,eyeBagPresetAliasWritePending,eyeBagPresetAliasWritePending);
  const recoveryAliasPending=useSyncExternalStore(subscribeRecoveryAliasWrites,recoveryAliasWritePending,recoveryAliasWritePending);
  const decorationSupportPending=useSyncExternalStore(subscribeSupportAliasWrites,supportAliasWritePending,supportAliasWritePending);
  const decorationPresetPending=useSyncExternalStore(subscribeDecorationPresetAliasWrites,decorationPresetAliasWritePending,decorationPresetAliasWritePending);
  const historyBusy = decorationPresetPending || decorationSupportPending || recoveryAliasPending || presetAliasPending || historyRefreshing || ['preflighting', 'committing', 'uncertain'].includes(history.ui.phase);
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
  const decorationAliasBatches=(status?.session?.sync?.batches??[]).filter(batch=>Object.hasOwn(batch,'face_decoration_alias_review'));
  const canDecorationAliasHistory=(batchId:string,action:'undo'|'redo')=>{
    const batch=decorationAliasBatches.find(row=>row.batch_id===batchId),classification=decorationMultiHistory(batchId);
    return enabled&&status?.ready_caps?.batch_preflight_protocol===1&&!!batch
      &&classification?.field==='face_decoration_alias_review'&&!!classification.marker
      &&status.session?.sync?.workspace_generation===value?.binding.document_epoch
      &&batch.face_decoration_alias_review?.version===classification.marker.version
      &&batch.face_decoration_alias_review?.review_sha256===classification.marker.review_sha256
      &&batch.face_decoration_alias_review?.member_count===classification.marker.member_count
      &&batch.targets===classification.memberCount&&JSON.stringify(batch.module_scope)===JSON.stringify(['lnx.people_graph.v1'])
      &&!state.pending&&!state.uncertain&&!historyBusy&&!historyRefreshError&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending
      &&(action==='undo'?!batch.undone&&!!status.session?.sync?.undoable.includes(batchId):batch.undone);
  };
  function restoreDecorationAlias(batchId:string,action:'undo'|'redo'){
    if(!canDecorationAliasHistory(batchId,action))return;
    setHistoryKind('face_decoration_alias');setHistoryRefreshError('');workflow.update(value,false);
    return action==='undo'?history.undo(batchId):history.redo(batchId);
  }
  const decorationSupportAliasBatches=(status?.session?.sync?.batches??[]).filter(batch=>Object.hasOwn(batch,'face_decoration_support_alias_review'));
  const canDecorationSupportAliasHistory=(batchId:string,action:'undo'|'redo')=>{
    const batch=decorationSupportAliasBatches.find(row=>row.batch_id===batchId),classification=supportAliasHistoryClass(batchId);
    return enabled&&status?.ready_caps?.batch_preflight_protocol===1&&!!batch&&!!classification?.marker
      &&status.session?.sync?.workspace_generation===value?.binding.document_epoch
      &&sameSupportAliasMarker(batch.face_decoration_support_alias_review,classification.marker)
      &&batch.targets===classification.memberCount&&JSON.stringify(batch.module_scope)===JSON.stringify(['lnx.people_graph.v1'])
      &&!state.pending&&!state.uncertain&&!historyBusy&&!historyRefreshError&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending
      &&(action==='undo'?!batch.undone&&!!status.session?.sync?.undoable.includes(batchId):batch.undone);
  };
  function restoreDecorationSupportAlias(batchId:string,action:'undo'|'redo'){
    if(!canDecorationSupportAliasHistory(batchId,action))return;
    setHistoryKind('face_decoration_support_alias');setHistoryRefreshError('');workflow.update(value,false);
    return action==='undo'?history.undo(batchId):history.redo(batchId);
  }
  const decorationPresetAliasBatches=(status?.session?.sync?.batches??[]).filter(batch=>Object.hasOwn(batch,'face_decoration_preset_alias_review'));
  const canDecorationPresetAliasHistory=(batchId:string,action:'undo'|'redo')=>{
    const batch=decorationPresetAliasBatches.find(row=>row.batch_id===batchId),classification=decorationPresetAliasHistoryClass(batchId);
    return enabled&&status?.ready_caps?.face_decoration_preset_alias_protocol===1&&status?.ready_caps?.batch_preflight_protocol===1&&!!batch&&!!classification?.marker
      &&status.session?.sync?.workspace_generation===value?.binding.document_epoch
      &&sameDecorationPresetAliasMarker(batch.face_decoration_preset_alias_review,classification.marker)
      &&batch.targets===classification.memberCount&&JSON.stringify(batch.module_scope)===JSON.stringify(['lnx.people_graph.v1'])
      &&!state.pending&&!state.uncertain&&!historyBusy&&!historyRefreshError&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending
      &&(action==='undo'?!batch.undone&&!!status.session?.sync?.undoable.includes(batchId):batch.undone);
  };
  function restoreDecorationPresetAlias(batchId:string,action:'undo'|'redo'){
    if(decorationHistoryReadback()||!canDecorationPresetAliasHistory(batchId,action))return;
    setHistoryKind('face_decoration_preset_alias');setHistoryRefreshError('');workflow.update(value,false);
    const work=action==='undo'?history.undo(batchId):history.redo(batchId);
    if(work&&value)beginDecorationHistoryReadback(value.binding.document_epoch,batchId,action,decorationPresetAliasHistoryClass(batchId)!.marker!);
    return work;
  }
  const guard = (action?: PeopleAction['action']) => {
    if (historyBusy) throw Error('共享来源批次历史仍在处理或查询中，不能重发修改。');
    if (action === 'skin_reference_choice' && status?.ready_caps?.skin_reference_choice_protocol !== 1)
      throw Error('当前引擎未提供已测人脸亮度建议协议，不会以旧图或人物置信度代替。');
    if (action?.startsWith('hair_smoothing_') && action !== 'hair_smoothing_detach' && status?.ready_caps?.hair_smoothing_protocol !== 1)
      throw Error('当前引擎未提供可见头发方向纹理柔顺审核协议。');
    if (action?.startsWith('neck_wrinkle_') && status?.ready_caps?.neck_wrinkle_protocol !== 1)
      throw Error('当前引擎未提供颈部细纹审核协议。');
    if (action && isSkinReferenceBodyAction(action) && status?.ready_caps?.skin_reference_body_protocol !== 1)
      throw Error('当前引擎未提供独立身体参考审核协议，不能借用脸部或其他身体功能提交。');
    if (action && isSkinReferenceAction(action) && status?.ready_caps?.skin_reference_match_protocol !== 1)
      throw Error('当前引擎未提供专用肤色参考匹配协议，不能使用其他操作代替。');
  };
  async function submit(action: PeopleAction['action'], payload: Record<string, unknown>, target: PeopleTarget): Promise<void> {
    guard(action);
    if (!value) return Promise.reject(Error('当前照片尚未提供人物状态。'));
    const {document_id, document_epoch, document_revision} = value.binding;
    return workflow.submit({document_id, document_epoch, document_revision,
      state_revision: value.revision, association_revision: value.association_revision,
      request_id: crypto.randomUUID(), target, action, payload});
  }
  return {value, state: {...state, pending: state.pending || historyBusy,
    uncertain: state.uncertain || history.ui.phase === 'uncertain'}, supported, enabled, submit,
    submitCaptured: async (command: PeopleAction) => {guard(command.action); return workflow.submit(command);},
    refreshCurrent: () => refreshRef.current(),
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
    decorationPresetAliasHistory:{batches:decorationPresetAliasBatches,
      state:historyKind==='face_decoration_preset_alias'?history.ui:{...history.ui,phase:'closed' as const,result:null},
      writePending:decorationPresetPending,needsRefresh:decorationHistoryReadback()?.terminalKnown===true,
      canUndo:(id:string)=>canDecorationPresetAliasHistory(id,'undo'),canRedo:(id:string)=>canDecorationPresetAliasHistory(id,'redo'),
      undo:(id:string)=>restoreDecorationPresetAlias(id,'undo'),redo:(id:string)=>restoreDecorationPresetAlias(id,'redo'),query:history.query,
      refreshError:historyRefreshError,refreshing:historyRefreshing,refresh:refreshHistory},
    decorationSupportAliasHistory:{batches:decorationSupportAliasBatches,
      state:historyKind==='face_decoration_support_alias'?history.ui:{...history.ui,phase:'closed' as const,result:null},
      writePending:decorationSupportPending,
      canUndo:(id:string)=>canDecorationSupportAliasHistory(id,'undo'),canRedo:(id:string)=>canDecorationSupportAliasHistory(id,'redo'),
      undo:(id:string)=>restoreDecorationSupportAlias(id,'undo'),redo:(id:string)=>restoreDecorationSupportAlias(id,'redo'),query:history.query,
      refreshError:historyRefreshError,refreshing:historyRefreshing,refresh:refreshHistory},
    decorationAliasHistory:{batches:decorationAliasBatches,
      state:historyKind==='face_decoration_alias'?history.ui:{...history.ui,phase:'closed' as const,result:null},
      canUndo:(id:string)=>canDecorationAliasHistory(id,'undo'),canRedo:(id:string)=>canDecorationAliasHistory(id,'redo'),
      undo:(id:string)=>restoreDecorationAlias(id,'undo'),redo:(id:string)=>restoreDecorationAlias(id,'redo'),query:history.query,
      refreshError:historyRefreshError,refreshing:historyRefreshing,refresh:refreshHistory},
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
