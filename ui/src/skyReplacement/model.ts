import type {SemanticDescriptor} from '../skySemantic/model';
export type SkyTarget='sky'|'person'|'water'|'recovery';
export type SkyScalar='vertical'|'horizontal'|'angle'|'scale'|'edge'|'gradient'|'temperature'|'tint'|'saturation'|'brightness'|'blur'|'opacity'|'scene'|'person'|'reflection'|'reflection_blur';
export type SkyParameters=Record<SkyScalar,number>&{flip:boolean};
export interface SkyStroke {id:string;name:string;enabled:boolean;operation:'add'|'subtract';kind:'brush';opacity:number;feather:number;points:[number,number][];axes:[[number,number],[number,number]]}
export interface SkyMask {version:1;domain:'source-normalized';objects:SkyStroke[]}
export interface SkyDraft {enabled:boolean;asset_path:string|null;asset_choice:string|null;parameters:SkyParameters;regions:Record<'sky'|'person'|'water',SkyMask>;person_mode:'unmarked'|'none'|'marked';horizon:number|null;recovery:SkyMask;semantic:SemanticDescriptor|null}
export interface SkyImage {source:string;after:string;overlay:string;width:number;height:number;source_width:number;source_height:number;domain:'source-normalized';output_domain:'production-output';quality:'proxy-render-srgb8';target:SkyTarget;automatic_detection:boolean;semantic_suspended?:string|null;note:string}
export interface SkyReport {version:2;enabled:boolean;editable:SkyDraft;asset:{path:string;sha256:string;width:number;height:number;bits:number;working_color:string;icc_sha256:string|null}|null;suspended:string|null;automatic_detection:boolean;working_color:string;bytes:number;boundaries:string[]}
export type SkyMutation={action:'view';target:SkyTarget}|{action:'replace';target:SkyTarget;draft:SkyDraft};
export interface SkyRequest {request_id:string;preview_id:string;session_id:string;document_id:string}
export interface SkyControl {key:SkyScalar;label:string;min:number;max:number;step:number;id:string;unit?:string}
export const CONTROLS:SkyControl[]=[
  {key:'vertical',label:'垂直位置',min:-100,max:100,step:.5,id:'6b87bf7388',unit:'%'},
  {key:'horizontal',label:'水平位置',min:-100,max:100,step:.5,id:'679dae32e6',unit:'%'},
  {key:'angle',label:'天空角度',min:-180,max:180,step:.5,id:'48ec19a95a',unit:'°'},
  {key:'scale',label:'素材大小',min:25,max:400,step:1,id:'local-sky-scale',unit:'%'},
  {key:'edge',label:'边缘调整',min:-100,max:100,step:1,id:'703d8271d5'},
  {key:'gradient',label:'渐变过渡',min:0,max:100,step:1,id:'999e4bf2f2'},
  {key:'temperature',label:'色温',min:-100,max:100,step:1,id:'106048a96f'},
  {key:'tint',label:'色调',min:-100,max:100,step:1,id:'dcca1d21c9'},
  {key:'saturation',label:'饱和度',min:-100,max:100,step:1,id:'482ce42caa'},
  {key:'brightness',label:'亮度',min:-100,max:100,step:1,id:'329a11842f'},
  {key:'blur',label:'天空虚化',min:0,max:100,step:1,id:'4a4a602101'},
  {key:'opacity',label:'不透明度',min:0,max:100,step:1,id:'d57398ba6c',unit:'%'},
  {key:'scene',label:'景物色彩（偏向天空）',min:-100,max:100,step:1,id:'aef60501f4'},
  {key:'person',label:'人物色彩（偏向天空）',min:-100,max:100,step:1,id:'0b58cf183b'},
  {key:'reflection',label:'景物水面反射',min:0,max:100,step:1,id:'98eade3987',unit:'%'},
  {key:'reflection_blur',label:'景物水效虚化',min:0,max:100,step:1,id:'3da6103009'},
];
export const TARGET_LABELS:Record<SkyTarget,string>={sky:'天空区域',person:'人物保护',water:'水面区域',recovery:'恢复换天空'};
export const TARGET_COLORS:Record<SkyTarget,string>={sky:'#43aaff',person:'#ffb428',water:'#28e6c8',recovery:'#f550aa'};
export function emptyMask():SkyMask{return {version:1,domain:'source-normalized',objects:[]};}
export function maskOf(draft:SkyDraft,target:SkyTarget):SkyMask{return target==='recovery'?draft.recovery:draft.regions[target];}
export function withMask(draft:SkyDraft,target:SkyTarget,mask:SkyMask):SkyDraft{
  if(target==='recovery')return {...draft,recovery:mask};
  return {...draft,regions:{...draft.regions,[target]:mask},...(target==='person'?{person_mode:(mask.objects.length||draft.semantic?.regions.person!==undefined)?'marked' as const:'unmarked' as const}:{})};
}
export function newStroke(point:[number,number],width:number,height:number,target:SkyTarget,size:number,erase:boolean,opacity:number):SkyStroke{
  const radius=Math.min(width,height)*size/200;
  return {id:crypto.randomUUID().replaceAll('-',''),name:TARGET_LABELS[target],enabled:true,operation:erase?'subtract':'add',kind:'brush',opacity:opacity/100,feather:2,
    points:[point],axes:[[radius/width,0],[0,radius/height]]};
}
