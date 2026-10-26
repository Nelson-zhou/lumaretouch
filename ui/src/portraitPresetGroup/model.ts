// SPDX-License-Identifier: GPL-3.0-or-later
// Source-only group review contract. Runtime/photographic acceptance UNRUN.
import {validReferenceReview,type ReferenceReview} from '../referenceColor/ReferenceColorReview';
export const REFERENCE_MODULE = 'lnx.reference_color.v1';
export const MODULES = ['lnx.skin.v1', 'lnx.exposure.v1', 'lnx.white_balance.v1'];
export const GLOBAL_MODULES = ['lnx.exposure.v1', 'lnx.white_balance.v1'];
export const PEOPLE_MODULES = ['lnx.skin_finish.v1', 'lnx.skin_texture.v1'];
export type GroupMode = 'legacy_scalar'|'retained_people'|'reference_color';
export type FaceRef = {asset_sha256:string;face_instance_id:string;analysis_revision:number};
export type ImageMeta = {mime:'image/png';width:number;height:number;sha256:string;byte_length:number;page_count:number};
export type Target = {document_id:string;revision:string;path:string;review_sha256:string;before:ImageMeta;after:ImageMeta;face_count?:number;face_refs?:FaceRef[];reference_color?:ReferenceReview};
export type Plan = {preflight_token:string;preset_id:string;preset_sha256:string;module_scope:string[];targets:Target[];mode?:GroupMode};
export type Preset = {id:string;name:string;preset_sha256:string;module_ids:string[];portrait_group_support?:{supported:boolean;reason:string|null;mode:GroupMode}};
export type Reply = Record<string,unknown>;
export const hash = (v:unknown):v is string => typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const id = (v:unknown):v is string => typeof v==='string'&&/^[A-Za-z0-9._:-]{1,128}$/.test(v);
const object = (v:unknown):v is Reply => !!v&&typeof v==='object'&&!Array.isArray(v);
export function imageMeta(v:unknown):v is ImageMeta {
  return object(v)&&v.mime==='image/png'&&hash(v.sha256)&&Number.isSafeInteger(v.width)&&Number(v.width)>0&&Number(v.width)<=1024
    &&Number.isSafeInteger(v.height)&&Number(v.height)>0&&Number(v.height)<=1024&&Number.isSafeInteger(v.byte_length)
    &&Number(v.byte_length)>=33&&Number(v.byte_length)<=4*1024*1024&&v.page_count===Math.ceil(Number(v.byte_length)/65536);
}
function peopleTarget(t:Reply):boolean {
  const refs=t.face_refs;
  return Number.isSafeInteger(t.face_count)&&Number(t.face_count)>=1&&Number(t.face_count)<=8
    &&Array.isArray(refs)&&refs.length===t.face_count&&refs.every((r,i)=>object(r)
      &&Object.keys(r).length===3&&hash(r.asset_sha256)&&id(r.face_instance_id)
      &&Number.isSafeInteger(r.analysis_revision)&&Number(r.analysis_revision)>=0
      &&r.asset_sha256===refs[0].asset_sha256&&!refs.slice(0,i).some(other=>other.face_instance_id===r.face_instance_id));
}
export function checkedPlan(v:unknown,docs:string[],preset:Preset):Plan {
  if(!object(v)||v.success!==true||v.portrait_preset!==true||!(typeof v.preflight_token==='string'&&/^[a-f0-9]{32}$/.test(v.preflight_token))||v.preset_id!==preset.id||v.preset_sha256!==preset.preset_sha256
    ||!Array.isArray(v.module_scope)||JSON.stringify([...v.module_scope].sort())!==JSON.stringify([...preset.module_ids].sort())
    ||!Array.isArray(v.targets)||v.targets.length!==docs.length||docs.length<1||docs.length>8||new Set(docs).size!==docs.length)throw Error('整组预检身份、预设或完整目标集不匹配。');
  const retained=preset.portrait_group_support?.mode==='retained_people';
  const reference=preset.portrait_group_support?.mode==='reference_color';
  if(reference?v.mode!=='reference_color':retained?v.mode!=='retained_people':v.mode!==undefined&&v.mode!=='legacy_scalar')throw Error('整组人物模式与所选预设不匹配。');
  const targets=v.targets;
  if(targets.some((t,i)=>!object(t)||t.document_id!==docs[i]||typeof t.revision!=='string'||!/^(0|[1-9][0-9]{0,19})$/.test(t.revision)||BigInt(t.revision)>18446744073709551615n
    ||(reference&&!validReferenceReview(t.reference_color,String(t.document_id),String(t.revision)))||(retained&&!peopleTarget(t))||typeof t.path!=='string'||!hash(t.review_sha256)||!imageMeta(t.before)||!imageMeta(t.after)))throw Error('目标缺少完整冻结前后图证明，整组未批准。');
  return structuredClone(v) as unknown as Plan;
}
export function catalogue(v:unknown):Preset[] {
  if(!object(v)||v.complete!==true||!Array.isArray(v.presets)||!Array.isArray(v.errors)||v.errors.length)throw Error('预设目录不完整，不能选择部分目录继续。');
  return v.presets.filter((p):p is Preset=>object(p)&&id(p.id)&&typeof p.name==='string'&&hash(p.preset_sha256)
    &&Array.isArray(p.module_ids)&&p.module_ids.length>0&&new Set(p.module_ids).size===p.module_ids.length
    &&(p.portrait_group_support===undefined?p.module_ids.every(op=>MODULES.includes(String(op))):
      object(p.portrait_group_support)&&p.portrait_group_support.supported===true&&p.portrait_group_support.reason===null
      &&(p.portrait_group_support.mode==='reference_color'?p.module_ids.length===1&&p.module_ids[0]===REFERENCE_MODULE:p.portrait_group_support.mode==='retained_people'?p.module_ids.some(op=>PEOPLE_MODULES.includes(String(op)))&&p.module_ids.every(op=>PEOPLE_MODULES.includes(String(op))||GLOBAL_MODULES.includes(String(op))):
        p.portrait_group_support.mode==='legacy_scalar'&&p.module_ids.every(op=>MODULES.includes(String(op))))));
}
export function scopeLabel(modules:string[]):string {
  const global=modules.filter(op=>GLOBAL_MODULES.includes(op)).map(op=>op==='lnx.exposure.v1'?'全图曝光':'全图白平衡');
  const people=modules.filter(op=>PEOPLE_MODULES.includes(op)).map(op=>op==='lnx.skin_finish.v1'?'逐脸美白／红润':'逐脸质感／清晰度');
  return [...global,...people,...(modules.includes(REFERENCE_MODULE)?['逐图参考白平衡／亮度统一']:[])].join(' ＋ ');
}
export const acknowledgments=(p:Plan)=>p.targets.map(t=>({document_id:t.document_id,revision:t.revision,before_sha256:t.before.sha256,after_sha256:t.after.sha256,review_sha256:t.review_sha256}));
async function digest(bytes:Uint8Array){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new Uint8Array(bytes).buffer))].map(b=>b.toString(16).padStart(2,'0')).join('');}
function encode(bytes:Uint8Array){let s='';for(let i=0;i<bytes.length;i+=16384)s+=String.fromCharCode(...bytes.subarray(i,i+16384));return btoa(s);}
export async function imageData(plan:Plan,target:Target,side:'before'|'after',read:(page:number)=>Promise<Reply>,current:()=>boolean):Promise<string>{
  const meta=target[side],bytes=new Uint8Array(meta.byte_length);
  for(let page=0;page<meta.page_count;page++){
    if(!current())throw Error('审核已变化。');
    const r=await read(page),size=Math.min(65536,meta.byte_length-page*65536);
    if(!current()||r.success!==true||r.portrait_preset!==true||r.preflight_token!==plan.preflight_token||r.document_id!==target.document_id||r.side!==side
      ||r.revision!==target.revision||r.review_sha256!==target.review_sha256||r.mime!==meta.mime||r.width!==meta.width||r.height!==meta.height
      ||r.page_bytes!==65536||r.offset!==page*65536||r.page_byte_length!==size||r.page!==page||r.page_count!==meta.page_count||r.byte_length!==meta.byte_length||r.sha256!==meta.sha256||!hash(r.page_sha256)
      ||typeof r.base64!=='string'||r.base64.length>87384)throw Error('图像页面不属于本次冻结目标。');
    let chunk:Uint8Array;try{chunk=Uint8Array.from(atob(r.base64),c=>c.charCodeAt(0));}catch{throw Error('图像编码无效。');}
    if(chunk.length!==size||encode(chunk)!==r.base64||await digest(chunk)!==r.page_sha256)throw Error('图像分页 SHA-256 不匹配。');
    bytes.set(chunk,page*65536);
  }
  const h=new DataView(bytes.buffer);
  if(!current()||await digest(bytes)!==meta.sha256||[137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82].some((x,i)=>bytes[i]!==x)
    ||h.getUint32(16)!==meta.width||h.getUint32(20)!==meta.height||bytes[24]!==8||bytes[25]!==2||bytes[26]||bytes[27]||bytes[28])throw Error('完整 PNG 内容、尺寸或 SHA-256 不匹配。');
  return `data:image/png;base64,${encode(bytes)}`;
}
