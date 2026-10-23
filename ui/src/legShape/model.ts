// SPDX-License-Identifier: GPL-3.0-or-later
export const OPERATION_ID='lnx.leg_shape.v1' as const;
export const IDS={overall:'LNX-REF-PC-32473-C-6519e4b67b',thigh:'LNX-REF-PC-32473-C-2cebb24a12',calf:'LNX-REF-PC-32473-C-c63c7afe15'} as const;
export const ANCHORS=[23,24,25,26,27,28] as const;
export const SEGMENTS=['left_thigh','right_thigh','left_calf','right_calf'] as const;
export const JOINTS={left_thigh:[23,25],right_thigh:[24,26],left_calf:[25,27],right_calf:[26,28]} as const;
export const STATIONS=[.25,.5,.75] as const;
export const LABELS={overall:'瘦腿（同时调整）',thigh:'大腿',calf:'小腿'} as const;
export const SEGMENT_LABELS={left_thigh:'本人左大腿',right_thigh:'本人右大腿',left_calf:'本人左小腿',right_calf:'本人右小腿'} as const;
export type Key=keyof typeof IDS;
export type Segment=typeof SEGMENTS[number];
export type LegRecipe={version:1;thigh:number;calf:number};
export type BodyRef={asset_sha256:string;body_instance_id:string;analysis_revision:number};
export type Point={index:number;x:number;y:number;z:number;visibility:number;presence:number};
export type Source={sha256:string;width:number;height:number;orientation:'exif_normalized_once'};
export type SupportSegment={negative:[number,number,number];positive:[number,number,number];support_radius:number};
export type Support={version:1;method:'user-reviewed-visible-silhouette';stations:[.25,.5,.75];segments:Record<Segment,SupportSegment>;joints_visible:true;separate_legs:true;not_foreshortened:true;ownership_confirmed:true;background_support_reviewed:true};
export type BodyChoice={body_ref:BodyRef;enabled:boolean;operation_enabled:boolean;points:Point[];points_sha256:string;source:Source;reviewed:boolean;support:Support|null;association:null|{person_id:string;body_ref:BodyRef;people_association_revision:number;confirmation_revision:number}};
export type Binding={document_id:string;document_epoch:string;document_revision:number;asset_sha256:string};
export type LegView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:LegRecipe;refusals:{body_ref:BodyRef;operation_id?:string;reason:string}[]};
export type Action='recipe'|'support_review'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;body_ref:BodyRef;operation_id:typeof OPERATION_ID;action:Action;payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';request_id:string;protocol?:1;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:LegView};
export type Transport={send:(request:Request)=>Promise<Result>;status:(requestId:string)=>Promise<Result>};
export function neutral():LegRecipe{return {version:1,thigh:0,calf:0};}
export function check(value:LegRecipe):LegRecipe{
 if(!value||Object.keys(value).sort().join(',')!=='calf,thigh,version'||value.version!==1)throw Error('腿形参数格式不匹配，整体调节不是额外强度。');
 for(const key of ['thigh','calf'] as const)if(typeof value[key]!=='number'||!Number.isFinite(value[key])||Math.abs(value[key])>1)throw Error('腿形数值超出本产品范围。');
 return {...value};
}
export function adjust(value:LegRecipe,key:Key,amount:number):LegRecipe{const out=check(value);if(key==='overall'){out.thigh=amount;out.calf=amount;}else if(key==='thigh'||key==='calf'){out[key]=amount;}else throw Error('未知腿形控件。');return check(out);}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(view:LegView):string{return `${view.binding.document_epoch}:${view.binding.document_id}:${refKey(view.selected_body_ref)}`;}
export function observed(p:Point|undefined):boolean{return !!p&&[p.x,p.y,p.z,p.visibility,p.presence].every(Number.isFinite)&&p.x>0&&p.x<1&&p.y>0&&p.y<1&&p.visibility>=.8&&p.visibility<=1&&p.presence>=.8&&p.presence<=1;}
export function canReview(body:BodyChoice):boolean{return body.points.length===33&&ANCHORS.every(i=>body.points[i]?.index===i&&observed(body.points[i]));}
export function request(view:LegView,action:Action,payload:Record<string,unknown>,gesture_id:string):Request{
 if(!view.selected_body_ref)throw Error('请先选择实际检测到的身体。');
 return {request_id:crypto.randomUUID(),gesture_id,document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,document_revision:view.binding.document_revision,state_revision:view.state_revision,association_revision:view.association_revision,people_association_revision:view.people_association_revision,body_graph_sha256:view.body_graph_sha256,people_graph_sha256:view.people_graph_sha256,body_ref:{...view.selected_body_ref},operation_id:OPERATION_ID,action,payload};
}
export function checkSupport(value:Support):Support{
 const flags=['joints_visible','separate_legs','not_foreshortened','ownership_confirmed','background_support_reviewed'] as const;
 if(!value||Object.keys(value).sort().join(',')!==['version','method','stations','segments',...flags].sort().join(',')||value.version!==1||value.method!=='user-reviewed-visible-silhouette'||JSON.stringify(value.stations)!==JSON.stringify(STATIONS)||flags.some(k=>value[k]!==true)||!value.segments||Object.keys(value.segments).sort().join(',')!==[...SEGMENTS].sort().join(','))throw Error('请完整复核原图可见轮廓，不补全遮挡解剖。');
 for(const key of SEGMENTS){const s=value.segments[key];if(!s||Object.keys(s).sort().join(',')!=='negative,positive,support_radius')throw Error('可见腿部支撑不完整。');for(const side of ['negative','positive'] as const)if(!Array.isArray(s[side])||s[side].length!==3||s[side].some(n=>typeof n!=='number'||!Number.isFinite(n)||n<=0||n>=1))throw Error('每侧需要三个真实可见轮廓测量。');const widest=Math.max(...s.negative,...s.positive);if(!Number.isFinite(s.support_radius)||s.support_radius<1.4*widest||s.support_radius>2.5*widest)throw Error('渐隐范围需为最大可见半宽的 1.4–2.5 倍（本产品策略）。');}
 return structuredClone(value);
}
