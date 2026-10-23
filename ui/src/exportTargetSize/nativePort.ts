import type {TargetSizePolicy} from './model';
/** Merge into native.ts runExport payload; Tauri maps targetSize -> target_size. */
export function targetSizeArguments(policy: TargetSizePolicy | undefined, quality: number):
  {targetSize?: TargetSizePolicy; quality?: number} {
  return policy ? {targetSize: {...policy}} : {quality};
}
