/** Explicit, reviewable portability policy. No photo raster is a preset asset. */
export const LOCAL_GRADE_OP='lnx.local_grade.v1';
export type MaskTransferType='subject'|'background'|'custom';
export type TransferGroupChoice={id:string;name:string;types:string[];portable:boolean;reason:string|null};
export type MaskTransferOptions={mode:'append'|'replace';types:MaskTransferType[];rebase:boolean;groups:string[]|null};
export const defaultMaskTransfer=():MaskTransferOptions=>({mode:'append',types:['subject','background','custom'],rebase:false,groups:null});
export function sameTransferOptions(a:MaskTransferOptions|undefined,b:MaskTransferOptions|undefined){
  return !!a&&!!b&&Array.isArray(a.types)&&Array.isArray(b.types)&&(a.groups===null||Array.isArray(a.groups))&&(b.groups===null||Array.isArray(b.groups))
    &&a.mode===b.mode&&a.rebase===b.rebase&&JSON.stringify([...a.types].sort())===JSON.stringify([...b.types].sort())
    &&JSON.stringify(a.groups===null?null:[...a.groups].sort())===JSON.stringify(b.groups===null?null:[...b.groups].sort());
}
export type MaskTransferEvidence={policy:MaskTransferOptions;added:string[];removed:string[];excluded:string[];legacy_removed:boolean;legacy_preserved:boolean;
  semantic_scope:'whole-photo-category';target_source:{sha256:string;width:number;height:number};preview_domain:'original-source-rgb8-coverage';
  preview_jpeg?:string;selected_group_ids:string[];groups:{id:string;covered_proxy_pixels:number}[];full_dimensions:[number,number]};
export function validTransferEvidence(value:unknown):value is MaskTransferEvidence {
  if(!value||typeof value!=='object')return false;const v=value as MaskTransferEvidence;
  return !!v.policy&&['append','replace'].includes(v.policy.mode)&&Array.isArray(v.policy.types)&&v.policy.types.length>0
    &&v.policy.types.every(t=>['subject','background','custom'].includes(t))&&typeof v.policy.rebase==='boolean'
    &&(v.policy.groups===null||(Array.isArray(v.policy.groups)&&v.policy.groups.every(id=>typeof id==='string')))
    &&[v.added,v.removed,v.excluded].every(a=>Array.isArray(a)&&a.every(s=>typeof s==='string'))&&typeof v.legacy_removed==='boolean'&&typeof v.legacy_preserved==='boolean'
    &&v.semantic_scope==='whole-photo-category'&&v.preview_domain==='original-source-rgb8-coverage'
    &&!!v.target_source&&/^[a-f0-9]{64}$/.test(v.target_source.sha256)&&Array.isArray(v.full_dimensions)&&v.full_dimensions.length===2
    &&v.full_dimensions.every(n=>Number.isSafeInteger(n)&&n>0)&&Array.isArray(v.groups)
    &&v.groups.every(g=>typeof g.id==='string'&&Number.isSafeInteger(g.covered_proxy_pixels)&&g.covered_proxy_pixels>=0)
    &&Array.isArray(v.selected_group_ids)&&v.selected_group_ids.length>0&&v.selected_group_ids.every(id=>typeof id==='string')
    &&(v.preview_jpeg===undefined||(typeof v.preview_jpeg==='string'&&v.preview_jpeg.length<=90000&&/^[A-Za-z0-9+/]+={0,2}$/.test(v.preview_jpeg)));
}
export function transferGroupsFromParams(value:unknown):TransferGroupChoice[]{
  const layers=(value as {groups?:{layers?:unknown[]}}|undefined)?.groups?.layers;
  if(!Array.isArray(layers))return [];
  return layers.flatMap(value=>{
    const layer=value as {id?:unknown;name?:unknown;mask?:{recipe?:{objects?:{kind?:string;channel?:string}[]}}};
    if(typeof layer?.id!=='string'||typeof layer.name!=='string'||!Array.isArray(layer.mask?.recipe?.objects))return [];
    const objects=layer.mask.recipe.objects,types=[...new Set(objects.map(o=>o.kind==='semantic'?(o.channel==='background'?'background':'subject'):'custom'))];
    const reason=objects.some(o=>o.kind==='brush')?'包含画笔，不可迁移':objects.some(o=>o.kind==='prompted')?'AI 提示选区绑定原图，不可迁移':null;
    return [{id:layer.id,name:layer.name,types:types.length?types:['custom'],portable:!reason,reason}];
  });
}
