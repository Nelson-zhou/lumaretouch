// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef as PeopleFaceRef} from '../people/model';

export const PORT_VERSION = 1 as const;
export const OPERATION_ID = 'lnx.expression_replacement.v1' as const;
export const REQUIREMENT_ID = 'LNX-REF-PC-32468-C-0e5f836ef1' as const;
export const OFFICIAL_REFERENCE = 'https://wiki.pixcakeai.com/guide/9406.html';
export const LIMITS = {faces:128, strokes:128, points:2048, previewEdge:1600, previewBase64:16_000_000, cropEdge:1024} as const;
export type Frozen<T> = T extends object ? {readonly [K in keyof T]:Frozen<T[K]>} : T;
export type FaceRef = Readonly<PeopleFaceRef>;
export type Source = Readonly<{
  asset_sha256:string; original_sha256:string; source_kind:'original'|'derived';
  width:number; height:number; orientation:'exif_normalized_once';
  /** Opaque host-owned retention identity, never a guessed path or URL. */
  retained_asset_id:string;
}>;
export type Binding = Readonly<{
  document_id:string; document_epoch:string; load_id:string; document_revision:number;
  state_revision:number; association_revision:number; people_graph_sha256:string; source:Source;
}>;
export type Crop = Readonly<{left:number;top:number;width:number;height:number}>;
/** These are independently measured host facts. A user checkbox cannot create them. */
export type Face = Readonly<{
  face_ref:FaceRef; enabled:boolean; analysis_status:'verified'; manual:false;
  landmarks_count:478; landmarks_sha256:string; crop:Crop;
  eligibility_sha256:string; protection_sha256:string;
}>;
export type FaceOwner = Readonly<{source:Source;face:Face}>;
export type Image = Readonly<{
  mime:'image/png'; width:number;height:number;sha256:string;base64:string;
  source_sha256:string; source_width:number;source_height:number;
  mapping:'normalized_full_frame';orientation:'exif_normalized_once';
}>;
export type Photograph = Readonly<{source:Source;label:string;faces:readonly Face[];image:Image}>;
export type Current = Readonly<{binding:Binding;photo:Photograph;available:boolean;unavailable_reason:string|null}>;
export type Point = readonly [number,number];
export type Stroke = Readonly<{mode:'add'|'erase';radius_px:number;points:readonly Point[]}>;
/** Pixel-centre coordinates on the complete target source. Never preview pixels. */
export type FusionMask = Readonly<{version:1;coordinates:'source_normalized_pixel_centres';initial:'empty';strokes:readonly Stroke[]}>;
export const CONFIRMATIONS = {
  same_person:'我已对照两张完整照片，确认选择的是同一个人；不是自动身份识别结果',
  same_session:'两张照片来自同一拍摄场次，光线、机位和外观可比较',
  real_measured_landmarks:'两个人脸都具有本图真实测得的 478 点定位，不是人工框或补造定位',
  reviewed_pose:'已检查两脸姿态和透视，接受保守二维对齐，不将眼睛或嘴强拉向当前表情',
  both_unoccluded:'两张照片中需要替换的面部均清晰可见，未遮挡，不推测隐藏内容',
  fusion_reviewed:'已手绘本图融合范围，排除他人、遮挡和不希望替换的区域',
} as const;
export type Confirmation = keyof typeof CONFIRMATIONS;
export const CONFIRMATION_KEYS = Object.keys(CONFIRMATIONS) as Confirmation[];
export type Confirmations = Readonly<Record<Confirmation,true>>;
export type Settings = Readonly<{density:number;pyramid_levels:1|2|3|4|5;colour_match_strength:0}>;
export type PreviewCommand = Readonly<{
  version:1;operation_id:typeof OPERATION_ID;action:'preview';request_id:string;binding:Binding;
  target:FaceOwner;donor:FaceOwner;fusion:FusionMask;settings:Settings;confirmations:Confirmations;
}>;
export type DonorCommand = Readonly<{version:1;operation_id:typeof OPERATION_ID;action:'choose_donor';request_id:string;binding:Binding}>;
export type CancelRequest = Readonly<{version:1;operation_id:typeof OPERATION_ID;request_id:string;command_sha256:string}>;
export type ApplyCommand = Readonly<{
  version:1;operation_id:typeof OPERATION_ID;action:'apply';request_id:string;binding:Binding;return_mode:'new_image';
  preview_request_id:string;preview_command_sha256:string;preview_token:string;
  candidate_sha256:string;fusion_mask_sha256:string;before_image_sha256:string;after_image_sha256:string;fusion_image_sha256:string;
  review:'full_before_after_and_fusion_confirmed';
}>;
export type Command = PreviewCommand|ApplyCommand|DonorCommand;
export type Packet<T extends Command=Command> = Readonly<{command:T;command_json:string;command_sha256:string}>;
export type Preview = Readonly<{
  preview_token:string;candidate_sha256:string;fusion_mask_sha256:string;
  /** Complete current-photo render, not the ≤1024 px native face-context crop. */
  output_width:number;output_height:number;before:Image;after:Image;fusion_image:Image;
}>;
export type ReceiptBase = Readonly<{
  version:1;operation_id:typeof OPERATION_ID;request_id:string;command_sha256:string;
  action:Command['action'];binding:Binding;
}>;
export type Receipt = ReceiptBase & (
  {readonly phase:'pending'|'unknown'|'cancelling';readonly message:string} |
  {readonly phase:'cancelled';readonly no_write:true;readonly message:string} |
  {readonly phase:'donor_ready';readonly action:'choose_donor';readonly photo:Photograph} |
  {readonly phase:'rejected';readonly no_write:true;readonly message:string} |
  {readonly phase:'ready';readonly action:'preview';readonly preview:Preview} |
  {readonly phase:'committed';readonly action:'apply';readonly preview_token:string;
    readonly candidate_sha256:string;readonly fusion_mask_sha256:string;
    readonly result_document_id:string;readonly copied_original_document_id:string;readonly result_source_sha256:string;
    readonly result_revision:number;readonly no_change:boolean}
);
/** Proposed boundary, NOT an existing native API. Mount only with a real adapter. */
export type ExpressionCapability = Readonly<{protocol:typeof PORT_VERSION;operation_id:typeof OPERATION_ID;available:boolean;reason:string|null}>;
export type ExpressionPort = Readonly<{
  protocol:typeof PORT_VERSION;
  capability:ExpressionCapability;
  chooseDonor:(packet:Packet<DonorCommand>)=>Promise<unknown>;
  cancel:(request:CancelRequest)=>Promise<unknown>;
  preview:(packet:Packet<PreviewCommand>)=>Promise<unknown>;
  apply:(packet:Packet<ApplyCommand>)=>Promise<unknown>;
  status:(requestId:string,commandSha256:string)=>Promise<unknown>;
  releasePreview:(previewToken:string)=>Promise<void>;
}>;

