// SPDX-License-Identifier: GPL-3.0-or-later
import type {AssociationReview,AssociationTarget,AssociationRequest} from '../people/associationProof';
import {validEndpoint,validFaceRef,validCollarboneCoverage,type CollarboneCoverage,type PeopleTransferReview} from '../people/transferProof';
import {COLLARBONE_TRANSFER_OP,validCollarboneVisualForTarget,type CollarboneVisual} from './transferModel';
type CohortPlan={collarbone_cohort?:boolean;persistent_association?:AssociationReview;association_source?:AssociationTarget;targets:(AssociationTarget&{people_transfer?:PeopleTransferReview|null})[];module_scope:string[]};
export type CollarboneReviewTarget={document_id:string;path:string;visual:CollarboneVisual;coverage:CollarboneCoverage;source:boolean};
/** Include the source member first, exactly as the atomic ledger acknowledgment. */
export function collarboneCohortTargets(plan:CohortPlan):CollarboneReviewTarget[]{
  if(plan.collarbone_cohort!==true||!plan.association_source)return [];
  return [plan.association_source,...plan.targets].flatMap((row,index)=>row.association?.collarbone_visual&&row.association.collarbone_coverage
    ?[{document_id:row.document_id,path:row.path,visual:row.association.collarbone_visual,coverage:row.association.collarbone_coverage,source:index===0}]:[]);
}
export function validCollarboneCohort(plan:CohortPlan,request:AssociationRequest):boolean{
  const knownRequired=Object.hasOwn(request.selection,COLLARBONE_TRANSFER_OP)||plan.persistent_association?.intent.some(v=>v.op===COLLARBONE_TRANSFER_OP)===true;
  const rows=plan.association_source?[plan.association_source,...plan.targets]:plan.targets;
  const fieldsPresent=rows.some(row=>row.association?.collarbone_visual!==undefined||row.association?.collarbone_coverage!==undefined);
  if(plan.collarbone_cohort!==true)return plan.collarbone_cohort===undefined&&!knownRequired&&!fieldsPresent;
  if(!plan.persistent_association||!plan.association_source||rows.length<2||rows.length>16||new Set(rows.map(row=>row.document_id)).size!==rows.length)return false;
  return rows.every(row=>{const a=row.association;return !!a&&!row.blocked&&typeof row.revision==='string'&&validEndpoint(a.owner)&&validFaceRef(a.ref)
    &&validCollarboneCoverage(a.collarbone_coverage,[a.ref])
    &&validCollarboneVisualForTarget(a.collarbone_visual,row.document_id,row.revision,a.owner.source_proof);});
}

/** Same image UI and proof format, without inventing a normal-transfer FaceRef. */
export function collarbonePlanTargets(plan:CohortPlan):CollarboneReviewTarget[]{
  if(plan.collarbone_cohort===true)return collarboneCohortTargets(plan);
  if(!plan.module_scope.includes(COLLARBONE_TRANSFER_OP))return [];
  return plan.targets.filter(row=>!row.blocked).flatMap(row=>row.people_transfer?.collarbone_visual&&row.people_transfer.collarbone_coverage
    ?[{document_id:row.document_id,path:row.path,visual:row.people_transfer.collarbone_visual,coverage:row.people_transfer.collarbone_coverage,source:false}]:[]);
}
