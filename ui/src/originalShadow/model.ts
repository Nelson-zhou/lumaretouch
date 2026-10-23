import type {LocalMaskReport,MaskObject} from '../localMasks/model';

export const ORIGINAL_SHADOW_LIMITS={edge:512,pngBytes:1024*1024,base64:1398104,objects:64,requestBytes:65536} as const;
export type OriginalShadowSource={sha256:string;width:number;height:number};
export type OriginalShadowBinding={version:1;reviewed:true;mask:{source:OriginalShadowSource;semantic_owner:null;recipe:LocalMaskReport['recipe']};recipe_sha256:string};
export type OriginalShadowBlend='normal'|'multiply'|'softlight';
export type OriginalShadowParameters={enabled:boolean;strength:number;blend:OriginalShadowBlend};
export type OriginalShadowRecipe=OriginalShadowParameters&{version:1;algorithm:'lrt-original-shadow-uniform-floor-v1';lit_floor:OriginalShadowBinding|null;retention:OriginalShadowBinding|null;uniform_floor_confirmed:boolean};
export type OriginalShadowFence={recipe_document_id:string;recipe_revision:string};
export type OriginalShadowImage={mime:'image/png';width:number;height:number;sha256:string;base64:string};
export type OriginalShadowReview=OriginalShadowFence&{version:1;token:string;source:OriginalShadowSource;candidate_sha256:string;before:OriginalShadowImage;after:OriginalShadowImage;boundaries:string[]};
export type OriginalShadowPreviewFields={parameters:OriginalShadowParameters;lit_ids:string[]|null;retention_ids:string[]|null;samples_reviewed:boolean;uniform_floor_confirmed:boolean};
export type OriginalShadowApplyFields={token:string;reviewed:true;before_sha256:string;after_sha256:string};
export type OriginalShadowNotSent={requested:false;not_sent:true;protocol:1;action:string;request_id:string;document_id:string;error:string};
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const exact=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const positive=(v:unknown,max:number):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>0&&v<=max;
const token=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{32}$/.test(v)&&!/^0+$/.test(v);
const revision=(v:unknown):v is string=>typeof v==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(v)&&BigInt(v)<=18446744073709551615n;
const ids=(v:unknown):v is string[]=>Array.isArray(v)&&v.length>0&&v.length<=ORIGINAL_SHADOW_LIMITS.objects&&new Set(v).size===v.length&&v.every(id=>typeof id==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(id));

