export type LiquifyMode='push'|'reconstruct'|'smooth'|'rotate'|'pucker'|'bloat'|'left'|'freeze'|'thaw';
export const LABELS:Record<LiquifyMode,string>={push:'向前变形',reconstruct:'重建',smooth:'平滑',rotate:'旋转',pucker:'褶皱',bloat:'膨胀',left:'左推',freeze:'冻结',thaw:'解冻'};
export interface LiquifyStroke {id:string;mode:LiquifyMode;axes:[[number,number],[number,number]];points:[number,number,number,number][];density:number;pressure:number;rate:number;fixed_edges:boolean;direction:1|-1}
export interface BrushSettings {mode:LiquifyMode;size:number;density:number;pressure:number;rate:number;fixedEdges:boolean;direction:1|-1;showMask:boolean}
export interface LiquifyFinalReview {after:string;width:number;height:number;domain:'final-optical-output';quality:'proxy-render-srgb8';read_only:true;optics_signature:string}
export interface LiquifyImage {before:string;after:string;protection:string;width:number;height:number;domain:'post-effects-pre-crop-normalized';quality:'proxy-render-srgb8';drawing_space:'pre-optics';optics_signature:string;optics_active:boolean;final_review:LiquifyFinalReview;note:string}
export interface LiquifyReport {version:1;domain:string;strokes:LiquifyStroke[];suspended:string|null;bytes_field:number;boundaries:string[]}
export type LiquifyMutation={action:'view'|'clear'}|{action:'delete';id:string}|{action:'stroke';stroke:LiquifyStroke};
export interface LiquifyRequest {request_id:string;preview_id:string;session_id:string;document_id:string}
export function newStroke(p:[number,number],width:number,height:number,settings:BrushSettings,penPressure:number):LiquifyStroke {
  const radius=Math.min(width,height)*settings.size/200;
  return {id:crypto.randomUUID().replaceAll('-',''),mode:settings.mode,axes:[[radius/width,0],[0,radius/height]],
    points:[[...p,penPressure,0]],density:settings.density/100,pressure:settings.pressure/100,rate:settings.rate/100,
    fixed_edges:settings.fixedEdges,direction:settings.direction};
}
