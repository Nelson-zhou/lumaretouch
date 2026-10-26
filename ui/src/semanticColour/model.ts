/** One retained recipe shared by quick/precise views, not two fake colour models. */
import type {SampleReference} from '../sampleLibrary/model';
export type Mode='extreme'|'harmonious';
export interface Context {document_id:string;revision:string}
export interface Binding extends Context {source:{sha256:string;width:number;height:number};render_sha256:string;geometry_sha256:string;state_key:string;width:number;height:number;stage:string}
export interface Mark {id:string;name:string;enabled:boolean;operation:'add'|'subtract'|'intersect';kind:'brush';opacity:number;feather:number;points:[number,number][];axes:[[number,number],[number,number]]}
export interface CanvasMask {id:string;name:string;domain:string;binding:Binding;base:unknown;objects:Mark[]}
export interface Group {id:string;name:string;enabled:boolean;mask_id:string|null;parameters:number[];baseline:number[]}
export interface Recipe {version:1;enabled:boolean;mode:Mode;local_only:boolean;strengths:number[];groups:Group[];masks:CanvasMask[];target:Binding|null;reference:SampleReference|null;last_review?:{proof:string;diagnostics:number[][];warnings:string[];authorization?:{schema:'lrt.automatic-semantic-assessment.v1';graph_sha256:string;operation_id:string;archive_sha256:string;reviewed:false}}|null}
export interface Report {recipe:Recipe;suspended:string|null;fit_runtime_quality:string;pending_capabilities:string[]}
export interface Capture {session_id:string;context:Context;target:{binding:Binding;image:string};reference:{binding:Binding;image:string};target_selection:CanvasMask;reference_selection:CanvasMask;notice:string}
export interface Review {proof:string;warnings:string[];diagnostics:number[][];coverage:{target:{class:string;usable_pixels:number;weighted_coverage:number}[];reference:{class:string;usable_pixels:number;weighted_coverage:number}[]};recipe:Recipe;quality_acceptance:string}
export interface Preview {before:string;after:string;notice:string}
export interface Result {state?:string;context?:Context|null;report?:Report;session_id?:string;review?:Review;preview?:Preview;error?:string}
export interface Port {request(action:string,payload:Record<string,unknown>):Promise<unknown>}
export const DOMAIN='rendered-canvas-normalized-semantic-colour-v1';
export const KNOTS=[0,.25,.5,.75,1] as const;
export const BAND_NAMES=['红','橙','黄','绿','青','蓝','紫','洋红'];
export const PARAMETER_LABELS=['曝光 EV','红通道增益（档）','绿通道增益（档）','蓝通道增益（档）','饱和度','对比度',
 ...['总曲线','红曲线','绿曲线','蓝曲线'].flatMap(c=>KNOTS.map(x=>`${c} ${x}`)),
 ...BAND_NAMES.flatMap(c=>[`${c}色相`,`${c}饱和度`,`${c}明亮度`])];
export function bounds(index:number):[number,number,number]{return index<4?[-2,2,.01]:index<6?[-100,100,1]:index<26?[0,1,.005]:(index-26)%3===0?[-60,60,1]:[-100,100,1];}
export function checkedParameters(value:number[]):number[]{
 if(value.length!==50||value.some((v,i)=>!Number.isFinite(v)||v<bounds(i)[0]||v>bounds(i)[1]))throw new Error('追色参数不完整或超出范围');
 return [...value];
}
export function message(error:unknown){return error instanceof Error?error.message:String(error);}
export function contextEqual(a:Context|null,b:Context|null){return !!a&&!!b&&a.document_id===b.document_id&&a.revision===b.revision;}
