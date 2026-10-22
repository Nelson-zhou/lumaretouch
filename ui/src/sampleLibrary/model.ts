/** Local, user-owned samples. Array order is authoritative; there are no seeded photos. */
export const SAMPLE_LIMIT = 2000;
export const IMPORT_LIMIT = 1000;
export const NAME_LIMIT = 120;
export const PAGE_SIZE = 48;
export const UNGROUPED_ID = 'ungrouped';
export type SampleKind = 'import' | 'render';
export interface SampleGroup { id: string; name: string }
export interface SampleSourceIdentity { sha256: string; width: number; height: number }
export interface SampleReference { source: SampleSourceIdentity; render_sha256: string; asset_id: string }
export interface LibrarySample {
  id: string;
  name: string;
  group_id: string | null;
  kind: SampleKind;
  original_sha256: string;
  bytes: number;
  width: number;
  height: number;
  format: string;
  precision: string;
  created_at: number;
  deleted_at: number | null;
  reference: SampleReference | null;
  reference_supported?: boolean;
  reference_reason?: string;
  notes?: string[];
}
export interface LibraryCapacity { active: number; limit: number; per_import: number }
export interface LibraryCounts { active: number; trash: number; total: number }
export interface LibraryStorage {
  bytes: number;
  library_bytes: number;
  shared_reference_bytes: number;
  free_disk_bytes: number;
  shared_free_disk_bytes: number;
  /** Configured admission policy, not a reserved or globally enforced quota. */
  budget_bytes: number;
}
export interface SampleLibrarySnapshot {
  version: 1;
  revision: number;
  groups: SampleGroup[];
  capacity: LibraryCapacity;
  storage: LibraryStorage;
  warnings: string[];
  counts: LibraryCounts;
  group_counts: Record<string, { active: number; trash: number }>;
  /** Complete stable active order, bounded by 2000 IDs, not full metadata. */
  order_ids: string[];
}
export interface SamplePageRequest { view: LibraryView; search: string; limit: number; cursor: string | null }
export interface SampleLibraryPage { revision: number; samples: LibrarySample[]; total: number; offset: number; limit: number; next_cursor: string | null }
export interface SampleOutcome {
  path?: string;
  name?: string;
  id?: string;
  index?: number;
  status: string;
  message?: string;
}
export interface LibraryMutationResult {
  revision: number;
  affected_ids: string[];
  capacity: LibraryCapacity;
  counts: LibraryCounts;
  outcomes?: SampleOutcome[];
}
export interface SelectedSampleReference extends SampleReference { sample_id: string }
export interface SampleSelectionResult {
  revision: number;
  sample_id: string;
  reference: SampleReference;
  notice?: string;
}
export type SampleLibraryCommand =
  | { op: 'group_create'; payload: { name: string } }
  | { op: 'group_rename'; payload: { id: string; name: string } }
  | { op: 'group_delete'; payload: { id: string } }
  | { op: 'group_reorder'; payload: { ids: string[] } }
  | { op: 'import_paths'; payload: { paths: string[]; group_id: string | null } }
  | { op: 'sample_rename'; payload: { id: string; name: string } }
  | { op: 'sample_move'; payload: { ids: string[]; group_id: string | null } }
  | { op: 'sample_remove'; payload: { ids: string[] } }
  | { op: 'sample_restore'; payload: { ids: string[] } }
  | { op: 'sample_reorder'; payload: { ids: string[] } };
export type LibraryView = 'all' | 'ungrouped' | 'trash' | { group: string };

