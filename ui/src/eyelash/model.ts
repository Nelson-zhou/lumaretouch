import {PATTERNS} from './catalogue';
import type {ParameterPatch,PeopleView,PeopleContext} from '../people/model';
export {PATTERNS,CATALOGUE_SHA256} from './catalogue';
export const OP='lnx.eyelash.v1';
export const IDS={family:'a985bd90b0',recommended:'97176ce30b',eyedropper:'6188d1c325',rgb:'cc564a6b8e',hex:'7379840b33',saved:'18779c33fa'} as const;
export const PARTS=['left_upper','left_lower','right_upper','right_lower'] as const;
export type Side=typeof PARTS[number];
export type Pattern=typeof PATTERNS[number]['id'];
export type Eye={pattern:Pattern;strength:number;colour:string};
export type EyelashRecipe={version:1;link_lr:boolean;link_ud:boolean}&Record<Side,Eye>;
export const neutralEye=():Eye=>({pattern:'airy',strength:0,colour:'#28232A'});
export const neutral=():EyelashRecipe=>({version:1,link_lr:true,link_ud:true,left_upper:neutralEye(),left_lower:neutralEye(),right_upper:neutralEye(),right_lower:neutralEye()});
export function colour(raw:string):string {
  if(!/^#[0-9a-fA-F]{6}$/.test(raw))throw Error('HEX 需为 #RRGGBB');return raw.toUpperCase();
}
export function rgb(values:readonly number[]):string {
  if(values.length!==3||values.some(n=>!Number.isInteger(n)||n<0||n>255))throw Error('RGB 需要三个 0–255 整数');
  return '#'+values.map(n=>n.toString(16).padStart(2,'0')).join('').toUpperCase();
}
export function channels(value:string):number[]{const c=colour(value);return [1,3,5].map(i=>parseInt(c.slice(i,i+2),16));}
export function palette(raw:unknown):string[]{
  if(!Array.isArray(raw)||raw.length>6||raw.some(c=>typeof c!=='string'))throw Error('最多收藏 6 色');
  const colors=raw.map(colour);if(new Set(colors).size!==colors.length)throw Error('收藏颜色重复');return colors;
}
/** Locks sampling to exact source + graph revision + explicit editing target. */
export function contextKey(view:PeopleView):string {
  return JSON.stringify([view.binding.document_id,view.binding.document_epoch,view.binding.document_revision,
    view.binding.asset_sha256,view.revision,view.association_revision,view.selected_face_id,view.editing_target]);
}
export function context(view:PeopleView):PeopleContext {
  if(!view.editing_target)throw Error('请先明确选择人物范围');
  return {document_id:view.binding.document_id,document_epoch:view.binding.document_epoch,
    document_revision:view.binding.document_revision,state_revision:view.revision,association_revision:view.association_revision,target:structuredClone(view.editing_target)};
}

export function checkEye(v:Eye):Eye{
 if(Object.keys(v).sort().join(',')!=='colour,pattern,strength'||!PATTERNS.some(p=>p.id===v.pattern)||typeof v.strength!=='number'||!Number.isFinite(v.strength)||v.strength<0||v.strength>1)throw Error('睫毛配方无效');
 return {...v,colour:colour(v.colour)};
}
export function check(v:EyelashRecipe):EyelashRecipe{
 if(Object.keys(v).sort().join(',')!==[...PARTS,'link_lr','link_ud','version'].sort().join(',')||v.version!==1||typeof v.link_lr!=='boolean'||typeof v.link_ud!=='boolean')throw Error('睫毛配方版本无效');
 const out={...v};for(const p of PARTS)out[p]=checkEye(v[p]);
 for(const p of PARTS){const [side,lid]=p.split('_');const lr=`${side==='left'?'right':'left'}_${lid}` as Side,ud=`${side}_${lid==='upper'?'lower':'upper'}` as Side;
  for(const q of [ ...(v.link_lr?[lr]:[]),...(v.link_ud?[ud]:[])])if((['pattern','strength','colour'] as const).some(k=>out[p][k]!==out[q][k]))throw Error('联动睫毛须一次更新全部关联部位');}
 return out;
}
export function edit(v:EyelashRecipe,part:Side,eye:Eye):EyelashRecipe{
 const out={...v},[side,lid]=part.split('_');for(const p of PARTS){const [s,l]=p.split('_');if((s===side||v.link_lr)&&(l===lid||v.link_ud))out[p]={...eye};}return check(out);
}
export function relink(v:EyelashRecipe,axis:'link_lr'|'link_ud',enabled:boolean,part:Side):EyelashRecipe{
 const out={...v,[axis]:enabled};if(!enabled)return check(out);
 const [side,lid]=part.split('_');for(const p of PARTS){const [s,l]=p.split('_');const source=(axis==='link_lr'?`${side}_${l}`:`${s}_${lid}`) as Side;out[p]={...v[source]};}
 return edit(out,part,v[part]);
}
export function patches(v:EyelashRecipe):ParameterPatch[]{const r=check(v);return [...(['link_lr','link_ud'] as const).map(k=>({operation_id:OP,parameter_path:`/${k}`,unset:false as const,value:r[k]})),...PARTS.flatMap(s=>(['pattern','strength','colour'] as const).map(k=>({operation_id:OP,parameter_path:`/${s}/${k}`,unset:false as const,value:r[s][k]})))];}
export function resolved(view:PeopleView):EyelashRecipe{const r=neutral(),v=view.resolved?.operations[OP];if(v){for(const k of ['link_lr','link_ud'] as const)if(v['/'+k])r[k]=v['/'+k].value as boolean;for(const s of PARTS)for(const k of ['pattern','strength','colour'] as const){const x=v[`/${s}/${k}`];if(x)Object.assign(r[s],{[k]:x.value});}}return check(r);}
export type EyelashView={recipe:EyelashRecipe;library:{version:1;catalogue_sha256:string;saved_colours:string[]};native_available:boolean;suspended:string|null;changed_pixels:number;reason:string|null;reviewed:boolean;face_ref:import('../people/model').FaceRef|null;source:{sha256:string;width:number;height:number};source_preview:import('../legShape/sourcePreview').SourcePreview|null};
