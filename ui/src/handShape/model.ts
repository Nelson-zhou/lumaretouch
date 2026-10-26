// SPDX-License-Identifier: GPL-3.0-or-later
export const HAND_SHAPE_OPERATION='lnx.hand_shape.v1' as const;
export const HAND_SHAPE_CONTROLS=['control:PC-46608:3'] as const;
export type Point=[number,number];
export type Kind='palm'|'finger'|'joint';
export type Part='palm'|'thumb'|'index'|'middle'|'ring'|'little';
export type Region={id:string;kind:Kind;part:Part;start:Point;end:Point;negative:Point;positive:Point};
export type Confirmations={visible_only:true;ownership:true;no_contact:true;transitions:true;protection_reviewed:true};
export type Review={version:1;domain:'source-normalized';hand_id:string;regions:Region[];protect:[number,number,number,number][];proposal_id:string|null;confirmed:Confirmations};
export type Amounts=Record<Kind,number>;
export type Image={mime:'image/png';base64:string;width:number;height:number;sha256:string};
export type Source={sha256:string;width:number;height:number};
export type Recipe={version:1;source:Source;review:Review;amounts:Amounts;[key:string]:unknown};
export type Capability={available:boolean;reason:string|null};
export type Reference={protocol:1;family:'hand_shape';reference_id:string;fence:string;source:Source;source_image:Image;current_recipe:Recipe|null;capability:Capability;model:Capability};
export type Proposal={proposal_id:string;points:{index:number;x:number;y:number;z:number}[];handedness:unknown[]};
export type Proposals={protocol:1;family:'hand_shape';reference_id:string;fence:string;proposals:Proposal[]};
export type PreviewPayload={reference_id:string;review:Review;amounts:Amounts};
export type Preview={protocol:1;family:'hand_shape';preview_id:string;fence:string;before:Image;after:Image;overlay:Image;candidate_sha256:string;facts:Record<string,unknown>};
export type ConfirmPayload={preview_id:string;reviewed:true;before_sha256:string;after_sha256:string;overlay_sha256:string;candidate_sha256:string};
export type Snapshot={bindingKey:string|null;reference:Reference|null;proposals:Proposals|null;preview:{request:PreviewPayload;value:Preview}|null;pending:boolean;uncertain:boolean;refreshRequired:boolean;message?:string};
export type HandShapePort={snapshot:Snapshot;reference:()=>Promise<void>;propose:(referenceId:string)=>Promise<void>;preview:(payload:PreviewPayload)=>Promise<void>;confirm:(payload:ConfirmPayload)=>Promise<void>;clear:()=>Promise<void>};
export const neutral=():Amounts=>({palm:0,finger:0,joint:0});
export const KIND_LABELS:Record<Kind,string>={palm:'手宽',finger:'手指',joint:'指节'};
export const PART_LABELS:Record<Part,string>={palm:'手掌',thumb:'拇指',index:'食指',middle:'中指',ring:'无名指',little:'小指'};
export function canonical(value:unknown):string {if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+canonical((value as Record<string,unknown>)[key])).join(',')+'}';return JSON.stringify(value)??'undefined';}
export const imageUrl=(image:Image):string=>`data:image/png;base64,${image.base64}`;
export function validImage(image:Image):boolean{return image?.mime==='image/png'&&Number.isInteger(image.width)&&image.width>0&&image.width<=1152&&Number.isInteger(image.height)&&image.height>0&&image.height<=1152&&typeof image.sha256==='string'&&/^[a-f0-9]{64}$/.test(image.sha256)&&typeof image.base64==='string'&&image.base64.length>0&&image.base64.length<=5592408&&image.base64.length%4===0&&image.base64.startsWith('iVBOR')&&/^[A-Za-z0-9+/]+={0,2}$/.test(image.base64);}
export function validAmounts(value:unknown):value is Amounts {if(!value||typeof value!=='object'||Array.isArray(value))return false;const a=value as Amounts;return Object.keys(a).sort().join(',')==='finger,joint,palm'&&(['palm','finger','joint'] as const).every(k=>typeof a[k]==='number'&&Number.isFinite(a[k])&&Math.abs(a[k])<=1);}
export function previewMatches(preview:Snapshot['preview'],request:PreviewPayload|null,reference:Reference):preview is NonNullable<Snapshot['preview']>{return !!preview&&!!request&&canonical(preview.request)===canonical(request)&&preview.value.protocol===1&&preview.value.family==='hand_shape'&&preview.value.fence===reference.fence&&[preview.value.before,preview.value.after,preview.value.overlay].every(validImage)&&preview.value.before.width===preview.value.after.width&&preview.value.before.height===preview.value.after.height&&Math.abs(preview.value.overlay.width*reference.source.height-preview.value.overlay.height*reference.source.width)<=Math.max(reference.source.width,reference.source.height)&&/^[a-f0-9]{64}$/.test(preview.value.candidate_sha256);}
