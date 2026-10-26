// AUTHORED / UNRUN. No UI/native/runtime acceptance claimed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {validRequest,validReceipt,sameRequest,type NamedMutation,type HistoryView} from '../historyNavigation/model.ts';
const view=():HistoryView=>({workspace:'workspace',document_id:'doc',load_id:'load',revision:'7',digest:'a'.repeat(64),cursor:1,undo_steps:1,redo_steps:0,history_max:64});
const request=():NamedMutation=>({cmd:'history_navigation',action:'named_create',request_id:'history-nav-v1:named',view:view(),catalog_digest:'b'.repeat(64),name:'自然光方案'});
const result=()=>({event:'history_navigation_result',protocol:1,request_id:request().request_id,original_request:request(),success:true,outcome_unknown:false,requires_reload:false,phase:'applied',completed_steps:1,
  reached:{...view(),revision:'8'},last_confirmed:{...view(),revision:'8'},catalog_digest:'c'.repeat(64),versions:[{id:'named-id',name:'自然光方案'}]});
test('named identity and exact revision are not old ordinals or queue ACKs',()=>{
  assert.ok(validRequest(request()));assert.ok(validReceipt(result(),request()));
  assert.equal(validRequest({...request(),target:1}),false);
  assert.equal(validRequest({...request(),request_id:'unreserved'}),false);
  assert.equal(sameRequest(request(),{...request(),catalog_digest:'d'.repeat(64)}),false);
  assert.equal(validReceipt({...result(),reached:view(),last_confirmed:view()},request()),false);
  assert.equal(validReceipt({requested:true,request_id:request().request_id},request()),false);
});
test('unknown remains fenced and cannot claim selected version success',()=>{
  const {catalog_digest:_,versions:__,...base}=result();
  const unknown={...base,success:false,phase:'unknown',completed_steps:0,reached:null,last_confirmed:null,outcome_unknown:true,requires_reload:true,error:'restore failed'};
  assert.ok(validReceipt(unknown,request()));
  assert.equal(validReceipt({...unknown,reached:view()},request()),false);
  assert.equal(validReceipt({...unknown,success:true},request()),false);
  assert.equal(validRequest({...request(),name:' padded '}),false);
});
test('named phase envelopes cannot carry unrelated or contradictory payloads',()=>{
  assert.equal(validReceipt({...result(),error:12},request()),false);
  assert.equal(validReceipt({...result(),snapshot:{}},request()),false);
  const {catalog_digest:_,versions:__,...base}=result();
  const rejected={...base,success:false,phase:'rejected',completed_steps:0,reached:null,last_confirmed:null,error:'stale'};
  assert.ok(validReceipt(rejected,request()));
  assert.equal(validReceipt({...rejected,versions:[]},request()),false);
  assert.equal(validReceipt({...result(),versions:[{id:'named-id',name:'not requested'}]},request()),false);
});
