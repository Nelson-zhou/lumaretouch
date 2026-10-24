import type {PortraitCohortVisual} from '../portraitCohort/model';
import {validFaceStyleRecipe,type FaceStyleRecipe} from '../faceStyle/model';
import {sameFaceStyleRecipe,validFaceStyleSelection} from '../faceStyle/batchModel';
import type {CollarboneVisual} from '../collarbone/transferModel';
import type {CollarboneCoverage} from './transferProof';
import type {FaceRef, ParameterValue} from './model';
import {digest, validEndpoint, validFaceRef, sameFace, sameEndpoint, type PeopleEndpointProof} from './transferProof';
export type AssociationMember={document_id:string;scope_id:string;original_sha256:string;ref:FaceRef};
export type AssociationIntent={op:string;path:string;value:ParameterValue};
export type AssociationCapsule={version:1;association_id:string;generation:string;local_document_id:string;members:AssociationMember[];intent:AssociationIntent[]};
export type AssociationRequest={target_policy:'persistent_association';operation:'create'|'patch'|'unlink';association_id:string;source_ref:FaceRef;
  selection:Record<string,string[]>;face_style?:FaceStyleRecipe;source:PeopleEndpointProof;targets:{target:PeopleEndpointProof;target_refs:FaceRef[]}[]};
export type AssociationReview={version:1;operation:AssociationRequest['operation'];association_id:string;generation:string;members:AssociationMember[];intent:AssociationIntent[]};
export type AssociationTarget={index:number|null;path:string;document_id:string;revision?:string;blocked?:string|null;
  association?:{owner:PeopleEndpointProof;ref:FaceRef;candidate_sha256:string;person_id:string;collarbone_coverage?:CollarboneCoverage;collarbone_visual?:CollarboneVisual;portrait_visual?:PortraitCohortVisual}};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const token=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_.:-]{1,128}$/.test(v);
