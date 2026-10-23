// SPDX-License-Identifier: GPL-3.0-or-later
export const OPERATION_ID='lnx.leg_length.v1' as const;
export const IDS={overall:'LNX-REF-PC-32473-C-d79658697a',thigh:'LNX-REF-PC-32473-C-eefc19db17',calf:'LNX-REF-PC-32473-C-17fb085b4c'} as const;
export const ANCHORS=[23,24,25,26,27,28,29,30,31,32] as const;
export const LABELS={overall:'长腿（同时设置）',thigh:'大腿长度',calf:'小腿长度'} as const;
export const COLUMNS=['outer_left','inner_left','inner_right','outer_right','foot_end','support_end'] as const;
export const FLAGS=['joints_visible','separate_legs','not_foreshortened','ownership_confirmed','background_support_reviewed','foot_contours_visible','torso_transition_reviewed'] as const;
export type Key=keyof typeof IDS;
export type LegLengthRecipe={version:1;thigh:number;calf:number};
export type BodyRef={asset_sha256:string;body_instance_id:string;analysis_revision:number};
export type Point={index:number;x:number;y:number;z:number;visibility:number;presence:number};
export type Source={sha256:string;width:number;height:number;orientation:'exif_normalized_once'};
export type Side='left'|'right';
export type Column=typeof COLUMNS[number];
export type Support={version:1;method:'user-reviewed-visible-length-support';legs:Record<Side,Record<Column,number>>}&Record<typeof FLAGS[number],true>;
export type BodyChoice={body_ref:BodyRef;enabled:boolean;operation_enabled:boolean;points:Point[];points_sha256:string;source:Source;reviewed:boolean;support:Support|null;association:null|{person_id:string;body_ref:BodyRef;people_association_revision:number;confirmation_revision:number}};
export type Binding={document_id:string;document_epoch:string;document_revision:number;asset_sha256:string};
export type LegLengthView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:LegLengthRecipe;refusals:{body_ref:BodyRef;operation_id?:string;reason:string}[]};
export type Action='recipe'|'support_review'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;body_ref:BodyRef;operation_id:typeof OPERATION_ID;action:Action;payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';request_id:string;protocol?:1;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:LegLengthView};
export type Transport={send:(request:Request)=>Promise<Result>;status:(requestId:string)=>Promise<Result>};
export function neutral():LegLengthRecipe{return {version:1,thigh:0,calf:0};}
export function check(value:LegLengthRecipe):LegLengthRecipe{
 if(!value||Object.keys(value).sort().join(',')!=='calf,thigh,version'||value.version!==1)throw Error('腿长参数格式不匹配，整体调节不是额外强度。');
 for(const key of ['thigh','calf'] as const)if(typeof value[key]!=='number'||!Number.isFinite(value[key])||(value[key]<0||value[key]>1))throw Error('腿长数值超出本产品范围。');
 return {...value};
}
export function adjust(value:LegLengthRecipe,key:Key,amount:number):LegLengthRecipe{const out=check(value);if(key==='overall'){out.thigh=amount;out.calf=amount;}else if(key==='thigh'||key==='calf'){out[key]=amount;}else throw Error('未知腿长控件。');return check(out);}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(view:LegLengthView):string{return `${view.binding.document_epoch}:${view.binding.document_id}:${refKey(view.selected_body_ref)}`;}
export function observed(p:Point|undefined):boolean{return !!p&&[p.x,p.y,p.z,p.visibility,p.presence].every(Number.isFinite)&&p.x>0&&p.x<1&&p.y>0&&p.y<1&&p.visibility>=.8&&p.visibility<=1&&p.presence>=.8&&p.presence<=1;}
export function canReview(body:BodyChoice):boolean{return body.points.length===33&&ANCHORS.every(i=>body.points[i]?.index===i&&observed(body.points[i]));}
export function request(view:LegLengthView,action:Action,payload:Record<string,unknown>,gesture_id:string):Request{
 if(!view.selected_body_ref)throw Error('请先选择实际检测到的身体。');
 return {request_id:crypto.randomUUID(),gesture_id,document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,document_revision:view.binding.document_revision,state_revision:view.state_revision,association_revision:view.association_revision,people_association_revision:view.people_association_revision,body_graph_sha256:view.body_graph_sha256,people_graph_sha256:view.people_graph_sha256,body_ref:{...view.selected_body_ref},operation_id:OPERATION_ID,action,payload};
}

export function checkSupport(value:Support):Support{
 if(!value||Object.keys(value).sort().join(',')!==['version','method','legs',...FLAGS].sort().join(',')||value.version!==1||value.method!=='user-reviewed-visible-length-support'||FLAGS.some(k=>value[k]!==true)||!value.legs||Object.keys(value.legs).sort().join(',')!=='left,right')throw Error('请复核全部可见关节、轮廓及过渡区。');
 for(const side of ['left','right'] as const){const s=value.legs[side];if(!s||Object.keys(s).sort().join(',')!==[...COLUMNS].sort().join(',')||COLUMNS.some(k=>typeof s[k]!=='number'||!Number.isFinite(s[k])||s[k]<=0||s[k]>=1)||!(s.outer_left<s.inner_left&&s.inner_left<s.inner_right&&s.inner_right<s.outer_right&&s.foot_end<s.support_end))throw Error('可见轮廓包络及渐隐边界必须完整有序。');}
 const a=value.legs.left,b=value.legs.right;if(!(a.outer_right<b.outer_left||b.outer_right<a.outer_left))throw Error('两腿支撑重叠，不支持交叉或无法分离的腿。');return structuredClone(value);
}
