/** Portable numeric intent only; ranges are local product policy. */
export const KEYS=["size", "iris_size", "height", "width", "spacing", "inner_corner", "outer_corner", "lower_lid", "tilt", "position"] as const;
export type EyeKey=typeof KEYS[number];
export type EyeSide='left'|'right';
export interface Bilateral {linked:boolean;left:number;right:number}
export type EyeShape={version:1}&Record<EyeKey,Bilateral>;
export interface EyeFact {side:EyeSide;control:EyeKey;reason:string|null;requested:boolean;applied:boolean;support_px:number;method:string;limitation:string}
export const IDS={"family": "PC-32466-C-9069cc8f2c", "size": "PC-32466-C-350a901827", "iris_size": "PC-32466-C-a40648c2c9", "height": "PC-32466-C-c39023ab15", "width": "PC-32466-C-02e379c464", "spacing": "PC-32466-C-4aa3486419", "inner_corner": "PC-32466-C-59bdc2ef4c", "outer_corner": "PC-32466-C-6f1eb8b201", "lower_lid": "PC-32466-C-b2458f8502", "tilt": "PC-32466-C-89afddb33a", "position": "PC-32466-C-37e5823f58"};
export const LABELS:Record<EyeKey,string>={"size": "整体大小", "iris_size": "眼瞳大小", "height": "眼高", "width": "眼宽", "spacing": "眼距", "inner_corner": "内眼角", "outer_corner": "外眼角", "lower_lid": "眼睑下至", "tilt": "倾斜", "position": "位置"};
export const HINTS:Record<EyeKey,string>={"size": "缩小 ← → 放大", "iris_size": "缩小现有可见虹膜 ← → 放大现有可见虹膜", "height": "上下眼睑间距缩短 ← → 拉大（不是眼睛上下位置）", "width": "横向缩短 ← → 拉长", "spacing": "靠近 ← → 分开", "inner_corner": "收缩眼头 ← → 延长眼头", "outer_corner": "收缩眼尾 ← → 延长眼尾", "lower_lid": "下眼睑上移 ← → 下移", "tilt": "眼尾下降/眼头上升 ← → 眼尾上升/眼头下降", "position": "下移 ← → 上移"};
export const neutral=():EyeShape=>({version:1,...Object.fromEntries(KEYS.map(k=>[k,{linked:true,left:0,right:0}]))} as EyeShape);
export function check(value:unknown):EyeShape {
  if(value==null) return neutral();
  if(typeof value!=='object'||Array.isArray(value)) throw new Error('眼形配方无效');
  const r=value as Record<string,unknown>;
  if(r.version!==1||Object.keys(r).sort().join(',')!==['version',...KEYS].sort().join(',')) throw new Error('眼形配方字段或版本无效');
  const out=neutral();
  for(const k of KEYS) {
    const b=r[k] as Bilateral;
    if(!b||typeof b!=='object'||Array.isArray(b)||Object.keys(b).sort().join(',')!=='left,linked,right'||typeof b.linked!=='boolean') throw new Error('眼形双侧配方无效');
    for(const side of ['left','right'] as const) if(typeof b[side]!=='number'||!Number.isFinite(b[side])||Math.abs(b[side])>1) throw new Error('眼形数值需在 -1 至 1');
    out[k]={...b};
  }
  return out;
}
export function adjust(value:EyeShape,k:EyeKey,side:EyeSide,n:number):EyeShape {
  const r=check(value);r[k][side]=n;if(r[k].linked)r[k][side==='left'?'right':'left']=n;return check(r);
}
export function link(value:EyeShape,k:EyeKey,linked:boolean):EyeShape {const r=check(value);r[k].linked=linked;return r;}
export const active=(v:unknown):boolean=>KEYS.some(k=>check(v)[k].left!==0||check(v)[k].right!==0);
const REASONS:Record<string,string>={atomic_request_refused:'同次请求中另一控件被拒绝，本次整体未应用',insufficient_resolution:'眼部太小',closed_or_insufficient_resolution:'闭眼或眼裂像素不足',closed_or_unobservable_opening:'无法确认真实可见眼裂；不进行睁眼生成',degenerate_eye_geometry:'眼部几何退化',visibility_support_unavailable:'缺少可信遮挡来源，请先完成人像分析',sideface_or_foreshortened:'侧脸或眼部透视压缩过强',clipped_support:'眼部参考超出画面',occluded_or_insufficient_support:'局部被遮挡或可靠像素不足',no_reliable_visible_eye_evidence:'局部缺少可靠可见纹理',iris_not_fully_observable:'虹膜环未完整可见，不能生成隐藏部分',iris_texture_evidence_missing:'未确认可靠虹膜纹理'};
export const reason=(fact?:EyeFact)=>fact?.reason?(REASONS[fact.reason]??fact.reason):undefined;
