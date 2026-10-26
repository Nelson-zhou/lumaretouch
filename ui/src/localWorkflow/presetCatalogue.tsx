// SPDX-License-Identifier: GPL-3.0-or-later
import type {WorkflowOperation} from './contracts';
export interface CataloguePreset {id: string; name: string; kind: string; builtin: boolean; preset_sha256: string; module_ids: string[]; workflow_supported: boolean; support_reason: string; automatic_supported?: boolean; automatic_support_reason?: string; automatic_reference?: {asset_id: string; render_sha256: string; source_sha256: string}}
export interface PresetCatalogue {schema: 'lrt.workflow-preset-catalogue.v1'; presets: CataloguePreset[]; errors: {code: string; file: string | null; message: string}[]; complete: boolean}
export function checkedCatalogue(raw: unknown): PresetCatalogue | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const value = raw as PresetCatalogue;
  if (value.schema !== 'lrt.workflow-preset-catalogue.v1' || typeof value.complete !== 'boolean' || !Array.isArray(value.presets) || value.presets.length > 256 || !Array.isArray(value.errors)) return null;
  if (new TextEncoder().encode(JSON.stringify(raw)).length > 512 * 1024) return null;
  const ids = new Set<string>();
  for (const row of value.presets) {
    if (!row || typeof row.id !== 'string' || !/^[a-z0-9._-]{1,64}$/.test(row.id) || ids.has(row.id)
      || typeof row.name !== 'string' || typeof row.kind !== 'string' || typeof row.builtin !== 'boolean'
      || typeof row.preset_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(row.preset_sha256)
      || typeof row.workflow_supported !== 'boolean' || typeof row.support_reason !== 'string'
      || (row.automatic_supported !== undefined && typeof row.automatic_supported !== 'boolean')
      || (row.automatic_support_reason !== undefined && typeof row.automatic_support_reason !== 'string')
      || (row.automatic_reference !== undefined && (!row.automatic_reference || typeof row.automatic_reference !== 'object' || Object.keys(row.automatic_reference).sort().join(',') !== 'asset_id,render_sha256,source_sha256' || !Object.values(row.automatic_reference).every(value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value))))
      || !Array.isArray(row.module_ids) || !row.module_ids.every(id => typeof id === 'string')) return null;
    ids.add(row.id);
  }
  if (!value.errors.every(row => row && typeof row.code === 'string' && (row.file === null || (typeof row.file === 'string' && row.file.length <= 4096)) && typeof row.message === 'string')) return null;
  return structuredClone(value);
}
export function WorkflowPresetPicker({catalogue, operation, onChange}: {catalogue: PresetCatalogue | null; operation: Extract<WorkflowOperation, {kind: 'compatible_preset' | 'automatic_preset'}>; onChange: (operation: WorkflowOperation) => void}) {
  const automatic = operation.kind === 'automatic_preset';
  const portrait = (row: CataloguePreset) => row.module_ids.some(id => id === 'lnx.skin_finish.v1' || id === 'lnx.skin_texture.v1');
  const reference = (row: CataloguePreset) => row.module_ids.includes('lnx.reference_color.v1');
  const supported = (row: CataloguePreset) => operation.kind === 'automatic_preset'
    ? row.automatic_supported === true && (reference(row)
      ? row.module_ids.length === 1 && !!row.automatic_reference && operation.intent.reference_scope === 'stored_reference_per_target_fit' && operation.intent.reference_source_policy === 'reject_same_source' && !operation.intent.portrait_scope
      : !operation.intent.reference_scope && (!portrait(row) || operation.intent.portrait_scope === 'all_verified_detected_faces'))
    : row.workflow_supported;
  const selected = catalogue?.presets.find(row => row.id === operation.preset_id && row.preset_sha256 === operation.preset_sha256);
  return <>
    <label>选择实际预设<select value={selected ? `${selected.id}:${selected.preset_sha256}` : ''} disabled={!catalogue?.complete}
      onChange={event => {const row = catalogue?.presets.find(item => `${item.id}:${item.preset_sha256}` === event.currentTarget.value);
        if (row && supported(row) && catalogue?.complete) onChange({...operation, preset_id: row.id, preset_sha256: row.preset_sha256});}}>
      <option value="">{operation.preset_id ? '原预设已变化或不可用，请重新选择' : '选择内置或已保存的预设'}</option>
      {catalogue?.presets.map(row => <option key={row.id} value={`${row.id}:${row.preset_sha256}`} disabled={!supported(row)}>{row.name} · {row.builtin ? '内置' : '我的预设'}{!supported(row) ? (row.support_reason === 'skin_requires_retained_target_preparation' ? ' · 逐图人像准备尚未接通' : ' · 工作流暂不支持') : ''}</option>)}
    </select></label>
    <small>原定义：{operation.preset_id || '未选择'} · {operation.preset_sha256 || '尚无内容指纹'}。{automatic ? '选择配方并非启动授权；每次启动仍须确认当前任务范围与输出。' : '目录选择不是逐图应用授权；仍需实际目标检测与审核。'}</small>
    {selected && automatic && <small>{supported(selected) ? (reference(selected) ? '仅使用已保存的不可变参考样片；每张目标独立匹配并拟合一次，冻结后仅核验，不复制源图滑块、蒙版或身份。参考图及同源别名拒绝并报告。' : portrait(selected) ? '仅作用于每张目标的全部已验证检测人脸，不做身份匹配；真实目标分析仍须通过，不能视为照片质量验收。' : '固定曝光／白平衡配方；不是自适应 AI 调色。') : `整份预设不支持自动模式：${reference(selected) && operation.kind === 'automatic_preset' && !operation.intent.reference_scope ? '请先选择仅参考色彩范围，并读取宿主固定样片身份' : portrait(selected) && operation.kind === 'automatic_preset' && !operation.intent.portrait_scope ? '请先明确选择全部已验证检测人脸范围' : selected.automatic_support_reason || '当前操作范围或样片身份不匹配，宿主尚未确认自动支持'}。不会只应用其中部分模块。`}</small>}
    {selected && !automatic && <small>{selected.workflow_supported ? '此预设配方可进入逐图审核，不表示已获应用授权。' : selected.support_reason === 'skin_requires_retained_target_preparation'
      ? '磨皮预设暂不可在此工作流执行：逐图分析、皮肤作用域及人物状态的审核与取消尚未接通。不会只应用其中的调色模块，也不会启动分析。'
      : `整份预设不可执行：${selected.support_reason}。不会丢弃不支持的模块后继续。`}</small>}
    {!catalogue && <p>真实预设目录尚未读取。不能手填指纹作为授权。</p>}
    {catalogue && !catalogue.complete && <p role="alert">目录读取不完整，保留原选择但不接受新的选择。</p>}
    {catalogue?.errors.map((row, index) => <p role="alert" key={`${row.code}:${index}`}>{row.file ?? '预设目录'}: {row.message}</p>)}
  </>;
}