export const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
export const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const id=(v:unknown):v is string=>typeof v==='string'&&v.length>0&&v.length<=256&&!/[\u0000-\u001f\u007f]/.test(v);
const integer=(v:unknown,min=0,max=Number.MAX_SAFE_INTEGER):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=min&&v<=max;
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
export function canonical(value:unknown):string {
  if(value===null||typeof value==='boolean'||typeof value==='string')return JSON.stringify(value);
  if(typeof value==='number'&&Number.isFinite(value))return JSON.stringify(Object.is(value,-0)?0:value);
  if(Array.isArray(value))return `[${value.map(canonical).join(',')}]`;
  if(object(value))return `{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  throw Error('不可序列化的表情替换数据。');
}
export function freeze<T>(value:T):Frozen<T> {
  const copy=structuredClone(value);
  const deep=(v:unknown):void=>{if(v&&typeof v==='object'){Object.values(v).forEach(deep);Object.freeze(v);}};
  deep(copy);return copy as Frozen<T>;
}
export const same=(a:unknown,b:unknown):boolean=>canonical(a)===canonical(b);
export const faceKey=(face:FaceRef|null):string=>face?canonical(face):'';
export const contextKey=(current:Current|null):string=>current?canonical({binding:current.binding,faces:current.photo.faces,reference_sha256:current.photo.image.sha256,available:current.available}):'';
export function validSource(v:unknown):v is Source {
  return object(v)&&keys(v,['asset_sha256','original_sha256','source_kind','width','height','orientation','retained_asset_id'])
    &&hash(v.asset_sha256)&&hash(v.original_sha256)&&['original','derived'].includes(String(v.source_kind))
    &&(v.source_kind!=='original'||v.original_sha256===v.asset_sha256)
    &&integer(v.width,2,1_000_000)&&integer(v.height,2,1_000_000)&&v.width*v.height<=100_000_000
    &&v.orientation==='exif_normalized_once'&&id(v.retained_asset_id);
}
export function validBinding(v:unknown):v is Binding {
  return object(v)&&keys(v,['document_id','document_epoch','load_id','document_revision','state_revision','association_revision','people_graph_sha256','source'])
    &&id(v.document_id)&&id(v.document_epoch)&&id(v.load_id)&&integer(v.document_revision)&&integer(v.state_revision)
    &&integer(v.association_revision)&&hash(v.people_graph_sha256)&&validSource(v.source);
}
export function validFace(v:unknown,source:Source):v is Face {
  if(!object(v)||!keys(v,['face_ref','enabled','analysis_status','manual','landmarks_count','landmarks_sha256','crop','eligibility_sha256','protection_sha256'])
    ||typeof v.enabled!=='boolean'||v.analysis_status!=='verified'||v.manual!==false||v.landmarks_count!==478
    ||!hash(v.landmarks_sha256)||!hash(v.eligibility_sha256)||!hash(v.protection_sha256))return false;
  const r=v.face_ref,c=v.crop;
  return object(r)&&keys(r,['asset_sha256','face_instance_id','analysis_revision'])&&r.asset_sha256===source.asset_sha256&&id(r.face_instance_id)&&integer(r.analysis_revision)
    &&object(c)&&keys(c,['left','top','width','height'])&&integer(c.left)&&integer(c.top)&&integer(c.width,2,LIMITS.cropEdge)&&integer(c.height,2,LIMITS.cropEdge)
    &&c.left+c.width<=source.width&&c.top+c.height<=source.height;
}
export function validImage(v:unknown,source:Source):v is Image {
  return object(v)&&keys(v,['mime','width','height','sha256','base64','source_sha256','source_width','source_height','mapping','orientation'])
    &&v.mime==='image/png'&&hash(v.sha256)&&integer(v.width,2,LIMITS.previewEdge)&&integer(v.height,2,LIMITS.previewEdge)
    &&v.width<=source.width&&v.height<=source.height&&Math.abs(v.width*source.height-v.height*source.width)<=Math.max(source.width,source.height)
    &&v.source_sha256===source.asset_sha256&&v.source_width===source.width&&v.source_height===source.height
    &&v.mapping==='normalized_full_frame'&&v.orientation==='exif_normalized_once'
    &&typeof v.base64==='string'&&v.base64.length>32&&v.base64.length<=LIMITS.previewBase64&&v.base64.length%4===0
    &&v.base64.startsWith('iVBOR')&&/^[A-Za-z0-9+/]+={0,2}$/.test(v.base64);
}
export function validPhotograph(v:unknown):v is Photograph {
  if(!object(v)||!keys(v,['source','label','faces','image'])||!validSource(v.source)||!id(v.label)||!Array.isArray(v.faces)||v.faces.length>LIMITS.faces)return false;
  const source=v.source;
  return v.faces.every(face=>validFace(face,source))&&new Set(v.faces.map(face=>faceKey(face.face_ref))).size===v.faces.length&&validImage(v.image,source);
}
export function validCurrent(v:unknown):v is Current {
  return object(v)&&keys(v,['binding','photo','available','unavailable_reason'])&&validBinding(v.binding)&&validPhotograph(v.photo)
    &&same(v.binding.source,v.photo.source)&&typeof v.available==='boolean'&&(v.unavailable_reason===null||typeof v.unavailable_reason==='string');
}
export function validFusion(v:unknown,source:Source,face:Face):v is FusionMask {
  if(!object(v)||!keys(v,['version','coordinates','initial','strokes'])||v.version!==1||v.coordinates!=='source_normalized_pixel_centres'||v.initial!=='empty'
    ||!Array.isArray(v.strokes)||v.strokes.length>LIMITS.strokes)return false;
  let total=0;
  return v.strokes.every(stroke=>{
    if(!object(stroke)||!keys(stroke,['mode','radius_px','points'])||!['add','erase'].includes(String(stroke.mode))||!finite(stroke.radius_px)
      ||stroke.radius_px<1||stroke.radius_px>Math.min(face.crop.width,face.crop.height)/2||!Array.isArray(stroke.points)||!stroke.points.length)return false;
    total+=stroke.points.length;
    return total<=LIMITS.points&&stroke.points.every(p=>Array.isArray(p)&&p.length===2&&p.every(finite)
      &&p[0]*(source.width-1)>=face.crop.left&&p[0]*(source.width-1)<=face.crop.left+face.crop.width-1
      &&p[1]*(source.height-1)>=face.crop.top&&p[1]*(source.height-1)<=face.crop.top+face.crop.height-1);
  });
}
export function pairError(target:FaceOwner,donor:FaceOwner):string|null {
  if(!validSource(target.source)||!validSource(donor.source)||!validFace(target.face,target.source)||!validFace(donor.face,donor.source)||!target.face.enabled||!donor.face.enabled)return '请分别选择两张照片中已启用、有真实测量和独立保护证据的人脸。';
  if(target.source.asset_sha256===donor.source.asset_sha256||target.source.original_sha256===donor.source.original_sha256)return '请选择另一张真实照片，不能用当前照片替换自身。';
  // Actual compatibility is measured by the native landmark fit, not invented Euler angles.
  return null;
}
export function emptyFusion():FusionMask{return freeze({version:1,coordinates:'source_normalized_pixel_centres',initial:'empty',strokes:[]} as FusionMask);}
export function previewCommand(input:PreviewCommand):PreviewCommand {
  if(!object(input)||!keys(input,['version','operation_id','action','request_id','binding','target','donor','fusion','settings','confirmations'])
    ||!object(input.target)||!keys(input.target,['source','face'])||!object(input.donor)||!keys(input.donor,['source','face'])
    ||!object(input.settings)||!keys(input.settings,['density','pyramid_levels','colour_match_strength'])
    ||input.version!==1||input.operation_id!==OPERATION_ID||input.action!=='preview'||!id(input.request_id)||!validBinding(input.binding)
    ||!same(input.target.source,input.binding.source)||pairError(input.target,input.donor)
    ||!validFusion(input.fusion,input.target.source,input.target.face)||!input.fusion.strokes.some(stroke=>stroke.mode==='add')
    ||!finite(input.settings.density)||input.settings.density<=0||input.settings.density>1||!integer(input.settings.pyramid_levels,1,5)||input.settings.colour_match_strength!==0
    ||!object(input.confirmations)||!keys(input.confirmations,[...CONFIRMATION_KEYS])||CONFIRMATION_KEYS.some(key=>input.confirmations[key]!==true))throw Error('来源、定位、姿态、融合范围或逐项确认不完整，未生成候选。');
  return freeze(input);
}
export async function sha256(bytes:Uint8Array):Promise<string>{return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');}
export async function packet<T extends Command>(command:T):Promise<Packet<T>>{
  const snapshot=freeze(command) as T;
  const command_json=canonical(snapshot);
  return freeze({command:snapshot,command_json,command_sha256:await sha256(new TextEncoder().encode(command_json))}) as Packet<T>;
}
export async function verifyImage(image:Image,source:Source):Promise<boolean>{
  if(!validImage(image,source))return false;
  try{
    const bytes=Uint8Array.from(atob(image.base64),c=>c.charCodeAt(0));
    if(bytes.length<33||[137,80,78,71,13,10,26,10].some((n,i)=>bytes[i]!==n)||String.fromCharCode(...bytes.slice(12,16))!=='IHDR')return false;
    const view=new DataView(bytes.buffer);
    return view.getUint32(8)===13&&view.getUint32(16)===image.width&&view.getUint32(20)===image.height&&await sha256(bytes)===image.sha256;
  }catch{return false;}
}
export function parseReceipt(value:unknown,sent:Packet):Receipt|null {
  if(!object(value)||value.version!==1||value.operation_id!==OPERATION_ID||value.action!==sent.command.action
    ||value.request_id!==sent.command.request_id||value.command_sha256!==sent.command_sha256||!validBinding(value.binding)||!same(value.binding,sent.command.binding))return null;
  const common=['version','operation_id','request_id','command_sha256','action','binding'];
  if(value.phase==='cancelling'&&sent.command.action==='apply')return null;
  if(['pending','unknown','cancelling'].includes(String(value.phase)))return keys(value,[...common,'phase','message'])&&typeof value.message==='string'?freeze(value) as Receipt:null;
  if(value.phase==='cancelled')return sent.command.action!=='apply'&&keys(value,[...common,'phase','no_write','message'])&&value.no_write===true&&typeof value.message==='string'?freeze(value) as Receipt:null;
  if(value.phase==='donor_ready')return sent.command.action==='choose_donor'&&keys(value,[...common,'phase','photo'])&&validPhotograph(value.photo)?freeze(value) as Receipt:null;
  if(value.phase==='rejected')return keys(value,[...common,'phase','no_write','message'])&&value.no_write===true&&typeof value.message==='string'&&value.message.trim()?freeze(value) as Receipt:null;
  if(value.phase==='ready'&&sent.command.action==='preview'){
    const p=value.preview,source=sent.command.target.source;
    return keys(value,[...common,'phase','preview'])&&object(p)&&keys(p,['preview_token','candidate_sha256','fusion_mask_sha256','output_width','output_height','before','after','fusion_image'])
      &&id(p.preview_token)&&hash(p.candidate_sha256)&&hash(p.fusion_mask_sha256)&&p.output_width===source.width&&p.output_height===source.height
      &&validImage(p.before,source)&&validImage(p.after,source)&&validImage(p.fusion_image,source)&&p.before.width===p.after.width&&p.before.height===p.after.height&&p.fusion_image.width===p.before.width&&p.fusion_image.height===p.before.height?freeze(value) as Receipt:null;
  }
  if(value.phase==='committed'&&sent.command.action==='apply')return keys(value,[...common,'phase','preview_token','candidate_sha256','fusion_mask_sha256','result_document_id','copied_original_document_id','result_source_sha256','result_revision','no_change'])
    &&value.preview_token===sent.command.preview_token&&value.candidate_sha256===sent.command.candidate_sha256&&value.fusion_mask_sha256===sent.command.fusion_mask_sha256
    &&typeof value.no_change==='boolean'&&integer(value.result_revision)&&id(value.result_document_id)&&value.result_document_id!==sent.command.binding.document_id
    &&value.copied_original_document_id===sent.command.binding.document_id&&value.result_source_sha256===sent.command.candidate_sha256&&sent.command.return_mode==='new_image'?freeze(value) as Receipt:null;
  return null;
}
