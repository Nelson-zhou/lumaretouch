/** Labels and selectable scopes use only capabilities reported by the engine. */
const globalModules = [
  ['lnx.exposure.v1', '曝光'], ['lnx.white_balance.v1', '白平衡'],
  ['lnx.colour_editor.v1', '色彩编辑器（逐图全源统计）'], ['lnx.photo_grain.v1', '照片颗粒（固定源像素图案）'], ['lnx.photo_detail.v1', '照片细节（非 AI、逐图重算）'], ['lnx.primary_calibration.v1', 'RGB 原色校准（三原色色相/饱和度）'], ['lnx.selective_colour.v1', '可选颜色（九色域 CMYK）'], ['lnx.colour_grading.v1', '颜色分级（四轮、混合、平衡）'], ['lnx.extended_tone.v1', '扩展影调（逐图重算）'], ['lnx.levels.v1', '色阶'], ['lnx.curves.v1', '曲线'],
  ['lnx.hsl.v1', 'HSL'], ['lnx.crop.v1', '裁剪'],
] as const;

export function batchScopeOptions(modules: readonly {operation_id: string; transferable: boolean}[]) {
  const supported = new Set(modules.filter(m => m.transferable === true).map(m => m.operation_id));
  const global = globalModules.filter(([op]) => supported.has(op));
  const skin = ['lnx.skin.v1', 'lnx.blemish.v1'].filter(op => supported.has(op));
  const out: {label: string; ops: string[]}[] = [];
  if (global.length) {
    out.push({label: `全图配方（${global.map(([, label]) => label).join('·')}）`, ops: global.map(([op]) => op)});
    if (skin.length) out.push({label: '全图配方 + 磨皮（逐张须单脸）', ops: [...global.map(([op]) => op), ...skin]});
    for (const [op, label] of global) out.push({label: `仅${label}`, ops: [op]});
  }
  if (skin.length) out.push({label: '仅磨皮（逐张须单脸）', ops: skin});
  if(supported.has('lnx.local_grade.v1')) {
    out.push({label:'仅局部调色组（预检追加/替换）',ops:['lnx.local_grade.v1']});
    if(global.length)out.push({label:'全图配方 + 局部调色组',ops:[...global.map(([op])=>op),'lnx.local_grade.v1']});
  }
  if(supported.has('lnx.original_shadow.v1')) out.push({label:'原图阴影（仅参数；目标须独立地面样本与逐图审核）',ops:['lnx.original_shadow.v1']});
  if(supported.has('lnx.spill_removal.v1')) out.push({label:'祛背景色反光（仅参数；目标逐图审核）',ops:['lnx.spill_removal.v1']});
  if(supported.has('lnx.studio_background.v1')) out.push({label:'影棚背景强度（目标须已有范围）',ops:['lnx.studio_background.v1']});
  if(supported.has('lnx.optics_manual.v1')) out.push({label:'镜头/透视手动参数（不复制自动结果）',ops:['lnx.optics_manual.v1']});
  if(supported.has('lnx.optics_auto.v1')){
    out.push({label:'镜头/透视逐图自动重算（含手动参数）',ops:['lnx.optics_auto.v1']});
    if(global.length)out.push({label:'全图配方 + 镜头/透视逐图重算',ops:[...global.map(([op])=>op),'lnx.optics_auto.v1']});
  }
  if(supported.has('lnx.brow_shape.v1'))out.push({label:'眉形七项（左右独立，目标逐图重算）',ops:['lnx.brow_shape.v1']});
  if(supported.has('lnx.nose_shape.v1'))out.push({label:'鼻形六项（二维几何，目标逐图重算）',ops:['lnx.nose_shape.v1']});
  if(supported.has('lnx.mouth_shape.v1'))out.push({label:'嘴形九项（目标逐图重算，不复制源图嘴部）',ops:['lnx.mouth_shape.v1']});
  if(supported.has('lnx.eye_shape.v1'))out.push({label:'眼形十项双侧（二维几何，目标逐图重算）',ops:['lnx.eye_shape.v1']});
  if(supported.has('lnx.brow_makeup.v1'))out.push({label:'眉妆（仅逐眉参数；目标须独立眉毛和额头审核）',ops:['lnx.brow_makeup.v1']});
  if(supported.has('lnx.eyeliner.v1'))out.push({label:'眼线（仅逐眼参数；目标须独立眼睑审核）',ops:['lnx.eyeliner.v1']});
  if(supported.has('lnx.iris_makeup.v1'))out.push({label:'美瞳（图案与程度；目标须独立虹膜、实测瞳孔和高光审核）',ops:['lnx.iris_makeup.v1']});
  if(supported.has('lnx.eyelash.v1'))out.push({label:'睫毛（四部位参数；目标须独立根部及延伸区审核）',ops:['lnx.eyelash.v1']});
  if(supported.has('lnx.lipstick.v1'))out.push({label:'口红（仅参数；目标须独立可见唇部审核）',ops:['lnx.lipstick.v1']});
  if(supported.has('lnx.blush_makeup.v1'))out.push({label:'腮红（仅参数；目标须独立人物审核）',ops:['lnx.blush_makeup.v1']});
  if(supported.has('lnx.lip_makeup.v1'))out.push({label:'唇妆增强（三控件，逐张须单脸）',ops:['lnx.lip_makeup.v1']});
  if(supported.has('lnx.facial_wrinkles.v1'))out.push({label:'面部祛纹八部位（逐张须单脸，仅参数）',ops:['lnx.facial_wrinkles.v1']});
  return out;
}

export function resolveBatchScope(options: {label: string; ops: string[]}[], requested: string) {
  return options.find(option => option.label === requested)
    ?? (!requested ? options[0] : undefined)
    ?? {label: options.length ? '原模块不可用，请重新选择' : '当前无可同步模块', ops: []};
}
