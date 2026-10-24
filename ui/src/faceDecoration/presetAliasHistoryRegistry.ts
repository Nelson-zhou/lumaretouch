// SPDX-License-Identifier: GPL-3.0-or-later
import type {DecorationPresetV2} from './transferModel';
/** Exact safety classifications and outstanding-write fence only. No undo snapshots or independent history owner. */
export type DecorationPresetAliasMarker={version:1;review_sha256:string;preset_sha256:string;applies_sha256:string;current_document_id:string;member_count:number;selected_modules:string[]};
type Classification={memberCount:number|null;marker:DecorationPresetAliasMarker|null};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const token=(v:unknown):v is string=>typeof v==='string'&&!!v.trim()&&!/[\u0000-\u001f\u007f-\u009f]/.test(v)&&new TextEncoder().encode(v).length<=128;
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const same=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b);
export function validDecorationPresetAliasMarker(v:unknown):v is DecorationPresetAliasMarker{
 return object(v)&&Object.keys(v).sort().join('|')==='applies_sha256|current_document_id|member_count|preset_sha256|review_sha256|selected_modules|version'
  &&v.version===1&&hash(v.review_sha256)&&hash(v.preset_sha256)&&hash(v.applies_sha256)&&typeof v.current_document_id==='string'&&/^[a-f0-9]{32}$/.test(v.current_document_id)
  &&typeof v.member_count==='number'&&Number.isSafeInteger(v.member_count)&&v.member_count>=2&&v.member_count<=16
  &&Array.isArray(v.selected_modules)&&v.selected_modules.length>0&&v.selected_modules.length<=32&&v.selected_modules.every(token)&&new Set(v.selected_modules).size===v.selected_modules.length
  &&!v.selected_modules.includes('lnx.people_graph.v1');
}
export const decorationPresetAliasMarker=(review:DecorationPresetV2,scope:string[]):DecorationPresetAliasMarker=>({version:1,review_sha256:review.review_sha256,preset_sha256:review.preset_sha256,applies_sha256:review.applies_sha256,current_document_id:review.visual.document_id,member_count:review.members.length,selected_modules:[...scope]});
export function sameDecorationPresetAliasMarker(v:unknown,expected:DecorationPresetAliasMarker):v is DecorationPresetAliasMarker{
 return validDecorationPresetAliasMarker(v)&&v.review_sha256===expected.review_sha256&&v.preset_sha256===expected.preset_sha256&&v.applies_sha256===expected.applies_sha256
  &&v.current_document_id===expected.current_document_id&&v.member_count===expected.member_count&&same(v.selected_modules,expected.selected_modules);
}
let workspace:string|null=null,lastObservation=0;
const marked=new Map<string,Classification>(),key=(epoch:string,id:string)=>JSON.stringify([epoch,id]);
function retain(epoch:string,id:string,next:Classification){
 const k=key(epoch,id),prior=marked.get(k);
 marked.set(k,prior&&(prior.memberCount!==next.memberCount||!prior.marker||!next.marker||!sameDecorationPresetAliasMarker(next.marker,prior.marker))?{memberCount:null,marker:null}:next);
}
export function observeDecorationPresetAliasHistory(sync:unknown,observation?:number):void{
 if(observation!==undefined){if(!Number.isSafeInteger(observation)||observation<=lastObservation)return;lastObservation=observation;}
 if(!object(sync)||!token(sync.workspace_generation)||!Array.isArray(sync.batches))return;
 if(workspace!==sync.workspace_generation){
  const previousWorkspace=workspace;workspace=sync.workspace_generation;marked.clear();
  // Only a verified replacement of a known workspace retires old request fences.
  // Initial observation, document navigation and panel closure are not recovery.
  if(previousWorkspace!==null){
   const retiredWrites:{requestId:string;epoch:string}[]=[];
   for(const [requestId,epoch] of writes)if(epoch!==null&&epoch!==workspace){writes.delete(requestId);readbacks.delete(requestId);retiredWrites.push({requestId,epoch});}
   if(retiredWrites.length)for(const listener of listeners)listener();
   const replacement={previous:previousWorkspace,current:workspace,retiredWrites};
   for(const listener of workspaceListeners)listener(replacement);
  }
 }
 for(const row of sync.batches){
  if(!object(row)||!token(row.batch_id)||!Object.hasOwn(row,'face_decoration_preset_alias_review'))continue;
  const marker=row.face_decoration_preset_alias_review;
  const valid=validDecorationPresetAliasMarker(marker)&&row.targets===marker.member_count&&same(row.module_scope,['lnx.people_graph.v1'])
   &&!['face_style_alias_review','eye_bag_alias_review','eye_bag_batch_review','eye_bag_cohort_review','eye_bag_recovery_alias_review','eye_bag_preset_alias_review','face_decoration_alias_review','face_decoration_batch_review','face_decoration_cohort_review','face_decoration_support_alias_review'].some(field=>Object.hasOwn(row,field));
  retain(workspace,row.batch_id,valid?{memberCount:marker.member_count,marker:structuredClone(marker)}:{memberCount:null,marker:null});
 }
}
/** Called only after a correlated receipt has been validated, including known uncertain group IDs. */
export function registerDecorationPresetAliasReceipt(epoch:string,batchId:string,marker:DecorationPresetAliasMarker):boolean{
 if(!token(epoch)||!token(batchId)||!validDecorationPresetAliasMarker(marker)||workspace!==null&&workspace!==epoch)return false;
 if(workspace===null)workspace=epoch;
 retain(epoch,batchId,{memberCount:marker.member_count,marker:structuredClone(marker)});
 return marked.get(key(epoch,batchId))?.marker!==null;
}
export function decorationPresetAliasHistoryClass(batchId:string|undefined):Classification|undefined{return workspace&&batchId?marked.get(key(workspace,batchId)):undefined;}
// Request identities are retained across panel closure and document switches. An unknown write cannot release the editing fence.
export type DecorationPresetAliasWorkspaceReplacement={previous:string;current:string;retiredWrites:{requestId:string;epoch:string}[]};
const writes=new Map<string,string|null>(),listeners=new Set<()=>void>(),workspaceListeners=new Set<(value:DecorationPresetAliasWorkspaceReplacement)=>void>();
export const decorationPresetAliasWorkspace=()=>workspace;
export const subscribeDecorationPresetAliasWorkspace=(listener:(value:DecorationPresetAliasWorkspaceReplacement)=>void)=>{workspaceListeners.add(listener);return()=>{workspaceListeners.delete(listener);};};
export function setDecorationPresetAliasWritePending(requestId:string,pending:boolean,epoch?:string):void{
 const before=writes.size;if(pending)writes.set(requestId,token(epoch)?epoch:null);else writes.delete(requestId);
 if(before!==writes.size)for(const listener of listeners)listener();
}
export const decorationPresetAliasWritePending=()=>writes.size>0;
export const subscribeDecorationPresetAliasWrites=(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener);};};

