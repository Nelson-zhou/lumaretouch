import type {EyeBagCohortPolicy} from '../eyeBagPreserve/cohortPolicy';
import {sameFace} from './transferProof';
import {endpointOf,isAvailableEntry,selectableFace,type PeopleInventoryResult,type FaceChoices} from './transferInventory';
import {sameAssociationRequest,type AssociationRequest,type AssociationCapsule} from './associationProof';
import type {FaceStyleRecipe} from '../faceStyle/model';
import type {FaceRef} from './model';
export function sourceAssociation(listing:PeopleInventoryResult|null,ref:FaceRef|undefined):AssociationCapsule|undefined{
  if(!listing||!ref)return undefined;
  return listing.source.associations?.find(c=>c.members.some(m=>m.document_id===listing.source.document.document_id&&m.ref.face_instance_id===ref.face_instance_id));
}
export function associationRequest(listing:PeopleInventoryResult|null,docs:string[],ref:FaceRef|undefined,selection:Record<string,string[]>,choices:FaceChoices,
  operation:AssociationRequest['operation'],newId:string,faceStyle?:FaceStyleRecipe,eyeBagCohort?:EyeBagCohortPolicy):AssociationRequest|undefined{
  if(!listing||!Array.isArray(listing.source.associations)||!ref||!docs.length||docs.length>15||listing.rejected_docs.length||listing.targets.length!==docs.length
    ||!listing.source.faces.some(f=>sameFace(f.face_ref,ref)&&selectableFace(f)))return undefined;
  const existing=sourceAssociation(listing,ref);
  if(operation==='create'?!!existing:!existing)return undefined;
  const request:AssociationRequest={target_policy:'persistent_association',operation,association_id:existing?.association_id??newId,
    ...(eyeBagCohort?{eye_bag_cohort:eyeBagCohort}:{}),source_ref:ref,selection:operation==='unlink'?{}:selection,...(operation!=='unlink'&&faceStyle?{face_style:faceStyle}:{}),source:endpointOf(listing.source),targets:[]};
  for(const id of docs){const entry=listing.targets.find(t=>t.document.document_id===id),refs=choices[id];
    if(!entry||!isAvailableEntry(entry)||!Array.isArray(entry.associations)||refs?.length!==1||!entry.faces.some(f=>sameFace(f.face_ref,refs[0])&&selectableFace(f)))return undefined;
    const linked=entry.associations?.find(c=>c.members.some(m=>m.document_id===id&&m.ref.face_instance_id===refs[0].face_instance_id));
    if(operation==='create'?!!linked:!linked||linked.association_id!==existing?.association_id||linked.generation!==existing?.generation)return undefined;
    request.targets.push({target:endpointOf(entry),target_refs:refs});}
  if(existing){const endpoints=[{target:request.source,target_refs:[ref]},...request.targets];
    if(existing.members.length!==endpoints.length||!endpoints.every(e=>existing.members.some(m=>m.document_id===e.target.document.document_id
      &&m.scope_id===e.target.people_scope&&m.original_sha256===e.target.source_proof.original_sha256&&sameFace(m.ref,e.target_refs[0]))))return undefined;}
  return sameAssociationRequest(request,request)?request:undefined;
}
