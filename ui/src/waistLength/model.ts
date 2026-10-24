// SPDX-License-Identifier: GPL-3.0-or-later
export const OPERATION_ID='lnx.waist_length.v1' as const;
export const REQUIREMENT_ID='LNX-REF-PC-32473-C-5d33f285bb' as const;
/** Face, head, shoulders, arms, hands and hips must be observed, not inferred. */
export const ANCHORS=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24] as const;
export const CONTEXT_ANCHORS=[11,12,23,24] as const;
export const COLUMNS=['outer_left','inner_left','inner_right','outer_right','upper_zero','upper_plateau'] as const;
export const BOXES=['head_box','left_arm_box','right_arm_box'] as const;
/** These are explicit source/screen coordinates, never inferred pose joints. */
export const WAIST_MARKERS=['waist_upper_left','waist_upper_right','waist_lower_left','waist_lower_right'] as const;
export const CONFIRMATIONS={
 joints_visible:'双肩、双髋及头部、双臂、双手定位真实可见且归属正确',
 upright_not_foreshortened:'近直立、近正面，无明显侧身或透视缩短',
 ownership_confirmed:'完整头发、双臂、双手及全部过渡像素属于所选身体',
 complete_head_hair_reviewed:'头部框包含完整头部、头发和脸，不只是人脸框',
 complete_arms_hands_reviewed:'分别框入每侧完整手臂与手，未裁切或补齐隐藏轮廓',
 background_transition_reviewed:'已查看上方与两侧背景余量，接受背景和衣纹可能移动',
 no_occlusion_or_contacts:'无遮挡、交叉、他人接触或持物，不推测隐藏身体',
 bilateral_waist_endpoints_visible:'画面左右两侧的腰部上、下端点均清晰可见，不把髋点或衣服猜测位置当成腰点',
 waist_endpoints_manually_marked:'四个腰部端点均由我在当前来源图上分别测量，没有推断或沿用其他工具定位',
 complete_upper_trunk_reviewed:'已检查上腰线以上完整上躯干、肩颈、头发及双臂属于该人物，轮廓均在移动内界之间',
} as const;
export const FLAGS=Object.keys(CONFIRMATIONS) as (keyof typeof CONFIRMATIONS)[];
export type Column=typeof COLUMNS[number];
export type BoxKey=typeof BOXES[number];
export type Box=[number,number,number,number];
export type WaistMarker=typeof WAIST_MARKERS[number];
export type MarkedPoint=[number,number];
export type WaistLengthRecipe={version:1;amount:number};
export type BodyRef={asset_sha256:string;body_instance_id:string;analysis_revision:number};
export type FaceRef={asset_sha256:string;face_instance_id:string;analysis_revision:number};
export type Point={index:number;x:number;y:number;z:number;visibility:number;presence:number};
export type Source={sha256:string;width:number;height:number;orientation:'exif_normalized_once'};
/** UI supplies reviewed geometry only. Canonical face facts are host-owned. */
export type ReviewSupport={version:1;method:'user-reviewed-visible-waist-length-support';confirmations:Record<keyof typeof CONFIRMATIONS,true>}&Record<Column,number>&Record<BoxKey,Box>&Record<WaistMarker,MarkedPoint>;
export type Support=ReviewSupport&{associated_face_ref:FaceRef;associated_face_box:Box;associated_face_evidence_sha256:string};
export type BodyChoice={body_ref:BodyRef;enabled:boolean;operation_enabled:boolean;points:Point[];points_sha256:string;source:Source;reviewed:boolean;support:Support|null;association:null|{person_id:string;body_ref:BodyRef;people_association_revision:number;confirmation_revision:number}};
export type Binding={document_id:string;document_epoch:string;document_revision:number;asset_sha256:string};
export type Publication={request_id:string;rendered:boolean;unapplied_reason:string|null};
export type WaistLengthView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:WaistLengthRecipe;refusals:{body_ref:BodyRef;operation_id?:string;reason:string}[];publication?:Publication};
export type Action='recipe'|'support_review'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;body_ref:BodyRef;operation_id:typeof OPERATION_ID;action:Action;payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';request_id:string;protocol?:1;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:WaistLengthView};
export type Transport={send:(request:Request)=>Promise<Result>;status:(requestId:string)=>Promise<Result>};
export function neutral():WaistLengthRecipe{return {version:1,amount:0};}
export function check(value:WaistLengthRecipe):WaistLengthRecipe{
 if(!value||Object.keys(value).sort().join(',')!=='amount,version'||value.version!==1||typeof value.amount!=='number'||!Number.isFinite(value.amount)||Math.abs(value.amount)>1)throw Error('腰部长度参数无效，本产品原创范围为 -100 到 100。');
 return {...value};
}
export function adjust(value:WaistLengthRecipe,amount:number):WaistLengthRecipe{return check({...check(value),amount});}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(view:WaistLengthView):string{return `${view.binding.document_epoch}:${view.binding.document_id}:${refKey(view.selected_body_ref)}`;}
export function observed(p:Point|undefined):boolean{return !!p&&[p.x,p.y,p.z,p.visibility,p.presence].every(n=>typeof n==='number'&&Number.isFinite(n))&&p.x>0&&p.x<1&&p.y>0&&p.y<1&&p.visibility>=.8&&p.visibility<=1&&p.presence>=.8&&p.presence<=1;}
export function canReview(body:BodyChoice):boolean{return body.points.length===33&&ANCHORS.every(i=>body.points[i]?.index===i&&observed(body.points[i]))&&!!body.association&&refKey(body.association.body_ref)===refKey(body.body_ref);}
export function request(view:WaistLengthView,action:Action,payload:Record<string,unknown>,gesture_id:string):Request{
 if(!view.selected_body_ref)throw Error('请先选择实际检测到并明确关联人物的身体。');
 return {request_id:crypto.randomUUID(),gesture_id,document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,document_revision:view.binding.document_revision,state_revision:view.state_revision,association_revision:view.association_revision,people_association_revision:view.people_association_revision,body_graph_sha256:view.body_graph_sha256,people_graph_sha256:view.people_graph_sha256,body_ref:{...view.selected_body_ref},operation_id:OPERATION_ID,action,payload:structuredClone(payload)};
}
const normalized=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)&&n>0&&n<1;
export function checkReviewSupport(value:ReviewSupport):ReviewSupport{
 if(!value||Object.keys(value).sort().join(',')!==['version','method','confirmations',...COLUMNS,...BOXES,...WAIST_MARKERS].sort().join(',')||value.version!==1||value.method!=='user-reviewed-visible-waist-length-support'||COLUMNS.some(k=>!normalized(value[k]))||!(value.outer_left<value.inner_left&&value.inner_left<value.inner_right&&value.inner_right<value.outer_right&&value.upper_zero<value.upper_plateau))throw Error('请独立点选四个真实腰部端点及完整、有序的两侧和上方背景过渡边界。');
 for(const key of BOXES){const b=value[key];if(!Array.isArray(b)||b.length!==4||!b.every(normalized)||!(b[0]<b[2]&&b[1]<b[3]&&value.inner_left<b[0]&&b[2]<value.inner_right&&value.upper_plateau<b[1]))throw Error('完整头部、手臂与手的框必须位于两侧内界之间及上方移动起始线以下。');}
 for(const key of WAIST_MARKERS){const p=value[key];if(!Array.isArray(p)||p.length!==2||!p.every(normalized)||!(value.inner_left<p[0]&&p[0]<value.inner_right&&value.upper_plateau<p[1]))throw Error('四个腰部端点须由当前来源图独立点选，并位于移动内界之间。');}
 const ul=value.waist_upper_left,ur=value.waist_upper_right,ll=value.waist_lower_left,lr=value.waist_lower_right;
 if(!(ul[0]<ur[0]&&ll[0]<lr[0]&&Math.max(ul[1],ur[1])<Math.min(ll[1],lr[1])))throw Error('画面左、右腰点不可交叉；上腰端点必须全部高于下腰端点。');
 if(!value.confirmations||Object.keys(value.confirmations).sort().join(',')!==[...FLAGS].sort().join(',')||FLAGS.some(k=>value.confirmations[k]!==true))throw Error('请逐项完成当前来源图的可见性、归属和背景复核。');
 return structuredClone(value);
}
/** Conservative source-pixel guards mirror the source contract. The host still
 * validates complete contour coverage, ownership and canonical face evidence. */
