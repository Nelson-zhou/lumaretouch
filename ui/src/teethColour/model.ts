/** Handbook controls only. [0,1] and neutral zero are local design choices. */
export const TEETH_CONTROL_IDS = {
  teeth_brightness: 'LNX-REF-PC-32469-C-6eb0bef21b',
  teeth_yellow_removal: 'LNX-REF-PC-32469-C-5462a41c9a',
} as const;

export function teethColourReadiness(value?: {
  teeth_colour_available?: boolean;
  teeth_colour_reason?: string | null;
} | null): {available:boolean;reason?:string} {
  if (value?.teeth_colour_available === true) return {available:true};
  return {available:false,reason:value?.teeth_colour_reason
    || '独立牙齿调整核心尚不可用，请使用包含该核心的完整版本'};
}
