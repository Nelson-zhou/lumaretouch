import type {PresetInfo,ScopeModule} from '../native';
const labels:Record<string,string>={'lnx.original_shadow.v1':'原图阴影（开关、强度、混合；目标独立地面与范围）','lnx.spill_removal.v1':'祛背景色反光（仅启用与强度，目标独立范围）','lnx.colour_editor.v1':'色彩编辑器（连续色域、HSL 偏移与均匀度）','lnx.photo_grain.v1':'照片颗粒（含固定图案种子）','lnx.photo_detail.v1':'照片细节（锐化、噪点消除、减少杂色）','lnx.primary_calibration.v1':'RGB 原色校准（三原色色相/饱和度）','lnx.selective_colour.v1':'可选颜色（九色域 CMYK、相对/绝对）','lnx.colour_grading.v1':'颜色分级（四轮、混合、平衡）','lnx.extended_tone.v1':'扩展影调（七控件与原创黑白输出）','lnx.custom_lut.v1':'自定义 CUBE 滤镜（含便携素材与强度）','lnx.iris_makeup.v1':'美瞳（11 款原创纹理与程度，目标独立审核）','lnx.eyelash.v1':'睫毛（14 款原创曲线、四部位独立、颜色）','lnx.brow_makeup.v1':'眉妆（14 款原创图案、左右独立、颜色）','lnx.eyeliner.v1':'眼线（六款原创曲线、独立双眼、颜色）','lnx.lipstick.v1':'口红（13 款空间效果、5 质地、程度与颜色）','lnx.blush_makeup.v1':'腮红（12 款原创图案、程度与颜色）','lnx.semantic_colour.v1':'AI 语义追色（专用全图批量/便携预设）','lnx.reference_color.v1':'同场景参考统一（逐图重算，样片需保留）','lnx.mouth_shape.v1':'嘴形九项（露龈可拆分，仅参数）','lnx.eye_shape.v1':'眼形十项（双侧二维几何，仅参数）','lnx.nose_shape.v1':'鼻形六项（二维几何，仅参数）','lnx.brow_shape.v1':'眉形七项（人物左右独立，仅参数）','lnx.lip_makeup.v1':'唇妆增强（三控件）','lnx.sky_replacement.v1':'换天空素材与参数（区域逐图保留）','lnx.optics_auto.v1':'镜头/透视逐图自动重算（含手动参数）','lnx.facial_wrinkles.v1':'面部祛纹八部位（人物与恢复笔迹不复制）','lnx.optics_manual.v1':'镜头/透视手动参数（不复制自动结果）','lnx.studio_background.v1':'影棚背景强度（范围不复制）','lnx.local_grade.v1':'独立局部调色组','lnx.exposure.v1':'曝光','lnx.white_balance.v1':'白平衡','lnx.levels.v1':'色阶',
  'lnx.skin_colour.v1':'面部肤色色温/色调',
  'lnx.skin_finish.v1':'美白红润（独立参数，目标单独审核身体范围）',
  'lnx.skin_gloss.v1':'皮肤光泽（面部已有高光，正负强度逐图重算）',
  'lnx.face_contour.v1':'面部轮廓（太阳穴、颧骨、下颌；左右独立二维参数）',
  'lnx.slim_face.v2':'新版瘦脸（左右独立二维参数，不转换旧版强度）',
  'lnx.face_size.v1':'脸部大小（整体等比缩放；正值缩小、负值放大，逐图重算）',
  'lnx.lower_face.v1':'下庭长度（鼻至下巴二维代理区间；正值拉长、负值缩短，逐图重算）',
  'lnx.mid_face.v1':'中庭长度（眼界至鼻部二维代理区间；正值拉长、负值缩短，逐图重算）',
  'lnx.chin_shape.v1':'新版尖下巴（左右独立；正值横向收尖、负值扩圆，不改高度，逐图重算）',
  'lnx.chin_length.v1':'新版下巴长度（嘴唇平面至下巴；正值拉长、负值缩短，逐图重算，不自动清零旧版）',
  'lnx.philtrum.v1':'人中（鼻部安全界至唇上界；负值缩短、正值拉长，嘴唇与下脸共同平移，逐图重算）',
  'lnx.eye_symmetry.v1':'眼睛对称（水平/大小强度与自动或左右大小参考策略；目标独立测量双眼，不复制眼睛）',
  'lnx.skin_texture.v1':'皮肤质感（面部纹理与精细清晰，来源细节逐图重算）',
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
  const supported=new Set(modules.filter(m=>m.transferable===true&&!m.dedicated_transport).map(m=>m.operation_id));
  return ops.filter(op=>!supported.has(op));
}
/** Legacy string-valued registry controls must never guess between colliding labels. */
export function presetFromLabel(label:string,list:PresetInfo[]){
  const matches=list.filter(p=>presetLabel(p,list)===label);
  return matches.length===1?matches[0]:undefined;
}
