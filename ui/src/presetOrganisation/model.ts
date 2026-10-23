export const schema='lrt.preset-organisation.v1';
export type Category={id:string;name:string;deleted:boolean};
export type Preset={id:string;name:string;kind:string;builtin:boolean;category_id:string;deleted:boolean;position:number};
export type Catalog={schema:string;revision:string;generation:number;categories:Category[];presets:Preset[];errors:{file:string;error:string}[];missing:{id:string;category_id:string}[]};
export type Action='category_create'|'category_rename'|'category_move'|'category_trash'|'category_restore'|'preset_rename'|'preset_move'|'preset_trash'|'preset_restore';
export type Edit={action:Action;id:string;name?:string;category_id?:string;before_id?:string|null};
export type Receipt={request_id:string;request_hash:string;action:Action;revision:string;generation:number};
export type Reply={protocol:number;request_id:string;action:string;success:boolean;outcome_unknown:boolean;error?:string;catalog?:Catalog;receipt?:Receipt|null;found?:boolean;target_request_id?:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const id=(v:unknown):v is string=>typeof v==='string'&&/^[a-z0-9._-]{1,64}$/.test(v)&&!v.startsWith('.')&&!v.includes('..');
const text=(v:unknown):v is string=>typeof v==='string'&&v.length>0;
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export function catalog(value:unknown):Catalog{
  if(!object(value)||value.schema!==schema||!hash(value.revision)||!Number.isSafeInteger(value.generation)||Number(value.generation)<0
    ||!Array.isArray(value.categories)||value.categories.length<2||value.categories.length>512||!Array.isArray(value.presets)||value.presets.length>10000||!Array.isArray(value.errors)||!Array.isArray(value.missing))throw Error('分类快照不完整');
  const categories=new Set<string>(),presets=new Set<string>(),positions=new Set<number>();
  for(const c of value.categories){if(!object(c)||!id(c.id)||!text(c.name)||typeof c.deleted!=='boolean'||categories.has(c.id))throw Error('分类身份无效');categories.add(c.id);}
  if(!categories.has('builtin')||!categories.has('custom'))throw Error('缺少系统分类');
  for(const p of value.presets){
    if(!object(p)||!id(p.id)||presets.has(p.id)||!text(p.name)||!text(p.kind)||typeof p.builtin!=='boolean'||typeof p.deleted!=='boolean'||!id(p.category_id)||!categories.has(p.category_id)||!Number.isSafeInteger(p.position)||Number(p.position)<0||positions.has(Number(p.position)))throw Error('预设引用或顺序无效');
    if(p.builtin&&(p.category_id!=='builtin'||p.deleted))throw Error('内置预设状态无效');
    presets.add(p.id);positions.add(Number(p.position));
  }
  if(!value.errors.every(e=>object(e)&&typeof e.file==='string'&&typeof e.error==='string'))throw Error('目录错误信息无效');
  if(!value.missing.every(v=>object(v)&&id(v.id)&&id(v.category_id)&&categories.has(v.category_id)&&!presets.has(v.id)))throw Error('离线预设引用无效');
  return value as unknown as Catalog;
}
export function validateReply(value:Reply,request:Record<string,unknown>){
  if(!value||value.protocol!==1||value.request_id!==request.request_id||value.action!==request.action||typeof value.success!=='boolean'||typeof value.outcome_unknown!=='boolean'||value.success&&value.outcome_unknown)throw Error('目录回执身份无效');
  if(!value.success)return;
  if(value.action==='snapshot'){catalog(value.catalog);return;}
  if(value.action==='receipt'&&value.target_request_id!==request.target_request_id)throw Error('回执查询目标不匹配');
  if(value.action==='receipt'&&value.found===false&&value.receipt===null)return;
  const r=value.receipt;
  if(!r||r.request_id!==(value.action==='receipt'?request.target_request_id:request.request_id)||!hash(r.revision)||!hash(r.request_hash)||!Number.isSafeInteger(r.generation)||r.generation<0||value.action!=='receipt'&&r.action!==value.action)throw Error('缺少持久化回执');
}
export const normalName=(value:string)=>value.trim().normalize('NFC');
export const validName=(value:string)=>Array.from(normalName(value)).length>0&&Array.from(normalName(value)).length<=20&&!/\p{C}/u.test(normalName(value));
