import type {Context,Port,Preview,Recipe} from './model';
export interface Progress {stage:'reference_analysis'|'target_fit';position?:number;targets:number;document_id?:string;path?:string}
export interface WorkflowPort extends Port {
 subscribeProgress?:(listener:(session:string,value:Progress)=>void)=>()=>void;
 subscribeInspection?:(listener:(required:boolean)=>void)=>()=>void;
 inspectMutationOutcome?:()=>Promise<unknown>;
 acknowledgeInspection?:()=>void;
 pendingExport?:()=>{receipt:ExportReceipt;path:string|null}|null;
}
export interface BatchInspection {state:'inspected';inspection:null|{kind:string;batch_id?:string;review_token?:string;notice:string;targets:{document_id:string;path:string;state:'before'|'after'|'both'|'different'|'missing'|'invalid';revision?:string;error?:string}[]};batches:unknown[]}
export interface IntentGroup {id:string;enabled:boolean;offsets:number[]}
export interface Intent {mode:'extreme'|'harmonious';strengths:number[];enabled:boolean;groups:IntentGroup[]}
export interface TargetSummary {document_id:string;path:string;index:number;blocked:string|null;semantic_colour?:{
 proof:string;diagnostics:number[][];warnings:string[];coverage:{target:{class:string;usable_pixels:number;weighted_coverage:number}[]};
 requested_groups:{id:string;enabled:boolean}[];
}}
export interface Plan {preflight_token:string;targets:TargetSummary[];ok:number;blocked:number;applies:Intent;policy:string}
export interface ImportReceipt {import_id:string;intent:Intent;reference_bytes:number;reference_sha256:string;notice:string}
export interface ExportReceipt {export_id:string;reference_bytes:number;reference_sha256:string;file_bytes:number;file_sha256:string;reference_included:true}
export interface TargetPreview extends Preview {proof?:string}
export interface WorkflowProps {port:WorkflowPort;context:Context|null;documentKey:string;targets:string[];disabled:boolean;mutationBlocked:boolean;portableReason:string|null;onBusyChange:(busy:boolean)=>void;onChanged:()=>void}
export const CLASS_NAMES:Record<string,string>={global:'全图',background:'背景',hair:'头发',body_skin:'身体皮肤',face_skin:'面部皮肤',clothes:'衣物',others:'其它（不是背景）'};
/** Mirrors portable source rejection, including disabled and orphaned marks. */
export function portableRecipeReason(recipe:Recipe|undefined,suspended:string|null|undefined):string|null{
 if(!recipe?.groups.length||!recipe.reference||!recipe.target||!recipe.last_review)return '请先明确审核并应用全图 AI 追色结果。';
 if(recipe.last_review.authorization)return '该结果来自明确授权的自动语义任务，未逐图查看批准；不能把机器评估作为已审核预设来源，请先完成单图审核应用。';
 if(suspended)return suspended;
 if(recipe.local_only)return '当前为局部双图追色，不能丢弃来源选区后携带。';
 if(recipe.masks.some(mask=>mask.objects.length>0))return '包含画笔、渐变或其它用户蒙版对象，关闭的对象也不能静默丢弃。';
 if(!recipe.groups.some(group=>group.id==='global')||recipe.groups.some(group=>!(group.id in CLASS_NAMES)))return '来源不是完整全图基础组及已知语义组。';
 const expected=new Set(recipe.groups.filter(group=>group.id!=='global').map(group=>`semantic_${group.id}`));
 if(recipe.groups.some(group=>group.id!=='global'&&group.mask_id!==`semantic_${group.id}`)||recipe.masks.length!==expected.size
    ||recipe.masks.some(mask=>mask.base===null||!expected.has(mask.id)))return '来源包含非生成语义蒙版或游离蒙版，不能移植。';
 return null;
}
