/** Position/rotation are baseline-backed; strength/pixel mapping are local design. */
export const ASSETS=['original-softbox-v1','original-window-v1'] as const;
export type EyeSide='left'|'right';
export interface EyeMaterial {asset:typeof ASSETS[number];strength:number;horizontal:number;vertical:number;rotation:number;flip:boolean}
export interface EyeLight {version:2;linked:boolean;left:EyeMaterial;right:EyeMaterial}
export const REQUIREMENTS={family:'LNX-REF-PC-32470-C-b26336005c',strength:'LNX-REF-PC-32470-C-1ea8023b43',vertical:'LNX-REF-PC-32470-C-50dce1838b',horizontal:'LNX-REF-PC-32470-C-9811052624',rotation:'LNX-REF-PC-32470-C-6280743410',flip:'LNX-REF-PC-32470-C-127642672f'} as const;
export const neutralEye=():EyeMaterial=>({asset:ASSETS[0],strength:0,horizontal:0,vertical:0,rotation:0,flip:false});
export const neutral=():EyeLight=>({version:2,linked:true,left:neutralEye(),right:neutralEye()});
function eye(input:unknown):EyeMaterial{
 if(!input||typeof input!=='object'||Array.isArray(input))throw Error('眼神光单眼配方无效');const v=input as Record<string,unknown>;
 if(Object.keys(v).sort().join(',')!==Object.keys(neutralEye()).sort().join(',')||!ASSETS.includes(v.asset as EyeMaterial['asset'])||typeof v.flip!=='boolean')throw Error('眼神光单眼字段无效');
 for(const key of ['strength','horizontal','vertical','rotation'] as const)if(typeof v[key]!=='number'||!Number.isFinite(v[key])||Number(v[key])<(key==='strength'?0:-100)||Number(v[key])>100)throw Error('眼神光数值越界');
 return {asset:v.asset as EyeMaterial['asset'],strength:Number(v.strength),horizontal:Number(v.horizontal),vertical:Number(v.vertical),rotation:Number(v.rotation),flip:v.flip};
}
export function check(input:unknown):EyeLight{
 if(!input||typeof input!=='object'||Array.isArray(input))throw Error('眼神光配方无效');const v=input as Record<string,unknown>;
 if(Object.keys(v).sort().join(',')!=='left,linked,right,version'||v.version!==2||typeof v.linked!=='boolean')throw Error('眼神光字段无效');
 const left=eye(v.left),right=eye(v.right);if(v.linked&&JSON.stringify(left)!==JSON.stringify(right))throw Error('联动眼神光需要原子更新双眼');return {version:2,linked:v.linked,left,right};
}
export function patchEye(value:EyeLight,side:EyeSide,patch:Partial<EyeMaterial>):EyeLight{const next={...value[side],...patch};return check(value.linked?{...value,left:next,right:{...next}}:{...value,[side]:next});}
export function setLinked(value:EyeLight,linked:boolean,reference:EyeSide):EyeLight{return check(linked?{...value,linked:true,left:{...value[reference]},right:{...value[reference]}}:{...value,linked:false});}
export const degrees=(rotation:number):number=>rotation*1.8;
export interface EyeLightReceipt {status:'unavailable'|'needs-review'|'ready'|'applied';personId:string;sourceRevision:number;reason?:string;changedPixels?:number}
export interface EyeLightView {recipe:EyeLight;source:{sha256:string;width:number;height:number};face_ref:import('../people/model').FaceRef;reviewed:boolean;native_available:boolean;changed_pixels:number;suspended:string|null;source_preview:import('../legShape/sourcePreview').SourcePreview|null}
