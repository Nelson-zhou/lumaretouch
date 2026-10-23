import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {sameOperationProject, type PendingVirtualCopy, type VirtualCopyEnvelope} from './model';

export interface ReceiptStatus { phase: 'pending' | 'done' | 'unknown'; result: VirtualCopyEnvelope | null }
const retained = new Map<string, PendingVirtualCopy>();
const STORAGE_KEY = 'lumaretouch.virtual-copy.pending.v2';
const LEGACY_STORAGE_KEY = 'lumaretouch.virtual-copy.pending.v1';

/** Saved-project uncertainty survives workspace replacement and app restart.
 * Store only operation/project/document IDs, never paths or image data. */
function loadRetained(): void {
  if (typeof window === 'undefined') return;
  let raw: string | null = null;
  try { raw = window.localStorage.getItem(STORAGE_KEY); } catch { /* Try per-tab fallback. */ }
  if (raw === null) try { raw = window.sessionStorage.getItem(STORAGE_KEY) ?? window.sessionStorage.getItem(LEGACY_STORAGE_KEY); } catch { /* In-memory fallback. */ }
  try {
    const value: unknown = JSON.parse(raw || '[]');
    if (!Array.isArray(value)) return;
    for (const item of value) {
      if (item && typeof item.workspace === 'string' && item.workspace && typeof item.request_id === 'string' && item.request_id
        && (item.project_id === undefined || item.project_id === null || (typeof item.project_id === 'string' && item.project_id))
        && ['create', 'trash', 'restore'].includes(item.action) && Array.isArray(item.document_ids)
        && item.document_ids.every((id: unknown) => typeof id === 'string')) {
        retained.set(item.request_id, {...item, project_id: item.project_id ?? null});
      }
    }
    if (raw !== null) persist();
  } catch { /* Storage unavailable: the live module still retains original request IDs. */ }
}
loadRetained();
function persist(): void {
  const value = JSON.stringify([...retained.values()]);
  try { window.localStorage.setItem(STORAGE_KEY, value); } catch { /* Session fallback. */ }
  try {
    window.sessionStorage.setItem(STORAGE_KEY, value);
    window.sessionStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch { /* In-memory fallback. */ }
}
export function pendingFor(workspace: string, projectId: string | null = null): PendingVirtualCopy | null {
  const candidates = [...retained.values()];
  const value = candidates.find(item => item.workspace === workspace && sameOperationProject(item, {workspace, project_id: projectId}))
    ?? candidates.find(item => sameOperationProject(item, {workspace, project_id: projectId}));
  if (!value) return null;
  // First save in the same still-live workspace supplies stable identity. Never
  // guess project identity for an orphaned prior workspace or from a file path.
  if (value.project_id === null && value.workspace === workspace && projectId !== null) {
    const promoted = {...value, project_id: projectId};
    retained.set(value.request_id, promoted); persist(); return promoted;
  }
  return value;
}
export function unboundPendingFor(workspace: string): PendingVirtualCopy[] {
  return [...retained.values()].filter(item => item.project_id === null && item.workspace !== workspace);
}
export function retainPending(value: PendingVirtualCopy): void {
  const prior = retained.get(value.request_id);
  retained.set(value.request_id, prior?.project_id && value.project_id === null ? {...value, project_id: prior.project_id} : value);
  persist();
}
export function clearPending(workspace: string, requestId: string): void {
  if (retained.get(requestId)?.workspace === workspace) { retained.delete(requestId); persist(); }
}

export async function request(payload: Record<string, unknown>): Promise<unknown> {
  if (['create', 'trash', 'restore'].includes(String(payload.action))) {
    notifyInspectionEditIntent();
  }
  return invoke('virtual_copy_request', {request: {cmd: 'virtual_copy', ...payload}});
}
export async function receipt(requestId: string): Promise<ReceiptStatus> {
  const result = await invoke<ReceiptStatus>('virtual_copy_status', {requestId});
  if (!result || !['pending', 'done', 'unknown'].includes(result.phase)) throw new Error('虚拟副本回执格式无效');
  if (result.result && (result.result.request_id !== requestId || result.result.event !== 'virtual_copy_result'
    || typeof result.result.success !== 'boolean')) throw new Error('虚拟副本回执身份不匹配');
  if (result.phase === 'done' && !result.result) throw new Error('虚拟副本完成回执缺失');
  return result;
}

/** Timed-out calls are not cancelled or replayed. Their original receipt remains recoverable. */
export function bounded<T>(promise: Promise<T>, milliseconds: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('等待回执超时；未重发操作')), milliseconds);
    promise.then(value => { clearTimeout(timer); resolve(value); }, error => { clearTimeout(timer); reject(error); });
  });
}
