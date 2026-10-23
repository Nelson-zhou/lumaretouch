// SPDX-License-Identifier: GPL-3.0-or-later
import {PATTERNS} from './catalogue';
import type {ParameterPatch,PeopleView,PeopleContext} from '../people/model';
export {PATTERNS,CATALOGUE_SHA256} from './catalogue';
export const OP='lnx.blush_makeup.v1';
export const IDS={family:'e7ccb5a9e2',recommended:'6be18714f8',eyedropper:'53df3c11b3',rgb:'3f0064d896',hex:'8059d0cdd0',saved:'6f5d708f87'} as const;
export type Pattern=typeof PATTERNS[number]['id'];
export type BlushRecipe={version:1;pattern:Pattern;strength:number;colour:string};
export const neutral=():BlushRecipe=>({version:1,pattern:'apple',strength:0,colour:'#D77A87'});
export function colour(raw:string):string {
  if(!/^#[0-9a-fA-F]{6}$/.test(raw))throw Error('HEX 需为 #RRGGBB');return raw.toUpperCase();
}
export function rgb(values:readonly number[]):string {
  if(values.length!==3||values.some(n=>!Number.isInteger(n)||n<0||n>255))throw Error('RGB 需要三个 0–255 整数');
  return '#'+values.map(n=>n.toString(16).padStart(2,'0')).join('').toUpperCase();
}
export function channels(value:string):number[]{const c=colour(value);return [1,3,5].map(i=>parseInt(c.slice(i,i+2),16));}
export function check(raw:unknown):BlushRecipe {
  if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('腮红配方无效');
  const v=raw as Record<string,unknown>;
  if(Object.keys(v).sort().join(',')!=='colour,pattern,strength,version'||v.version!==1||!PATTERNS.some(p=>p.id===v.pattern)
    ||typeof v.strength!=='number'||!Number.isFinite(v.strength)||v.strength<0||v.strength>1||typeof v.colour!=='string')throw Error('腮红配方字段或范围无效');
  return {version:1,pattern:v.pattern as Pattern,strength:v.strength,colour:colour(v.colour)};
}
export function patches(value:BlushRecipe,keys:('pattern'|'strength'|'colour')[]=['pattern','strength','colour']):ParameterPatch[]{
  const r=check(value);return keys.map(key=>({operation_id:OP,parameter_path:'/'+key,unset:false,value:r[key]}));
}
export function resolved(view:PeopleView):BlushRecipe {
  const r=neutral();const values=view.resolved?.operations[OP];
  return check({...r,...Object.fromEntries(['pattern','strength','colour'].flatMap(k=>values?.['/'+k]?[ [k,values['/'+k].value] ]:[]))});
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
export type BlushView={recipe:BlushRecipe;library:{version:1;catalogue_sha256:string;saved_colours:string[]};
  facts:{changed_pixels?:number;reason?:string;limitation?:string};native_available:boolean;suspended:string|null;
  reviewed:boolean;face_ref:import('../people/model').FaceRef|null;source:{sha256:string;width:number;height:number};
  source_preview:import('../legShape/sourcePreview').SourcePreview|null};
