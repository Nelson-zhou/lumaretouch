// SPDX-License-Identifier: GPL-3.0-or-later
import {PATTERNS} from './catalogue';
import type {ParameterPatch,PeopleView,PeopleContext} from '../people/model';
export {PATTERNS,CATALOGUE_SHA256} from './catalogue';
export const OP='lnx.lipstick.v1';
export const IDS={family:'79b10e6c77',recommended:'afeef2f365',eyedropper:'aa527d3820',rgb:'7143856a26',hex:'ff8f73cbc7',saved:'adcea25fde'} as const;
export const TEXTURES=[['satin','缎面','4c9236d46f'],['matte','哑光','499cecca98'],['cream','奶油','d0e1f03b0f'],['pearl','珠光','565b3b9081'],['water_gloss','水光','bdd6881023']] as const;
export type Texture=typeof TEXTURES[number][0];
export type Pattern=typeof PATTERNS[number]['id'];
export type LipstickRecipe={version:1;pattern:Pattern;strength:number;colour:string;texture:Texture};
export const neutral=():LipstickRecipe=>({version:1,pattern:'full',strength:0,colour:'#A94359',texture:'satin'});
export function colour(raw:string):string {
  if(!/^#[0-9a-fA-F]{6}$/.test(raw))throw Error('HEX 需为 #RRGGBB');return raw.toUpperCase();
}
export function rgb(values:readonly number[]):string {
  if(values.length!==3||values.some(n=>!Number.isInteger(n)||n<0||n>255))throw Error('RGB 需要三个 0–255 整数');
  return '#'+values.map(n=>n.toString(16).padStart(2,'0')).join('').toUpperCase();
}
export function channels(value:string):number[]{const c=colour(value);return [1,3,5].map(i=>parseInt(c.slice(i,i+2),16));}
export function check(raw:unknown):LipstickRecipe {
  if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('口红配方无效');
  const v=raw as Record<string,unknown>;
  if(Object.keys(v).sort().join(',')!=='colour,pattern,strength,texture,version'||v.version!==1||!PATTERNS.some(p=>p.id===v.pattern)||!TEXTURES.some(t=>t[0]===v.texture)
    ||typeof v.strength!=='number'||!Number.isFinite(v.strength)||v.strength<0||v.strength>1||typeof v.colour!=='string')throw Error('口红配方字段或范围无效');
  return {texture:v.texture as Texture,version:1,pattern:v.pattern as Pattern,strength:v.strength,colour:colour(v.colour)};
}
export function patches(value:LipstickRecipe,keys:('pattern'|'strength'|'colour'|'texture')[]=['pattern','strength','colour','texture']):ParameterPatch[]{
  const r=check(value);return keys.map(key=>({operation_id:OP,parameter_path:'/'+key,unset:false,value:r[key]}));
}
export function resolved(view:PeopleView):LipstickRecipe {
  const r=neutral();const values=view.resolved?.operations[OP];
  return check({...r,...Object.fromEntries(['pattern','strength','colour','texture'].flatMap(k=>values?.['/'+k]?[ [k,values['/'+k].value] ]:[]))});
}
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
export type LipstickView={recipe:LipstickRecipe;library:{version:1;catalogue_sha256:string;saved_colours:string[]};
  facts:{changed_pixels?:number;reason?:string;limitation?:string};native_available:boolean;suspended:string|null;
  reviewed:boolean;face_ref:import('../people/model').FaceRef|null;source:{sha256:string;width:number;height:number};
  source_preview:import('../legShape/sourcePreview').SourcePreview|null};
