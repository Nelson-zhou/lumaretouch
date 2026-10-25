// SPDX-License-Identifier: GPL-3.0-or-later
import type {MaskObject} from '../localMasks/model';
export const FABRIC_SWEAT_OPERATION = 'lnx.fabric_sweat.v1' as const;
export const FABRIC_SWEAT_CONTROLS = ['control:PC-32477:5','control:PC-32477:6','control:PC-32477:14','control:PC-32477:15','control:PC-32477:16','control:PC-32477:17'] as const;
export type Brush = Extract<MaskObject, {kind:'brush'}>;
export type Mask = {version:1;domain:'source-normalized';objects:Brush[]};
export type Role = 'garment'|'target'|'reference'|'protect';
export type Masks = Record<Role,Mask>;
export type Image = {mime:'image/png';base64:string;width:number;height:number;sha256:string};
export type Source = {sha256:string;width:number;height:number};
export type Reference = {protocol:1;family:'fabric_sweat';reference_id:string;fence:string;
  source:Source;source_image:Image;current_amount:number;capability:{available:boolean;reason:string|null}};
export type Review = Masks & {version:1;domain:'source-normalized';same_garment_confirmed:true;clean_reference_confirmed:true};
export type PreviewPayload = {reference_id:string;amount:number;radius_px:number;review:Review};
export type Preview = {protocol:1;family:'fabric_sweat';preview_id:string;fence:string;
  before:Image;after:Image;mask:Image;facts:Record<string,unknown>;candidate_sha256:string};
export type ConfirmPayload = {preview_id:string;reviewed:true;before_sha256:string;after_sha256:string;mask_sha256:string;candidate_sha256:string};
export type Snapshot = {
  /** Canonical document ID + epoch + revision; must change on any source/history change. */
  bindingKey:string|null; reference:Reference|null;
  /** The canonical owner validates receipt identity and returns its exact sent payload. */
  preview:{request:PreviewPayload;value:Preview}|null;
  pending:boolean;uncertain:boolean;refreshRequired:boolean;message?:string;
};
export type FabricSweatPort = {
  snapshot:Snapshot;
  reference:()=>Promise<void>;
  preview:(payload:PreviewPayload)=>Promise<void>;
  confirm:(payload:ConfirmPayload)=>Promise<void>;
  clear:()=>Promise<void>;
};
export const emptyMask = ():Mask => ({version:1,domain:'source-normalized',objects:[]});
export const emptyMasks = ():Masks => ({garment:emptyMask(),target:emptyMask(),reference:emptyMask(),protect:emptyMask()});
export const ROLE_LABELS:Record<Role,string> = {garment:'同一件衣物范围',target:'汗渍修正区域',reference:'干净参考区域',protect:'保护区域'};
export const LIMITS = {strokes:64,pointsPerStroke:1024,totalPoints:4096} as const;
export function canonical(value:unknown):string {
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+canonical((value as Record<string,unknown>)[key])).join(',')+'}';
  return JSON.stringify(value)??'undefined';
}
export const imageUrl = (image:Image):string => `data:image/png;base64,${image.base64}`;
export function validImage(image:Image):boolean {
  return image?.mime==='image/png'&&Number.isInteger(image.width)&&image.width>0&&image.width<=1152
    &&Number.isInteger(image.height)&&image.height>0&&image.height<=1152
    &&typeof image.sha256==='string'&&/^[a-f0-9]{64}$/.test(image.sha256)
    &&typeof image.base64==='string'&&image.base64.length>0&&image.base64.length<=5_592_408
    &&image.base64.length%4===0&&image.base64.startsWith('iVBOR')&&/^[A-Za-z0-9+/]+={0,2}$/.test(image.base64);
}
export function maskHasPaint(mask:Mask):boolean {return mask.objects.some(row=>row.enabled&&row.operation==='add'&&row.opacity>0);}
/** Display validation only. Host retains authoritative source, mask and receipt checks. */
export function previewMatches(preview:Snapshot['preview'],request:PreviewPayload|null,reference:Reference):preview is NonNullable<Snapshot['preview']> {
  return !!preview&&!!request&&canonical(preview.request)===canonical(request)
    &&preview.value.protocol===1&&preview.value.family==='fabric_sweat'
    &&canonical(preview.value.fence)===canonical(reference.fence)
    &&[preview.value.before,preview.value.after,preview.value.mask].every(validImage)
    &&preview.value.before.width===preview.value.after.width&&preview.value.before.height===preview.value.after.height
    &&Math.abs(preview.value.mask.width*reference.source.height-preview.value.mask.height*reference.source.width)<=Math.max(reference.source.width,reference.source.height)
    &&/^[a-f0-9]{64}$/.test(preview.value.candidate_sha256);
}
