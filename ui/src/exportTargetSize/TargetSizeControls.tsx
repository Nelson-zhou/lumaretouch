import {targetSizePolicy, sizeSummary, type TargetSizeDraft, type SizeUnit, type TargetSizeReceipt} from './model';

/** Mount beside the existing quality control; caller disables its quality slider while enabled. */
export function TargetSizeControls({value, onChange, format, bitDepth, busy = false}: {
  value: TargetSizeDraft; onChange: (value: TargetSizeDraft) => void;
  format: string; bitDepth: number; busy?: boolean;
}) {
  const patch = (part: Partial<TargetSizeDraft>) => onChange({...value, ...part});
  let error = '';
  try { targetSizePolicy(value, format, bitDepth); } catch (e) { error = String(e); }
  return <fieldset disabled={busy} aria-label="近似目标大小">
    <label><input type="checkbox" checked={value.enabled} onChange={e => patch({enabled: e.target.checked})}/>
      使用近似目标大小（代替品质设置）</label>
    {value.enabled && <>
      <p>不保证精确字节数。保留当前尺寸、8-bit JPEG、4:4:4 和元数据策略；不会缩图或转为其他格式。容差可允许超过目标；水印/无水印副本分别计算，排版 PNG/PDF 不受此目标约束。</p>
      <label>目标大小<input inputMode="decimal" value={value.amount} onChange={e => patch({amount: e.target.value})}/></label>
      <label>单位<select value={value.unit} onChange={e => patch({unit: e.target.value as SizeUnit})}>
        {(['B', 'kB', 'MB', 'KiB', 'MiB'] as SizeUnit[]).map(unit => <option key={unit}>{unit}</option>)}
      </select></label>
      <p>kB = 1000 B；KiB = 1024 B；MB = 1000000 B；MiB = 1048576 B。</p>
      <label>允许误差（± B）<input inputMode="numeric" value={value.toleranceBytes} onChange={e => patch({toleranceBytes: e.target.value})}/></label>
      <label>最低品质<input inputMode="numeric" value={value.minQuality} onChange={e => patch({minQuality: e.target.value})}/></label>
      <label>最高品质<input inputMode="numeric" value={value.maxQuality} onChange={e => patch({maxQuality: e.target.value})}/></label>
      <label>最多编码次数<input inputMode="numeric" value={value.maxAttempts} onChange={e => patch({maxAttempts: e.target.value})}/></label>
      <label>搜索时间预算（ms）<input inputMode="numeric" value={value.timeBudgetMs} onChange={e => patch({timeBudgetMs: e.target.value})}/></label>
      <p>编码间检查取消和时间预算，单次编码不能中途打断。品质采用本产品 1–100 编码器刻度，不等价于其他产品 0–14。</p>
      <label><input type="checkbox" checked={value.allowBestEffort} onChange={e => patch({allowBestEffort: e.target.checked})}/>
        未达目标也保存已搜索候选中最接近的文件，并保留警告（可能超出目标）</label>
      {error && <p role="alert">{error}</p>}
    </>}
  </fieldset>;
}
export function TargetSizeResult({receipt}: {receipt?: TargetSizeReceipt}) {
  if (!receipt) return null;
  return <span role="status" className={receipt.within_tolerance ? 'targetSizeMatched' : 'targetSizeWarning'}>
    {sizeSummary(receipt)}
  </span>;
}
