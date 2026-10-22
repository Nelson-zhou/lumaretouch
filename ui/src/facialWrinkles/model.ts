/** PC-32464. Continuous values are local [0,1] scales, not proprietary parity. */
export const REGIONS = ['forehead','glabellar','eye_area','nose','nasolabial','cheek','marionette','mouth_surround'] as const;
export type Region = typeof REGIONS[number];
export const LABELS:Record<Region,string> = {
  forehead:'祛抬头纹',glabellar:'祛川字纹',eye_area:'祛眼周纹',nose:'祛鼻背纹',
  nasolabial:'祛法令纹',cheek:'祛脸颊纹',marionette:'祛木偶纹',mouth_surround:'祛嘴周纹',
};
export const CONTROL_IDS:Record<Region|'family',string> = {
  family:'d9e8e03577',forehead:'294d9a2188',glabellar:'3e1a0bb386',eye_area:'24f710ab2b',
  nose:'fcd0c13b5f',nasolabial:'942d0bfb79',cheek:'f28262041d',marionette:'5aa8868572',mouth_surround:'22b2d6e2a0',
};
export const KEYS = ['wrinkle_forehead','wrinkle_glabellar','wrinkle_eye_area','wrinkle_nose',
  'wrinkle_nasolabial_left','wrinkle_nasolabial_right','wrinkle_cheek','wrinkle_marionette','wrinkle_mouth_surround'] as const;
export const LINK_KEY = 'wrinkle_nasolabial_unlocked';
export const neutral = ():Record<string,number> => Object.fromEntries([...KEYS,LINK_KEY].map(k=>[k,0]));
export interface RegionFact {geom_px:number;gated_px:number;changed_px?:number;reason:string|null;
  partial?:boolean;sides?:Record<string,{geom_px:number;gated_px:number;reason:string|null}>}
const REASONS:Record<string,string> = {
  disabled:'尚未启用',skin_semantics_unavailable:'缺少可信皮肤支持，请先完成人像分析',
  actual_selected_face_required:'请先选中实际检测到的人物',insufficient_resolution:'人物太小，无法可靠区分细纹与纹理',
  foreshortened_or_inadequate_pose:'该侧压缩或姿态不适合处理',inadequate_pose_for_central_region:'当前姿态不适合处理此部位',
  no_eligible_skin_or_occluded:'未找到可处理皮肤，可能被头发、配饰或其他物体遮挡',
  insufficient_visible_skin_support:'可见皮肤支持不足，保留此区域',
  no_detected_wrinkle_lines:'此区域未检测到可淡化的线状细纹',
};
export function explanation(fact?:RegionFact):string|undefined {
  if(!fact) return undefined;
  if(fact.reason && fact.reason !== 'disabled') return REASONS[fact.reason] ?? fact.reason;
  if(fact.partial) return Object.entries(fact.sides??{}).filter(([,f])=>f.reason)
    .map(([side,f])=>`${side==='left'?'人物左侧':side==='right'?'人物右侧':'此部位'}：${REASONS[f.reason!]??f.reason}`).join('；');
  return undefined;
}
export function linkedPatch(value:number):Record<string,number> {
  if(!Number.isFinite(value)||value<0||value>1) throw new Error('法令纹强度无效');
  return {wrinkle_nasolabial_left:value,wrinkle_nasolabial_right:value};
}
export function linkPatch(unlocked:boolean):Record<string,number> {
  // Relinking intentionally does not overwrite either saved side. The next
  // deliberate linked slider move resolves mixed values by setting both.
  return {[LINK_KEY]:unlocked?1:0};
}
export function active(amounts:Record<string,number>):boolean {return KEYS.some(k=>(amounts[k]??0)>0);}
export type WrinkleKey = typeof KEYS[number] | typeof LINK_KEY;
export function transportPatch(amounts?:Partial<Record<WrinkleKey,number>>):Record<string,number>|undefined {
  if(!amounts) return undefined;
  const keys:readonly WrinkleKey[]=[...KEYS,LINK_KEY];
  const entries=keys.filter(k=>amounts[k]!==undefined).map(k=>[k,amounts[k]!]);
  return entries.length?Object.fromEntries(entries):undefined;
}
