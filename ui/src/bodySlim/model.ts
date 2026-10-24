// SPDX-License-Identifier: GPL-3.0-or-later
export const OPERATION_ID='lnx.body_slim.v1' as const;
export const REQUIREMENT_ID='LNX-REF-PC-32473-C-bc54b9eb3c' as const;
/** Actual full-person observations, never inferred silhouette bounds. */
export const ANCHORS=[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32] as const;
export const CONFIRMATIONS={
 whole_person_visible:'完整人物（包括头发、手和双脚）均实际可见，所有定位真实可靠',
 upright_not_foreshortened:'人物近直立、近正面，无明显侧身、弯曲或透视缩短',
 actual_complete_silhouette_traced:'已手工沿实际完整人物轮廓逐点测量，未以关节点或框代替轮廓',
 ownership_confirmed:'整个轮廓和背景支撑均明确属于当前所选人物的处理区域',
 only_one_person_in_source:'已检查完整来源图，图中只有这一人，没有漏检的人物',
 no_occlusion_or_contacts:'没有遮挡、交叉、他人接触或持物，不推测隐藏身体',
 background_collar_and_gaps_reviewed:'接受明确背景过渡及手臂/腿间空隙、衣纹与人物一起横向变化，支撑外保持不动',
} as const;
export const FLAGS=Object.keys(CONFIRMATIONS) as (keyof typeof CONFIRMATIONS)[];
export type Vertex=[number,number];
export type Box=[number,number,number,number];
export type BodySlimRecipe={version:1;amount:number};
export type BodyRef={asset_sha256:string;body_instance_id:string;analysis_revision:number};
export type FaceRef={asset_sha256:string;face_instance_id:string;analysis_revision:number};
export type Point={index:number;x:number;y:number;z:number;visibility:number;presence:number};
export type Source={sha256:string;width:number;height:number;orientation:'exif_normalized_once'};
/** UI supplies reviewed geometry only. Canonical face facts are host-owned. */
export type ReviewSupport={version:1;method:'user-traced-complete-person-silhouette-v1';outline:Vertex[];collar_box:Box;confirmations:Record<keyof typeof CONFIRMATIONS,true>};
export type Support=ReviewSupport&{associated_face_ref:FaceRef;associated_face_box:Box;associated_face_evidence_sha256:string};
export type BodyChoice={body_ref:BodyRef;enabled:boolean;operation_enabled:boolean;points:Point[];points_sha256:string;source:Source;reviewed:boolean;support:Support|null;association:null|{person_id:string;body_ref:BodyRef;people_association_revision:number;confirmation_revision:number}};
export type Binding={document_id:string;document_epoch:string;document_revision:number;asset_sha256:string};
export type BodySlimView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:BodySlimRecipe;refusals:{body_ref:BodyRef;operation_id?:string;reason:string}[]};
export type Action='recipe'|'support_review'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;body_ref:BodyRef;operation_id:typeof OPERATION_ID;action:Action;payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';request_id:string;protocol?:1;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:BodySlimView};
export type Transport={send:(request:Request)=>Promise<Result>;status:(requestId:string)=>Promise<Result>};
export function neutral():BodySlimRecipe{return {version:1,amount:0};}
export function check(value:BodySlimRecipe):BodySlimRecipe{
 if(!value||Object.keys(value).sort().join(',')!=='amount,version'||value.version!==1||typeof value.amount!=='number'||!Number.isFinite(value.amount)||Math.abs(value.amount)>1)throw Error('全身瘦身参数无效，本产品原创范围为 -100 到 100。');
 return {...value};
}
export function adjust(value:BodySlimRecipe,amount:number):BodySlimRecipe{return check({...check(value),amount});}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(view:BodySlimView):string{return `${view.binding.document_epoch}:${view.binding.document_id}:${refKey(view.selected_body_ref)}`;}
export function observed(p:Point|undefined):boolean{return !!p&&[p.x,p.y,p.z,p.visibility,p.presence].every(n=>typeof n==='number'&&Number.isFinite(n))&&p.x>0&&p.x<1&&p.y>0&&p.y<1&&p.visibility>=.8&&p.visibility<=1&&p.presence>=.8&&p.presence<=1;}
export function canReview(body:BodyChoice):boolean{return body.points.length===33&&ANCHORS.every(i=>body.points[i]?.index===i&&observed(body.points[i]))&&!!body.association&&refKey(body.association.body_ref)===refKey(body.body_ref);}
export function request(view:BodySlimView,action:Action,payload:Record<string,unknown>,gesture_id:string):Request{
 if(!view.selected_body_ref)throw Error('请先选择实际检测到并明确关联人物的身体。');
 return {request_id:crypto.randomUUID(),gesture_id,document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,document_revision:view.binding.document_revision,state_revision:view.state_revision,association_revision:view.association_revision,people_association_revision:view.people_association_revision,body_graph_sha256:view.body_graph_sha256,people_graph_sha256:view.people_graph_sha256,body_ref:{...view.selected_body_ref},operation_id:OPERATION_ID,action,payload:structuredClone(payload)};
}
const normalized=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)&&n>0&&n<1;
export function checkReviewSupport(value:ReviewSupport):ReviewSupport{
 if(!value||Object.keys(value).sort().join(',')!==['version','method','outline','collar_box','confirmations'].sort().join(',')||value.version!==1||value.method!=='user-traced-complete-person-silhouette-v1')throw Error('全身轮廓复核格式无效。');
 const vertices=value.outline,b=value.collar_box;
 if(!Array.isArray(vertices)||vertices.length<8||vertices.length>128||vertices.some(p=>!Array.isArray(p)||p.length!==2||!p.every(normalized)))throw Error('请逐点测量 8 至 128 个真实人物轮廓顶点，不重复首点。');
 if(!Array.isArray(b)||b.length!==4||!b.every(normalized)||!(b[0]<b[2]&&b[1]<b[3])||vertices.some(p=>p[0]<=b[0]||p[0]>=b[2]||p[1]<=b[1]||p[1]>=b[3]))throw Error('完整实测轮廓必须严格位于明确的四侧背景过渡框内。');
 if(!value.confirmations||Object.keys(value.confirmations).sort().join(',')!==[...FLAGS].sort().join(',')||FLAGS.some(k=>value.confirmations[k]!==true))throw Error('请逐项核对实际全身轮廓、单人归属、遮挡与背景。');
 return structuredClone(value);
}
