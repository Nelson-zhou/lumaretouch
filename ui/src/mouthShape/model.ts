/** PC-32466 mouth intent. Only gummy promises bilateral unlock in the guide. */
export const KEYS=['size','width','vertical','horizontal','gummy','m_lip','tilt','upper','lower'] as const;
export type MouthKey=typeof KEYS[number];
export type ScalarKey=Exclude<MouthKey,'gummy'>;
export type MouthSide='left'|'right';
export interface Gummy {linked:boolean;left:number;right:number}
export type MouthShape={version:1;gummy:Gummy}&Record<ScalarKey,number>;
export interface MouthFact {control:string;reason:string|null;requested:boolean;applied:boolean;support_px:number;method:string;limitation:string}
export const IDS={family:'PC-32466-C-cbb4c198e8',size:'PC-32466-C-c6608e6df0',width:'PC-32466-C-25a12375ad',vertical:'PC-32466-C-d9f05e02e0',horizontal:'PC-32466-C-76ebd0c9bb',gummy:'PC-32466-C-eb54b58b96',m_lip:'PC-32466-C-64e1410070',tilt:'PC-32466-C-120b651906',upper:'PC-32466-C-71447c0f00',lower:'PC-32466-C-5fd3068bc8'};
export const LABELS:Record<MouthKey,string>={size:'大小',width:'嘴宽',vertical:'上下',horizontal:'左右',gummy:'露龈调整',m_lip:'M 唇',tilt:'倾斜',upper:'丰上唇',lower:'丰下唇'};
export const HINTS:Record<MouthKey,string>={size:'缩小 ← → 放大',width:'变窄 ← → 变宽',vertical:'上移 ← → 下移（与眼形、鼻高的符号不同）',horizontal:'向画面左侧 ← → 向画面右侧',gummy:'仅将已有上唇向下移动，遮盖部分牙龈/牙齿；不反向暴露未知组织',m_lip:'唇珠与唇峰更明显、嘴角微扬 ← → 唇型较平整；不是旧版微笑',tilt:'头部局部平面逆时针 ← → 顺时针；官网方向文案重复，此正负约定属于本产品',upper:'上唇变薄 ← → 变厚',lower:'下唇变薄 ← → 变厚'};
export const neutral=():MouthShape=>({version:1,size:0,width:0,vertical:0,horizontal:0,m_lip:0,tilt:0,upper:0,lower:0,gummy:{linked:true,left:0,right:0}});
export function check(value:unknown):MouthShape {
  if(value==null)return neutral();
  if(typeof value!=='object'||Array.isArray(value))throw new Error('嘴形配方无效');
  const r=value as Record<string,unknown>;
  if(r.version!==1||Object.keys(r).sort().join(',')!==['version',...KEYS].sort().join(','))throw new Error('嘴形字段或版本无效');
  const out=neutral();
  for(const k of KEYS) {
    if(k==='gummy') {
      const g=r.gummy as Gummy;
      if(!g||typeof g!=='object'||Array.isArray(g)||Object.keys(g).sort().join(',')!=='left,linked,right'||typeof g.linked!=='boolean')throw new Error('露龈联动参数无效');
      for(const s of ['left','right'] as const)if(typeof g[s]!=='number'||!Number.isFinite(g[s])||g[s]<0||g[s]>1)throw new Error('露龈调整只接受 0 至 1');
      out.gummy={...g};
    } else {
      const n=r[k];
      if(typeof n!=='number'||!Number.isFinite(n)||Math.abs(n)>1)throw new Error('嘴形数值需在 -1 至 1');
      out[k]=n;
    }
  }
  return out;
}
export function adjust(value:MouthShape,key:MouthKey,n:number,side?:MouthSide):MouthShape {
  const r=check(value);
  if(key==='gummy') {
    if(!side)throw new Error('露龈调整需要人物侧别');
    r.gummy[side]=n;
    if(r.gummy.linked)r.gummy[side==='left'?'right':'left']=n;
  } else {r[key]=n;}
  return check(r);
}
export function link(value:MouthShape,linked:boolean):MouthShape {const r=check(value);r.gummy.linked=linked;return r;}
export const active=(value:unknown):boolean=>{const r=check(value);return KEYS.some(k=>k==='gummy'?r.gummy.left!==0||r.gummy.right!==0:r[k]!==0);};
const REASONS:Record<string,string>={atomic_request_refused:'同次请求有其他控件被拒绝，本项也未应用',no_reliable_lip_texture:'缺少可靠的可见唇部纹理',insufficient_resolution:'嘴部像素不足',insufficient_lip_resolution:'上下唇纹理像素不足',degenerate_lip_geometry:'唇部几何退化',clipped_or_degenerate_lips:'唇环被裁切或退化',insufficient_lip_ring:'可靠唇环纹理不足',visibility_support_unavailable:'缺少可信遮挡来源，请先完成人像分析',sideface_or_foreshortened:'侧脸或透视压缩过强',occluded_or_insufficient_support:'局部遮挡或可靠像素不足',closed_or_unobservable_aperture:'闭口或无法确认可见嘴部开口；不生成嘴部内部'};
export const reason=(fact?:MouthFact)=>fact?.reason?(REASONS[fact.reason]??fact.reason):undefined;
