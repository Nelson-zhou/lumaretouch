// SPDX-License-Identifier: GPL-3.0-or-later
/** Whole-head/hair support is independent of the face-size operation. */
export const OPERATION_ID='lnx.head_size.v1' as const;
export const REQUIREMENT_ID='LNX-REF-PC-32473-C-dc1b0ba40a' as const;
export const ANCHORS=[0,1,2,3,4,5,6,7,8,9,10,11,12] as const;
export const HEAD_ANCHORS=[0,1,2,3,4,5,6,7,8,9,10] as const;
export const BOXES=['head_box','transition_box'] as const;
export const CONFIRMATIONS={
 complete_head_hair_reviewed:'头部框完整包含头发、头顶、双耳、下颌及整张脸，不只是人脸框',
 head_bounds_manually_marked:'完整头部边界由我在当前来源图上手工测量，没有推测发际或省略长发',
 transition_bounds_manually_marked:'外围过渡框由我在当前来源图上独立测量，四边均留有清晰背景余量',
 pivot_manually_marked:'缩小中心由我在完整头部框内明确点选，不采用自动中心',
 clear_background_transition_reviewed:'已检查完整过渡范围，接受背景可能随连续形变移动',
 no_contacts:'头发及过渡范围不接触肩部、衣物、手、饰物或他人；不存在拖到肩部的长发',
 ownership_confirmed:'完整头部、头发和过渡范围已复核，归属当前关联人物',
 not_occluded:'完整头部和头发没有裁切或遮挡，不推测隐藏轮廓',
 upright_not_foreshortened:'头部近正面且近直立，没有明显侧身、俯仰或透视缩短',
 head_and_shoulders_visible:'真实头部定位点与双肩均清晰可见，外围过渡底边位于双肩上方',
} as const;
export const FLAGS=Object.keys(CONFIRMATIONS) as (keyof typeof CONFIRMATIONS)[];
export type Box=[number,number,number,number];
export type MarkedPoint=[number,number];
export type BoxKey=typeof BOXES[number];
export type HeadSizeRecipe={version:1;amount:number};
export type BodyRef={asset_sha256:string;body_instance_id:string;analysis_revision:number};
export type FaceRef={asset_sha256:string;face_instance_id:string;analysis_revision:number};
export type Point={index:number;x:number;y:number;z:number;visibility:number;presence:number};
export type Source={sha256:string;width:number;height:number;orientation:'exif_normalized_once'};
/** Only manual geometry/confirmations cross from UI. Face evidence is host-owned. */
export type ReviewSupport={version:1;method:'user-reviewed-complete-head-hair-support';head_box:Box;transition_box:Box;pivot:MarkedPoint;confirmations:Record<keyof typeof CONFIRMATIONS,true>};
export type AssociatedFace={associated_face_ref:FaceRef;associated_face_box:Box;associated_face_evidence_sha256:string};
export type Support=ReviewSupport&AssociatedFace;
export type BodyChoice={body_ref:BodyRef;enabled:boolean;operation_enabled:boolean;points:Point[];points_sha256:string;source:Source;reviewed:boolean;support:Support|null;associated_face:AssociatedFace|null;associated_face_error:string|null;association:null|{person_id:string;body_ref:BodyRef;people_association_revision:number;confirmation_revision:number}};
export type Binding={document_id:string;document_epoch:string;document_revision:number;asset_sha256:string};
export type Publication={request_id:string;rendered:boolean;unapplied_reason:string|null};
export type HeadSizeView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:HeadSizeRecipe;refusals:{body_ref:BodyRef;operation_id?:string;reason:string}[];publication?:Publication};
export type Action='recipe'|'support_review'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;body_ref:BodyRef;operation_id:typeof OPERATION_ID;action:Action;payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';request_id:string;protocol?:1;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:HeadSizeView};
export type Transport={send:(request:Request)=>Promise<Result>;status:(requestId:string)=>Promise<Result>};
export function neutral():HeadSizeRecipe{return {version:1,amount:0};}
export function check(value:HeadSizeRecipe):HeadSizeRecipe{
 if(!value||Object.keys(value).sort().join(',')!=='amount,version'||value.version!==1||typeof value.amount!=='number'||!Number.isFinite(value.amount)||value.amount<0||value.amount>1)throw Error('小头参数无效：本产品原创范围为 0 到 100，只缩小完整头部，不放大。');
 return {...value};
}
export function adjust(value:HeadSizeRecipe,amount:number):HeadSizeRecipe{return check({...check(value),amount});}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(view:HeadSizeView):string{return `${view.binding.document_epoch}:${view.binding.document_id}:${refKey(view.selected_body_ref)}`;}
export function observed(p:Point|undefined):boolean{return !!p&&[p.x,p.y,p.z,p.visibility,p.presence].every(n=>typeof n==='number'&&Number.isFinite(n))&&p.x>0&&p.x<1&&p.y>0&&p.y<1&&p.visibility>=.8&&p.visibility<=1&&p.presence>=.8&&p.presence<=1;}
export function canReview(body:BodyChoice):boolean{
 const face=body.associated_face,box=face?.associated_face_box;
 return body.points.length===33&&ANCHORS.every(i=>body.points[i]?.index===i&&observed(body.points[i]))&&!!body.association&&refKey(body.association.body_ref)===refKey(body.body_ref)&&body.source.sha256===body.body_ref.asset_sha256&&!!face&&face.associated_face_ref.asset_sha256===body.source.sha256&&/^[a-f0-9]{64}$/.test(face.associated_face_evidence_sha256)&&Array.isArray(box)&&box.length===4&&box.every(normalized)&&box[0]<box[2]&&box[1]<box[3];
}
export function request(view:HeadSizeView,action:Action,payload:Record<string,unknown>,gesture_id:string):Request{
 if(!view.selected_body_ref)throw Error('请先选择实际检测到并明确关联人物的身体。');
 return {request_id:crypto.randomUUID(),gesture_id,document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,document_revision:view.binding.document_revision,state_revision:view.state_revision,association_revision:view.association_revision,people_association_revision:view.people_association_revision,body_graph_sha256:view.body_graph_sha256,people_graph_sha256:view.people_graph_sha256,body_ref:{...view.selected_body_ref},operation_id:OPERATION_ID,action,payload:structuredClone(payload)};
}
const normalized=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)&&n>0&&n<1;
export function inside(box:Box,p:MarkedPoint):boolean{return box[0]<p[0]&&p[0]<box[2]&&box[1]<p[1]&&p[1]<box[3];}
export function checkReviewSupport(value:ReviewSupport):ReviewSupport{
 if(!value||Object.keys(value).sort().join(',')!=='confirmations,head_box,method,pivot,transition_box,version'||value.version!==1||value.method!=='user-reviewed-complete-head-hair-support')throw Error('请独立测量完整头发/头部框、外围过渡框及缩小中心。');
 for(const key of BOXES){const box=value[key];if(!Array.isArray(box)||box.length!==4||!box.every(normalized)||!(box[0]<box[2]&&box[1]<box[3]))throw Error('完整头部和过渡框必须是来源图内部的有效矩形，裁切头部不受支持。');}
 const head=value.head_box,outer=value.transition_box,p=value.pivot;
 if(!inside(outer,[head[0],head[1]])||!inside(outer,[head[2],head[3]]))throw Error('过渡框必须严格包围完整头发和头部，四边都留有背景余量。');
 if(!Array.isArray(p)||p.length!==2||!p.every(normalized)||!inside(head,p))throw Error('请在完整头部框内明确测量缩小中心，不能自动采用框中心。');
 if(!value.confirmations||Object.keys(value.confirmations).sort().join(',')!==[...FLAGS].sort().join(',')||FLAGS.some(k=>value.confirmations[k]!==true))throw Error('请逐项完成当前来源图的完整头发、背景、无接触与归属复核。');
 return structuredClone(value);
}
/** Pose guards are not a hairline detector. Canonical full-face evidence and
 * source ownership are revalidated by the engine before any review is retained. */
