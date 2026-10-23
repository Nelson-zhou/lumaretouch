// SPDX-License-Identifier: GPL-3.0-or-later
export const OPERATION_ID='lnx.neck_shape.v1' as const;
export const IDS={length:'LNX-REF-PC-32473-C-903ca47834',width:'LNX-REF-PC-32473-C-614d728bcd'} as const;
export const ANCHORS=[0,7,8,11,12] as const;
export const CONFIRMATIONS={bounds_visible:'真实可见的脖子上下界',contours_visible:'五站双侧轮廓真实可见',not_occluded:'无衣领、头发或物体遮挡脖子',not_foreshortened:'无严重透视或侧身',ownership_confirmed:'身体、头发、脸部与过渡区归属明确',transition_reviewed:'接受过渡范围内背景和衣纹可能移动',complete_head_hair_reviewed:'完整头部和头发都在头部框内，非仅脸框'} as const;
export type NeckRecipe={version:1;length:number;width:{linked:boolean;left:number;right:number}};
export type Box=[number,number,number,number];
export type Support={version:1;upper:number;lower:number;center_x:number;negative:number[];positive:number[];head_box:Box;transition_box:Box;anatomical_left:'negative'|'positive';exclusions:Box[];confirmations:Record<keyof typeof CONFIRMATIONS,true>};
export type {BodyRef,Binding,Point,Source} from '../waistShape/model';
import type {BodyRef,Binding,BodyChoice as CommonBody} from '../waistShape/model';
export type BodyChoice=Omit<CommonBody,'support'>&{support:Support|null};
export type NeckView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:NeckRecipe;refusals:{body_ref:BodyRef;operation_id?:string;reason:string}[]};
export type Action='recipe'|'support_review'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;body_ref:BodyRef;operation_id:typeof OPERATION_ID;action:Action;payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';request_id:string;protocol?:1;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:NeckView};
export type Transport={send:(r:Request)=>Promise<Result>;status:(id:string)=>Promise<Result>};
export function neutral():NeckRecipe{return {version:1,length:0,width:{linked:true,left:0,right:0}};}
export function check(v:NeckRecipe):NeckRecipe{if(!v||Object.keys(v).sort().join(',')!=='length,version,width'||v.version!==1||!v.width||Object.keys(v.width).sort().join(',')!=='left,linked,right'||typeof v.width.linked!=='boolean'||[v.length,v.width.left,v.width.right].some(n=>typeof n!=='number'||!Number.isFinite(n)||Math.abs(n)>1))throw Error('颈部参数无效，本产品原创范围 -100 到 100。');return structuredClone(v);}
export function adjust(v:NeckRecipe,key:'length'|'width',n:number,side:'left'|'right'='left'):NeckRecipe{v=check(v);if(key==='length')v.length=n;else for(const k of v.width.linked?['left','right'] as const:[side])v.width[k]=n;return check(v);}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(v:NeckView):string{return `${v.binding.document_epoch}:${v.binding.document_id}:${refKey(v.selected_body_ref)}`;}
export function request(v:NeckView,action:Action,payload:Record<string,unknown>,gesture_id:string):Request{if(!v.selected_body_ref)throw Error('请先选择真实身体');return {request_id:crypto.randomUUID(),gesture_id,document_id:v.binding.document_id,document_epoch:v.binding.document_epoch,document_revision:v.binding.document_revision,state_revision:v.state_revision,association_revision:v.association_revision,people_association_revision:v.people_association_revision,body_graph_sha256:v.body_graph_sha256,people_graph_sha256:v.people_graph_sha256,body_ref:{...v.selected_body_ref},operation_id:OPERATION_ID,action,payload:structuredClone(payload)};}
