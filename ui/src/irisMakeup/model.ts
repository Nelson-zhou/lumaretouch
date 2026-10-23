// SPDX-License-Identifier: GPL-3.0-or-later
import type {ParameterPatch,PeopleView} from '../people/model';
export const OP='lnx.iris_makeup.v1';
export const PATTERNS=[['amber_rays','琥珀放射'],['slate_fibres','岩灰纤维'],['olive_crypts','橄榄隐窝'],['honey_speckle','蜜糖细斑'],['ocean_arcs','海蓝弧纹'],['copper_star','铜棕星芒'],['moss_lace','苔绿蕾纹'],['violet_fan','紫雾扇纹'],['silver_rings','银灰环纹'],['chestnut_branches','栗棕枝纹'],['teal_mosaic','青碧镶纹']] as const;
export type Pattern=typeof PATTERNS[number][0];
export type IrisRecipe={version:1;pattern:Pattern;strength:number};
export const neutral=():IrisRecipe=>({version:1,pattern:'amber_rays',strength:0});
export function check(raw:unknown):IrisRecipe {
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('美瞳配方无效');const v=raw as Record<string,unknown>;
 if(Object.keys(v).sort().join(',')!=='pattern,strength,version'||v.version!==1||!PATTERNS.some(p=>p[0]===v.pattern)||typeof v.strength!=='number'||!Number.isFinite(v.strength)||v.strength<0||v.strength>1)throw Error('美瞳配方字段或范围无效');
 return {version:1,pattern:v.pattern as Pattern,strength:v.strength};
}
export function patches(value:IrisRecipe):ParameterPatch[]{const r=check(value);return (['pattern','strength'] as const).map(k=>({operation_id:OP,parameter_path:'/'+k,unset:false,value:r[k]}));}
export function contextKey(view:PeopleView):string{return JSON.stringify([view.binding,view.revision,view.association_revision,view.editing_target,view.selected_face_id]);}
export type Point=[number,number];
export type EyeReview={iris:Point[];pupil:Point[];highlights:Point[][];confirmed:boolean};
export type Review=Record<'left'|'right',EyeReview>;
export type IrisView={recipe:IrisRecipe;reviewed:boolean;native_available:boolean;suspended:string|null;facts:{changed_pixels?:number;limitation?:string};source:{sha256:string;width:number;height:number};face_ref:import('../people/model').FaceRef|null;source_preview:import('./sourcePreview').SourcePreview|null};
