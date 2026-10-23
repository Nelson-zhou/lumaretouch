export type Category='subject'|'contact'|'all';
export type RGB=[number,number,number];
export type Background={kind:'none'|'solid'|'asset';color:RGB|null;asset:null|{path:string;sha256:string;width:number;height:number;bits:8|16;working_color:string;icc_sha256:string;pixels_sha256:string;alpha_sha256?:string|null};fit:'center'|'stretch';x:number;y:number;scale:number};
export type Shadow={kind:'none'|'soft'|'hard'|'silhouette';blend:'normal'|'multiply'|'softlight';opacity:number;blur:number;gradient:number;x:number;y:number;distance:number;angle:number;color:RGB};
type RecipeFields={enabled:boolean;source:unknown;background:Background;support:Record<Category,null|{reviewed:true;recipe_sha256:string}>;selected_support:Category;edge:number;opacity:number;shadow:Shadow;favourites:RGB[]};
// Legacy v1 is not silently rewritten. Only the separately reviewed spill action
// may introduce v2; ordinary id_set intentionally never contains this field.
export type Recipe=RecipeFields&({version:1;spill?:never}|{version:2;spill:import('../spillRemoval/model').SpillRecipe});
export type Report={recipe_document_id:string;recipe_revision:string;recipe:Recipe;available:boolean;suspended?:string|null;boundaries?:string[];spill_protocol?:1;spill_available?:boolean};
export type Reply={event:'id_background_result';request_id:string;document_id:string;success:boolean;action?:string;protocol?:1;outcome_unknown?:boolean;requires_reload?:boolean;error?:string;report?:Report;review?:unknown};
export const control=(id:string)=>`LNX-REF-PC-32475-C-${id}`;
export const presets:{name:string;color:RGB}[]=[{name:'白色',color:[255,255,255]},{name:'蓝色',color:[67,142,219]},{name:'红色',color:[205,41,49]},{name:'浅灰',color:[224,224,224]}];
export const categories:{key:Category;name:string;id:string}[]=[{key:'subject',name:'主体',id:'4169de2512'},{key:'contact',name:'主体及接触关联物品',id:'c0143cd19e'},{key:'all',name:'主体、关联及非关联物品',id:'d58738ab24'}];
export function hex(rgb:RGB):string{return '#'+rgb.map(v=>v.toString(16).padStart(2,'0')).join('');}
export function parseHex(value:string):RGB|null{const m=/^#?([0-9a-f]{6})$/i.exec(value);return m?[0,2,4].map(i=>parseInt(m[1].slice(i,i+2),16)) as RGB:null;}
export function editable(r:Recipe){return {enabled:r.enabled,background:r.background,selected_support:r.selected_support,edge:r.edge,opacity:r.opacity,shadow:r.shadow,favourites:r.favourites};}

export type PickerMode='original'|'reference'|'subject';
export const pickerActions={original:'id_background',reference:'id_background_reference',subject:'id_background_subject'} as const;
export const pickerStages={original:'id-background-source',reference:'id-background-reference',subject:'id-background-subject'} as const;
export const pickerLabels={original:'当前源图',reference:'参考图',subject:'主体及关联物品'};
