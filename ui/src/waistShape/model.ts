// SPDX-License-Identifier: GPL-3.0-or-later
export const OPERATION_ID='lnx.waist_shape.v1' as const;
export const REQUIREMENT_ID='LNX-REF-PC-32473-C-8268ea3e37' as const;
export const ANCHORS=[11,12,23,24] as const;
export const STATIONS=[.1,.2,.3,.4,.5,.6,.7,.8,.9] as const;
export const CONFIRMATIONS={bilateral_visible:'两侧腰部或衣物外轮廓都真实可见',bounds_reviewed:'已从原图指定腰部调整的上界和下界',not_occluded:'轮廓未被手臂、头发、物品或其他身体遮挡',not_foreshortened:'没有严重侧身、透视或缩短导致双侧归属不清',ownership_confirmed:'上下界、两侧轮廓及过渡区属于所选身体',visible_material_only:'只调整可见皮肤或衣物轮廓，不推算衣下身材',transition_pixels_reviewed:'已核对过渡范围和排除区域，接受范围内背景与衣纹可能移动'} as const;
export type WaistRecipe={version:1;amount:number};
export type Box=[number,number,number,number];
export type Support={version:1;upper:number;lower:number;stations:number[];negative:number[];positive:number[];region:{selection_box:Box;exclusions:Box[]};confirmations:Record<keyof typeof CONFIRMATIONS,true>};
export type BodyRef={asset_sha256:string;body_instance_id:string;analysis_revision:number};
export type Point={index:number;x:number;y:number;z:number;visibility:number;presence:number};
export type Source={sha256:string;width:number;height:number;orientation:'exif_normalized_once'};
export type BodyChoice={body_ref:BodyRef;enabled:boolean;operation_enabled:boolean;points:Point[];points_sha256:string;source:Source;reviewed:boolean;support:Support|null;association:null|{person_id:string;body_ref:BodyRef;people_association_revision:number;confirmation_revision:number}};
export type Binding={document_id:string;document_epoch:string;document_revision:number;asset_sha256:string};
export type WaistView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:WaistRecipe;refusals:{body_ref:BodyRef;operation_id?:string;reason:string}[]};
export type Action='recipe'|'support_review'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;body_ref:BodyRef;operation_id:typeof OPERATION_ID;action:Action;payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';request_id:string;protocol?:1;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:WaistView};
export type Transport={send:(request:Request)=>Promise<Result>;status:(requestId:string)=>Promise<Result>};
export function neutral():WaistRecipe{return {version:1,amount:0};}
export function check(value:WaistRecipe):WaistRecipe{
 if(!value||Object.keys(value).sort().join(',')!=='amount,version'||value.version!==1||!Number.isFinite(value.amount)||value.amount<0||value.amount>1)throw Error('瘦腰强度超出本产品原创范围。');
 return {...value};
}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(view:WaistView):string{return `${view.binding.document_epoch}:${view.binding.document_id}:${refKey(view.selected_body_ref)}`;}
export function observed(p:Point|undefined):boolean{return !!p&&[p.x,p.y,p.z,p.visibility,p.presence].every(Number.isFinite)&&p.x>0&&p.x<1&&p.y>0&&p.y<1&&p.visibility>=.8&&p.visibility<=1&&p.presence>=.8&&p.presence<=1;}
export function canReview(body:BodyChoice):boolean{return body.points.length===33&&ANCHORS.every(i=>body.points[i]?.index===i&&observed(body.points[i]));}
export function request(view:WaistView,action:Action,payload:Record<string,unknown>,gesture_id:string):Request{
 if(!view.selected_body_ref)throw Error('请先选择实际检测到的身体。');
 return {request_id:crypto.randomUUID(),gesture_id,document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,document_revision:view.binding.document_revision,state_revision:view.state_revision,association_revision:view.association_revision,people_association_revision:view.people_association_revision,body_graph_sha256:view.body_graph_sha256,people_graph_sha256:view.people_graph_sha256,body_ref:{...view.selected_body_ref},operation_id:OPERATION_ID,action,payload:structuredClone(payload)};
}
export function checkSupport(value:Support):Support{
 if(!value||Object.keys(value).sort().join(',')!=='confirmations,lower,negative,positive,region,stations,upper,version'||value.version!==1||!Number.isFinite(value.upper)||!Number.isFinite(value.lower)||value.upper<=0||value.lower>=1||value.upper>=value.lower||JSON.stringify(value.stations)!==JSON.stringify(STATIONS))throw Error('请完整指定原图腰部上下界。');
 for(const side of ['negative','positive'] as const)if(!Array.isArray(value[side])||value[side].length!==9||value[side].some(n=>typeof n!=='number'||!Number.isFinite(n)||n<=0||n>=1))throw Error('需要分别测量双侧各九个可见轮廓点，不会镜像补齐。');
 if(!value.confirmations||Object.keys(value.confirmations).sort().join(',')!==Object.keys(CONFIRMATIONS).sort().join(',')||Object.keys(CONFIRMATIONS).some(k=>value.confirmations[k as keyof typeof CONFIRMATIONS]!==true))throw Error('请完成全部可见性与归属复核。');
 const box=(a:Box)=>Array.isArray(a)&&a.length===4&&a.every(n=>Number.isFinite(n)&&n>=0&&n<=1)&&a[0]<a[2]&&a[1]<a[3];
 if(!value.region||Object.keys(value.region).sort().join(',')!=='exclusions,selection_box'||!box(value.region.selection_box)||!Array.isArray(value.region.exclusions)||value.region.exclusions.length>32||!value.region.exclusions.every(box))throw Error('请在原图绘制有效复核范围及排除区域。');
 return structuredClone(value);
}
