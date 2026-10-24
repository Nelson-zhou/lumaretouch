// SPDX-License-Identifier: GPL-3.0-or-later
import type {AssociationRequest,AssociationReview,AssociationTarget} from '../people/associationProof';
import {validAssociationReview} from '../people/associationProof';
import {canonical} from './model';
import {sameFace} from '../people/transferProof';
import {OP,validDecorationCoverage,sameDecorationRender,decorationAck,sameDecorationAck,type DecorationCoverage,type DecorationVisual,type DecorationAck} from './transferModel';
import {validCollarboneVisualForTarget} from '../collarbone/transferModel';
export type DecorationCohortPlan={face_decoration_cohort?:boolean;persistent_association?:AssociationReview;association_source?:AssociationTarget;targets:AssociationTarget[];module_scope:string[]};
export type DecorationCohortTarget={path:string;source:boolean;coverage:DecorationCoverage;visual:DecorationVisual};
export function decorationCohortTargets(plan:DecorationCohortPlan):DecorationCohortTarget[]{
 if(plan.face_decoration_cohort!==true||!plan.association_source)return [];
 return [plan.association_source,...plan.targets].flatMap((row,index)=>row.association?.face_decoration_cohort&&row.association.face_decoration_cohort_visual?[{path:row.path,source:index===0,coverage:row.association.face_decoration_cohort,visual:row.association.face_decoration_cohort_visual}]:[]);
}
export function validDecorationCohort(plan:DecorationCohortPlan,request:AssociationRequest):boolean{
 const rows=plan.association_source?[plan.association_source,...plan.targets]:plan.targets;
 const required=Object.hasOwn(request.selection,OP)||plan.persistent_association?.intent.some(leaf=>leaf.op===OP)===true;
 const present=rows.some(row=>row.association&&(row.association.face_decoration_cohort!==undefined||row.association.face_decoration_cohort_visual!==undefined));
 if(plan.face_decoration_cohort!==true)return plan.face_decoration_cohort===undefined&&!required&&!present;
 if(!plan.association_source||!plan.persistent_association||!validAssociationReview(plan.persistent_association,request,plan.association_source,plan.targets)||rows.length<2||rows.length>16)return false;
 const ids=[request.source.document.document_id,...request.targets.map(t=>t.target.document.document_id)];
 return rows.length===ids.length&&rows.every((row,index)=>{
  const a=row.association;
  if(!a||row.blocked||row.document_id!==ids[index]||typeof row.revision!=='string'||!validDecorationCoverage(a.face_decoration_cohort,a.owner.source_proof)||!a.face_decoration_cohort.targets.some(t=>sameFace(t.face_ref,a.ref))||!validCollarboneVisualForTarget(a.face_decoration_cohort_visual,row.document_id,row.revision,a.owner.source_proof))return false;
  return [a.collarbone_visual,a.portrait_visual,a.eye_bag_cohort_visual].every(other=>!other||sameDecorationRender(a.face_decoration_cohort_visual!,Object.fromEntries(Object.entries(other).filter(([key])=>key!=='cohort_sha256')) as DecorationVisual));
 });
}
export const decorationCohortKey=(token:string,target:DecorationCohortTarget)=>JSON.stringify(['decoration-cohort',token,target]);
export const decorationCohortReady=(token:string,targets:DecorationCohortTarget[],ready:Record<string,boolean>)=>targets.length>=2&&targets.length<=16&&targets.every(t=>ready[decorationCohortKey(token,t)]===true);
export const decorationCohortAck=(targets:DecorationCohortTarget[]):DecorationAck[]=>decorationAck(targets.map(t=>t.visual));
export const sameDecorationCohortAck=(value:unknown,expected:DecorationAck[]|undefined)=>!!expected&&expected.length>=2&&sameDecorationAck(value,expected);

export async function decorationCohortAckDigest(ack:DecorationAck[]):Promise<string>{return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(ack)))),n=>n.toString(16).padStart(2,'0')).join('');}
