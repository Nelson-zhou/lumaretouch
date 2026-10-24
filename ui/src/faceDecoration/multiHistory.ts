// SPDX-License-Identifier: GPL-3.0-or-later
import {validDecorationBatchMarker,type DecorationBatchMarker} from './batchHistoryRegistry';
export type DecorationHistoryField='face_decoration_cohort_review'|'face_decoration_alias_review';
export type DecorationHistory={field:DecorationHistoryField;marker:DecorationBatchMarker|null;memberCount:number|null};
const fields:DecorationHistoryField[]=['face_decoration_cohort_review','face_decoration_alias_review'];
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const token=(v:unknown):v is string=>typeof v==='string'&&!!v.trim()&&!/[\u0000-\u001f\u007f]/.test(v)&&new TextEncoder().encode(v).length<=128;
let epoch:string|null=null,last=0;const entries=new Map<string,DecorationHistory>();
export function observeDecorationMultiHistory(sync:unknown,observation?:number){
 if(observation!==undefined){if(!Number.isSafeInteger(observation)||observation<=last)return;last=observation;}
 if(!object(sync)||!token(sync.workspace_generation))return;
 if(epoch!==sync.workspace_generation){epoch=sync.workspace_generation;entries.clear();}
 if(!Array.isArray(sync.batches))return;
 for(const row of sync.batches){if(!object(row)||!token(row.batch_id))continue;
  const found=fields.filter(k=>Object.hasOwn(row,k));if(!found.length)continue;
  const field=found[0],marker=row[field];
  const incompatible=['face_decoration_preset_alias_review','face_decoration_support_alias_review','face_decoration_batch_review','face_style_alias_review','eye_bag_alias_review','eye_bag_preset_alias_review','eye_bag_recovery_alias_review','eye_bag_batch_review'];
  const valid=found.length===1&&!incompatible.some(k=>Object.hasOwn(row,k))&&(field==='face_decoration_cohort_review'||!Object.hasOwn(row,'eye_bag_cohort_review'))&&validDecorationBatchMarker(marker)&&marker.member_count>=2&&row.targets===marker.member_count&&JSON.stringify(row.module_scope)===JSON.stringify(['lnx.people_graph.v1']);
  registerDecorationMultiHistory(epoch!,row.batch_id,field,valid?marker:null);
 }
}
export function registerDecorationMultiHistory(workspace:string,id:string,field:DecorationHistoryField,marker:DecorationBatchMarker|null):boolean{
 if(!token(workspace)||!token(id)||!fields.includes(field)||marker!==null&&(!validDecorationBatchMarker(marker)||marker.member_count<2)||epoch!==null&&epoch!==workspace)return false;if(epoch===null)epoch=workspace;
 const prior=entries.get(id),next={field,marker:marker?{...marker}:null,memberCount:marker?.member_count??null};
 if(prior&&(prior.field!==field||prior.marker?.version!==marker?.version||prior.marker?.review_sha256!==marker?.review_sha256||prior.marker?.member_count!==marker?.member_count)){entries.set(id,{field,marker:null,memberCount:null});return false;}
 entries.set(id,next);return marker!==null;
}
export const decorationMultiHistory=(id:string|undefined)=>id?entries.get(id):undefined;
