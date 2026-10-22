/** Portable numeric intent only; ranges are local product policy. */
export const KEYS=['thickness','spacing','tilt','arch','position','inner_length','outer_length'] as const;
export type BrowKey=typeof KEYS[number];
export type BrowSide='left'|'right';
export interface Bilateral {linked:boolean;left:number;right:number}
export type BrowShape={version:1}&Record<BrowKey,Bilateral>;
export interface BrowFact {side:BrowSide;reason:string|null;requested:boolean;applied:boolean;support_px:number}
export const IDS={family:'PC-32466-C-a25ee7adaa',thickness:'PC-32466-C-3a0e5b3aa6',spacing:'PC-32466-C-aef1ac96b6',tilt:'PC-32466-C-75f4aab5d9',arch:'PC-32466-C-5cd2097ba1',position:'PC-32466-C-3b36aa8899',inner_length:'PC-32466-C-b7ff3a0ac6',outer_length:'PC-32466-C-29f403bf68'};
export const LABELS:Record<BrowKey,string>={thickness:'粗细',spacing:'眉距',tilt:'倾斜',arch:'形状',position:'位置',inner_length:'眉头长短',outer_length:'眉尾长短'};
export const HINTS:Record<BrowKey,string>={thickness:'细 ← → 粗',spacing:'远 ← → 近',tilt:'眉尾上倾 ← → 眉尾下倾',arch:'平眉 ← → 挑眉',position:'下移 ← → 上移',inner_length:'缩短 ← → 延长眉头',outer_length:'缩短 ← → 延长眉尾'};
export const neutral=():BrowShape=>({version:1,...Object.fromEntries(KEYS.map(k=>[k,{linked:true,left:0,right:0}]))} as BrowShape);
export function check(value:unknown):BrowShape {
  if(value==null) return neutral();
  if(typeof value!=='object'||Array.isArray(value)) throw new Error('眉形配方无效');
  const r=value as Record<string,unknown>;
  if(r.version!==1||Object.keys(r).sort().join(',')!==['version',...KEYS].sort().join(',')) throw new Error('眉形配方字段或版本无效');
  const out=neutral();
  for(const k of KEYS) {
    const b=r[k] as Bilateral;
    if(!b||typeof b!=='object'||Array.isArray(b)||Object.keys(b).sort().join(',')!=='left,linked,right'||typeof b.linked!=='boolean') throw new Error('眉形双侧配方无效');
    for(const side of ['left','right'] as const) if(typeof b[side]!=='number'||!Number.isFinite(b[side])||Math.abs(b[side])>1) throw new Error('眉形数值需在 -1 至 1');
    out[k]={...b};
  }
  return out;
}
export function adjust(value:BrowShape,k:BrowKey,side:BrowSide,n:number):BrowShape {
  const r=check(value);r[k][side]=n;if(r[k].linked)r[k][side==='left'?'right':'left']=n;return check(r);
}
export function link(value:BrowShape,k:BrowKey,linked:boolean):BrowShape {const r=check(value);r[k].linked=linked;return r;}
export const active=(v:unknown):boolean=>KEYS.some(k=>check(v)[k].left!==0||check(v)[k].right!==0);
const REASONS:Record<string,string>={insufficient_resolution:'眉毛太小，暂不应用',visibility_support_unavailable:'缺少可信遮挡来源，请先完成人像分析',degenerate_brow_chains:'眉毛上下边界异常',folded_or_foreshortened:'眉形压缩或关键点异常',sideface_or_foreshortened:'侧脸压缩过强',clipped_brow:'眉毛超出画面',clipped_reference_support:'眉毛附近可见参考不足',occluded_or_insufficient_support:'被遮挡或可靠支持不足',no_reliable_visible_brow_evidence:'未确认可靠的可见眉毛，可能颜色过浅或被遮挡',incomplete_visible_brow_support:'眉头、中段或眉尾缺少可见支持'};
export const reason=(fact?:BrowFact)=>fact?.reason?(REASONS[fact.reason]??fact.reason):undefined;
