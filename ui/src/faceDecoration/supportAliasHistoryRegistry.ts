// SPDX-License-Identifier: GPL-3.0-or-later
/** Separate support-bank history classification and unresolved-write fence. Never stores editable support. */
export type SupportAliasMarker = {version: 1; review_sha256: string; member_count: number};
type Classification = {memberCount: number | null; marker: SupportAliasMarker | null};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const token = (v: unknown): v is string => typeof v === 'string' && !!v.trim() && !/[\u0000-\u001f\u007f]/.test(v) && new TextEncoder().encode(v).length <= 128;
export function validSupportAliasMarker(v: unknown): v is SupportAliasMarker {
  return object(v) && Object.keys(v).sort().join('|') === 'member_count|review_sha256|version' && v.version === 1
    && typeof v.review_sha256 === 'string' && /^[a-f0-9]{64}$/.test(v.review_sha256)
    && typeof v.member_count === 'number' && Number.isSafeInteger(v.member_count) && v.member_count >= 2 && v.member_count <= 16;
}
export const sameSupportAliasMarker = (v: unknown, expected: SupportAliasMarker): v is SupportAliasMarker => validSupportAliasMarker(v)
  && v.review_sha256 === expected.review_sha256 && v.member_count === expected.member_count;
let workspace: string | null = null, lastObservation = 0;
const marked = new Map<string, Classification>(), key = (epoch: string, id: string) => JSON.stringify([epoch, id]);
function retain(epoch: string, id: string, next: Classification) {
  const k = key(epoch, id), prior = marked.get(k);
  marked.set(k, prior && (prior.memberCount !== next.memberCount || !prior.marker || !next.marker || !sameSupportAliasMarker(next.marker, prior.marker))
    ? {memberCount: null, marker: null} : next);
}
export type SupportAliasWorkspaceReplacement = {previous: string; current: string; retiredWrites: {requestId: string; epoch: string}[]};
const writes = new Map<string, string | null>(), listeners = new Set<() => void>(), workspaceListeners = new Set<(value: SupportAliasWorkspaceReplacement) => void>();
export function observeSupportAliasHistory(sync: unknown, observation?: number): void {
  if (observation !== undefined) {if (!Number.isSafeInteger(observation) || observation <= lastObservation) return; lastObservation = observation;}
  if (!object(sync) || !token(sync.workspace_generation) || !Array.isArray(sync.batches)) return;
  if (workspace !== sync.workspace_generation) {
    const previous = workspace; workspace = sync.workspace_generation; marked.clear();
    if (previous !== null) {
      const retiredWrites: {requestId: string; epoch: string}[] = [];
      for (const [requestId, epoch] of writes) if (epoch !== null && epoch !== workspace) {writes.delete(requestId); retiredWrites.push({requestId, epoch});}
      if (retiredWrites.length) for (const listener of listeners) listener();
      for (const listener of workspaceListeners) listener({previous, current: workspace, retiredWrites});
    }
  }
  for (const row of sync.batches) {
    if (!object(row) || !token(row.batch_id) || !Object.hasOwn(row, 'face_decoration_support_alias_review')) continue;
    const marker = row.face_decoration_support_alias_review;
    const valid = validSupportAliasMarker(marker) && row.targets === marker.member_count && JSON.stringify(row.module_scope) === JSON.stringify(['lnx.people_graph.v1'])
      && !['face_decoration_alias_review', 'face_decoration_cohort_review', 'face_decoration_batch_review', 'face_style_alias_review', 'eye_bag_alias_review',
        'eye_bag_batch_review', 'eye_bag_cohort_review', 'eye_bag_preset_alias_review', 'eye_bag_recovery_alias_review'].some(field => Object.hasOwn(row, field));
    retain(workspace, row.batch_id, valid ? {memberCount: marker.member_count, marker: structuredClone(marker)} : {memberCount: null, marker: null});
  }
}
export function registerSupportAliasReceipt(epoch: string, batchId: string, marker: SupportAliasMarker): boolean {
  if (!token(epoch) || !token(batchId) || !validSupportAliasMarker(marker) || workspace !== null && workspace !== epoch) return false;
  if (workspace === null) workspace = epoch;
  retain(epoch, batchId, {memberCount: marker.member_count, marker: structuredClone(marker)});
  return marked.get(key(epoch, batchId))?.marker !== null;
}
export const supportAliasHistoryClass = (batchId: string | undefined): Classification | undefined => workspace && batchId ? marked.get(key(workspace, batchId)) : undefined;
export const supportAliasWorkspace = () => workspace;
export const subscribeSupportAliasWorkspace = (listener: (value: SupportAliasWorkspaceReplacement) => void) => {workspaceListeners.add(listener); return () => {workspaceListeners.delete(listener);};};
export function setSupportAliasWritePending(requestId: string, pending: boolean, epoch?: string): void {
  const before = writes.size;
  if (pending) writes.set(requestId, token(epoch) ? epoch : null); else writes.delete(requestId);
  if (before !== writes.size) for (const listener of listeners) listener();
}
export const supportAliasWritePending = () => writes.size > 0;
export const subscribeSupportAliasWrites = (listener: () => void) => {listeners.add(listener); return () => {listeners.delete(listener);};};
