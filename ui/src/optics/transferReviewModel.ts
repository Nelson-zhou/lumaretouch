import type {LensProfile,Perspective,AutoMode} from './model';
export const OPTICS_AUTO_OP='lnx.optics_auto.v1';
export const OPTICS_MANUAL_OP='lnx.optics_manual.v1';
export interface OpticalTargetReview {
 version:1;document_id:string;revision:string;success:boolean;error?:string;method?:string;
 proof:string;candidate_key:string;auto_mode:AutoMode;lens_auto:boolean;
 analysis?:Perspective['analysis'];lens?:LensProfile|null;crop_zoom?:number;note?:string;
 comparison?:{before:string;after:string;width:number;height:number;domain:'post-manual-liquify-pre-crop-normalized'};
}
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const hash=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const number=(v:unknown,lo:number,hi:number)=>typeof v==='number'&&Number.isFinite(v)&&v>=lo&&v<=hi;
const integer=(v:unknown)=>typeof v==='number'&&Number.isInteger(v);
const text=(v:unknown)=>typeof v==='string'&&v.length>0&&v.length<=512;
export function validOpticalReview(value:unknown,documentId:string,revision?:string,params?:unknown):value is OpticalTargetReview{
 if(!object(value)||value.version!==1||value.success!==true||value.document_id!==documentId||typeof value.revision!=='string'||!/^\d{1,20}$/.test(value.revision)||BigInt(value.revision)>18446744073709551615n||
   (revision!==undefined&&value.revision!==revision)||!hash(value.proof)||!hash(value.candidate_key)||!number(value.crop_zoom,1,32)||typeof value.lens_auto!=='boolean'||!['off','smart','horizontal','vertical'].includes(String(value.auto_mode)))return false;
 if(params!==undefined&&(!object(params)||!object(params.request)||params.request.auto_mode!==value.auto_mode||params.request.lens_auto!==value.lens_auto))return false;
 if(value.auto_mode==='off'){if(value.analysis!==null)return false;}
 else {const a=value.analysis;if(!object(a)||!text(a.method)||!number(a.confidence,.45,1)||!integer(a.lines)||!number(a.lines,4,512)||!number(a.residual_degrees,0,90)||typeof a.message!=='string')return false;}
 if(value.lens_auto){const p=value.lens;if(!object(p)||!hash(p.database_sha256)||!text(p.library_version)||!text(p.camera_model)||!text(p.lens_model)||!number(p.focal,.1,10000)||!Array.isArray(p.flags)||!p.flags.length||!p.flags.every(f=>['distortion','tca','vignette'].includes(String(f))))return false;}
 else if(value.lens!==null)return false;
 if(value.comparison!==undefined){const c=value.comparison;if(!object(c)||!integer(c.width)||!integer(c.height)||!number(c.width,1,320)||!number(c.height,1,320)||c.domain!=='post-manual-liquify-pre-crop-normalized'||typeof c.before!=='string'||typeof c.after!=='string'||!c.before.startsWith('data:image/png;base64,iVBOR')||!c.after.startsWith('data:image/png;base64,iVBOR')||c.before.length+c.after.length>1024*1024)return false;}
 return true;
}
