/** Three independent local scales, not claimed PixCake numeric parity. */
export const KEYS = ['saturation','brightness','dimensionality'] as const;
export type LipKey = typeof KEYS[number];
export interface LipMakeup {version:1;saturation:number;brightness:number;dimensionality:number}
export interface LipFact {reason:string|null;geom_px?:number;gated_px:number;changed_px?:number;face_identity?:string;limitation?:string}
export const IDS = {family:'944899f5fd',saturation:'3d1502871b',brightness:'d5fc30a763',dimensionality:'21e4a8d464'};
export const LABELS:Record<LipKey,string> = {saturation:'饱和度',brightness:'明度',dimensionality:'立体度'};
export const neutral = ():LipMakeup => ({version:1,saturation:0,brightness:0,dimensionality:0});
export function check(value:unknown):LipMakeup {
  if(value==null) return neutral();
  if(typeof value!=='object'||Array.isArray(value)) throw new Error('唇妆配方无效');
  const v=value as Record<string,unknown>;
  if(v.version!==1||Object.keys(v).sort().join(',')!==['version',...KEYS].sort().join(',')) throw new Error('唇妆配方字段或版本无效');
  for(const key of KEYS) if(typeof v[key]!=='number'||!Number.isFinite(v[key])||Number(v[key]) < -1||Number(v[key])>1) throw new Error('唇妆数值必须在 -1 至 1');
  return {version:1,saturation:Number(v.saturation),brightness:Number(v.brightness),dimensionality:Number(v.dimensionality)};
}
export const active=(v:unknown):boolean=>KEYS.some(k=>check(v)[k]!==0);
export function patch(value:LipMakeup,key:LipKey,amount:number):LipMakeup {return check({...value,[key]:amount});}
export function preset(value:unknown):LipMakeup {return check(value);}
const REASONS:Record<string,string>={
  actual_selected_face_required:'请先选中真实检测到的人物',insufficient_resolution:'嘴唇太小，无法可靠保留唇纹',
  sideface_or_foreshortened:'侧脸或唇形压缩过强，暂不应用',clipped_or_degenerate_lips:'唇部边界不完整或关键点几何异常',
  insufficient_lip_ring:'可处理的唇缘区域不足',visibility_support_unavailable:'缺少可信的遮挡排除来源，请先完成人像分析',
  occluded_or_insufficient_support:'嘴唇被遮挡或可靠支持不足',no_measurable_change:'当前设置没有可测量的像素变化',
};
export const explanation=(fact?:LipFact):string|undefined=>fact?.reason&&fact.reason!=='disabled'?(REASONS[fact.reason]??fact.reason):undefined;
