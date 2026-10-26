export type SizeUnit = 'B' | 'kB' | 'MB' | 'KiB' | 'MiB';
export const unitBytes: Record<SizeUnit, number> = {B: 1, kB: 1000, MB: 1000000, KiB: 1024, MiB: 1048576};
export interface TargetSizePolicy {
  schema: 1; target_bytes: number; tolerance_bytes: number;
  min_quality: number; max_quality: number; max_attempts: number;
  time_budget_ms: number; max_encoded_bytes: number; max_pixels: number;
  allow_best_effort: boolean;
}
export interface TargetSizeDraft {
  enabled: boolean; amount: string; unit: SizeUnit; toleranceBytes: string;
  minQuality: string; maxQuality: string; maxAttempts: string; timeBudgetMs: string;
  allowBestEffort: boolean;
}
export const initialTargetSize: TargetSizeDraft = {
  enabled: false, amount: '2', unit: 'MiB', toleranceBytes: '104858',
  minQuality: '60', maxQuality: '100', maxAttempts: '41', timeBudgetMs: '30000', allowBestEffort: false,
};
function integer(raw: string, label: string, min: number, max: number): number {
  if (!/^\d+$/.test(raw)) throw new Error(`${label}必须是整数`);
  const n = Number(raw);
  if (!Number.isSafeInteger(n) || n < min || n > max) throw new Error(`${label}须在 ${min}–${max} 之间`);
  return n;
}
export function targetSizePolicy(draft: TargetSizeDraft, format: string, bitDepth: number | undefined): TargetSizePolicy | undefined {
  if (!draft.enabled) return undefined;
  // Original stays unresolved here; the engine requires ALL entries to be JPEG8.
  if (format !== 'original' && (!['jpg', 'jpeg'].includes(format.toLowerCase()) || bitDepth !== 8))
    throw new Error('近似目标大小仅支持 8-bit JPEG；Original 须逐图预览且整批均为 JPEG8，不会自动转换');
  if (!/^\d+(\.\d+)?$/.test(draft.amount)) throw new Error('请输入目标大小');
  const target = Number(draft.amount) * unitBytes[draft.unit];
  if (!Number.isSafeInteger(target) || target < 1 || target > 2147483647)
    throw new Error('目标须换算为 1–2147483647 的整数 B');
  const min = integer(draft.minQuality, '最低品质', 1, 100);
  const max = integer(draft.maxQuality, '最高品质', 1, 100);
  if (min > max) throw new Error('最低品质不可高于最高品质');
  return {schema: 1, target_bytes: target,
    tolerance_bytes: integer(draft.toleranceBytes, '容差 B', 0, target),
    min_quality: min, max_quality: max,
    max_attempts: integer(draft.maxAttempts, '最多编码次数', 1, 100),
    time_budget_ms: integer(draft.timeBudgetMs, '搜索时间预算 ms', 1, 300000),
    max_encoded_bytes: 134217728, max_pixels: 50000000,
    allow_best_effort: draft.allowBestEffort};
}
export interface TargetSizeReceipt {
  schema: number; status: string; target_bytes: number; tolerance_bytes: number;
  actual_bytes: number | null; difference_bytes: number | null;
  encoder_quality: number | null; within_tolerance: boolean; published?: boolean;
  exhaustive: boolean; attempts: {quality: number; bytes: number | null; status: string}[];
}
export function sizeSummary(receipt: TargetSizeReceipt): string {
  if (receipt.status === 'skipped') return `已跳过 · 目标 ${receipt.target_bytes} B ± ${receipt.tolerance_bytes} B · 未编码或写入`;
  const outcome = receipt.published === false ? '未写入' : receipt.published === true ? '已写入' : '候选结果';
  const status = receipt.within_tolerance ? '达到近似目标' : receipt.exhaustive ? '当前品质范围内不可达' : '预算内未找到匹配';
  return `${outcome} · ${status} · 目标 ${receipt.target_bytes} B ± ${receipt.tolerance_bytes} B · 实际 ${receipt.actual_bytes ?? '无候选'} B · 品质 ${receipt.encoder_quality ?? '—'} · ${receipt.attempts.length} 次编码`;
}
