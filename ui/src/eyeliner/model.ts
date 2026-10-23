import {PATTERNS} from './catalogue';
import type {ParameterPatch,PeopleView,PeopleContext} from '../people/model';
export {PATTERNS,CATALOGUE_SHA256} from './catalogue';
export const OP='lnx.eyeliner.v1';
export const IDS={family:'fa257bcc51',recommended:'97481ec9e4',eyedropper:'d1f91e8f4d',rgb:'e42b06d0e5',hex:'0677331ed6',saved:'2590457a9a'} as const;
export type Side='left'|'right';
export type Pattern=typeof PATTERNS[number]['id'];
export type Eye={pattern:Pattern;strength:number;colour:string};
export type EyelinerRecipe={version:1;linked:boolean;left:Eye;right:Eye};
export const neutralEye=():Eye=>({pattern:'fine',strength:0,colour:'#28232A'});
export const neutral=():EyelinerRecipe=>({version:1,linked:true,left:neutralEye(),right:neutralEye()});
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
 if(Object.keys(v).sort().join(',')!=='colour,pattern,strength'||!PATTERNS.some(p=>p.id===v.pattern)||typeof v.strength!=='number'||!Number.isFinite(v.strength)||v.strength<0||v.strength>1)throw Error('眼线配方无效');
 return {...v,colour:colour(v.colour)};
}
export function check(v:EyelinerRecipe):EyelinerRecipe{
 if(Object.keys(v).sort().join(',')!=='left,linked,right,version'||v.version!==1||typeof v.linked!=='boolean')throw Error('眼线配方版本无效');
 const left=checkEye(v.left),right=checkEye(v.right);
 if(v.linked&&(['pattern','strength','colour'] as const).some(k=>left[k]!==right[k]))throw Error('联动眼线须同时更新两眼');return {...v,left,right};
}
export function edit(v:EyelinerRecipe,side:Side,eye:Eye):EyelinerRecipe{return check({...v,[side]:eye,...(v.linked?{left:eye,right:eye}:{})});}
export function patches(v:EyelinerRecipe):ParameterPatch[]{const r=check(v);return [{operation_id:OP,parameter_path:'/linked',unset:false,value:r.linked},...(['left','right'] as const).flatMap(s=>(['pattern','strength','colour'] as const).map(k=>({operation_id:OP,parameter_path:`/${s}/${k}`,unset:false as const,value:r[s][k]})))];}
export function resolved(view:PeopleView):EyelinerRecipe{const r=neutral(),v=view.resolved?.operations[OP];if(v){if(v['/linked'])r.linked=v['/linked'].value as boolean;for(const s of ['left','right'] as const)for(const k of ['pattern','strength','colour'] as const){const x=v[`/${s}/${k}`];if(x)Object.assign(r[s],{[k]:x.value});}}return check(r);}
export type EyelinerView={recipe:EyelinerRecipe;library:{version:1;catalogue_sha256:string;saved_colours:string[]};native_available:boolean;suspended:string|null;changed_pixels:number;reason:string|null;reviewed:boolean;face_ref:import('../people/model').FaceRef|null;source:{sha256:string;width:number;height:number};source_preview:import('../legShape/sourcePreview').SourcePreview|null};
