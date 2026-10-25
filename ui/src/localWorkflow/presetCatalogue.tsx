// SPDX-License-Identifier: GPL-3.0-or-later
import type {WorkflowOperation} from './contracts';
export interface CataloguePreset {id: string; name: string; kind: string; builtin: boolean; preset_sha256: string; module_ids: string[]; workflow_supported: boolean; support_reason: string}
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
      || !Array.isArray(row.module_ids) || !row.module_ids.every(id => typeof id === 'string')) return null;
    ids.add(row.id);
  }
  if (!value.errors.every(row => row && typeof row.code === 'string' && (row.file === null || (typeof row.file === 'string' && row.file.length <= 4096)) && typeof row.message === 'string')) return null;
  return structuredClone(value);
}
export function WorkflowPresetPicker({catalogue, operation, onChange}: {catalogue: PresetCatalogue | null; operation: Extract<WorkflowOperation, {kind: 'compatible_preset'}>; onChange: (operation: WorkflowOperation) => void}) {
  const selected = catalogue?.presets.find(row => row.id === operation.preset_id && row.preset_sha256 === operation.preset_sha256);
  return <>
    <label>选择实际预设<select value={selected ? `${selected.id}:${selected.preset_sha256}` : ''} disabled={!catalogue?.complete}
      onChange={event => {const row = catalogue?.presets.find(item => `${item.id}:${item.preset_sha256}` === event.currentTarget.value);
        if (row?.workflow_supported && catalogue?.complete) onChange({...operation, preset_id: row.id, preset_sha256: row.preset_sha256});}}>
      <option value="">{operation.preset_id ? '原预设已变化或不可用，请重新选择' : '选择内置或已保存的预设'}</option>
      {catalogue?.presets.map(row => <option key={row.id} value={`${row.id}:${row.preset_sha256}`} disabled={!row.workflow_supported}>{row.name} · {row.builtin ? '内置' : '我的预设'}{!row.workflow_supported ? ' · 工作流暂不支持' : ''}</option>)}
    </select></label>
    <small>原定义：{operation.preset_id || '未选择'} · {operation.preset_sha256 || '尚无内容指纹'}。目录选择不是逐图应用授权；仍需实际目标检测与审核。</small>
    {selected && <small>{selected.workflow_supported ? '此预设配方可进入逐图审核，不表示已获应用授权。' : `整份预设不可执行：${selected.support_reason}。不会丢弃不支持的模块后继续。`}</small>}
    {!catalogue && <p>真实预设目录尚未读取。不能手填指纹作为授权。</p>}
    {catalogue && !catalogue.complete && <p role="alert">目录读取不完整，保留原选择但不接受新的选择。</p>}
    {catalogue?.errors.map((row, index) => <p role="alert" key={`${row.code}:${index}`}>{row.file ?? '预设目录'}: {row.message}</p>)}
  </>;
}
