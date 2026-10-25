// Local, user-owned background materials. Preview pixels never leave this module.
export const PAGE_SIZE = 48;
export const UNGROUPED = 'ungrouped';
export type MaterialSelection = Readonly<{ version: 1; library_id: string; material_id: string; catalog_revision: number; sha256: string }>;
export type MaterialGroup = { id: string; name: string };
export type Counts = { active: number; trash: number; total: number };
export type Material = { id: string; name: string; group_id: string; sha256: string; bytes: number; width: number; height: number;
  bits: 8 | 16; format: string; has_alpha: boolean; created_at: number; deleted_at: number | null };
export type MaterialSnapshot = { version: 1; library_id: string; revision: number; groups: MaterialGroup[]; order_ids: string[];
  counts: Counts; storage: { bytes: number; budget_bytes: number };
  limits: { max_active: number; max_records: number; max_groups: number; max_import: number; max_object_bytes: number; max_pixels: number }; warnings: string[] };
export type MaterialQuery = { group_id: string | null; text: string; trash: boolean;
  sort: 'manual' | 'name_asc' | 'name_desc' | 'newest' | 'oldest'; offset: number; limit: number };
export type MaterialPage = { version: 1; library_id: string; revision: number; query: MaterialQuery; total: number; items: Material[]; next_offset: number | null };
export type ImportOutcome = { index: number; name: string; status: string; material_id: string | null; message: string };
export type MaterialMutation = { version: 1; library_id: string; revision: number; changed: boolean; counts: Counts; outcomes?: ImportOutcome[] };
export type MaterialCommand =
  | { op: 'group_create'; payload: { name: string } }
  | { op: 'group_rename' | 'material_rename'; payload: { id: string; name: string } }
  | { op: 'group_delete'; payload: { id: string } }
  | { op: 'group_reorder' | 'material_reorder' | 'material_remove' | 'material_restore'; payload: { ids: string[] } }
  | { op: 'import_paths'; payload: { paths: string[]; group_id: string } }
  | { op: 'material_move'; payload: { ids: string[]; group_id: string } };
