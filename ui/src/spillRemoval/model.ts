import type {MaskObject} from '../localMasks/model';

export const SPILL_LIMITS={edge:640,pngBytes:1024*1024,base64:1398104,objects:64} as const;
export type SpillRecipe={version:1;algorithm:'lrt-spill-removal-v1';enabled:boolean;strength:number;coverage:null|{reviewed:true;[key:string]:unknown}};
export type SpillParameters={enabled:boolean;strength:number};
export type SpillImage={mime:'image/png';width:number;height:number;sha256:string;base64:string};
export type SpillFence={recipe_document_id:string;recipe_revision:string};
export type SpillReview=SpillFence&{version:1;token:string;source:{sha256:string;width:number;height:number};candidate_sha256:string;before:SpillImage;after:SpillImage;boundaries:string[]};
export type SpillPreviewFields={parameters:SpillParameters;coverage_ids:null|string[];coverage_reviewed:boolean};
export type SpillApplyFields={token:string;reviewed:true;before_sha256:string;after_sha256:string};
export type SpillNotSent={requested:false;not_sent:true;protocol:1;action:string;request_id:string;document_id:string;error:string};
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const fields=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const size=(v:unknown,max:number):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>0&&v<=max;
export function spillNotSent(value:unknown,expected:{action:string;request_id:string;document_id:string}):value is SpillNotSent{
 return object(value)&&fields(value,['requested','not_sent','protocol','action','request_id','document_id','error'])
  &&value.requested===false&&value.not_sent===true&&value.protocol===1&&value.action===expected.action
  &&value.request_id===expected.request_id&&value.document_id===expected.document_id
  &&typeof value.error==='string'&&value.error.length>0&&value.error.length<=4096;
}
export const spillToken=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{32}$/.test(v)&&!/^0+$/.test(v);
// Local mask IDs have a different, legacy-compatible contract from review tokens.
export const spillObjectId=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(v);
export function spillRevision(v:unknown):v is string{return typeof v==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(v)&&BigInt(v)<=18446744073709551615n;}
export function validSpillImage(v:unknown):v is SpillImage{
 return object(v)&&fields(v,['mime','width','height','sha256','base64'])&&v.mime==='image/png'&&hash(v.sha256)
  &&size(v.width,SPILL_LIMITS.edge)&&size(v.height,SPILL_LIMITS.edge)&&typeof v.base64==='string'
  &&v.base64.length<=SPILL_LIMITS.base64&&v.base64.length%4===0&&v.base64.startsWith('iVBOR')&&/^[A-Za-z0-9+/]+={0,2}$/.test(v.base64);
}
export function validSpillReview(v:unknown,fence:SpillFence):v is SpillReview{
 return object(v)&&fields(v,['version','token','recipe_document_id','recipe_revision','source','candidate_sha256','before','after','boundaries'])
  &&v.version===1&&spillToken(v.token)&&v.recipe_document_id===fence.recipe_document_id&&!!fence.recipe_document_id
  &&spillRevision(v.recipe_revision)&&v.recipe_revision===fence.recipe_revision&&hash(v.candidate_sha256)
  &&object(v.source)&&fields(v.source,['sha256','width','height'])&&hash(v.source.sha256)&&size(v.source.width,1000000)&&size(v.source.height,1000000)
  &&validSpillImage(v.before)&&validSpillImage(v.after)&&v.before.width===v.after.width&&v.before.height===v.after.height
  &&Array.isArray(v.boundaries)&&v.boundaries.length<=32&&v.boundaries.every(s=>typeof s==='string'&&s.length<=4096);
}
/** Real browser decode/load is a separate requirement from byte hashing. */
export async function verifySpillImage(value:SpillImage):Promise<boolean>{
 try{
  if(!validSpillImage(value))return false;
  const decoded=atob(value.base64);
  if(btoa(decoded)!==value.base64||decoded.length<33||decoded.length>SPILL_LIMITS.pngBytes)return false;
  const bytes=Uint8Array.from(decoded,c=>c.charCodeAt(0));
  if(![137,80,78,71,13,10,26,10].every((v,i)=>bytes[i]===v))return false;
  const view=new DataView(bytes.buffer);
  if(view.getUint32(8)!==13||view.getUint32(12)!==0x49484452||view.getUint32(16)!==value.width||view.getUint32(20)!==value.height)return false;
  const digest=await crypto.subtle.digest('SHA-256',bytes);
  return Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('')===value.sha256;
 }catch{return false;}
}
export function spillReviewKey(value:SpillReview):string{return JSON.stringify([value.token,value.recipe_document_id,value.recipe_revision,value.source,value.candidate_sha256,value.before.sha256,value.after.sha256]);}
export function spillApplyFields(value:SpillReview):SpillApplyFields{return {token:value.token,reviewed:true,before_sha256:value.before.sha256,after_sha256:value.after.sha256};}
export const manualSpillObject=(value:MaskObject):boolean=>value.enabled&&(value.kind==='brush'&&value.points.length>0||value.kind==='linear'||value.kind==='radial');
export function validSpillPreviewFields(value:SpillPreviewFields):boolean{
 const ids=value.coverage_ids;
 return typeof value.parameters.enabled==='boolean'&&Number.isFinite(value.parameters.strength)&&value.parameters.strength>=0&&value.parameters.strength<=100
  &&typeof value.coverage_reviewed==='boolean'&&(ids===null?!value.coverage_reviewed:Array.isArray(ids)&&ids.length<=SPILL_LIMITS.objects&&new Set(ids).size===ids.length
   &&ids.every(spillObjectId)&&(ids.length>0?value.coverage_reviewed:!value.coverage_reviewed));
}
