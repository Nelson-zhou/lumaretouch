// UNRUN: authored from source contracts; no tests, imports or typecheck executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sameAssociationRequest,validAssociationReview,type AssociationRequest,type AssociationReview,type AssociationTarget,type AssociationCapsule} from './associationProof.ts';
import {associationRequest} from './associationRequest.ts';
import {samePeopleRequest} from './transferProof.ts';
import {inventory,request,sourceId,targetId,sourceRef,selection} from './transferFixtureData.test.ts';
function req():AssociationRequest{return {...request(),target_policy:'persistent_association',operation:'create',association_id:'reviewed-person'};}
function evidence(r=req()):{review:AssociationReview;source:AssociationTarget;targets:AssociationTarget[]}{
  const endpoints=[{target:r.source,target_refs:[r.source_ref]},...r.targets];
  const members=endpoints.map(e=>({document_id:e.target.document.document_id,scope_id:e.target.people_scope,original_sha256:e.target.source_proof.original_sha256,ref:e.target_refs[0]}));
  const rows=endpoints.map((e,index)=>({index,path:`/photo-${index}.png`,document_id:e.target.document.document_id,revision:String(e.target.document.revision),blocked:null,
    association:{owner:e.target,ref:e.target_refs[0],candidate_sha256:'f'.repeat(64),person_id:'reviewed-person'}}));
  return {review:{version:1,operation:r.operation,association_id:r.association_id,generation:'9'.repeat(64),members,intent:[{op:'lnx.deform.v1',path:'/face_slim',value:.3}]},source:rows[0],targets:rows.slice(1)};
}
test('persistent request preserves identical bytes but distinct independently reviewed owners',()=>{
  const r=req(),e=evidence(r);assert.equal(samePeopleRequest(r,r),true);assert.equal(validAssociationReview(e.review,r,e.source,e.targets),true);
});
test('persistent review requires source member proof and exact target analysis',()=>{
  const r=req();for(const mutate of [(e:any)=>{e.source.association.owner.document.revision++;},(e:any)=>{e.source.association=undefined;},
    (e:any)=>{e.review.members[1].ref.analysis_revision++;},(e:any)=>{e.targets[0].association.candidate_sha256='bad';},
    (e:any)=>{e.review.members.pop();},(e:any)=>{e.review.intent.push({op:'lnx.deform.v1',path:'/unrequested',value:.1});}]){
    const e=structuredClone(evidence(r));mutate(e);assert.equal(validAssociationReview(e.review,r,e.source,e.targets),false);}
});
test('persistent requests reject multiple faces and repeated graph owner scopes',()=>{
  for(const mutate of [(r:any)=>{r.targets[0].target_refs.push({...sourceRef});},(r:any)=>{r.source.people_scope='project';r.targets[0].target.people_scope='project';},
    (r:any)=>{r.targets[0].target.document.epoch='different-workspace';}]){const r=req();mutate(r);assert.equal(sameAssociationRequest(r,r),false);}
});
test('unlink is explicit empty selection; ordinary create cannot use empty intent selection',()=>{
  const r=req();r.operation='unlink';r.selection={};assert.equal(sameAssociationRequest(r,r),true);r.operation='create';assert.equal(sameAssociationRequest(r,r),false);
});
test('inventory without explicit capsule metadata cannot authorize a persistent create',()=>{
  const list=inventory(),choices={[targetId]:[sourceRef]};assert.equal(associationRequest(list,[targetId],sourceRef,selection,choices,'create','new-person'),undefined);
  list.source.associations=[];const target=list.targets[0];if(target.blocked!==null)throw Error('fixture');target.associations=[];
  assert.ok(associationRequest(list,[targetId],sourceRef,selection,choices,'create','new-person'));
});
test('persistent patch requires all stored members and their exact accepted generation',()=>{
  const list=inventory(),e=evidence(),capsule=(id:string):AssociationCapsule=>({version:1,association_id:'reviewed-person',generation:e.review.generation,
    local_document_id:id,members:e.review.members,intent:e.review.intent});
  list.source.associations=[capsule(sourceId)];const target=list.targets[0];if(target.blocked!==null)throw Error('fixture');target.associations=[capsule(targetId)];
  assert.ok(associationRequest(list,[targetId],sourceRef,selection,{[targetId]:[sourceRef]},'patch','unused'));
  target.associations[0].generation='8'.repeat(64);
  assert.equal(associationRequest(list,[targetId],sourceRef,selection,{[targetId]:[sourceRef]},'patch','unused'),undefined);
});
test('exact stored face analysis mismatch suspends persistent reuse',()=>{
  const list=inventory(),e=evidence();list.source.associations=[{version:1,association_id:'reviewed-person',generation:e.review.generation,local_document_id:sourceId,members:e.review.members,intent:e.review.intent}];
  const target=list.targets[0];if(target.blocked!==null)throw Error('fixture');target.associations=[{...list.source.associations[0],local_document_id:targetId}];
  list.source.associations[0].members[0].ref={...sourceRef,analysis_revision:99};
  assert.equal(associationRequest(list,[targetId],sourceRef,{}, {[targetId]:[sourceRef]},'unlink','unused'),undefined);
});