/** Bounded post-terminal readback identity only. No pixels, editable state or undo snapshot. */
export type DecorationPresetAliasReadback={id:string;epoch:string;marker:DecorationPresetAliasMarker|null;batchId:string|null;reviewSha256:string;memberIds:string[]};
const readbacks=new Map<string,DecorationPresetAliasReadback>();
export const decorationPresetAliasReadback=():DecorationPresetAliasReadback|null=>{const value=readbacks.values().next().value;return value?structuredClone(value):null;};
export function retainDecorationPresetAliasReadback(value:DecorationPresetAliasReadback):void{
 if(!token(value.id)||!token(value.epoch)||!hash(value.reviewSha256)||value.memberIds.length<2||value.memberIds.length>16||new Set(value.memberIds).size!==value.memberIds.length
  ||value.memberIds.some(id=>!/^[a-f0-9]{32}$/.test(id))||workspace!==null&&workspace!==value.epoch||readbacks.size>0&&!readbacks.has(value.id)
  ||(value.marker===null?value.batchId!==null:!validDecorationPresetAliasMarker(value.marker)||!token(value.batchId)||value.marker.review_sha256!==value.reviewSha256||value.marker.member_count!==value.memberIds.length||value.marker.current_document_id!==value.memberIds[0]))throw Error('完整成员状态读取身份不完整');
 readbacks.set(value.id,structuredClone(value));setDecorationPresetAliasWritePending(value.id,true,value.epoch);
}
export function completeDecorationPresetAliasReadback(id:string):void{readbacks.delete(id);setDecorationPresetAliasWritePending(id,false);}
