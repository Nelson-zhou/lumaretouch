// SPDX-License-Identifier: GPL-3.0-or-later
import type {BatchUi} from '../batch/batchWorkflow';
import {engineStatus} from '../native';
import {decorationPresetAliasWorkspace,sameDecorationPresetAliasMarker,setDecorationPresetAliasWritePending,subscribeDecorationPresetAliasWorkspace,type DecorationPresetAliasMarker} from '../faceDecoration/presetAliasHistoryRegistry';

type Readback={id:string;epoch:string;batchId:string;action:'undo'|'redo';marker:DecorationPresetAliasMarker;terminalKnown:boolean;expectedUndone?:boolean};
// App-independent request identity survives panel/hook teardown. No undo snapshot lives here.
let pending:Readback|null=null;
subscribeDecorationPresetAliasWorkspace(value=>{if(pending?.epoch===value.previous)pending=null;});
export const decorationHistoryReadback=()=>pending;
export function beginDecorationHistoryReadback(epoch:string,batchId:string,action:'undo'|'redo',marker:DecorationPresetAliasMarker){
 if(pending)throw Error('原装饰预设历史仍等待状态核对');
 pending={id:`decoration-preset-history-${crypto.randomUUID()}`,epoch,batchId,action,marker:structuredClone(marker),terminalKnown:false};
 setDecorationPresetAliasWritePending(pending.id,true,epoch);
}
export function observeDecorationHistoryTerminal(completed:BatchUi){
 const captured=pending,result=completed.result;
 if(captured&&result&&['done','error'].includes(completed.phase)&&result.outcome_unknown===false
   &&completed.operation===captured.action&&result.batch_id===captured.batchId&&decorationPresetAliasWorkspace()===captured.epoch
   &&sameDecorationPresetAliasMarker(result.face_decoration_preset_alias_review,captured.marker)){captured.terminalKnown=true;captured.expectedUndone=result.success?captured.action==='undo':captured.action==='redo';}
}
export async function settleDecorationHistoryReadback(captured:Readback|null,terminalAtStart:boolean){
 if(!captured||!terminalAtStart||pending!==captured||!captured.terminalKnown)return;
 const fresh=await engineStatus();
 if(pending!==captured)return; // Only verified workspace replacement can retire another identity.
 const sync=fresh.session?.sync,row=sync?.batches.find(item=>item.batch_id===captured.batchId);
 if(!fresh.engine_alive||sync?.workspace_generation!==captured.epoch||decorationPresetAliasWorkspace()!==captured.epoch
   ||!row||row.undone!==captured.expectedUndone||row.targets!==captured.marker.member_count||JSON.stringify(row.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])
   ||!sameDecorationPresetAliasMarker(row.face_decoration_preset_alias_review,captured.marker))throw Error('新状态未证明原装饰预设历史批次与工作区');
 setDecorationPresetAliasWritePending(captured.id,false);pending=null;
}
