/** PC-32470 eye-white purification, separate from brightness and red vessels.
 * [0,1] and neutral zero are local choices, not published handbook values.
 */
export const SCLERA_PURIFY_CONTROL_ID = 'LNX-REF-PC-32470-C-26ab900915';
export type ScleraPurifyCapability = {
  sclera_purify_available?: boolean;
  sclera_purify_reason?: string | null;
};

export function scleraPurifyReadiness(value?: ScleraPurifyCapability | null): {available:boolean;reason?:string} {
  if (value?.sclera_purify_available === true) return {available:true};
  return {available:false,reason:value?.sclera_purify_reason
    || '眼白净化核心尚不可用，请使用包含该核心的完整版本'};
}
