/** PC-32470 flash red-eye, not sclera veins. [0,1]/zero are local choices. */
export const RED_EYE_CONTROL_ID = 'LNX-REF-PC-32470-C-ee00f0a195';

export function redEyeReadiness(value?: {
  red_eye_available?: boolean;
  red_eye_reason?: string | null;
} | null): {available:boolean;reason?:string} {
  if (value?.red_eye_available === true) return {available:true};
  return {available:false,reason:value?.red_eye_reason
    || '祛红眼核心尚不可用，请使用包含该核心的完整版本'};
}
