/** PC-32466 six independent 2D controls. Numeric ranges are local policy. */
export const KEYS=['size','height','position','bridge','wing','tip'] as const;
export type NoseKey=typeof KEYS[number];
export type NoseShape={version:1}&Record<NoseKey,number>;
export interface NoseFact {control:NoseKey;reason:string|null;requested:boolean;applied:boolean;support_px:number;method:string;limitation:string}
export const IDS={family:'PC-32466-C-ba582ff45d',size:'PC-32466-C-0025490aa7',height:'PC-32466-C-180241806a',position:'PC-32466-C-1ef85157f8',bridge:'PC-32466-C-6598ad2758',wing:'PC-32466-C-aed80c5608',tip:'PC-32466-C-aec9e15569'};
export const LABELS:Record<NoseKey,string>={size:'大小',height:'鼻高',position:'左右',bridge:'鼻梁',wing:'鼻翼',tip:'鼻尖'};
export const HINTS:Record<NoseKey,string>={size:'整体缩小 ← → 整体放大',height:'下移 ← → 上移（位置，不是鼻梁立体高度）',position:'画面左移 ← → 画面右移（随头部倾斜，不是人物侧别）',bridge:'鼻梁收窄 ← → 鼻梁增宽',wing:'鼻翼收窄 ← → 鼻翼增宽',tip:'鼻尖缩小 ← → 鼻尖放大'};
export const neutral=():NoseShape=>({version:1,size:0,height:0,position:0,bridge:0,wing:0,tip:0});
export function check(value:unknown):NoseShape {
  if(value==null)return neutral();
  if(typeof value!=='object'||Array.isArray(value))throw new Error('鼻形配方无效');
  const raw=value as Record<string,unknown>;
  if(raw.version!==1||Object.keys(raw).sort().join(',')!==['version',...KEYS].sort().join(','))throw new Error('鼻形配方字段或版本无效');
  const result=neutral();
  for(const k of KEYS){const n=raw[k];if(typeof n!=='number'||!Number.isFinite(n)||Math.abs(n)>1)throw new Error('鼻形数值需在 -1 至 1');result[k]=n;}
  return result;
}
export function adjust(value:NoseShape,k:NoseKey,n:number):NoseShape{return check({...check(value),[k]:n});}
export const active=(value:unknown):boolean=>{const r=check(value);return KEYS.some(k=>r[k]!==0);};
const REASONS:Record<string,string>={insufficient_resolution:'鼻部太小，暂不应用',visibility_support_unavailable:'缺少可信遮挡来源，请先完成人像分析',sideface_or_foreshortened:'侧脸或鼻部压缩过强',degenerate_nose_geometry:'鼻部关键点关系异常',clipped_support:'鼻部或周围参考超出画面',occluded_or_insufficient_support:'被遮挡或可靠像素不足',no_reliable_visible_nose_evidence:'鼻部缺少可靠可见纹理，可能低对比或遮挡',nostril_evidence_missing:'未确认足够的鼻孔阴影支持'};
export const reason=(fact?:NoseFact)=>fact?.reason?(REASONS[fact.reason]??fact.reason):undefined;
