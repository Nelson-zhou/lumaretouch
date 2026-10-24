// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. Only source authored; no import, test, typecheck, build or app run.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {recoveryWithoutCore,waistLengthAvailability} from './availability.ts';
import {ANCHORS,FLAGS,type ReviewSupport} from './model.ts';
test('native availability is exact and separate from implemented recovery protocol',()=>{
 const missing=waistLengthAvailability({ready_caps:{waist_length_protocol:1,waist_length_available:false,waist_length_unavailable_reason:'native unavailable'}} as never);
 assert.equal(missing.supported,true);assert.equal(missing.coreAvailable,false);assert.equal(missing.unavailableReason,'native unavailable');
 assert.equal(waistLengthAvailability(null).supported,false);
 assert.equal(waistLengthAvailability({ready_caps:{waist_length_protocol:1}} as never).coreAvailable,false);
 assert.equal(waistLengthAvailability({ready_caps:{waist_length_protocol:1,waist_length_available:true}} as never).coreAvailable,true);
 assert.equal(waistLengthAvailability({ready_caps:{waist_length_protocol:1,waist_length_available:true,waist_length_unavailable_reason:null}} as never).coreAvailable,true);
 assert.equal(waistLengthAvailability({ready_caps:{waist_length_protocol:0,waist_length_available:true}} as never).coreAvailable,false);
 assert.equal(waistLengthAvailability({ready_caps:{waist_length_protocol:1,waist_length_available:'true'}} as never).coreAvailable,false);
});
test('missing native core permits exact neutral recipe and disabling; no active fallback',()=>{
 assert.equal(recoveryWithoutCore('recipe',{recipe:{version:1,amount:0}}),true);
 assert.equal(recoveryWithoutCore('operation_status',{enabled:false}),true);
 for(const amount of [-1,.1,1,true,'0',null])assert.equal(recoveryWithoutCore('recipe',{recipe:{version:1,amount}}),false);
 assert.equal(recoveryWithoutCore('recipe',{recipe:{version:1,amount:0,hidden_waist:true}}),false);
 assert.equal(recoveryWithoutCore('operation_status',{enabled:true}),false);
 assert.equal(recoveryWithoutCore('support_review',{data:{}}),false);
});
test('source-only review without core requires exact independent marks, all confirmations and pose identity',()=>{
 const data:ReviewSupport={version:1,method:'user-reviewed-visible-waist-length-support',outer_left:.05,inner_left:.15,inner_right:.85,outer_right:.95,upper_zero:.03,upper_plateau:.08,head_box:[.4,.1,.6,.24],left_arm_box:[.2,.28,.35,.75],right_arm_box:[.65,.28,.8,.75],waist_upper_left:[.36,.48],waist_upper_right:[.64,.48],waist_lower_left:[.38,.66],waist_lower_right:[.62,.66],confirmations:Object.fromEntries(FLAGS.map(k=>[k,true])) as ReviewSupport['confirmations']};
 const payload={data,points_sha256:'a'.repeat(64),visible_anchors:[...ANCHORS],ownership_confirmed:true};
 assert.equal(recoveryWithoutCore('support_review',payload),true);
 for(const patch of [{points_sha256:'guess'},{visible_anchors:[11,12,23,24]},{ownership_confirmed:false},{data:{...data,waist_upper_left:undefined}},{data:{...data,confirmations:{...data.confirmations,waist_endpoints_manually_marked:false}}},{unexpected:true}])assert.equal(recoveryWithoutCore('support_review',{...payload,...patch}),false);
});