export class SampleLibraryError extends Error {
  constructor(message: string, readonly code: string, readonly mutationState: 'not-applied' | 'unknown' = 'not-applied') {
    super(message);
    this.name = 'SampleLibraryError';
  }
}
export function normalizedName(value: string): string {
  const name = value.trim();
  if (!name || Array.from(name).length > NAME_LIMIT || /[\u0000-\u001f\u007f]/.test(name)) {
    throw new SampleLibraryError(`名称须为 1–${NAME_LIMIT} 个字符，不能包含控制字符。`, 'invalid_name');
  }
  return name;
}
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : typeof error === 'string' ? error : '操作未完成，请查看当前目录后重试。';
}
export function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GiB`;
}
/** Reorder only the visible subset, preserving all hidden positions and hidden samples. */
export function reorderedIds(all: readonly string[], visible: readonly string[], from: string, to: string): string[] {
  if (from === to || !visible.includes(from) || !visible.includes(to)) return [...all];
  const next = [...visible];
  const fromIndex = next.indexOf(from), toIndex = next.indexOf(to);
  next.splice(fromIndex, 1);
  next.splice(toIndex, 0, from);
  const visibleSet = new Set(visible);
  let index = 0;
  return all.map(id => visibleSet.has(id) ? next[index++]! : id);
}
export function outcomeLabel(status: string): string {
  const labels: Record<string, string> = {
    imported: '已导入', added: '已添加', captured: '已保存', restored: '已恢复', removed: '已移入回收站',
    duplicate: '重复，未新增', cancelled: '已取消', skipped: '已跳过', rejected: '未导入', failed: '失败', error: '失败',
    limit: '超出数量上限', unsupported: '不支持的格式', capacity: '容量不足',
  };
  return labels[status] ?? status;
}

function object(value: unknown, at: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new SampleLibraryError(`${at} 格式不正确。`, 'invalid_reply');
  return value as Record<string, unknown>;
}
function string(value: unknown, at: string): string {
  if (typeof value !== 'string' || !value.length) throw new SampleLibraryError(`${at} 缺少文本。`, 'invalid_reply');
  return value;
}
function integer(value: unknown, at: string, positive = false): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < (positive ? 1 : 0)) {
    throw new SampleLibraryError(`${at} 不是有效数值。`, 'invalid_reply');
  }
  return value;
}
function hash(value: unknown, at: string): string {
  const result = string(value, at);
  if (!/^[a-f0-9]{64}$/i.test(result)) throw new SampleLibraryError(`${at} 缺少稳定的内容校验值。`, 'invalid_reply');
  return result.toLowerCase();
}
export function parseReference(value: unknown): SampleReference {
  const v = object(value, '样片引用');
  const source = object(v.source, '引用来源');
  return { source: { sha256: hash(source.sha256, '来源校验值'), width: integer(source.width, '来源宽度', true), height: integer(source.height, '来源高度', true) },
    render_sha256: hash(v.render_sha256, '渲染校验值'), asset_id: hash(v.asset_id, '引用资源') };
}
function parseCapacity(value: unknown): LibraryCapacity {
  const v = object(value, '样片容量');
  const active = integer(v.active, '可用样片数'), limit = integer(v.limit, '样片上限', true), perImport = integer(v.per_import, '单次导入上限', true);
  if (active > limit || limit > SAMPLE_LIMIT || perImport > IMPORT_LIMIT) throw new SampleLibraryError('样片容量数值不一致。', 'invalid_reply');
  return { active, limit, per_import: perImport };
}
function parseCounts(value: unknown): LibraryCounts {
  const v = object(value, '目录计数');
  const active = integer(v.active, '可用计数'), trash = integer(v.trash, '回收站计数'), total = integer(v.total, '全部记录数');
  if (active + trash !== total) throw new SampleLibraryError('目录总数不一致。', 'invalid_reply');
  return { active, trash, total };
}
function parseStorage(value: unknown): LibraryStorage {
  const v = object(value, '本地存储');
  const bytes = integer(v.bytes, '策略计量合计'), libraryBytes = integer(v.library_bytes, '样片库自有文件占用');
  const sharedBytes = integer(v.shared_reference_bytes, '整个共享参考缓存占用');
  if (bytes !== libraryBytes + sharedBytes) throw new SampleLibraryError('自有文件与共享缓存计量合计不一致。', 'invalid_reply');
  // Usage may already exceed policy because shared-cache writers do not reserve.
  // Never hide that state or claim these two free-space figures are additive.
  return { bytes, library_bytes: libraryBytes, shared_reference_bytes: sharedBytes,
    free_disk_bytes: integer(v.free_disk_bytes, '样片库所在文件系统剩余空间'),
    shared_free_disk_bytes: integer(v.shared_free_disk_bytes, '参考缓存所在文件系统剩余空间'),
    budget_bytes: integer(v.budget_bytes, '本库当前入库策略上限') };
}
export function parseReceiptRevision(value: unknown): number { return integer(object(value, '操作回执').revision, '目录版本'); }
/** Header only. Full metadata is never fetched or accumulated as a catalog snapshot. */
export function parseSnapshot(value: unknown): SampleLibrarySnapshot {
  const v = object(value, '样片目录');
  if (v.version !== 1 || !Array.isArray(v.groups) || !Array.isArray(v.order_ids) || !Array.isArray(v.warnings) || v.samples !== undefined) {
    throw new SampleLibraryError('样片目录分页协议或版本不正确，请更新配套程序。', 'invalid_reply');
  }
  const groups = v.groups.map(raw => {
    const group = object(raw, '分组');
    return { id: string(group.id, '分组 ID'), name: string(group.name, '分组名称') };
  });
  const groupIds = new Set(groups.map(group => group.id));
  if (!groupIds.has(UNGROUPED_ID) || groupIds.size !== groups.length) throw new SampleLibraryError('目录分组无效。', 'invalid_reply');
  const capacity = parseCapacity(v.capacity), counts = parseCounts(v.counts), storage = parseStorage(v.storage);
  const orderIds = v.order_ids.map(id => string(id, '活动样片顺序'));
  if (orderIds.length !== capacity.active || new Set(orderIds).size !== orderIds.length || counts.active !== capacity.active) {
    throw new SampleLibraryError('样片顺序、容量与真实计数不一致。', 'invalid_reply');
  }
  const rawGroupCounts = object(v.group_counts, '分组计数');
  const groupCounts: Record<string, { active: number; trash: number }> = {};
  let activeSum = 0, trashSum = 0;
  for (const group of groups) {
    const count = object(rawGroupCounts[group.id], '分组计数');
    const active = integer(count.active, '分组可用计数'), trash = integer(count.trash, '分组回收站计数');
    groupCounts[group.id] = { active, trash }; activeSum += active; trashSum += trash;
  }
  if (activeSum !== counts.active || trashSum !== counts.trash || Object.keys(rawGroupCounts).some(id => !groupIds.has(id))) {
    throw new SampleLibraryError('分组计数与目录总数不一致。', 'invalid_reply');
  }
  return { version: 1, revision: integer(v.revision, '目录版本'), groups, capacity, counts, group_counts: groupCounts,
    order_ids: orderIds, storage,
    warnings: v.warnings.map(warning => string(warning, '目录提示')) };
}
function parseSample(raw: unknown): LibrarySample {
  const sample = object(raw, '样片');
  if (sample.kind !== 'import' && sample.kind !== 'render') throw new SampleLibraryError('样片来源无效。', 'invalid_reply');
  return {
    id: string(sample.id, '样片 ID'), name: string(sample.name, '样片名称'),
    group_id: sample.group_id === null ? null : string(sample.group_id, '样片分组'),
    kind: sample.kind, original_sha256: hash(sample.original_sha256, '原图校验值'), bytes: integer(sample.bytes, '样片字节数'),
    width: integer(sample.width, '样片宽度', true), height: integer(sample.height, '样片高度', true), format: string(sample.format, '样片格式'),
    precision: string(sample.precision, '样片精度'), created_at: integer(sample.created_at, '创建时间'),
    deleted_at: sample.deleted_at === null ? null : integer(sample.deleted_at, '移除时间'),
    reference: sample.reference === null ? null : parseReference(sample.reference),
    ...(typeof sample.reference_supported === 'boolean' ? { reference_supported: sample.reference_supported } : {}),
    ...(typeof sample.reference_reason === 'string' ? { reference_reason: sample.reference_reason } : {}),
    ...(Array.isArray(sample.notes) ? { notes: sample.notes.map(note => string(note, '样片说明')) } : {}),
  };
}
export function parsePage(value: unknown, request: SamplePageRequest, expectedRevision: number): SampleLibraryPage {
  const v = object(value, '样片分页');
  if (v.revision !== expectedRevision) throw new SampleLibraryError('目录已变化，当前分页不可继续，请刷新目录。', 'stale_page');
  if (!Array.isArray(v.samples) || v.samples.length > request.limit || request.limit > PAGE_SIZE) {
    throw new SampleLibraryError('返回的样片元数据超过本页预算，未截断显示。', 'invalid_reply');
  }
  const samples = v.samples.map(parseSample), total = integer(v.total, '筛选总数');
  const offset = integer(v.offset, '分页起点'), limit = integer(v.limit, '分页容量', true);
  if (limit !== request.limit || offset + samples.length > total) throw new SampleLibraryError('分页范围与请求不一致。', 'invalid_reply');
  if (new Set(samples.map(sample => sample.id)).size !== samples.length || total < samples.length) throw new SampleLibraryError('分页数量或身份不正确。', 'invalid_reply');
  for (const sample of samples) {
    if ((sample.deleted_at !== null) !== (request.view === 'trash') ||
      (request.view === 'ungrouped' && sample.group_id !== null && sample.group_id !== UNGROUPED_ID) ||
      (typeof request.view === 'object' && sample.group_id !== request.view.group)) {
      throw new SampleLibraryError('分页内容与请求的分组或回收站状态不同。', 'invalid_reply');
    }
  }
  const nextCursor = v.next_cursor === null ? null : string(v.next_cursor, '后续分页游标');
  if (samples.length !== Math.min(limit, total - offset) || (nextCursor !== null) !== (offset + samples.length < total)) {
    throw new SampleLibraryError('分页被截断或结束游标不正确，未隐藏剩余样片。', 'invalid_reply');
  }
  if (nextCursor !== null && (nextCursor === request.cursor || samples.length === 0)) throw new SampleLibraryError('分页游标没有前进。', 'invalid_reply');
  return { revision: expectedRevision, samples, total, offset, limit, next_cursor: nextCursor };
}
export function parseMutation(value: unknown): LibraryMutationResult {
  const v = object(value, '操作回执');
  if (v.snapshot !== undefined || !Array.isArray(v.affected_ids)) throw new SampleLibraryError('操作回执未使用有界分页协议。', 'invalid_reply');
  const revision = parseReceiptRevision(v), capacity = parseCapacity(v.capacity), counts = parseCounts(v.counts);
  if (capacity.active !== counts.active) throw new SampleLibraryError('操作回执计数不一致。', 'invalid_reply');
  const affectedIds = v.affected_ids.map(id => string(id, '受影响样片身份'));
  if (new Set(affectedIds).size !== affectedIds.length) throw new SampleLibraryError('回执存在重复身份。', 'invalid_reply');
  if (v.outcomes !== undefined && (!Array.isArray(v.outcomes) || v.outcomes.length > IMPORT_LIMIT)) throw new SampleLibraryError('逐文件回执格式或数量不正确。', 'invalid_reply');
  const outcomes = (v.outcomes as unknown[] | undefined)?.map(raw => {
    const row = object(raw, '文件回执');
    return { status: string(row.status, '文件处理结果'),
      ...(typeof row.path === 'string' ? { path: row.path } : {}),
      ...(typeof row.id === 'string' ? { id: row.id } : typeof row.sample_id === 'string' ? { id: row.sample_id } : {}),
      ...(typeof row.name === 'string' ? { name: row.name } : {}),
      ...(typeof row.index === 'number' && Number.isSafeInteger(row.index) ? { index: row.index } : {}),
      ...(typeof row.message === 'string' ? { message: row.message } : {}),
    };
  });
  return { revision, affected_ids: affectedIds, capacity, counts, outcomes };
}
