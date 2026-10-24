// Synthetic source-contract DTO only. No actual image quality acceptance.
import {request,sourceId,targetId} from '../people/transferFixtureData.test';
import type {AssociationRequest,AssociationReview,AssociationTarget} from '../people/associationProof';
import type {CollarboneVisual} from './transferModel';
import type {CollarboneCoverage} from '../people/transferProof';
export function cohortFixture(operation:AssociationRequest['operation']='create',activeOnly=false){
 const people:AssociationRequest={...request(),target_policy:'persistent_association',operation,association_id:'person-cohort'};
 people.selection=operation==='unlink'?{}:activeOnly?{'lnx.deform.v1':['/face_slim']}:{'lnx.collarbone.v1':['/amount']};
 const endpoints=[{target:people.source,target_refs:[people.source_ref]},...people.targets];
 const rows:AssociationTarget[]=endpoints.map((e,index)=>{
  const document=e.target.document.document_id,revision=String(e.target.document.revision);
  const coverage:CollarboneCoverage={version:1,support_transfer:'none',targets:[{face_ref:e.target_refs[0],scope:'neutral-no-effect',body_review_sha256:null,clavicle_category:null,clavicle_sides:[]}]};
  const visual:CollarboneVisual={version:1,document_id:document,revision,source_proof:e.target.source_proof,
   before_state_sha256:'1'.repeat(64),candidate_state_sha256:'2'.repeat(64),before_people_sha256:'3'.repeat(64),candidate_people_sha256:'4'.repeat(64),coverage_sha256:'5'.repeat(64),
   source_size:[1,1],before_output_size:[1,1],after_output_size:[1,1],before:{mime:'image/png',width:1,height:1,sha256:String(index+6).repeat(64)},after:{mime:'image/png',width:1,height:1,sha256:String(index+8).repeat(64)}};
  return {index,path:index?'/target.raw':'/source.raw',document_id:document,revision,blocked:null,
    association:{owner:e.target,ref:e.target_refs[0],person_id:'person-cohort',candidate_sha256:'e'.repeat(64),collarbone_coverage:coverage,collarbone_visual:visual}};
 });
 const association:AssociationReview={version:1,operation,association_id:people.association_id,generation:'9'.repeat(64),
  members:endpoints.map(e=>({document_id:e.target.document.document_id,scope_id:e.target.people_scope,original_sha256:e.target.source_proof.original_sha256,ref:e.target_refs[0]})),
  intent:activeOnly?[{op:'lnx.deform.v1',path:'/face_slim',value:.2}]:[{op:'lnx.collarbone.v1',path:'/amount',value:0}]};
 return {people,sourceId,targetId,plan:{collarbone_cohort:true,persistent_association:association,association_source:rows[0],targets:rows.slice(1),module_scope:Object.keys(people.selection)}};
}
