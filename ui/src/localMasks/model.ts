import type {Point} from '../sourcePatch/geometry';
import type {TransferGroupChoice} from './transferModel';
export type MaskKind='brush'|'linear'|'radial'|'color_range'|'luminance_range'|'semantic'|'full'|'prompted'|'automatic_foreground';
export type MaskOperation='add'|'subtract'|'intersect';
interface Common {id:string;name:string;enabled:boolean;operation:MaskOperation;opacity:number;feather:number}
export interface PromptSet {points:{x:number;y:number;label:0|1}[];box:[number,number,number,number]|null}
export interface PromptSelection {prompts:PromptSet;candidate:number;model:{id:string;checkpoint_sha256:string;config_sha256:string;code_revision:string;contract:string};input_sha256:string;device:'cpu'|'cuda'}
export interface AutomaticForegroundSelection {origin:'automatic';contract:string;model_sha256:string;runtime:string;input_sha256:string;alpha_sha256:string;width:number;height:number;source:{sha256:string;width:number;height:number}}
export type MaskObject=Common & (
  {kind:'brush';points:Point[];axes:[Point,Point]}|
  {kind:'linear';start:Point;end:Point;cross:Point}|
  {kind:'radial';center:Point;axes:[Point,Point]}|
  // Omission is accepted only for legacy input. New/report-normalized objects
  // carry a boolean; the engine rejects non-boolean values instead of coercing.
  {kind:'color_range';color:[number,number,number];tolerance:number;invert?:boolean}|
  {kind:'luminance_range';low:number;high:number}|
  {kind:'semantic';channel:string}|
  {kind:'full'}|{kind:'prompted';selection:PromptSelection}|{kind:'automatic_foreground';selection:AutomaticForegroundSelection});
export interface LocalGradeLayer {id:string;name:string;enabled:boolean;grade:[number,number,number,number];mask:{recipe:{version:1;domain:'source-normalized';objects:MaskObject[]}};types:string[]}
export interface LocalGradeReport {version:1;layers:LocalGradeLayer[];suspended:string|null;max_layers:number;grade_limits:[number,number,number]}
export interface LocalMaskReport {recipe:{version:1;domain:'source-normalized';objects:MaskObject[]};bound:boolean;suspended:string|null;channels:string[];channel_labels?:Record<string,string>;semantic_scope?:'whole-photo-category';layers?:LocalGradeReport;transfer_groups?:TransferGroupChoice[]}
export type PromptAcceptance={action:'accept_prompted';preview_id:string;candidate:number;id:string;name:string;operation:MaskOperation;opacity:number;feather:number};
export type BaseMaskMutation={action:'upsert';coordinate_space:'capture'|'source';object:MaskObject}|
  {action:'delete';id:string}|{action:'move';id:string;index:number}|{action:'bind';enabled:boolean}|{action:'clear'};
export type LayerMutation={action:'layer_update';id:string;name:string;enabled:boolean;grade:[number,number,number,number]}|
  {action:'layer_delete';id:string}|{action:'layer_move';id:string;index:number}|{action:'layer_mask';id:string;mutation:BaseMaskMutation};
export type MaskMutation=PromptAcceptance|BaseMaskMutation|LayerMutation;
export function mutationGroupId(mutation:MaskMutation|null):string|null {
  return mutation&&(mutation.action==='layer_update'||mutation.action==='layer_delete'||mutation.action==='layer_move'||mutation.action==='layer_mask')?mutation.id:null;
}
export function objectMutation(mutation:MaskMutation|null):Extract<BaseMaskMutation,{action:'upsert'}>|null {
  const inner=mutation?.action==='layer_mask'?mutation.mutation:mutation;
  return inner?.action==='upsert'?inner:null;
}
export function withObjectMutation(mutation:MaskMutation,inner:Extract<BaseMaskMutation,{action:'upsert'}>):MaskMutation {
  return mutation.action==='layer_mask'?{...mutation,mutation:inner}:inner;
}
export const MASK_LABELS:Record<MaskKind,string>={brush:'画笔',linear:'线性渐变',radial:'径向渐变',color_range:'颜色范围',luminance_range:'亮度范围',semantic:'语义区域',full:'全图',prompted:'AI提示选区',automatic_foreground:'自动人像前景建议（待审核）'};
export const OPERATION_LABELS:Record<MaskOperation,string>={add:'添加（最大值）',subtract:'减去',intersect:'交集（最小值）'};
export const MASK_SOURCE_LABEL='蒙版编辑视图：当前不可变来源底图，保留构图，不含其上的修补、磨皮、形变或调色；不是最终效果图';
export function newMask(kind:MaskKind,channel=''):MaskObject {
  const common:Common={id:crypto.randomUUID().replaceAll('-',''),name:MASK_LABELS[kind],enabled:true,operation:'add',opacity:1,feather:0};
  switch(kind){
    case 'brush':return {...common,kind,points:[],axes:[[.025,0],[0,.025]]};
    case 'linear':return {...common,kind,start:[.25,.5],end:[.75,.5],cross:[0,.5]};
    case 'radial':return {...common,kind,center:[.5,.5],axes:[[.25,0],[0,.25]]};
    case 'color_range':return {...common,kind,color:[.5,.5,.5],tolerance:.15,invert:false};
    case 'luminance_range':return {...common,kind,low:.25,high:.75};
    case 'semantic':return {...common,kind,channel};
    case 'full':return {...common,kind};
    case 'prompted':throw Error('AI提示选区必须由已显示的模型候选生成');
    case 'automatic_foreground':throw Error('自动前景必须由源图模型初始化产生，不能手工伪造来源');
  }
}
export const drawingKind=(kind?:MaskKind)=>kind==='brush'||kind==='linear'||kind==='radial';
export function geometryDescription(object:MaskObject):string {
  const p=(v:Point)=>v.map(n=>(n*100).toFixed(1)).join(', ');
  switch(object.kind){
    case 'brush':return `${object.points.length} 个保留路径点；源图坐标`;
    case 'linear':return `源图起点 (${p(object.start)})，终点 (${p(object.end)})`;
    case 'radial':return `源图中心 (${p(object.center)})；保留椭圆轴`;
    case 'color_range':return `颜色范围使用原始源图的 sRGB 颜色距离${object.invert?'；已反转选区':''}`;
    case 'luminance_range':return '亮度范围使用原始源图的线性亮度 Y';
    case 'semantic':return `区域：${object.channel}`;
    case 'prompted':return 'AI提示选区；保留提示与模型绑定，参数编辑不改变选区来源';
    case 'automatic_foreground':return '自动六类人像模型建议；覆盖整图已知人像类别，不识别人数或单人实例；来源证据不可编辑，需检查与画笔修正';
    case 'full':return '全图对象不可隐藏、修改或删除';
  }
}