const keys=(v:Record<string,unknown>, names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
export function validAssociationContent(v:unknown):v is AssociationReview{
  if(!object(v)||v.version!==1||!token(v.association_id)||!digest(v.generation)||!Array.isArray(v.members)||v.members.length<2||v.members.length>16
    ||!Array.isArray(v.intent)||v.intent.length<1||v.intent.length>256)return false;
  const ids=new Set<string>(),scopes=new Set<string>(),leaves=new Set<string>();
  for(const m of v.members){if(!object(m)||!keys(m,['document_id','scope_id','original_sha256','ref'])||typeof m.document_id!=='string'
    ||!/^[a-f0-9]{32}$/.test(m.document_id)||(m.scope_id!=='project'&&m.scope_id!==m.document_id)||!digest(m.original_sha256)||!validFaceRef(m.ref)
    ||ids.has(m.document_id)||scopes.has(m.scope_id))return false;ids.add(m.document_id);scopes.add(m.scope_id);}
  for(const leaf of v.intent){if(!object(leaf)||!keys(leaf,['op','path','value'])||!token(leaf.op)||typeof leaf.path!=='string'||!leaf.path.startsWith('/')||leaf.path.length>512
    ||!(['boolean','string'].includes(typeof leaf.value)||typeof leaf.value==='number'&&Number.isFinite(leaf.value)))return false;
    const key=JSON.stringify([leaf.op,leaf.path]);if(leaves.has(key))return false;leaves.add(key);}
  return true;
}
export function validCapsule(v:unknown):v is AssociationCapsule{return object(v)&&keys(v,['version','association_id','generation','local_document_id','members','intent'])
  &&validAssociationContent(v)&&typeof v.local_document_id==='string'&&v.members.some(m=>m.document_id===v.local_document_id);}
export function sameAssociationRequest(v:unknown,e:AssociationRequest):boolean{
  const named=e.face_style!==undefined;
  if(named?e.operation==='unlink'||!validFaceStyleRecipe(e.face_style)||!validFaceStyleSelection(e.selection):Object.hasOwn(e,'face_style'))return false;
  if(!object(v)||!keys(v,['target_policy','operation','association_id','source_ref','selection','source','targets',...(named?['face_style']:[])])||v.target_policy!=='persistent_association'
    ||v.operation!==e.operation||!['create','patch','unlink'].includes(e.operation)||v.association_id!==e.association_id||!token(e.association_id)
    ||!validFaceRef(v.source_ref)||!sameFace(v.source_ref,e.source_ref)||!validEndpoint(v.source)||!sameEndpoint(v.source,e.source)
    ||v.source_ref.asset_sha256!==v.source.source_proof.asset_sha256||!object(v.selection)||!object(e.selection)
    ||!Array.isArray(v.targets)||v.targets.length<1||v.targets.length>15||v.targets.length!==e.targets.length)return false;
  if(named&&(!sameFaceStyleRecipe(v.face_style,e.face_style!)||!validFaceStyleSelection(v.selection)))return false;
  const ops=Object.keys(e.selection).sort();if(JSON.stringify(Object.keys(v.selection).sort())!==JSON.stringify(ops)|| (e.operation==='unlink'?ops.length!==0:ops.length===0))return false;
  for(const op of ops){const paths=v.selection[op],expected=e.selection[op];if(!Array.isArray(paths)||!paths.length||new Set(paths).size!==paths.length
    ||!paths.every(p=>typeof p==='string'&&p.startsWith('/'))||JSON.stringify([...paths].sort())!==JSON.stringify([...expected].sort()))return false;}
  const ids=new Set([e.source.document.document_id]),scopes=new Set([e.source.people_scope]);
  for(const row of v.targets){if(!object(row)||!keys(row,['target','target_refs'])||!validEndpoint(row.target)||!Array.isArray(row.target_refs)||row.target_refs.length!==1
    ||!validFaceRef(row.target_refs[0])||row.target_refs[0].asset_sha256!==row.target.source_proof.asset_sha256||row.target.document.epoch!==e.source.document.epoch
    ||ids.has(row.target.document.document_id)||scopes.has(row.target.people_scope))return false;
    const actualTarget=row.target;
    const expected=e.targets.find(t=>t.target.document.document_id===actualTarget.document.document_id);
    if(!expected||expected.target_refs.length!==1||!sameEndpoint(row.target,expected.target)||!sameFace(row.target_refs[0],expected.target_refs[0]))return false;
    ids.add(row.target.document.document_id);scopes.add(row.target.people_scope);}
  return true;
}
export function validAssociationReview(v:unknown,request:AssociationRequest,source:AssociationTarget,targets:AssociationTarget[]):v is AssociationReview{
  if(!object(v)||!keys(v,['version','operation','association_id','generation','members','intent'])||!validAssociationContent(v)
    ||v.operation!==request.operation||v.association_id!==request.association_id||!sameAssociationRequest(request,request)
    ||v.members.length!==request.targets.length+1||targets.length!==request.targets.length)return false;
  const endpoints=[{target:request.source,target_refs:[request.source_ref]},...request.targets],reviews=[source,...targets];
  for(const endpoint of endpoints){const proof=endpoint.target,ref=endpoint.target_refs[0],m=v.members.find(m=>m.document_id===proof.document.document_id);
    const target=reviews.find(t=>t.document_id===proof.document.document_id),a=target?.association;
    if(!m||m.scope_id!==proof.people_scope||m.original_sha256!==proof.source_proof.original_sha256||!sameFace(m.ref,ref)||!target||target.blocked
      ||typeof target.path!=='string'||!Number.isInteger(target.index)||(target.index??-1)<0
      ||target.revision!==String(proof.document.revision)||!a||!object(a)||!keys(a,['owner','ref','candidate_sha256','person_id',...((a.collarbone_coverage!==undefined||a.collarbone_visual!==undefined)?['collarbone_coverage','collarbone_visual']:[]),...(a.portrait_visual!==undefined?['portrait_visual']:[])])||!validEndpoint(a.owner)||!sameEndpoint(a.owner,proof)||!validFaceRef(a.ref)||!sameFace(a.ref,ref)
      ||!digest(a.candidate_sha256)||!token(a.person_id))return false;}
  if(request.operation==='create'&&v.intent.length!==Object.values(request.selection).reduce((n,paths)=>n+paths.length,0))return false;
  if(request.operation!=='unlink')for(const [op,paths] of Object.entries(request.selection))for(const path of paths)if(!v.intent.some(leaf=>leaf.op===op&&leaf.path===path))return false;
  return new Set(reviews.map(t=>t.document_id)).size===endpoints.length;
}
/** Receipt equality is content-based; a new generation cannot stand in for the reviewed cohort. */
export function sameAssociationReview(value:unknown,expected:AssociationReview):boolean{
  if(!object(value)||!keys(value,['version','operation','association_id','generation','members','intent'])||!validAssociationContent(value)
    ||value.operation!==expected.operation||value.association_id!==expected.association_id||value.generation!==expected.generation
    ||value.members.length!==expected.members.length||value.intent.length!==expected.intent.length)return false;
  return expected.members.every(member=>value.members.some(m=>m.document_id===member.document_id&&m.scope_id===member.scope_id
    &&m.original_sha256===member.original_sha256&&sameFace(m.ref,member.ref)))
    &&expected.intent.every(leaf=>value.intent.some(v=>v.op===leaf.op&&v.path===leaf.path&&v.value===leaf.value));
}
