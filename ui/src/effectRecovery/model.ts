import type {Point} from '../sourcePatch/geometry';
import type {MaskObject} from '../localMasks/model';
export type RecoveryTarget='skin_smoothing'|'fabric_fine'|'facial_wrinkles'|'lip_makeup'|'eye_light'|'blush_makeup'|'background_replace';
export type RecoveryStroke=Extract<MaskObject,{kind:'brush'}>;
export type RecoveryMutation={action:'stroke';target:RecoveryTarget;stroke:RecoveryStroke}|
  {action:'view'|'clear';target:RecoveryTarget}|{action:'enable';target:RecoveryTarget;enabled:boolean}|
  {action:'delete';target:RecoveryTarget;id:string};
export interface RecoveryReport {
  version:1;targets:{target:RecoveryTarget;label:string;stage:string;active:boolean;reason:string|null;enabled:boolean;strokes:RecoveryStroke[]}[];
  suspended:string|null;suspended_targets?:Partial<Record<RecoveryTarget,string>>;bytes_masks:number;boundaries:string[];
}
export interface BrushSettings {size:number;strength:number;feather:number;operation:'add'|'subtract'}
export const LABELS:Record<RecoveryTarget,string>={skin_smoothing:'磨皮与肌理',fabric_fine:'衣物细褶',facial_wrinkles:'面部祛纹八部位',lip_makeup:'唇妆增强',eye_light:'眼神光素材',blush_makeup:'腮红',background_replace:'换底边缘'};
export function newStroke(point:Point,width:number,height:number,settings:BrushSettings):RecoveryStroke {
  const radius=Math.min(width,height)*settings.size/200;
  return {id:crypto.randomUUID().replaceAll('-',''),name:settings.operation==='add'?'擦回效果':'重新显示效果',
    kind:'brush',enabled:true,operation:settings.operation,opacity:settings.strength/100,feather:settings.feather,
    points:[point],axes:[[radius/width,0],[0,radius/height]]};
}
export interface RecoveryImage {
  before:string;after:string;width:number;height:number;domain:'production-output';quality:'proxy-render-srgb8';note:string;
}
export interface RecoveryRequest {request_id:string;preview_id:string;capture_id:string;ticket:string;document_id:string}
