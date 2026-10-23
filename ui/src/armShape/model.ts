// SPDX-License-Identifier: GPL-3.0-or-later
export const FAMILY_ID='lnx.arm_shape.v1' as const;
export const REQUIREMENT_ID='LNX-REF-PC-32473-C-5d25f1744f' as const;
export const SEGMENTS=['left_upper','left_forearm','right_upper','right_forearm'] as const;
export const JOINTS={left_upper:[11,13],left_forearm:[13,15],right_upper:[12,14],right_forearm:[14,16]} as const;
export const LABELS={left_upper:'本人左上臂',left_forearm:'本人左前臂',right_upper:'本人右上臂',right_forearm:'本人右前臂'};
export const STATIONS=[.1,.2,.3,.4,.5,.6,.7,.8,.9] as const;
export const FLAGS=['joints_visible','entire_segment_visible','not_crossing','not_foreshortened','clear_torso_border','ownership_confirmed','visible_material_only','transition_pixels_reviewed'] as const;
export type Segment=typeof SEGMENTS[number];
export type Strategy='reviewed-contour'|'sam2-prompted-contour';
export type Recipe={version:1;strategy:Strategy;amount:number};
export type Family=Record<Segment,Recipe>;
export type Rect=[number,number,number,number];
export type Region={selection_box:Rect;exclusions:Rect[]};
export type BodyRef={asset_sha256:string;body_instance_id:string;analysis_revision:number};
export type Point={index:number;x:number;y:number;z:number;visibility:number;presence:number};
export type Source={sha256:string;width:number;height:number;orientation:'exif_normalized_once'};
export type Mask={width:number;height:number;encoding:'packbits-big-base64';chunks:string[];sha256:string};
export type Selection={version:1;binding:{prompts:unknown;candidate:number;model:{id:string;checkpoint_sha256:string;config_sha256:string;code_revision:string;contract:string};input_sha256:string;device:'cpu'|'cuda'};runtime_sha256:string;mask:Mask;source:Source;body_ref:BodyRef;points_sha256:string;segment:Segment;score:number;actual_device:'CPU'|'CUDA'|'ROCm'};
export type Support={version:1;segment:Segment;strategy:Strategy;stations:number[];negative:number[];positive:number[];region:Region;selection:Selection|null;confirmations:Record<typeof FLAGS[number],true>};
export type BodyChoice={body_ref:BodyRef;enabled:boolean;points:Point[];points_sha256:string;source:Source;association:unknown;operations:Record<Segment,{enabled:boolean;reviewed:boolean;support:Support|null}>};
export type Binding={document_id:string;document_epoch:string;document_revision:number;asset_sha256:string};
export type ArmView={binding:Binding;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;bodies:BodyChoice[];selected_body_ref:BodyRef|null;recipe:Family;refusals:{body_ref:BodyRef;operation_id:string;reason:string}[];runtime_quality_accepted:false};
export type Action='recipe'|'support_review'|'operation_status';
export type Request={request_id:string;gesture_id:string;document_id:string;document_epoch:string;document_revision:number;state_revision:number;association_revision:number;people_association_revision:number;body_graph_sha256:string;people_graph_sha256:string;body_ref:BodyRef;family_id:typeof FAMILY_ID;action:Action|'proposal';payload:Record<string,unknown>};
export type Result={phase:'pending'|'done'|'unavailable';request_id:string;protocol?:1;success?:boolean;outcome_unknown?:boolean;rendered?:boolean;unapplied_reason?:string|null;error?:string;reason?:string;view?:ArmView};
export type Proposal={version:1;source:Source;body_ref:BodyRef;points_sha256:string;segment:Segment;region:Region;proposals:{selection:Selection;negative:number[]|null;positive:number[]|null;refusal:string|null}[];reviewed:false;runtime_quality_accepted:false};
export type ProposalResult={phase:'pending'|'done'|'unavailable';job_id:string;success:boolean;error?:string;context?:{document_id:string;document_epoch:string;body_graph_sha256:string;people_graph_sha256:string};proposal?:Proposal|null};
export type Transport={send:(request:Request)=>Promise<Result>;status:(id:string)=>Promise<Result>;startProposal:(request:Request)=>Promise<ProposalResult>;proposalStatus:(id:string)=>Promise<ProposalResult>;cancelProposal:(id:string)=>Promise<ProposalResult>};
export function neutral():Recipe{return {version:1,strategy:'reviewed-contour',amount:0};}
export function neutralFamily():Family{return Object.fromEntries(SEGMENTS.map(k=>[k,neutral()])) as Family;}
export function check(value:Family):Family{
 if(!value||Object.keys(value).sort().join(',')!==[...SEGMENTS].sort().join(','))throw Error('手臂参数缺少明确的侧别或分段。');
 for(const key of SEGMENTS){const r=value[key];if(!r||Object.keys(r).sort().join(',')!=='amount,strategy,version'||r.version!==1||!['reviewed-contour','sam2-prompted-contour'].includes(r.strategy)||typeof r.amount!=='number'||!Number.isFinite(r.amount)||r.amount<0||r.amount>1)throw Error('手臂数值超出本产品 0–100 收细范围。');}
 return structuredClone(value);
}
export function refKey(ref:BodyRef|null):string{return ref?`${ref.asset_sha256}:${ref.body_instance_id}:${ref.analysis_revision}`:'none';}
export function viewKey(view:ArmView):string{return `${view.binding.document_epoch}:${view.binding.document_id}:${refKey(view.selected_body_ref)}`;}
export function reviewKey(view:ArmView,segment:Segment):string{return `${viewKey(view)}:${view.body_graph_sha256}:${view.people_graph_sha256}:${segment}`;}
export function targets(segment:Segment,linked:boolean,whole:boolean):Segment[]{const side=segment.startsWith('left_')?'left':'right';const part=segment.endsWith('_upper')?'upper':'forearm';return SEGMENTS.filter(k=>(linked||k.startsWith(side+'_'))&&(whole||k.endsWith('_'+part)));}
export function available(body:BodyChoice,segment:Segment):boolean{return body.enabled&&JOINTS[segment].every(i=>{const p=body.points[i];return !!p&&p.index===i&&[p.x,p.y,p.z,p.visibility,p.presence].every(Number.isFinite)&&p.x>0&&p.x<1&&p.y>0&&p.y<1&&p.visibility>=.8&&p.presence>=.8;});}
export function canApply(body:BodyChoice,keys:Segment[],strategy:Strategy):boolean{return keys.every(k=>available(body,k)&&body.operations[k].enabled&&body.operations[k].reviewed&&body.operations[k].support?.strategy===strategy);}
export function request(view:ArmView,action:Action|'proposal',payload:Record<string,unknown>,gesture_id:string=crypto.randomUUID()):Request{
 if(!view.selected_body_ref)throw Error('先选择实际检测到的身体。');
 return {request_id:crypto.randomUUID(),gesture_id,document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,document_revision:view.binding.document_revision,state_revision:view.state_revision,association_revision:view.association_revision,people_association_revision:view.people_association_revision,body_graph_sha256:view.body_graph_sha256,people_graph_sha256:view.people_graph_sha256,body_ref:{...view.selected_body_ref},family_id:FAMILY_ID,action,payload,
 // Source belongs in BodyRef/binding fences, not an extra protocol field.
 } as Request;
}
export function manualWidth(body:BodyChoice,segment:Segment,station:number,side:'negative'|'positive',x:number,y:number):number{
 if(!Number.isInteger(station)||station<0||station>=STATIONS.length||![x,y].every(n=>Number.isFinite(n)&&n>=0&&n<=1)||!available(body,segment))throw Error('需要当前真实可见分段与有效原图点击。');
 const [ai,bi]=JOINTS[segment],a=body.points[ai],b=body.points[bi];const w=body.source.width-1,h=body.source.height-1;
 const dx=(b.x-a.x)*w,dy=(b.y-a.y)*h,length=Math.hypot(dx,dy),nx=-dy/length,ny=dx/length;
 if(!Number.isFinite(length)||length<32||length<Math.min(w,h)*.04)throw Error('该分段太短，无法可靠测量轮廓。');
 const rx=x*w-(a.x*w+STATIONS[station]*dx),ry=y*h-(a.y*h+STATIONS[station]*dy);const offset=rx*nx+ry*ny;
 if(Math.abs((rx*dx+ry*dy)/length)>Math.max(3,length*.02)||(side==='negative'?offset>=0:offset<=0))throw Error('请点击选中截线对应侧的真实可见边缘，不要点击轴心或补全遮挡。');
 const width=Math.abs(offset);if(width<2||width>length*.3)throw Error('可见轮廓宽度超出安全测量范围。');
 return width/Math.min(w,h);
}
