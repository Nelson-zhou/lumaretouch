// SPDX-License-Identifier: GPL-3.0-or-later
export const OPERATION_ID='lnx.torso_length.v1' as const;
export const REQUIREMENT_ID='LNX-REF-PC-32473-C-f1662d2dec' as const;
/** Face, head, shoulders, arms, hands and hips must be observed, not inferred. */
export const ANCHORS=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24] as const;
export const TORSO_ANCHORS=[11,12,23,24] as const;
export const COLUMNS=['outer_left','inner_left','inner_right','outer_right','upper_zero','upper_plateau'] as const;
export const BOXES=['head_box','left_arm_box','right_arm_box'] as const;
export const CONFIRMATIONS={
 joints_visible:'双肩、双髋及头部、双臂、双手定位真实可见且归属正确',
 upright_not_foreshortened:'近直立、近正面，无明显侧身或透视缩短',
 ownership_confirmed:'完整头发、双臂、双手及全部过渡像素属于所选身体',
 complete_head_hair_reviewed:'头部框包含完整头部、头发和脸，不只是人脸框',
 complete_arms_hands_reviewed:'分别框入每侧完整手臂与手，未裁切或补齐隐藏轮廓',
 background_transition_reviewed:'已查看上方与两侧背景余量，接受背景和衣纹可能移动',
 no_occlusion_or_contacts:'无遮挡、交叉、他人接触或持物，不推测隐藏身体',
} as const;
export const FLAGS=Object.keys(CONFIRMATIONS) as (keyof typeof CONFIRMATIONS)[];
export type Column=typeof COLUMNS[number];
export type BoxKey=typeof BOXES[number];
export type Box=[number,number,number,number];
export type TorsoLengthRecipe={version:1;amount:number};
export type BodyRef={asset_sha256:string;body_instance_id:string;analysis_revision:number};
export type FaceRef={asset_sha256:string;face_instance_id:string;analysis_revision:number};
export type Point={index:number;x:number;y:number;z:number;visibility:number;presence:number};
export type Source={sha256:string;width:number;height:number;orientation:'exif_normalized_once'};
/** UI supplies reviewed geometry only. Canonical face facts are host-owned. */
export type ReviewSupport={version:1;method:'user-reviewed-visible-torso-length-support';confirmations:Record<keyof typeof CONFIRMATIONS,true>}&Record<Column,number>&Record<BoxKey,Box>;
export type Support=ReviewSupport&{associated_face_ref:FaceRef;associated_face_box:Box;associated_face_evidence_sha256:string};
export type BodyChoice={body_ref:BodyRef;enabled:boolean;operation_enabled:boolean;points:Point[];points_sha256:string;source:Source;reviewed:boolean;support:Support|null;association:null|{person_id:string;body_ref:BodyRef;people_association_revision:number;confirmation_revision:number}};
export type Binding={document_id:string;document_epoch:string;document_revision:number;asset_sha256:string};
export type TorsoLengthView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:TorsoLengthRecipe;refusals:{body_ref:BodyRef;operation_id?:string;reason:string}[]};
export type Action='recipe'|'support_review'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;body_ref:BodyRef;operation_id:typeof OPERATION_ID;action:Action;payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';request_id:string;protocol?:1;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:TorsoLengthView};
export type Transport={send:(request:Request)=>Promise<Result>;status:(requestId:string)=>Promise<Result>};
export function neutral():TorsoLengthRecipe{return {version:1,amount:0};}
export function check(value:TorsoLengthRecipe):TorsoLengthRecipe{
 if(!value||Object.keys(value).sort().join(',')!=='amount,version'||value.version!==1||typeof value.amount!=='number'||!Number.isFinite(value.amount)||Math.abs(value.amount)>1)throw Error('上身长度参数无效，本产品原创范围为 -100 到 100。');
 return {...value};
}
export function adjust(value:TorsoLengthRecipe,amount:number):TorsoLengthRecipe{return check({...check(value),amount});}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(view:TorsoLengthView):string{return `${view.binding.document_epoch}:${view.binding.document_id}:${refKey(view.selected_body_ref)}`;}
export function observed(p:Point|undefined):boolean{return !!p&&[p.x,p.y,p.z,p.visibility,p.presence].every(n=>typeof n==='number'&&Number.isFinite(n))&&p.x>0&&p.x<1&&p.y>0&&p.y<1&&p.visibility>=.8&&p.visibility<=1&&p.presence>=.8&&p.presence<=1;}
export function canReview(body:BodyChoice):boolean{return body.points.length===33&&ANCHORS.every(i=>body.points[i]?.index===i&&observed(body.points[i]))&&!!body.association&&refKey(body.association.body_ref)===refKey(body.body_ref);}
export function request(view:TorsoLengthView,action:Action,payload:Record<string,unknown>,gesture_id:string):Request{
 if(!view.selected_body_ref)throw Error('请先选择实际检测到并明确关联人物的身体。');
 return {request_id:crypto.randomUUID(),gesture_id,document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,document_revision:view.binding.document_revision,state_revision:view.state_revision,association_revision:view.association_revision,people_association_revision:view.people_association_revision,body_graph_sha256:view.body_graph_sha256,people_graph_sha256:view.people_graph_sha256,body_ref:{...view.selected_body_ref},operation_id:OPERATION_ID,action,payload:structuredClone(payload)};
}
const normalized=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)&&n>0&&n<1;
export function checkReviewSupport(value:ReviewSupport):ReviewSupport{
 if(!value||Object.keys(value).sort().join(',')!==['version','method','confirmations',...COLUMNS,...BOXES].sort().join(',')||value.version!==1||value.method!=='user-reviewed-visible-torso-length-support'||COLUMNS.some(k=>!normalized(value[k]))||!(value.outer_left<value.inner_left&&value.inner_left<value.inner_right&&value.inner_right<value.outer_right&&value.upper_zero<value.upper_plateau))throw Error('请独立点选完整、有序的两侧和上方背景过渡边界。');
 for(const key of BOXES){const b=value[key];if(!Array.isArray(b)||b.length!==4||!b.every(normalized)||!(b[0]<b[2]&&b[1]<b[3]&&value.inner_left<b[0]&&b[2]<value.inner_right&&value.upper_plateau<b[1]))throw Error('完整头部、手臂与手的框必须位于两侧内界之间及上方移动起始线以下。');}
 if(!value.confirmations||Object.keys(value.confirmations).sort().join(',')!==[...FLAGS].sort().join(',')||FLAGS.some(k=>value.confirmations[k]!==true))throw Error('请逐项完成当前来源图的可见性、归属和背景复核。');
 return structuredClone(value);
}