export function originalShadowActive(value:OriginalShadowRecipe|null|undefined):boolean{return !!value?.enabled&&value.strength>0;}
export const originalShadowManualObject=(value:MaskObject):boolean=>value.enabled&&(value.kind==='brush'&&value.points.length>0||value.kind==='linear'||value.kind==='radial');
/** Missing legacy metadata fails closed only for this full-source method. */
export function originalShadowSubjectEligible(value:{mask?:OriginalShadowBinding['mask']}|null|undefined):boolean{
 const objects=value?.mask?.recipe.objects;
 return !!objects?.length&&objects.every(object=>object.kind==='brush'||object.kind==='linear'||object.kind==='radial');
}
export function validOriginalShadowPreviewFields(value:unknown):value is OriginalShadowPreviewFields{
 if(!object(value)||!exact(value,['parameters','lit_ids','retention_ids','samples_reviewed','uniform_floor_confirmed'])||!object(value.parameters)
  ||!exact(value.parameters,['enabled','strength','blend']))return false;
 const p=value.parameters,replacing=value.lit_ids!==null||value.retention_ids!==null;
 return typeof p.enabled==='boolean'&&typeof p.strength==='number'&&Number.isFinite(p.strength)&&p.strength>=0&&p.strength<=100
  &&['normal','multiply','softlight'].includes(p.blend as string)&&typeof value.uniform_floor_confirmed==='boolean'
  &&(!p.enabled||value.uniform_floor_confirmed)&&value.samples_reviewed===replacing
  &&(value.lit_ids===null||ids(value.lit_ids))&&(value.retention_ids===null||ids(value.retention_ids))
  &&(!Array.isArray(value.lit_ids)||!Array.isArray(value.retention_ids)||!value.lit_ids.some(id=>(value.retention_ids as unknown[]).includes(id)));
}
export function validOriginalShadowImage(value:unknown):value is OriginalShadowImage{
 return object(value)&&exact(value,['mime','width','height','sha256','base64'])&&value.mime==='image/png'&&hash(value.sha256)
  &&positive(value.width,ORIGINAL_SHADOW_LIMITS.edge)&&positive(value.height,ORIGINAL_SHADOW_LIMITS.edge)
  &&typeof value.base64==='string'&&value.base64.length<=ORIGINAL_SHADOW_LIMITS.base64&&value.base64.length%4===0
  &&value.base64.startsWith('iVBOR')&&/^[A-Za-z0-9+/]+={0,2}$/.test(value.base64);
}
export function validOriginalShadowReview(value:unknown,fence:OriginalShadowFence):value is OriginalShadowReview{
 return object(value)&&exact(value,['version','token','recipe_document_id','recipe_revision','source','candidate_sha256','before','after','boundaries'])
  &&value.version===1&&token(value.token)&&!!fence.recipe_document_id&&value.recipe_document_id===fence.recipe_document_id
  &&revision(value.recipe_revision)&&value.recipe_revision===fence.recipe_revision&&hash(value.candidate_sha256)
  &&object(value.source)&&exact(value.source,['sha256','width','height'])&&hash(value.source.sha256)&&positive(value.source.width,1000000)&&positive(value.source.height,1000000)
  &&validOriginalShadowImage(value.before)&&validOriginalShadowImage(value.after)&&value.before.width===value.after.width&&value.before.height===value.after.height
  &&Array.isArray(value.boundaries)&&value.boundaries.length<=32&&value.boundaries.every(v=>typeof v==='string'&&v.length<=4096&&!v.includes('\0'));
}
export function originalShadowNotSent(value:unknown,expected:{action:string;request_id:string;document_id:string}):value is OriginalShadowNotSent{
 return object(value)&&exact(value,['requested','not_sent','protocol','action','request_id','document_id','error'])
  &&value.requested===false&&value.not_sent===true&&value.protocol===1&&value.action===expected.action&&value.request_id===expected.request_id
  &&value.document_id===expected.document_id&&typeof value.error==='string'&&value.error.length>0&&value.error.length<=4096;
}
export function originalShadowRequestFits(value:unknown):boolean{return new TextEncoder().encode(JSON.stringify(value)).length<=ORIGINAL_SHADOW_LIMITS.requestBytes;}
export function originalShadowReviewKey(value:OriginalShadowReview):string{return JSON.stringify([value.token,value.recipe_document_id,value.recipe_revision,value.source,value.candidate_sha256,value.before.sha256,value.after.sha256]);}
export function originalShadowApplyFields(value:OriginalShadowReview):OriginalShadowApplyFields{return {token:value.token,reviewed:true,before_sha256:value.before.sha256,after_sha256:value.after.sha256};}

function crc32(bytes:Uint8Array,start:number,end:number):number{
 let value=0xffffffff;
 for(let index=start;index<end;index++){value^=bytes[index];for(let bit=0;bit<8;bit++)value=(value>>>1)^((value&1)?0xedb88320:0);}
 return (value^0xffffffff)>>>0;
}
/** Integrity is separate from a real browser load and the user's view acknowledgment. */
export async function verifyOriginalShadowImage(value:OriginalShadowImage):Promise<boolean>{
 try{
  if(!validOriginalShadowImage(value))return false;
  const decoded=atob(value.base64);
  if(btoa(decoded)!==value.base64||decoded.length<57||decoded.length>ORIGINAL_SHADOW_LIMITS.pngBytes)return false;
  const bytes=Uint8Array.from(decoded,c=>c.charCodeAt(0)),view=new DataView(bytes.buffer);
  if(![137,80,78,71,13,10,26,10].every((v,i)=>bytes[i]===v))return false;
  let offset=8,header=false,data=false,seenData=false,dataEnded=false,ended=false;
  while(offset+12<=bytes.length){
   const size=view.getUint32(offset),type=view.getUint32(offset+4),end=offset+12+size;
   if(end>bytes.length||crc32(bytes,offset+4,end-4)!==view.getUint32(end-4))return false;
   const name=String.fromCharCode(...bytes.subarray(offset+4,offset+8));
   if(!/^[A-Za-z]{2}[A-Z][A-Za-z]$/.test(name))return false;
   if(!header){
    if(type!==0x49484452||size!==13||view.getUint32(offset+8)!==value.width||view.getUint32(offset+12)!==value.height
     ||bytes[offset+16]!==8||![2,6].includes(bytes[offset+17])||bytes[offset+18]!==0||bytes[offset+19]!==0||bytes[offset+20]!==0)return false;
    header=true;
   }else if(type===0x49444154){if(dataEnded)return false;seenData=true;data=data||size>0;}
   else if(type===0x49454e44){if(size!==0||!data||end!==bytes.length)return false;ended=true;break;}
   else{if(!/^[a-z]/.test(name)||['acTL','fcTL','fdAT'].includes(name))return false;if(seenData)dataEnded=true;}
   offset=end;
  }
  if(!ended)return false;
  const digest=await crypto.subtle.digest('SHA-256',bytes);
  return Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('')===value.sha256;
 }catch{return false;}
}
