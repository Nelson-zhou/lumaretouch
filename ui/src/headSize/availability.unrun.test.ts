// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. Availability fixtures do not prove a native kernel exists.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {headSizeAvailability,recoveryWithoutCore} from './availability.ts';
import {ANCHORS,FLAGS,type ReviewSupport} from './model.ts';
const data:ReviewSupport={version:1,method:'user-reviewed-complete-head-hair-support',head_box:[.3,.1,.7,.3],transition_box:[.22,.04,.78,.36],pivot:[.51,.21],confirmations:Object.fromEntries(FLAGS.map(k=>[k,true])) as ReviewSupport['confirmations']};
const review=()=>({data:structuredClone(data),points_sha256:'a'.repeat(64),visible_anchors:[...ANCHORS],ownership_confirmed:true});
test('protocol and head native availability are independent and fail closed',()=>{
 assert.equal(headSizeAvailability(null).supported,false);
 assert.equal(headSizeAvailability({ready_caps:{head_size_protocol:1,head_size_available:false}} as never).supported,true);
 assert.equal(headSizeAvailability({ready_caps:{head_size_protocol:1,head_size_available:false}} as never).coreAvailable,false);
 assert.equal(headSizeAvailability({ready_caps:{head_size_protocol:1,head_size_available:true}} as never).coreAvailable,true);
 assert.equal(headSizeAvailability({ready_caps:{head_size_available:true}} as never).coreAvailable,false);
 assert.equal(headSizeAvailability({ready_caps:{head_size_protocol:1,head_size_available:'true'}} as never).coreAvailable,false);
});
test('without core only independent review, neutral reset and disable may be requested',()=>{
 assert.equal(recoveryWithoutCore('support_review',review()),true);
 assert.equal(recoveryWithoutCore('recipe',{recipe:{version:1,amount:0},base:{version:1,amount:.5}}),true);
 assert.equal(recoveryWithoutCore('recipe',{recipe:{version:1,amount:.001},base:{version:1,amount:0}}),false);
 assert.equal(recoveryWithoutCore('recipe',{recipe:{version:1,amount:-.1}}),false);
 assert.equal(recoveryWithoutCore('operation_status',{enabled:false}),true);
 assert.equal(recoveryWithoutCore('operation_status',{enabled:true}),false);
 assert.equal(recoveryWithoutCore('operation_status',{enabled:false,other:true}),false);
});
test('review recovery cannot manufacture missing ownership, head observations or manual support',()=>{
 for(const patch of [{ownership_confirmed:false},{points_sha256:'invalid'},{visible_anchors:Array.from({length:11},(_,i)=>i)},{visible_anchors:[...ANCHORS].reverse()},{data:{...data,pivot:undefined}},{data:{...data,confirmations:{...data.confirmations,complete_head_hair_reviewed:false}}},{data:{...data,associated_face_box:[.4,.15,.6,.25]}}])assert.equal(recoveryWithoutCore('support_review',{...review(),...patch}),false);
});
