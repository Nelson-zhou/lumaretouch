/** Functional grouping follows the official desktop workflow, without copying assets.
 * Sources: pixcakeai.com/guide/47246 and pixcakeai.com/guide/32455. */
export const TOOL_GROUPS = [
  {id:'presets',label:'预设',features:['PC-32452']},
  {id:'color',label:'调色',features:['PC-32455']},
  {id:'local',label:'局部',features:['PC-32454','PC-32481','PC-32482','PC-32479']},
  {id:'portrait',label:'人像',features:['PC-32464','PC-32465','PC-32466','PC-32468','PC-32469','PC-32470','PC-32471','PC-32472','PC-46608','PC-9XYcMCvHXW','PC-32473']},
  {id:'image',label:'图像',features:['PC-32474','PC-32475','PC-32476']},
  {id:'clothes',label:'衣物',features:['PC-32477']},
  {id:'pets',label:'宠物',features:['PC-4WvzDIBakP','PC-DaMvAbwxp4']},
  {id:'crop',label:'裁剪',features:['PC-32478','PC-AlCcjw85ql','PC-165385']},
  {id:'history',label:'历史',features:['PC-47209']},
  {id:'batch',label:'同步',features:['PC-32480']},
] as const;
export type ToolGroup = typeof TOOL_GROUPS[number]['id'];
export function toolGroupOf(id:string): ToolGroup | null {
  return TOOL_GROUPS.find(g=>(g.features as readonly string[]).includes(id))?.id ?? null;
}
