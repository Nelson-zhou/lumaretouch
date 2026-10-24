// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. Only source authored; no import, test, typecheck, build or app run.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {recoveryWithoutCore,torsoAvailability} from './availability.ts';
test('native availability is exact and separate from implemented recovery protocol',()=>{
 const missing=torsoAvailability({ready_caps:{torso_length_protocol:1,torso_length_available:false,torso_length_unavailable_reason:'native unavailable'}} as never);
 assert.equal(missing.supported,true);assert.equal(missing.coreAvailable,false);assert.equal(missing.unavailableReason,'native unavailable');
 assert.equal(torsoAvailability(null).supported,false);
 assert.equal(torsoAvailability({ready_caps:{torso_length_protocol:1}} as never).coreAvailable,false);
 assert.equal(torsoAvailability({ready_caps:{torso_length_protocol:1,torso_length_available:true}} as never).coreAvailable,true);
 assert.equal(torsoAvailability({ready_caps:{torso_length_protocol:1,torso_length_available:true,torso_length_unavailable_reason:null}} as never).coreAvailable,true);
 assert.equal(torsoAvailability({ready_caps:{torso_length_protocol:0,torso_length_available:true}} as never).coreAvailable,false);
 assert.equal(torsoAvailability({ready_caps:{torso_length_protocol:1,torso_length_available:'true'}} as never).coreAvailable,false);
});
test('missing native core permits only exact neutral recipe and disabling; no active fallback',()=>{
 assert.equal(recoveryWithoutCore('recipe',{recipe:{version:1,amount:0}}),true);
 assert.equal(recoveryWithoutCore('operation_status',{enabled:false}),true);
 for(const amount of [-1,.1,1,true,'0',null])assert.equal(recoveryWithoutCore('recipe',{recipe:{version:1,amount}}),false);
 assert.equal(recoveryWithoutCore('recipe',{recipe:{version:1,amount:0,hidden_waist:true}}),false);
 assert.equal(recoveryWithoutCore('operation_status',{enabled:true}),false);
 assert.equal(recoveryWithoutCore('support_review',{data:{}}),false);
});
