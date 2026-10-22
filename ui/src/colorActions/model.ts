import type {CaptureDescriptor,CaptureRegion} from '../captureModel';
import type {VerifiedCapture} from '../captureFrame';

export type ColorAction='levels_black'|'levels_white'|'curve'|'hsl';
export type ColorChannel='master'|'red'|'green'|'blue'|'luminance';
export interface ColorActionContext {enabled:boolean;canStart?:boolean;documentId:string;contextKey:string;reason?:string}
export interface ColorActionRequest {
  request_id:string;capture_id:string;ticket:string;document_id:string;
  action:ColorAction;channel:ColorChannel;region:CaptureRegion;delta:number;
}
export interface ColorActionSample {
  version:1;action:ColorAction;channel:ColorChannel;policy:'stage-targeted-srgb-v1';mean_srgb:[number,number,number];hsl:[number,number,number];
  samples:number;region:CaptureRegion;source_stage:string;
  point?:[number,number];point_index?:number;sample_x?:number;weights?:number[];achieved_delta?:number;
}
export interface ColorActionPreview {
  format:'png';width:number;height:number;domain:'targeted-tool-stage';quality:'bounded-proxy-float-operator';data:string;
}
export interface ColorActionState {
  phase:'idle'|'arming'|'painting'|'ready'|'probing'|'sending'|'waiting'|'success'|'failure'|'uncertain';
  frame:VerifiedCapture|null;action:ColorAction|null;channel:ColorChannel|null;
  region:CaptureRegion|null;delta:number;sample:ColorActionSample|null;preview:ColorActionPreview|null;
  request:ColorActionRequest|null;message:string;
}
export interface ColorActionTransport {
  arm:(captureId:string,documentId:string,action:ColorAction,channel:ColorChannel)=>Promise<{ticket:string}>;
  status:(captureId:string,ticket:string)=>Promise<{phase:string;capture_id?:string;ticket?:string;descriptor?:CaptureDescriptor|null;error?:string|null}>;
  frame:(captureId:string,ticket:string)=>Promise<ArrayBuffer>;
  presented:(captureId:string,ticket:string,documentId:string)=>Promise<{eligible:boolean}>;
  cancel:(captureId:string,ticket:string|null,documentId:string)=>Promise<unknown>;
  submit:(request:ColorActionRequest,preview:boolean)=>Promise<unknown>;
  result:(requestId:string,preview:boolean)=>Promise<unknown>;
}
export const COLOR_ACTION_NAMES:Record<ColorAction,string>={levels_black:'RGB 黑场吸管',levels_white:'RGB 白场吸管',curve:'曲线定向调整',hsl:'HSL 定向色相'};
export const COLOR_CHANNEL_NAMES:Record<ColorChannel,string>={master:'RGB',red:'红',green:'绿',blue:'蓝',luminance:'亮度'};
export const colorActionStage=(action:ColorAction,channel:ColorChannel|null)=>action==='curve'?`curve-${channel}-input`:action==='hsl'?'hsl-input':'levels-input';
export const colorActionLimit=(action:ColorAction)=>action==='hsl'?60:action==='curve'?1:0;
export const object=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
const count=(value:unknown)=>Number.isSafeInteger(value)&&Number(value)>=0;
const vector=(value:unknown,length:number)=>Array.isArray(value)&&value.length===length&&value.every(v=>typeof v==='number'&&Number.isFinite(v));
const sameRegion=(value:unknown,region:CaptureRegion)=>object(value)&&['x','y','width','height'].every(k=>value[k]===region[k as keyof CaptureRegion]);
export function validateColorReceipt(packet:unknown,request:ColorActionRequest):Record<string,unknown>|null {
  if(!object(packet)||packet.request_id!==request.request_id)throw Error('定向调整回执身份不匹配');
  if(packet.phase==='pending')return null;
  if(packet.phase!=='done'||!object(packet.result))throw Error('原操作结果不可用；不会重新提交');
  const r=packet.result;
  if(r.protocol!==1||r.request_id!==request.request_id||r.capture_id!==request.capture_id||r.ticket!==request.ticket||
    r.document_id!==request.document_id||r.action!==request.action||r.channel!==request.channel||
    typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean')throw Error('定向调整完成回执不完整');
  if(r.outcome_unknown)throw Error(typeof r.error==='string'?r.error:'定向调整结果尚未确认');
  return r;
}
export function validateColorSample(value:unknown,request:ColorActionRequest):ColorActionSample {
  if(!object(value)||value.version!==1||value.action!==request.action||value.channel!==request.channel||value.policy!=='stage-targeted-srgb-v1'||!vector(value.mean_srgb,3)||!vector(value.hsl,3)||
    !count(value.samples)||Number(value.samples)<1||Number(value.samples)!==request.region.width*request.region.height||
    !sameRegion(value.region,request.region)||value.source_stage!==colorActionStage(request.action,request.channel))throw Error('取样来源或颜色回执无效');
  const hsl=value.hsl as number[];
  if((value.mean_srgb as number[]).some(v=>v<0||v>1)||hsl[0]<0||hsl[0]>=360||hsl[1]<0||hsl[1]>1||hsl[2]<0||hsl[2]>1)throw Error('RGB / HSL 取样范围无效');
  if(request.action==='curve'&&(!vector(value.point,2)||(value.point as number[]).some(v=>v<0||v>1)||!count(value.point_index)||Number(value.point_index)>63||
    typeof value.sample_x!=='number'||!Number.isFinite(value.sample_x)||value.sample_x<0||value.sample_x>1||
    typeof value.achieved_delta!=='number'||!Number.isFinite(value.achieved_delta)||Math.abs(value.achieved_delta)>1))throw Error('曲线节点预览证据不完整');
  if(request.action==='hsl'&&(!vector(value.weights,8)||(value.weights as number[]).some(v=>v<0||v>1)||
    typeof value.achieved_delta!=='number'||!Number.isFinite(value.achieved_delta)||Math.abs(value.achieved_delta)>120))throw Error('八色定向权重证据不完整');
  return value as unknown as ColorActionSample;
}
export function validateColorPreview(value:unknown):ColorActionPreview {
  if(!object(value)||value.format!=='png'||value.domain!=='targeted-tool-stage'||value.quality!=='bounded-proxy-float-operator'||
    !count(value.width)||!count(value.height)||Number(value.width)<1||Number(value.height)<1||Number(value.width)>512||Number(value.height)>512||
    typeof value.data!=='string'||value.data.length>3*1024*1024||!/^iVBORw0KGgo[A-Za-z0-9+/=]+$/.test(value.data))throw Error('工具阶段预览无效');
  return value as unknown as ColorActionPreview;
}
export function validateColorCommit(result:Record<string,unknown>){
  const recipes=result.action==='hsl'?vector(result.before,24)&&vector(result.after,24):object(result.before)&&object(result.after);
  if(result.requires_reload!==false||typeof result.no_change!=='boolean'||!recipes||
    !object(result.history)||!count(result.history.undo_steps)||!count(result.history.redo_steps))throw Error('定向调整缺少提交前后与历史证据');
}
