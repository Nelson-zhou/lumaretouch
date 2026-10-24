// SPDX-License-Identifier: GPL-3.0-or-later
/** Recovery safety classification only. Never stores edit state or authorizes a command. */
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const token = (v: unknown): v is string => typeof v === 'string' && !!v.trim() && !/[\u0000-\u001f\u007f]/.test(v)
  && new TextEncoder().encode(v).length <= 128;
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const count = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 2 && v <= 16;
type Classification = {memberCount: number | null; reviewSha256: string | null};
let workspace: string | null = null, lastObservation = 0;
const marked = new Map<string, Classification>();
const key = (epoch: string, id: string) => JSON.stringify([epoch, id]);
/** Reopened ledger summary requires query-only unknown undo/redo and atomic success.
 * A malformed marker can only tighten this fence, never grant validity or weaken recovery. */
export function observeEyeBagCohortHistory(sync: unknown, observation?: number): void {
  if (observation !== undefined) {
    if (!Number.isSafeInteger(observation) || observation <= lastObservation) return;
    lastObservation = observation;
  }
  if (!object(sync) || !token(sync.workspace_generation)) return;
  if (workspace !== sync.workspace_generation) {workspace = sync.workspace_generation; marked.clear();}
  if (!Array.isArray(sync.batches)) return;
  for (const entry of sync.batches) {
    if (!object(entry) || !token(entry.batch_id) || !Object.hasOwn(entry, 'eye_bag_cohort_review')) continue;
    const marker = entry.eye_bag_cohort_review;
    let next: Classification = {memberCount: null, reviewSha256: null};
    if (object(marker) && Object.keys(marker).sort().join('|') === 'member_count|review_sha256|version'
      && marker.version === 1 && hash(marker.review_sha256) && count(marker.member_count)
      && entry.targets === marker.member_count && JSON.stringify(entry.module_scope) === JSON.stringify(['lnx.people_graph.v1']))
      next = {memberCount: marker.member_count, reviewSha256: marker.review_sha256};
    const id = key(workspace!, entry.batch_id), previous = marked.get(id);
    // A valid local receipt has no ledger digest yet; a matching status may add it.
    // Conflicting or malformed identities cannot erase an existing recovery fence.
    marked.set(id, previous && (previous.memberCount !== next.memberCount
      || previous.reviewSha256 !== null && previous.reviewSha256 !== next.reviewSha256)
      ? {memberCount: null, reviewSha256: null} : next);
  }
}
/** A verified local commit protects other batch controllers before the next status poll. */
export function registerEyeBagCohortReceipt(epoch: string, batchId: string, memberCount: number): boolean {
  if (!token(epoch) || !token(batchId) || !count(memberCount) || workspace !== null && workspace !== epoch) return false;
  if (workspace === null) workspace = epoch;
  const id = key(epoch, batchId), previous = marked.get(id);
  if (previous && previous.memberCount !== memberCount) return false;
  marked.set(id, previous ?? {memberCount, reviewSha256: null}); return true;
}
export function eyeBagCohortHistoryClass(batchId: string | undefined): Classification | undefined {
  return workspace && batchId ? marked.get(key(workspace, batchId)) : undefined;
}
export const isEyeBagCohortHistory = (batchId: string | undefined) => eyeBagCohortHistoryClass(batchId) !== undefined;
