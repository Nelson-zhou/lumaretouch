// AUTHORED / UNRUN. Static-contract fixtures, not UI or photographic acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fixture} from './fixture.unrun.test';
import {presetFixture} from '../collarbone/presetFixture';
import {validAliasReview,aliasAck,sameDecorationAliasAck,aliasEchoMatches,validAliasConfirmation,type DecorationAliasReview} from './aliasModel';
import {observeDecorationMultiHistory,decorationMultiHistory} from './multiHistory';
import {command} from './model';
export function aliasFixture(){
 const view=fixture(),base=presetFixture();
 view.binding.document_id='a'.repeat(32);
 const owner={...base.owner,document:{document_id:view.binding.document_id,epoch:view.binding.document_epoch,revision:view.binding.document_revision},people_scope:'project',state_revision:view.revision,association_revision:view.association_revision,source_proof:{asset_sha256:view.binding.asset_sha256,original_sha256:view.binding.asset_sha256,creative_source:null}};
 const face=view.editing_target!.face_ref!,coverage={version:1 as const,support_transfer:'none' as const,targets:[{face_ref:face,scope:'target-reviewed-visible-skin' as const,visibility_sha256:'c'.repeat(64),recipe_sha256:'d'.repeat(64)}]};
 const visual={...base.visual,document_id:owner.document.document_id,revision:String(owner.document.revision),source_proof:owner.source_proof,candidate_state_sha256:base.visual.before_state_sha256};
 const review:DecorationAliasReview={version:1,token:'e'.repeat(32),owner,face_ref:face,recipe:{version:1,pattern:'mole_pair',strength:1},candidate_state_revision:view.revision+2,review_sha256:'f'.repeat(64),members:[{path:'/first.png',coverage,visual},{path:'/copy.png',coverage,visual:{...visual,document_id:'b'.repeat(32)}}]};
 return {view,review};
}
test('shared alias requires exact source first and per-document own proof; numeric engine digest stays opaque',()=>{
 const {view,review}=aliasFixture();assert.ok(validAliasReview(review,view,review.recipe));
 for(const mutate of [(r:DecorationAliasReview)=>r.members.reverse(),(r:DecorationAliasReview)=>{r.members[1].visual.document_id=r.members[0].visual.document_id;},(r:DecorationAliasReview)=>{r.members[1].visual.candidate_state_sha256='0'.repeat(64);},(r:DecorationAliasReview)=>{r.candidate_state_revision=review.owner.state_revision;},(r:DecorationAliasReview)=>{r.members[1].coverage.targets[0].visibility_sha256=null as any;}]){const bad=structuredClone(review);mutate(bad);assert.equal(validAliasReview(bad,view,review.recipe),false);}
 const derived=structuredClone(review);derived.owner.source_proof.creative_source={sha256:view.binding.asset_sha256,width:1,height:1};
 for(const m of derived.members)m.visual.source_proof=structuredClone(derived.owner.source_proof);
 derived.members[1].visual.source_proof.original_sha256='9'.repeat(64);
 assert.ok(validAliasReview(derived,view,derived.recipe));
});
test('ACK binds every ordered member; alias echo cannot borrow old reference/review envelope',()=>{
 const {view,review}=aliasFixture(),ack=aliasAck(review);assert.ok(sameDecorationAliasAck(ack,review));
 assert.equal(sameDecorationAliasAck({...ack,members:[...ack.members].reverse()},review),false);
 const request=command(view,'face_decoration_alias_confirm','test',{token:review.token,ack}),{request_id,...echo}=request;
 const result={protocol:1 as const,request_id,action:request.action,document_id:request.document_id,success:true,outcome_unknown:false,face_decoration_alias_request:echo};
 assert.ok(aliasEchoMatches(request,result));assert.equal(aliasEchoMatches(request,{...result,face_decoration_alias_request:undefined,face_decoration_request:echo}),false);
 assert.equal(validAliasConfirmation(review,result),false);
});
test('reopened alias/cohort safety classification cannot accept mixed or partial ledger markers',()=>{
 const marker={version:1,review_sha256:'a'.repeat(64),member_count:2};
 observeDecorationMultiHistory({workspace_generation:'alias-test',batches:[{batch_id:'valid',module_scope:['lnx.people_graph.v1'],targets:2,face_decoration_alias_review:marker},{batch_id:'mixed',module_scope:['lnx.people_graph.v1'],targets:2,face_decoration_alias_review:marker,eye_bag_cohort_review:marker},{batch_id:'cohort',module_scope:['lnx.people_graph.v1'],targets:2,face_decoration_cohort_review:marker,eye_bag_cohort_review:marker}]});
 assert.equal(decorationMultiHistory('valid')?.memberCount,2);assert.equal(decorationMultiHistory('mixed')?.marker,null);assert.equal(decorationMultiHistory('cohort')?.memberCount,2);
});
