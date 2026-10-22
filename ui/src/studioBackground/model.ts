export type RegionMode='manual'|'semantic_background';
export type Target='background'|'floor'|'protect'|'intrusion'|'blemish'|'recover_intrusions'|'recover_blemishes'|'recover_uniformity'|'recover_banding';
export type Parameters={intrusions:number;blemish_background:number;blemish_floor:number;uniformity:number;brightness:number;banding:number;enhancement:number};
export interface Stroke {id:string;target:Target;operation:'add'|'subtract';axes:[[number,number],[number,number]];points:[number,number,number][];feather:number;flow:number;opacity:number}
export interface Proposal {parameters:Parameters;region_mode:RegionMode;strokes:Stroke[]}
export interface Report extends Proposal {version:1;domain:'source-normalized';semantic_available:boolean;suspended:string|null;analysis:{region:string;solid:boolean;residual_median:number;inlier_fraction:number}[];bytes_fields:number;boundaries:string[]}
export interface Review {before:string;after:string;source:string;mask:string;width:number;height:number;source_width:number;source_height:number;domain:'source-normalized';review_domain:'production-output';quality:'proxy-render-srgb8';target:Target;note:string}
export type Mutation={action:'view';target:Target}|{action:'replace';target:Target;proposal:Proposal};
export interface Request {request_id:string;preview_id:string;session_id:string;document_id:string}
export interface Brush {target:Target;operation:'add'|'subtract';size:number;feather:number;flow:number;opacity:number}
export const TARGETS:Record<Target,string>={background:'背景范围',floor:'地面范围（手动）',protect:'保护主体 / 道具 / 阴影',intrusion:'穿帮标记',blemish:'祛瑕疵增强画笔',recover_intrusions:'恢复祛穿帮',recover_blemishes:'恢复祛瑕疵',recover_uniformity:'恢复光影均匀',recover_banding:'恢复色阶断层'};
export const neutral=():Proposal=>({parameters:{intrusions:0,blemish_background:0,blemish_floor:0,uniformity:0,brightness:0,banding:0,enhancement:0},region_mode:'manual',strokes:[]});
export function proposal(report?:Report):Proposal{return report?structuredClone({parameters:report.parameters,region_mode:report.region_mode,strokes:report.strokes}):neutral();}
export function stroke(point:[number,number,number],width:number,height:number,brush:Brush):Stroke {
 const radius=Math.min(width,height)*brush.size/200;
 return {id:crypto.randomUUID().replaceAll('-',''),target:brush.target,operation:brush.operation,
   axes:[[radius/width,0],[0,radius/height]],points:[point],feather:brush.feather/100,flow:brush.flow/100,opacity:brush.opacity/100};
}
export const CONTROL_IDS={intrusions:'d637886dca',blemishes:'c03981fad1',brush:'0eb173d7d8',uniformity:'508ddebe87',brightness:'07dabe5ea7',banding:'b5e8d5499a',enhancement:'98057214a1',recovery:'c68a287a5a',background:'75549ae6f0',floor:'f06957c177',add:'8505883728',subtract:'77953fa019',size:'5efc6b6509',feather:'4f3c23e230',flow:'7c9a2c1313',opacity:'6cd4af46bd',source_mask:'fcfeb35c00',update:'7e059306ef',confirm:'6a47eb1816'} as const;
export const control=(name:keyof typeof CONTROL_IDS)=>`PC-32474-C-${CONTROL_IDS[name]}`;
