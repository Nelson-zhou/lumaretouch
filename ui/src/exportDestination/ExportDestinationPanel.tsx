import {decisionForEntry, originalFormatPlan, type DestinationPolicy, type DestinationPreview, type OriginalFormatPlan} from './model';
type Props = {policy: DestinationPolicy; preview: DestinationPreview | null; busy: boolean;
  available: boolean; onChange: (policy: DestinationPolicy) => void; onPreview: () => void; error?: string};
/** Mount inside the existing export dialog; no separate agent confirmation flow. */
export function ExportDestinationPanel({policy, preview, busy, available, onChange, onPreview, error}: Props) {
  const change = (patch: Partial<DestinationPolicy>) => onChange({...policy, ...patch});
  let formatPlan: OriginalFormatPlan | null = null;
  let formatError = '';
  try { if (preview) formatPlan = originalFormatPlan(preview); } catch (error) { formatError = String(error); }
  return <fieldset disabled={busy || !available} aria-label="导出存储位置">
    <legend>导出存储位置</legend>
    {!available && <p role="status">目录规划尚未接入，暂不可用</p>}
    <label>存储位置 <select value={policy.mode} onChange={e => change({mode: e.target.value as DestinationPolicy['mode']})}>
      <option value="chosen_root">指定文件夹</option><option value="source_folder">原始照片所在文件夹</option>
    </select></label>
    {policy.mode === 'chosen_root' ? <>
      <label>指定文件夹 <input value={policy.chosen_root ?? ''} onChange={e => change({chosen_root: e.target.value})}/></label>
      <label><input type="checkbox" checked={policy.retain_hierarchy} onChange={e => change({retain_hierarchy: e.target.checked})}/>保留导入文件夹及其内部层级</label>
      <p>从导入时的末端文件夹命名；同名导入目录会添加稳定标识，避免合并。</p>
    </> : <>
      <label>新建存储文件夹 <select value={policy.source_subfolder} onChange={e => change({source_subfolder: e.target.value as DestinationPolicy['source_subfolder']})}>
        <option value="project">以项目名称命名</option><option value="import_root">以导入文件夹命名</option><option value="none">不新建子文件夹</option>
      </select></label>
      {policy.source_subfolder === 'project' && <label>项目文件夹名称 <input value={policy.project_name} onChange={e => change({project_name: e.target.value})}/></label>}
    </>}
    <label>排版汇总目录（跨原图目录排版时必填）<input value={policy.layout_root ?? ""} onChange={e => change({layout_root: e.target.value || null})}/></label>
    <label><input type="checkbox" checked={policy.create_missing} onChange={e => change({create_missing: e.target.checked})}/>允许创建缺失的目标文件夹</label>
    <label>同名文件 <select value={policy.conflict} onChange={e => change({conflict: e.target.value as DestinationPolicy['conflict']})}>
      <option value="rename">保留已有文件，导出为唯一名称</option><option value="skip">跳过并报告</option><option value="ask">先预览冲突再决定</option>
    </select></label>
    <p>不覆盖任何原片或已有文件。目标、色彩及隐私设置会随本批次冻结。</p>
    <button type="button" onClick={onPreview}>预览导出位置</button>
    {error && <p role="alert">{error}</p>}
    {formatError && <p role="alert">{formatError}</p>}
    {formatPlan && <p>Original 已逐图解析：以下为本批冻结的实际容器与位深。排版页仍使用独立 PNG / PDF 8-bit 交付，不继承 Original。</p>}
    {preview && !formatError && <ul>{preview.entries.map(e => {
      const decision = decisionForEntry(formatPlan, e.item_id);
      return <li key={e.item_id}>
      {e.target} · {e.disposition === 'write' ? '待导出' : e.disposition === 'skip' ? '跳过' : '请确认改名或跳过'}
      {decision && <span> · {decision.codec.toUpperCase()} {decision.bits}-bit（.{decision.extension}）<small title={`决策 ${decision.decision_id} · 源事实 ${decision.fact_id}`}> · 冻结决策 {decision.decision_id.slice(0, 12)}</small></span>}
      {formatPlan && e.item_id.startsWith('layout::') && <span> · 排版独立交付（PNG / PDF 8-bit；清单为 JSON）</span>}
      {e.origin_kind === "legacy_parent" && <span> · 旧项目未记录导入根目录，本次按源文件父目录规划，请核对</span>}
      {e.renamed_from && <span>（原目标：{e.renamed_from}）</span>}
      {e.missing_directories.length > 0 && <span> · 将创建目录</span>}
    </li>;})}</ul>}
  </fieldset>;
}