export class MaterialError extends Error {
  constructor(message: string, readonly code = 'invalid_reply', readonly outcome: 'not-applied' | 'unknown' = 'not-applied') {
    super(message); this.name = 'MaterialError';
  }
}
export const errorText = (value: unknown): string => value instanceof Error ? value.message : String(value);
export function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new MaterialError('背景素材回执不是有效对象。');
  return value as Record<string, unknown>;
}
function fields(value: Record<string, unknown>, expected: string[]): void {
  if (Object.keys(value).length !== expected.length || expected.some(key => !(key in value))) throw new MaterialError('背景素材回执字段不符合协议。');
}
export function integer(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new MaterialError('背景素材数值无效。');
  return value;
}
function positive(value: unknown): number { const n = integer(value); if (!n) throw new MaterialError('背景素材尺寸或限制无效。'); return n; }
function text(value: unknown, max = 4096): string {
  if (typeof value !== 'string' || value.length > max || value.includes('\0')) throw new MaterialError('背景素材文本无效。');
  return value;
}
function id(value: unknown): string { const s = text(value, 32); if (!/^[0-9a-f]{32}$/.test(s)) throw new MaterialError('背景素材身份无效。'); return s; }
function groupId(value: unknown): string { return value === UNGROUPED ? UNGROUPED : id(value); }
function hash(value: unknown): string { const s = text(value, 64); if (!/^[0-9a-f]{64}$/.test(s)) throw new MaterialError('背景素材校验值无效。'); return s; }
function boolean(value: unknown): boolean { if (typeof value !== 'boolean') throw new MaterialError('背景素材布尔标记无效。'); return value; }
function array(value: unknown, max: number): unknown[] { if (!Array.isArray(value) || value.length > max) throw new MaterialError('背景素材列表超过协议限制。'); return value; }
export function normalizedName(value: string): string {
  const name = value.trim();
  if (!name || Array.from(name).length > 120 || /[\u0000-\u001f\u007f-\u009f]/u.test(name) || /[\uD800-\uDFFF]/u.test(name)) {
    throw new MaterialError('名称须为 1–120 个字符，不能包含控制字符。', 'invalid_name');
  }
  return name;
}
function counts(value: unknown): Counts {
  const v = object(value); fields(v, ['active', 'trash', 'total']);
  const c = { active: integer(v.active), trash: integer(v.trash), total: integer(v.total) };
  if (c.active + c.trash !== c.total || c.active > 2000 || c.total > 20000) throw new MaterialError('背景素材目录计数不一致。');
  return c;
}
export function parseSelection(value: unknown): MaterialSelection {
  const v = object(value); fields(v, ['version', 'library_id', 'material_id', 'catalog_revision', 'sha256']);
  if (v.version !== 1) throw new MaterialError('背景素材选择协议不兼容。');
  return Object.freeze({ version: 1, library_id: id(v.library_id), material_id: id(v.material_id), catalog_revision: integer(v.catalog_revision), sha256: hash(v.sha256) });
}
export function parseSnapshot(value: unknown): MaterialSnapshot {
  const v = object(value);
  fields(v, ['version', 'library_id', 'revision', 'groups', 'order_ids', 'counts', 'storage', 'limits', 'warnings']);
  if (v.version !== 1) throw new MaterialError('背景素材目录协议不兼容。');
  const groups = array(v.groups, 200).map(raw => { const g = object(raw); fields(g, ['id', 'name']); return { id: groupId(g.id), name: normalizedName(text(g.name)) }; });
  if (!groups.some(g => g.id === UNGROUPED) || new Set(groups.map(g => g.id)).size !== groups.length) throw new MaterialError('背景素材分组身份不一致。');
  const order = array(v.order_ids, 2000).map(id), c = counts(v.counts), s = object(v.storage), l = object(v.limits);
  if (order.length !== c.active || new Set(order).size !== order.length) throw new MaterialError('背景素材顺序与计数不一致。');
  fields(s, ['bytes', 'budget_bytes']); fields(l, ['max_active', 'max_records', 'max_groups', 'max_import', 'max_object_bytes', 'max_pixels']);
  const limits = { max_active: positive(l.max_active), max_records: positive(l.max_records), max_groups: positive(l.max_groups),
    max_import: positive(l.max_import), max_object_bytes: positive(l.max_object_bytes), max_pixels: positive(l.max_pixels) };
  if (limits.max_active > 2000 || limits.max_records > 20000 || limits.max_groups > 200 || limits.max_import > 1000 || c.active > limits.max_active || c.total > limits.max_records) throw new MaterialError('背景素材容量策略不一致。');
  return { version: 1, library_id: id(v.library_id), revision: integer(v.revision), groups, order_ids: order, counts: c,
    storage: { bytes: integer(s.bytes), budget_bytes: positive(s.budget_bytes) }, limits, warnings: array(v.warnings, 200).map(w => text(w)) };
}
function parseMaterial(value: unknown): Material {
  const v = object(value); fields(v, ['id', 'name', 'group_id', 'sha256', 'bytes', 'width', 'height', 'bits', 'format', 'has_alpha', 'created_at', 'deleted_at']);
  if ((v.bits !== 8 && v.bits !== 16) || !['JPEG', 'PNG', 'TIFF', 'BMP'].includes(String(v.format).toUpperCase())) throw new MaterialError('背景素材精度或格式不兼容。');
  return { id: id(v.id), name: normalizedName(text(v.name)), group_id: groupId(v.group_id), sha256: hash(v.sha256), bytes: positive(v.bytes),
    width: positive(v.width), height: positive(v.height), bits: v.bits, format: text(v.format), has_alpha: boolean(v.has_alpha),
    created_at: integer(v.created_at), deleted_at: v.deleted_at === null ? null : integer(v.deleted_at) };
}
export function parsePage(value: unknown, query: MaterialQuery, head: MaterialSnapshot): MaterialPage {
  const v = object(value); fields(v, ['version', 'library_id', 'revision', 'query', 'total', 'items', 'next_offset']);
  const q = object(v.query); fields(q, ['group_id', 'text', 'trash', 'sort', 'offset', 'limit']);
  if (v.version !== 1 || v.library_id !== head.library_id || v.revision !== head.revision || Object.keys(query).some(key => q[key] !== query[key as keyof MaterialQuery])) throw new MaterialError('目录或分页条件已变化，请刷新。', 'stale_page');
  const items = array(v.items, PAGE_SIZE).map(parseMaterial), total = integer(v.total), next = v.next_offset === null ? null : integer(v.next_offset);
  const expectedSize = Math.min(query.limit, Math.max(0, total - query.offset));
  if (query.offset > total || items.length !== expectedSize || new Set(items.map(item => item.id)).size !== items.length ||
    next !== (query.offset + items.length < total ? query.offset + items.length : null)) throw new MaterialError('背景素材分页不完整，未隐藏剩余素材。');
  const groupIds = new Set(head.groups.map(g => g.id)), order = new Set(head.order_ids);
  for (const item of items) if (!groupIds.has(item.group_id) || (item.deleted_at !== null) !== query.trash ||
    (query.group_id !== null && query.group_id !== item.group_id) || (!query.trash && !order.has(item.id))) throw new MaterialError('背景素材分页身份与目录不一致。');
  if (total > (query.trash ? head.counts.trash : head.counts.active) || (!query.text && query.group_id === null && total !== (query.trash ? head.counts.trash : head.counts.active))) throw new MaterialError('背景素材分页总数不一致。');
  return { version: 1, library_id: head.library_id, revision: head.revision, query: { ...query }, total, items, next_offset: next };
}
export function parseMutation(value: unknown, head: MaterialSnapshot): MaterialMutation {
  const v = object(value); fields(v, ['version', 'library_id', 'revision', 'changed', 'counts', ...(v.outcomes === undefined ? [] : ['outcomes'])]);
  if (v.version !== 1 || v.library_id !== head.library_id || integer(v.revision) < head.revision) throw new MaterialError('背景素材写入回执与目录不一致。', 'invalid_reply', 'unknown');
  return { version: 1, library_id: head.library_id, revision: integer(v.revision), changed: boolean(v.changed), counts: counts(v.counts),
    ...(v.outcomes === undefined ? {} : { outcomes: array(v.outcomes, 1000).map(raw => { const o = object(raw);
      fields(o, ['index', 'name', 'status', 'material_id', 'message']);
      if (!['imported', 'duplicate', 'trashed_duplicate', 'error', 'cancelled'].includes(String(o.status))) throw new MaterialError('背景素材逐文件结果无效。');
      return { index: integer(o.index), name: text(o.name), status: text(o.status), material_id: o.material_id === null ? null : id(o.material_id), message: text(o.message) };
    }) }) };
}
export function parseThumbnail(value: unknown, materialId: string, revision: number): string {
  const v = object(value); fields(v, ['version', 'id', 'revision', 'thumbnail_sha256', 'data_url']);
  if (v.version !== 1 || v.id !== materialId || v.revision !== revision) throw new MaterialError('缩略图身份已过期，请刷新。', 'stale_thumbnail');
  hash(v.thumbnail_sha256); const data = text(v.data_url, Math.ceil(256 * 1024 / 3) * 4 + 32);
  if (!/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(data)) throw new MaterialError('背景素材缩略图无效。');
  return data;
}
export function reorderedIds(all: readonly string[], visible: readonly string[], from: string, to: string): string[] {
  if (from === to || !visible.includes(from) || !visible.includes(to)) return [...all];
  const next = [...visible]; next.splice(next.indexOf(from), 1); next.splice(visible.indexOf(to), 0, from);
  const selected = new Set(visible); let index = 0;
  return all.map(value => selected.has(value) ? next[index++]! : value);
}
export function formatBytes(value: number): string {
  return value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(1)} GiB` : value >= 1024 ** 2 ? `${(value / 1024 ** 2).toFixed(1)} MiB` : `${Math.ceil(value / 1024)} KiB`;
}
