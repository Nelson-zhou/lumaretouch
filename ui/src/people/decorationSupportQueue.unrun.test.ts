// AUTHORED / UNRUN. No product execution or UI acceptance was performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createDecorationSupportQueue} from './decorationSupportQueue';
import {fixture} from '../faceDecoration/fixture.unrun.test';
import {command} from '../faceDecoration/model';
import {supportAliasWritePending,setSupportAliasWritePending} from '../faceDecoration/supportAliasHistoryRegistry';
import type {PeopleResult} from './model';
test('support confirmation cannot borrow absent or scalar review authority',()=>{
 const queue=createDecorationSupportQueue(),view=fixture();
 const request=command(view,'face_decoration_support_alias_confirm','support-no-review',{token:'a'.repeat(32),ack:{review_sha256:'b'.repeat(64),members:[]}});
 assert.throws(()=>queue.prepare(request,view));
 assert.equal(supportAliasWritePending(),false);
});
test('uncertain support write retains original pending fence; malformed read cannot become success',async()=>{
 const queue=createDecorationSupportQueue(),view=fixture();
 const request=command(view,'face_decoration_support_alias_confirm','support-unknown',{token:'a'.repeat(32),ack:{}});
 queue.sent(request);assert.equal(supportAliasWritePending(),true);
 const {request_id:_,...echo}=request;
 const receipt={protocol:1,action:request.action,request_id:request.request_id,document_id:request.document_id,
  success:false,outcome_unknown:true,face_decoration_support_alias_request:echo} as PeopleResult;
 await assert.rejects(queue.validate(request,receipt,()=>view));
 assert.equal(supportAliasWritePending(),true);
 // Fixture cleanup is not production reconciliation authority.
 setSupportAliasWritePending(request.request_id,false);
 const image=command(view,'face_decoration_support_alias_image','support-image',{token:'a'.repeat(32),document_id:view.binding.document_id,side:'before',sha256:'b'.repeat(64),review_sha256:'c'.repeat(64)});
 const {request_id:__,...imageEcho}=image;
 await assert.rejects(queue.validate(image,{...receipt,action:image.action,request_id:image.request_id,
  outcome_unknown:false,success:true,face_decoration_support_alias_request:imageEcho,batch_id:'unrequested-write'} as PeopleResult,()=>view));
});