export function checkBodySupport(value:ReviewSupport,body:BodyChoice):ReviewSupport{
 const support=checkReviewSupport(value);
 if(!canReview(body))throw Error('需要实际可见的头部与双肩定位，以及当前人物的明确身体关联。');
 const w=body.source.width-1,h=body.source.height-1;
 if(!Number.isSafeInteger(w)||!Number.isSafeInteger(h)||w<1||h<1||body.source.orientation!=='exif_normalized_once')throw Error('当前规范来源图的尺寸或方向无效。');
 if(HEAD_ANCHORS.some(i=>!inside(support.head_box,[body.points[i].x,body.points[i].y])))throw Error('完整头部框必须包含全部真实头部定位点，不能只包围脸或裁掉头发。');
 const head=support.head_box,outer=support.transition_box,face=body.associated_face!.associated_face_box;
 if(!inside(head,[face[0],face[1]])||!inside(head,[face[2],face[3]]))throw Error('完整头部框必须严格包围引擎提供的当前本人完整脸框，不能裁掉脸部或借用其他人脸。');
 if((head[2]-head[0])*w<32||(head[3]-head[1])*h<32)throw Error('完整头部的宽、高均须至少 32 来源像素。');
 if(Math.min((head[0]-outer[0])*w,(outer[2]-head[2])*w,(head[1]-outer[1])*h,(outer[3]-head[3])*h)<16)throw Error('完整头部外的四边过渡余量均须至少 16 来源像素。');
 if(Math.min(outer[0]*w,(1-outer[2])*w,outer[1]*h,(1-outer[3])*h)<1)throw Error('外围过渡框须与来源图边缘保留至少 1 像素。');
 const shoulderWidth=Math.abs(body.points[11].x-body.points[12].x)*w,shoulderTilt=Math.abs(body.points[11].y-body.points[12].y)*h;
 if(shoulderWidth<32||shoulderTilt>.25*shoulderWidth||Math.abs(body.points[11].z-body.points[12].z)*w>.35*shoulderWidth)throw Error('双肩须真实可见并近水平，不支持明显转身、倾斜或透视缩短。');
 if(!(support.transition_box[3]<Math.min(body.points[11].y,body.points[12].y)))throw Error('过渡底边必须在两侧真实肩部上方；长发到肩、接触衣物或低头情形不受支持，不能缩小框来省略头发。');
 return support;
}
