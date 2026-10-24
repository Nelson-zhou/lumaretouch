// SPDX-License-Identifier: GPL-3.0-or-later
import type {PeopleAction,PeopleResult,PeopleView,FaceRef} from '../people/model';
import {sourceProof} from '../cropTransfer/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {validEndpoint,validFaceRef,documentId,digest,type PeopleEndpointProof} from '../people/transferProof';
import {validCollarboneVisualForTarget,validCollarboneImage,verifyCollarboneImage} from '../collarbone/transferModel';
import {canonical,check,commandCurrent,targetReady,sameFace,type Recipe} from './model';
import {validDecorationCoverage,verifyDecorationCoverage,type DecorationCoverage,type DecorationVisual} from './transferModel';
export type DecorationAliasAction='face_decoration_alias_preview'|'face_decoration_alias_image'|'face_decoration_alias_confirm';
export type DecorationAliasReview={version:1;token:string;recipe:Recipe;owner:PeopleEndpointProof;face_ref:FaceRef;candidate_state_revision:number;members:{path:string;coverage:DecorationCoverage;visual:DecorationVisual}[];review_sha256:string};
export type DecorationAliasReceipt={command:PeopleAction;result:PeopleResult};
export const isDecorationAliasAction=(v:string):v is DecorationAliasAction=>['face_decoration_alias_preview','face_decoration_alias_image','face_decoration_alias_confirm'].includes(v);
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const revision=(v:unknown):v is string=>typeof v==='string'&&/^(0|[1-9]\d{0,15})$/.test(v)&&Number.isSafeInteger(Number(v));
export function validDecorationAliasReview(v:unknown,view:PeopleView|null,recipe:unknown):v is DecorationAliasReview{
 if(!view||!targetReady(view)||view.editing_target?.scope!=='face'||view.editing_target.target_id!==view.selected_face_id||!object(v)||!keys(v,['version','token','recipe','owner','face_ref','candidate_state_revision','members','review_sha256'])||v.version!==1||typeof v.token!=='string'||!/^[a-f0-9]{32}$/.test(v.token)||!digest(v.review_sha256)||!validEndpoint(v.owner)||!validFaceRef(v.face_ref)||!sameFace(v.face_ref,view.editing_target.face_ref))return false;
 try{if(canonical(check(v.recipe))!==canonical(check(recipe)))return false;}catch{return false;}
 const o=v.owner;
 if(o.people_scope!=='project'||o.document.document_id!==view.binding.document_id||o.document.epoch!==view.binding.document_epoch||o.document.revision!==view.binding.document_revision||o.state_revision!==view.revision||o.association_revision!==view.association_revision||o.source_proof.asset_sha256!==view.binding.asset_sha256||!Number.isSafeInteger(v.candidate_state_revision)||(v.candidate_state_revision as number)<=o.state_revision||(v.candidate_state_revision as number)>o.state_revision+2||!Array.isArray(v.members)||v.members.length<2||v.members.length>16)return false;
 const ids=new Set<string>();
 return v.members.every((m,index)=>{
  if(!object(m)||!keys(m,['path','coverage','visual'])||typeof m.path!=='string'||!m.path.trim()||m.path.includes('\0')||new TextEncoder().encode(m.path).length>4096||!object(m.visual)||!documentId(m.visual.document_id)||!revision(m.visual.revision)||ids.has(m.visual.document_id)||!sourceProof(m.visual.source_proof)||m.visual.source_proof.asset_sha256!==o.source_proof.asset_sha256||!validCollarboneVisualForTarget(m.visual,m.visual.document_id,m.visual.revision,m.visual.source_proof)||!validDecorationCoverage(m.coverage,m.visual.source_proof)||!m.coverage.targets.some(t=>sameFace(t.face_ref,v.face_ref as FaceRef))||index===0&&(m.visual.document_id!==o.document.document_id||m.visual.revision!==String(o.document.revision)||!sameSpillSourceProof(m.visual.source_proof,o.source_proof)))return false;
  // Scalar-only shared graph mutation: each member keeps its own colour/crop state.
  if(m.visual.before_state_sha256!==m.visual.candidate_state_sha256||canonical(m.visual.before_output_size)!==canonical(m.visual.after_output_size))return false;
  ids.add(m.visual.document_id);return true;
 });
}
export const decorationAliasAck=(r:DecorationAliasReview)=>({review_sha256:r.review_sha256,members:r.members.map(({visual:v})=>({document_id:v.document_id,revision:v.revision,before_sha256:v.before.sha256,after_sha256:v.after.sha256}))});
export const sameDecorationAliasAck=(v:unknown,r:DecorationAliasReview)=>canonical(v)===canonical(decorationAliasAck(r));
export const decorationAliasKey=(r:DecorationAliasReview,v:DecorationVisual)=>canonical([r.token,r.review_sha256,v]);
export async function verifyDecorationAliasReview(r:DecorationAliasReview):Promise<boolean>{
 // The engine digest covers Python-normalized recipe floats. Treat it as an opaque
 // frozen identity, not JS JSON equivalence; independently hash integer/string coverage.
 return digest(r.review_sha256)&&(await Promise.all(r.members.map(m=>verifyDecorationCoverage(m.visual,m.coverage)))).every(Boolean);
}
export function decorationAliasReceiptCurrent(command:PeopleAction,result:PeopleResult,view:PeopleView|null):boolean{
 return isDecorationAliasAction(command.action)&&aliasEchoMatches(command,result)&&result.success&&!result.outcome_unknown&&result.request_id===command.request_id&&result.action===command.action&&result.document_id===command.document_id&&!!view&&(command.action==='face_decoration_alias_confirm'?command.document_id===view.binding.document_id&&command.document_epoch===view.binding.document_epoch&&sameFace(command.target.face_ref,view.editing_target?.face_ref)&&view.binding.document_revision===command.document_revision+1:commandCurrent(command,view));
}
export async function decorationAliasImage(payload:unknown,review:DecorationAliasReview,document:string,side:'before'|'after'){
 const member=review.members.find(m=>m.visual.document_id===document),expected=member?.visual[side];
 if(!expected||!object(payload)||!keys(payload,['kind','token','document_id','side','sha256','review_sha256','image'])||payload.kind!=='face_decoration_alias_image'||payload.token!==review.token||payload.document_id!==document||payload.side!==side||payload.sha256!==expected.sha256||payload.review_sha256!==review.review_sha256||!validCollarboneImage(payload.image))throw Error('共享来源装饰图像身份不匹配');
 const image=payload.image;
 if(image.sha256!==expected.sha256||image.width!==expected.width||image.height!==expected.height||!await verifyCollarboneImage(image))throw Error('共享来源装饰图像内容不匹配');
 return image;
}
export function validDecorationAliasConfirmation(r:DecorationAliasReview,result:PeopleResult):boolean{
 const p=result.payload,o=r.owner,next=result.doc_state?.people;
 if(!object(p)||!keys(p,['kind','token','review_sha256','recipe','candidate_state_revision','ack','alias_members','history_review_sha256'])||p.kind!=='face_decoration_alias_confirm'||p.token!==r.token||p.review_sha256!==r.review_sha256||canonical(p.recipe)!==canonical(r.recipe)||p.candidate_state_revision!==r.candidate_state_revision||!digest(p.history_review_sha256)||!sameDecorationAliasAck(p.ack,r)||typeof result.batch_id!=='string'||!result.batch_id.trim()||new TextEncoder().encode(result.batch_id).length>128||/[\u0000-\u001f\u007f]/.test(result.batch_id)||!Array.isArray(p.alias_members)||p.alias_members.length!==r.members.length)return false;
 return p.alias_members.every((m,i)=>object(m)&&keys(m,['document_id','expected_revision','result_revision'])&&m.document_id===r.members[i].visual.document_id&&m.expected_revision===r.members[i].visual.revision&&revision(m.result_revision)&&BigInt(m.result_revision)===BigInt(r.members[i].visual.revision)+1n)
  &&result.protocol===1&&result.success&&result.outcome_unknown===false&&result.action==='face_decoration_alias_confirm'&&result.document_id===o.document.document_id&&!!next&&next.binding.document_id===o.document.document_id&&next.binding.document_epoch===o.document.epoch&&next.binding.asset_sha256===o.source_proof.asset_sha256&&next.binding.document_revision===o.document.revision+1&&next.revision===r.candidate_state_revision&&next.association_revision===o.association_revision;
}

export const aliasAck=decorationAliasAck;
export const validAliasReview=validDecorationAliasReview;
export const validAliasConfirmation=validDecorationAliasConfirmation;
export const aliasReceiptCurrent=decorationAliasReceiptCurrent;
export type DecorationAliasCommit={batchId:string;documentEpoch:string;requestId:string;review:DecorationAliasReview;command:PeopleAction;result:PeopleResult};
export function aliasEchoMatches(command:PeopleAction,result:PeopleResult):boolean{const {request_id:_id,...expected}=command;return result.protocol===1&&typeof result.success==='boolean'&&typeof result.outcome_unknown==='boolean'&&canonical(result.face_decoration_alias_request)===canonical(expected);}
export async function aliasHistoryDigest(review:DecorationAliasReview):Promise<string>{return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(aliasAck(review))))),n=>n.toString(16).padStart(2,'0')).join('');}
