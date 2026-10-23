// SPDX-License-Identifier: GPL-3.0-or-later
export type Side='left'|'right';
export type Key='square'|'width';
export type Pair={linked:boolean;left:number;right:number};
export type ShoulderRecipe={version:1;square:Pair;width:Pair};
export type BodyRef={asset_sha256:string;body_instance_id:string;analysis_revision:number};
export type Point={index:number;x:number;y:number;z:number;visibility:number;presence:number};
export type Binding={document_id:string;document_epoch:string;document_revision:number;asset_sha256:string};
export type BodyChoice={unapplied_operations?:string[];shoulder_enabled?:boolean;body_ref:BodyRef;enabled:boolean;points:Point[];points_sha256:string;source:{sha256:string;width:number;height:number;orientation:'exif_normalized_once'};reviewed:boolean;association:null|{person_id:string;body_ref:BodyRef;people_association_revision:number;confirmation_revision:number}};
export type ShoulderView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:ShoulderRecipe;persons:Record<string,{anonymous:true}>;refusals:{body_ref:BodyRef;reason:string}[];analysis_run:null|{detector_limit:number;limit_reached:boolean;census_complete:false}};
export const IDS={square:'LNX-REF-PC-32473-C-1b5aae1f25',width:'LNX-REF-PC-32473-C-57c31b17e1'} as const;
export const ANCHORS=[0,7,8,11,12,13,14,23,24] as const;
export const LABELS={square:'直角肩',width:'肩膀宽度'} as const;
export function neutral():ShoulderRecipe{return {version:1,square:{linked:true,left:0,right:0},width:{linked:true,left:0,right:0}};}
export function check(value:ShoulderRecipe):ShoulderRecipe {
  if(!value||value.version!==1||Object.keys(value).sort().join(',')!=='square,version,width')throw Error('肩形参数版本不匹配');
  for(const key of ['square','width'] as const){const p=value[key];if(!p||typeof p.linked!=='boolean'||Object.keys(p).sort().join(',')!=='left,linked,right')throw Error('肩形左右参数不完整');for(const side of ['left','right'] as const){const n=p[side];if(typeof n!=='number'||!Number.isFinite(n)||n<(key==='square'?0:-1)||n>1)throw Error('肩形数值超出本产品范围');}}
  return {version:1,square:{...value.square},width:{...value.width}};
}
export function adjust(value:ShoulderRecipe,key:Key,side:Side,amount:number):ShoulderRecipe{const out=check(value);for(const target of out[key].linked?(['left','right'] as const):[side])out[key][target]=amount;return check(out);}
export function link(value:ShoulderRecipe,key:Key,linked:boolean):ShoulderRecipe{const out=check(value);out[key].linked=linked;return out;}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(view:ShoulderView):string{return `${view.binding.document_epoch}:${view.binding.document_id}:${refKey(view.selected_body_ref)}`;}
export function observed(point:Point|undefined):boolean{return !!point&&Number.isFinite(point.x)&&Number.isFinite(point.y)&&point.x>0&&point.x<1&&point.y>0&&point.y<1&&point.visibility>=.8&&point.presence>=.8;}
export function canReview(body:BodyChoice):boolean{return body.points.length===33&&ANCHORS.every(i=>body.points[i]?.index===i&&observed(body.points[i]));}
export type Action='recipe'|'review'|'associate'|'unlink'|'body_status'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_ref:BodyRef;action:Action;payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';protocol?:1;request_id:string;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:ShoulderView};
export type Transport={send:(request:Request)=>Promise<Result>;status:(requestId:string)=>Promise<Result>};
export function request(view:ShoulderView,action:Action,payload:Record<string,unknown>,gesture_id:string):Request{if(!view.selected_body_ref)throw Error('请先选定实际检测到的身体');return {document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,document_revision:view.binding.document_revision,state_revision:view.state_revision,association_revision:view.association_revision,people_association_revision:view.people_association_revision,body_ref:{...view.selected_body_ref},action,payload,gesture_id,request_id:crypto.randomUUID()};}
