// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. No browser, engine, renderer or photographic acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {validHairSmoothingAbandonment,validHairSmoothingRecovery} from './recovery.ts';
import {createPeopleWorkflow} from '../people/workflow.ts';
import type {PeopleAction,PeopleMailbox,PeopleView} from '../people/model';
const face={asset_sha256:'a'.repeat(64),face_instance_id:'face',analysis_revision:1};
function fixture(){
  const value:PeopleView={binding:{document_id:'doc',document_epoch:'workspace',document_revision:1},revision:1,association_revision:0,
    faces:[{face_ref:face,enabled:true,manual:false,analysis_status:'verified',box:[.1,.1,.5,.5]}],groups:{},persons:{},links:[],
    selected_face_id:'face',editing_target:{scope:'face',target_id:'face',face_ref:face},editing_overrides:{},resolved:null} as PeopleView;
  value.binding.asset_sha256=face.asset_sha256;
  const command:PeopleAction={document_id:'doc',document_epoch:'workspace',document_revision:1,state_revision:1,association_revision:0,
    request_id:'smoothing-old',target:value.editing_target!,action:'patch',payload:{patches:[{operation_id:'lnx.hair_smoothing.v1',parameter_path:'/amount',unset:false,value:0}]}};
  const {request_id,...binding}=command;
  const proof={authority:'native-verified-replacement',previous_outcome:'unknown',request_id,hair_smoothing_request:binding,
    owner_engine_epoch:'1'.repeat(32),replacement_engine_epoch:'2'.repeat(32),replacement_serial:2};
  return {value,command,proof};
}
test('UNRUN: replacement proof binds exact old request and never means success',()=>{
  const {command,proof}=fixture();assert.equal(validHairSmoothingAbandonment(proof,command),true);
  for(const patch of [{previous_outcome:'success'},{authority:'document-navigation'},{request_id:'another'},{replacement_serial:0},{extra:true}])
    assert.equal(validHairSmoothingAbandonment({...proof,...patch},command),false);
  assert.equal(validHairSmoothingRecovery({engine_epoch:'1'.repeat(32),replacement_serial:2}),true);
  assert.equal(validHairSmoothingRecovery({engine_epoch:'1'.repeat(32),replacement_serial:NaN}),false);
});
test('UNRUN: status stamp alone cannot retire; exact native proof abandons without resend',async()=>{
  const {value,command,proof}=fixture();let sends=0,recovery=false;
  const flow=createPeopleWorkflow({send:async()=>{sends++;},refresh:async()=>{},read:async()=>({phase:'done',request_id:command.request_id,
    result:{protocol:1,action:command.action,request_id:command.request_id,document_id:'doc',success:false,outcome_unknown:true,error:'transport unknown'},
    ...(recovery?{hair_smoothing_recovery:proof}:{})} as PeopleMailbox)});
  flow.update(value,true);await assert.rejects(flow.submit(command));assert.equal(flow.snapshot().uncertain,true);
  flow.observeHairSmoothingRecovery({engine_epoch:'2'.repeat(32),replacement_serial:2});
  await Promise.resolve();await flow.check().catch(()=>{});assert.equal(flow.snapshot().pending,true);
  recovery=true;await flow.check();assert.equal(flow.snapshot().pending,false);assert.equal(sends,1);
  assert.equal(flow.snapshot().abandonedHairSmoothingRequest?.outcome,'unknown');assert.equal(flow.snapshot().lastHairSmoothingResult,null);
});
test('UNRUN: another People owner ignores smoothing replacement metadata',async()=>{
  const {value,command,proof}=fixture();command.payload={patches:[{operation_id:'lnx.enhance.v1',parameter_path:'/eye_light',unset:false,value:.1}]};
  const flow=createPeopleWorkflow({send:async()=>{},refresh:async()=>{},read:async()=>({phase:'done',request_id:command.request_id,
    result:{protocol:1,action:'patch',request_id:command.request_id,document_id:'doc',success:false,outcome_unknown:true,error:'unknown'},hair_smoothing_recovery:proof} as PeopleMailbox)});
  flow.update(value,true);await assert.rejects(flow.submit(command));flow.observeHairSmoothingRecovery({engine_epoch:'2'.repeat(32),replacement_serial:2});
  await Promise.resolve();assert.equal(flow.snapshot().pending,true);assert.equal(flow.snapshot().abandonedHairSmoothingRequest,null);
});
