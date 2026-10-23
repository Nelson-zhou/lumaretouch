/** Document identity, not a shared source path, is the unit of selection. */
export type VirtualCopyAction = 'create' | 'trash' | 'restore';
export interface VirtualCopyRow {
  document_id: string;
  source_asset_id: string;
  root_document_id: string;
  copy_number: number;
  path: string;
  trashed: boolean;
  revision: number;
}
export interface VirtualCopyState { workspace: string; project_id: string | null; rows: VirtualCopyRow[] }
export interface VirtualCopyOutcome {
  status: 'succeeded' | 'failed' | 'pending' | 'unknown';
  operation_id: string;
  state?: VirtualCopyState;
  changed_document_ids?: string[];
  error?: string;
}
export interface VirtualCopyEnvelope {
  event: 'virtual_copy_result'; request_id: string; success: boolean;
  result: VirtualCopyState | VirtualCopyOutcome | null; error?: string | null;
}
export interface PendingVirtualCopy {
  request_id: string; workspace: string; project_id: string | null; action: VirtualCopyAction; document_ids: string[];
}

/** A non-null project identity survives reopening; a workspace never names another project. */
export function sameOperationProject(operation: PendingVirtualCopy, state: Pick<VirtualCopyState, 'workspace' | 'project_id'>): boolean {
  if (operation.project_id !== null && state.project_id !== null && operation.project_id !== state.project_id) return false;
  return operation.workspace === state.workspace
    || (operation.project_id !== null && operation.project_id === state.project_id);
}

export function isState(value: unknown): value is VirtualCopyState {
  if (!value || typeof value !== 'object') return false;
  const state = value as Partial<VirtualCopyState>;
  if (typeof state.workspace !== 'string' || !state.workspace || !Array.isArray(state.rows)
    || !(state.project_id === null || (typeof state.project_id === 'string' && !!state.project_id))) return false;
  const ids = new Set<string>();
  return state.rows.every(row => {
    if (!row || typeof row.document_id !== 'string' || !row.document_id || ids.has(row.document_id)
      || typeof row.source_asset_id !== 'string' || !row.source_asset_id
      || typeof row.root_document_id !== 'string' || !row.root_document_id
      || typeof row.path !== 'string' || typeof row.trashed !== 'boolean'
      || !Number.isSafeInteger(row.copy_number) || row.copy_number < 0
      || !Number.isSafeInteger(row.revision) || row.revision < 0) return false;
    ids.add(row.document_id); return true;
  });
}

export function isOutcome(value: unknown): value is VirtualCopyOutcome {
  if (!value || typeof value !== 'object') return false;
  const outcome = value as Partial<VirtualCopyOutcome>;
  return typeof outcome.operation_id === 'string' && !!outcome.operation_id
    && ['succeeded', 'failed', 'pending', 'unknown'].includes(outcome.status ?? '')
    && (outcome.state === undefined || isState(outcome.state));
}

/** Include unchanged selected rows in the revision fence as well as the cascade. */
export function affectedRows(state: VirtualCopyState, selected: readonly string[], action: VirtualCopyAction): VirtualCopyRow[] {
  const selectedIds = new Set(selected);
  const picked = state.rows.filter(row => selectedIds.has(row.document_id));
  const ids = new Set(picked.map(row => row.document_id));
  if (action === 'trash') {
    const roots = new Set(picked.filter(row => row.copy_number === 0).map(row => row.root_document_id));
    for (const row of state.rows) if (roots.has(row.root_document_id)) ids.add(row.document_id);
  } else if (action === 'restore') {
    for (const row of picked) if (row.copy_number > 0) ids.add(row.root_document_id);
  }
  return state.rows.filter(row => ids.has(row.document_id));
}

export function changedRows(rows: readonly VirtualCopyRow[], action: VirtualCopyAction): VirtualCopyRow[] {
  return rows.filter(row => action === 'create' || (action === 'trash' ? !row.trashed : row.trashed));
}

export function rowLabel(row: VirtualCopyRow): string {
  const name = row.path.split(/[\\/]/).pop() || row.path;
  return `${name} · ${row.copy_number === 0 ? '原件' : `虚拟副本 ${row.copy_number}`}`;
}
