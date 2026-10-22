import type {PresetInfo,ScopeModule} from '../native';
const labels:Record<string,string>={'lnx.nose_shape.v1':'鼻形六项（二维几何，仅参数）','lnx.brow_shape.v1':'眉形七项（人物左右独立，仅参数）','lnx.lip_makeup.v1':'唇妆增强（三控件）','lnx.sky_replacement.v1':'换天空素材与参数（区域逐图保留）','lnx.optics_auto.v1':'镜头/透视逐图自动重算（含手动参数）','lnx.facial_wrinkles.v1':'面部祛纹八部位（人物与恢复笔迹不复制）','lnx.optics_manual.v1':'镜头/透视手动参数（不复制自动结果）','lnx.studio_background.v1':'影棚背景强度（范围不复制）','lnx.local_grade.v1':'独立局部调色组','lnx.exposure.v1':'曝光','lnx.white_balance.v1':'白平衡','lnx.levels.v1':'色阶',
  'lnx.curves.v1':'曲线','lnx.hsl.v1':'HSL','lnx.crop.v1':'裁剪','lnx.skin.v1':'磨皮','lnx.blemish.v1':'瑕疵处理','lnx.skin_mask.v1':'皮肤蒙版'};
export const moduleLabel=(op:string)=>labels[op]??op;
export function presetLabel(preset:PresetInfo,list:PresetInfo[]){
  return list.filter(p=>p.name===preset.name).length>1?`${preset.name} · ${preset.id}`:preset.name;
}
export type PresetForm={name:string;nameRevision:number;selectedId:string;scope:string[]};
export const initialPresetForm:PresetForm={name:'',nameRevision:0,selectedId:'',scope:[]};
export type FormAction={type:'name';value:string}|{type:'select';id:string}|{type:'scope';ops:string[]}
  |{type:'saved';id:string;nameRevision:number}|{type:'imported';id:string}|{type:'deleted';id:string};
export function presetFormReducer(state:PresetForm,action:FormAction):PresetForm{
  switch(action.type){
    case 'name':return {...state,name:action.value,nameRevision:state.nameRevision+1};
    case 'select':return {...state,selectedId:action.id};
    case 'scope':return {...state,scope:[...new Set(action.ops)]};
    case 'saved':return {...state,selectedId:action.id,name:state.nameRevision===action.nameRevision?'':state.name};
    case 'imported':return {...state,selectedId:action.id};
    case 'deleted':return {...state,selectedId:state.selectedId===action.id?'':state.selectedId};
  }
}
export function unavailableScope(ops:string[],modules:ScopeModule[]){
  const supported=new Set(modules.filter(m=>m.transferable===true).map(m=>m.operation_id));
  return ops.filter(op=>!supported.has(op));
}
/** Legacy string-valued registry controls must never guess between colliding labels. */
export function presetFromLabel(label:string,list:PresetInfo[]){
  const matches=list.filter(p=>presetLabel(p,list)===label);
  return matches.length===1?matches[0]:undefined;
}
