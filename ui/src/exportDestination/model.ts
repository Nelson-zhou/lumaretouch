export type DestinationPolicy = {
  mode: 'chosen_root' | 'source_folder'; chosen_root: string | null;
  retain_hierarchy: boolean; source_subfolder: 'none' | 'project' | 'import_root';
  project_name: string; layout_root?: string | null; conflict: 'rename' | 'skip' | 'ask'; create_missing: boolean;
};
export type DestinationEntry = {
  item_id: string; source_path: string; frame_receipt: string; target: string;
  disposition: 'write' | 'skip' | 'needs_confirmation'; renamed_from: string | null;
  missing_directories: string[]; origin_kind?: string;
};
export type DestinationPreview = {
  schema_version: 'lrt.export-destination.v1'; plan_id: string; intent_revision: number;
  entries: DestinationEntry[];
  /** Exact frozen engine settings; never sent back as client-authoritative facts. */
  settings_json?: string;
};
export const initialDestination = (): DestinationPolicy => ({
  mode: 'chosen_root', chosen_root: null, retain_hierarchy: false,
  source_subfolder: 'project', project_name: 'Exports', conflict: 'skip', create_missing: false,
});

export type OriginalFormatDecision = {
  schema: 'lrt.export-format-decision.v1'; item_id: string; document_id: string;
  source_asset_id: string; recipe_version_id: string; fact_id: string; decision_id: string;
  codec: 'jpg' | 'png' | 'tif' | 'webp'; bits: 8 | 16; extension: 'jpg' | 'png' | 'tif' | 'webp';
  applicable_options: {quality: boolean; tiff_compression: boolean; gps: boolean; target_size: boolean};
  source_facts: Record<string, unknown>; effective_asset: Record<string, unknown>;
  options: Record<string, unknown>;
};
export type OriginalFormatPlan = {
  schema: 'lrt.export-format-plan.v1'; requested_format: 'original';
  entries: Record<string, OriginalFormatDecision>;
};
const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const identity = (value: unknown): value is string => typeof value === 'string' && value.length > 0;
const digest = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);

/** Read only the versioned engine receipt. This does not resolve formats or authorize export. */
export function originalFormatPlan(preview: DestinationPreview, required = false): OriginalFormatPlan | null {
  if (preview.settings_json === undefined && !required) return null;
  if (typeof preview.settings_json !== 'string') throw new Error('Original 预览缺少冻结格式计划，请重新预览');
  const settings: unknown = JSON.parse(preview.settings_json);
  if (!object(settings)) throw new Error('导出预览设置无效');
  if (settings.format !== 'original' && settings.format_plan === undefined && !required) return null;
  const plan = settings.format_plan;
  if (settings.format !== 'original') throw new Error('Original 预览意图与格式计划不一致');
  if (!object(plan) || plan.schema !== 'lrt.export-format-plan.v1' || plan.requested_format !== 'original'
      || !object(plan.entries) || !Object.keys(plan.entries).length) throw new Error('Original 格式计划版本或条目无效');
  for (const [key, value] of Object.entries(plan.entries)) {
    if (!key.startsWith('document:') || key.endsWith('::clean') || !object(value) || value.schema !== 'lrt.export-format-decision.v1' || value.item_id !== key
        || !identity(value.document_id) || !identity(value.source_asset_id) || !identity(value.recipe_version_id)
        || !digest(value.fact_id) || !digest(value.decision_id)
        || !['jpg', 'png', 'tif', 'webp'].includes(String(value.codec))
        || value.extension !== value.codec || ![8, 16].includes(Number(value.bits))
        || typeof value.bits !== 'number' || !object(value.applicable_options)
        || !['quality', 'tiff_compression', 'gps', 'target_size'].every(k => typeof (value.applicable_options as Record<string, unknown>)[k] === 'boolean')
        || !object(value.source_facts) || value.source_facts.schema !== 'lrt.export-source-facts.v1'
        || !object(value.effective_asset) || !object(value.options)) {
      throw new Error('Original 格式决策不完整，请重新预览');
    }
    if (value.bits === 16 && !['png', 'tif'].includes(String(value.codec))) throw new Error('Original 预览包含不支持的位深');
    if (!preview.entries.some(e => e.item_id === key)) throw new Error('Original 格式决策与导出文档不一致');
  }
  for (const entry of preview.entries) {
    if (entry.item_id.startsWith('layout::')) continue;
    const key = entry.item_id.endsWith('::clean') ? entry.item_id.slice(0, -7) : entry.item_id;
    if (!Object.hasOwn(plan.entries, key)) throw new Error('Original 预览缺少逐图格式决策');
  }
  return {schema: 'lrt.export-format-plan.v1', requested_format: 'original',
    entries: plan.entries as Record<string, OriginalFormatDecision>};
}

export function decisionForEntry(plan: OriginalFormatPlan | null, itemId: string): OriginalFormatDecision | undefined {
  if (!plan || itemId.startsWith('layout::')) return undefined;
  return plan.entries[itemId.endsWith('::clean') ? itemId.slice(0, -7) : itemId];
}
