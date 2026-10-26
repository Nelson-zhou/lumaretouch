// AUTHORED / UNRUN. DTO source fixtures, not UI/native runtime acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {validReceipt,validRequest,validView,type HistoryRequest,type HistoryView} from './model.ts';
const view=():HistoryView=>({workspace:'workspace',document_id:'doc',load_id:'load',revision:'7',digest:'a'.repeat(64),cursor:3,undo_steps:3,redo_steps:1,history_max:64});
const request=():HistoryRequest=>({cmd:'history_navigation',action:'navigate',request_id:'history-nav-v1:jump',view:view(),target:0});
const result=()=>({event:'history_navigation_result',protocol:1,request_id:'history-nav-v1:jump',original_request:request(),success:false,outcome_unknown:false,requires_reload:false,phase:'partial',completed_steps:1,
  reached:{...view(),revision:'9',digest:'b'.repeat(64),cursor:2,undo_steps:2,redo_steps:2},last_confirmed:{...view(),revision:'9',digest:'b'.repeat(64),cursor:2,undo_steps:2,redo_steps:2},error:'protected edge refused'});
test('exact retained metadata, not target-only or raw snapshots',()=>{
  assert.ok(validView(view()));assert.ok(validRequest(request()));
  assert.equal(validView({...view(),snapshot:{}}),false);
  assert.equal(validRequest({...request(),view:{...view(),digest:''}}),false);
  assert.equal(validRequest({...request(),target:5}),false);
  assert.equal(validRequest({...request(),target:true}),false);
  assert.equal(validRequest({...request(),view:{...view(),revision:'18446744073709551615'}}),false);
});
test('known partial states actual cursor, never requested target success',()=>{
  assert.ok(validReceipt(result(),request()));
  assert.equal(validReceipt({...result(),success:true},request()),false);
  assert.equal(validReceipt({...result(),phase:'applied'},request()),false);
  assert.equal(validReceipt({...result(),reached:{...result().reached,cursor:0}},request()),false);
  assert.equal(validReceipt({requested:true,request_id:'history-nav-v1:jump'},request()),false);
});
test('unknown cannot claim a current reached cursor',()=>{
  const unknown={...result(),phase:'unknown',outcome_unknown:true,requires_reload:true,reached:null};
  assert.ok(validReceipt(unknown,request()));
  assert.equal(validReceipt({...unknown,reached:result().reached},request()),false);
  assert.equal(validReceipt({...unknown,outcome_unknown:false},request()),false);
});
test('another owner/load/revision/digest cannot settle original',()=>{
  for(const key of ['workspace','document_id','load_id','revision','digest'] as const){
    const original=request();if(original.action!=='navigate')throw Error('fixture');
    const changed={...original,view:{...original.view,[key]:key==='revision'?'6':'different'}};
    assert.equal(validReceipt({...result(),original_request:changed},request()),false);
  }
});
test('no_change requires exact original retained view including digest',()=>{
  const r={...request(),target:3};const original=view();
  const noop={...result(),original_request:r,phase:'no_change',success:true,completed_steps:0,reached:original,last_confirmed:original};
  assert.ok(validReceipt(noop,r));
  const changed={...original,digest:'c'.repeat(64)};
  assert.equal(validReceipt({...noop,reached:changed,last_confirmed:changed},r),false);
});

test('reserved namespace is mandatory; no unprefixed target can be replayed',()=>{
  assert.equal(validRequest({...request(),request_id:'ordinary-id'}),false);
  assert.equal(validRequest({...request(),request_id:'history-nav-v1:'}),false);
  assert.ok(validRequest({...request(),request_id:'history-nav-v1:12345678-1234-1234-1234-123456789abc'}));
});