export function checkBodySupport(value:ReviewSupport,body:BodyChoice):ReviewSupport{
 const support=checkReviewSupport(value);
 if(!canReview(body))throw Error('请先取得真实身体定位并确认当前人物归属。');
 const w=body.source.width-1,h=body.source.height-1;
 if(!Number.isSafeInteger(w)||!Number.isSafeInteger(h)||w<1||h<1)throw Error('当前来源图尺寸无效。');
 const ul=support.waist_upper_left,ur=support.waist_upper_right,ll=support.waist_lower_left,lr=support.waist_lower_right;
 if(!(Math.max(body.points[11].y,body.points[12].y)<Math.min(ul[1],ur[1])&&Math.max(ll[1],lr[1])<Math.min(body.points[23].y,body.points[24].y)))throw Error('四个腰点必须位于实际肩线下方、髋线上方，不能用肩髋点代替腰点。');
 if((Math.min(ll[1],lr[1])-Math.max(ul[1],ur[1]))*h<64)throw Error('当前来源图的完整腰段须至少相隔 64 像素；不猜测缺失或过短腰段。');
 for(const key of WAIST_MARKERS){const p=support[key];if(Math.min(p[0]*w,(1-p[0])*w,p[1]*h,(1-p[1])*h)<1)throw Error('腰部端点须与来源图边缘保留至少 1 像素。');}
 for(const [left,right] of [[ul,ur],[ll,lr]]){
  const width=(right[0]-left[0])*w,tilt=Math.abs(right[1]-left[1])*h;
  if(width<32||tilt>.25*width)throw Error('左右腰点须清晰分开且近水平；不支持明显倾斜或透视缩短。');
  for(const center of [(body.points[11].x+body.points[12].x)/2,(body.points[23].x+body.points[24].x)/2])if(!(left[0]<center&&center<right[0]))throw Error('左右腰点必须包围实际肩部和髋部中心，不能标到另一人物或单侧。');
 }
 for(const [top,bottom] of [[ul,ll],[ur,lr]]){const height=(bottom[1]-top[1])*h;if(height<64||Math.abs(bottom[0]-top[0])*w>.35*height)throw Error('同侧上、下腰点须沿近直立可见腰线测量，不支持过度倾斜或交叉。');}
 if(support.head_box[3]>=Math.max(body.points[11].y,body.points[12].y))throw Error('完整头部框必须位于实际肩线以上；不支持低头、遮挡或不清晰分界。');
 return support;
}
