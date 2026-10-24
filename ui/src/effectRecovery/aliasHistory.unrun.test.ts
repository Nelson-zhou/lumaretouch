// AUTHORED / UNRUN. No tests, typecheck, browser or product execution acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createBatchWorkflow,type BatchReply} from '../batch/batchWorkflow.ts';
import {observeRecoveryAliasHistory,type RecoveryAliasMarker} from './aliasHistoryRegistry.ts';
const marker:RecoveryAliasMarker={version:1,review_sha256:'a'.repeat(64),member_count:2};
async function history(overrides:Partial<BatchReply>){observeRecoveryAliasHistory({workspace_generation:`history-fixture-${crypto.randomUUID()}`,
  batches:[{batch_id:'history-batch',module_scope:['lnx.people_graph.v1'],targets:2,undone:false,eye_bag_recovery_alias_review:marker}]});
  const flow=createBatchWorkflow({request:async()=>({requested:true}),read:async request_id=>({phase:'done',request_id,result:{request_id,action:'undo',success:false,
    outcome_unknown:false,no_write:false,rolled_back:true,batch_id:'history-batch',module_scope:['lnx.people_graph.v1'],eye_bag_recovery_alias_review:marker,restored:[],error:'fully compensated; member versions advanced',...overrides}})},()=>{}, {uuid:()=> 'history-request'});
  await flow.undo('history-batch');const snapshot=flow.snapshot();flow.dispose();return snapshot;
}
test('explicit compensated full-member history failure is definite, not a false no-write claim',async()=>{
  const value=await history({});assert.equal(value.phase,'error');assert.equal(value.result?.no_write,false);assert.equal(value.result?.rolled_back,true);assert.deepEqual(value.result?.restored,[]);
});
test('only explicit preclaim refusal can use no_write true',async()=>{
  assert.equal((await history({no_write:true,rolled_back:undefined})).phase,'error');
  assert.equal((await history({no_write:false,rolled_back:undefined})).phase,'uncertain');
  assert.equal((await history({no_write:true,rolled_back:true})).phase,'uncertain');
  assert.equal((await history({restored:[0]})).phase,'uncertain');
});
test('people-owned recovery history keeps a global review fence until its own refresh succeeds',()=>{
  const owner=readFileSync(new URL('../people/usePeopleWorkflow.ts',import.meta.url),'utf8');
  assert.ok(owner.includes('const work=action===\'undo\'?history.undo(batchId):history.redo(batchId)'));
  assert.ok(owner.includes('setRecoveryAliasWritePending(id,true,epoch)'));
  assert.ok(owner.includes('await refreshRef.current()'));
  assert.ok(owner.includes('terminalAtStart&&recoveryAtStart&&recoveryReadback.current===recoveryAtStart'));
  assert.ok(owner.includes('terminalAtStart=recoveryAtStart?.terminalKnown===true'));
  assert.ok(owner.includes('recoveryAliasWorkspace()===recoveryAtStart.epoch'));
  assert.ok(owner.includes('completed.operation===readback.action&&result.batch_id===readback.batchId'));
  assert.ok(owner.includes('sameRecoveryAliasMarker(result.eye_bag_recovery_alias_review,readback.marker))readback.terminalKnown=true'));
  assert.ok(owner.includes('if(recoveryReadback.current||recoveryAliasWritePending()||!canRecoveryAliasHistory(batchId,action))return'));
  assert.ok(owner.includes('setRecoveryAliasWritePending(recoveryAtStart.id,false)'));
  const hook=readFileSync(new URL('./useEffectRecoveryWorkflow.ts',import.meta.url),'utf8');
  assert.ok(hook.includes('workflow.usesAliasHistory()'));
  assert.ok(hook.includes('完整成员恢复批次历史中整体撤销或重做'));
});
