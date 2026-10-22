import type {Point} from '../sourcePatch/geometry';
export type MaskKind='brush'|'linear'|'radial'|'color_range'|'luminance_range'|'semantic'|'full';
export type MaskOperation='add'|'subtract'|'intersect';
interface Common {id:string;name:string;enabled:boolean;operation:MaskOperation;opacity:number;feather:number}
export type MaskObject=Common & (
  {kind:'brush';points:Point[];axes:[Point,Point]}|
  {kind:'linear';start:Point;end:Point;cross:Point}|
  {kind:'radial';center:Point;axes:[Point,Point]}|
  {kind:'color_range';color:[number,number,number];tolerance:number}|
  {kind:'luminance_range';low:number;high:number}|
  {kind:'semantic';channel:string}|
  {kind:'full'});
export interface LocalMaskReport {recipe:{version:1;domain:'source-normalized';objects:MaskObject[]};bound:boolean;suspended:string|null;channels:string[];channel_labels?:Record<string,string>;semantic_scope?:'whole-photo-category'}
export type MaskMutation={action:'upsert';coordinate_space:'capture'|'source';object:MaskObject}|
  {action:'delete';id:string}|{action:'move';id:string;index:number}|{action:'bind';enabled:boolean}|{action:'clear'};
export const MASK_LABELS:Record<MaskKind,string>={brush:'画笔',linear:'线性渐变',radial:'径向渐变',color_range:'颜色范围',luminance_range:'亮度范围',semantic:'语义区域',full:'全图'};
export const OPERATION_LABELS:Record<MaskOperation,string>={add:'添加（最大值）',subtract:'减去',intersect:'交集（最小值）'};
export const MASK_SOURCE_LABEL='蒙版编辑视图：原始源图，保留构图，不含修补、磨皮、形变或调色；不是最终效果图';
export function newMask(kind:MaskKind,channel=''):MaskObject {
  const common:Common={id:crypto.randomUUID().replaceAll('-',''),name:MASK_LABELS[kind],enabled:true,operation:'add',opacity:1,feather:0};
  switch(kind){
    case 'brush':return {...common,kind,points:[],axes:[[.025,0],[0,.025]]};
    case 'linear':return {...common,kind,start:[.25,.5],end:[.75,.5],cross:[0,.5]};
    case 'radial':return {...common,kind,center:[.5,.5],axes:[[.25,0],[0,.25]]};
    case 'color_range':return {...common,kind,color:[.5,.5,.5],tolerance:.15};
    case 'luminance_range':return {...common,kind,low:.25,high:.75};
    case 'semantic':return {...common,kind,channel};
    case 'full':return {...common,kind};
  }
}
export const drawingKind=(kind?:MaskKind)=>kind==='brush'||kind==='linear'||kind==='radial';
export function geometryDescription(object:MaskObject):string {
  const p=(v:Point)=>v.map(n=>(n*100).toFixed(1)).join(', ');
  switch(object.kind){
    case 'brush':return `${object.points.length} 个保留路径点；源图坐标`;
    case 'linear':return `源图起点 (${p(object.start)})，终点 (${p(object.end)})`;
    case 'radial':return `源图中心 (${p(object.center)})；保留椭圆轴`;
    case 'color_range':return '颜色范围使用原始源图的 sRGB 颜色距离';
    case 'luminance_range':return '亮度范围使用原始源图的线性亮度 Y';
    case 'semantic':return `区域：${object.channel}`;
    case 'full':return '全图对象不可隐藏、修改或删除';
  }
}
