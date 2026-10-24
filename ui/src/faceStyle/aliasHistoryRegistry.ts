import {object, validFaceStyleAliasCommit, type FaceStyleAliasCommit} from './model';

/** Safety classification only: no undo state, document snapshots, or permission to send a command. */
type Classification = {memberCount: number | null; reviewSha256: string | null};
let workspace: string | null = null;
let lastObservation = 0;
const classifications = new Map<string, Classification>();
const token = (value: unknown): value is string => typeof value === 'string' && !!value.trim()
  && !value.includes('\0') && new TextEncoder().encode(value).length <= 128;
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const key = (epoch: string, id: string) => JSON.stringify([epoch, id]);

/** Consume only the existing engine ledger's read-only status, including reopened history. */
export function observeFaceStyleAliasHistory(sync: unknown, observation?: number): void {
  if (observation !== undefined) {
    if (!Number.isSafeInteger(observation) || observation <= lastObservation) return;
    lastObservation = observation;
  }
  if (!object(sync) || !token(sync.workspace_generation)) return;
  if (workspace !== sync.workspace_generation) {workspace = sync.workspace_generation; classifications.clear();}
  if (!Array.isArray(sync.batches)) return;
  for (const entry of sync.batches) {
    if (!object(entry) || !token(entry.batch_id) || !Object.hasOwn(entry, 'face_style_alias_review')) continue;
    const marker = entry.face_style_alias_review;
    let classification: Classification = {memberCount: null, reviewSha256: null};
    if (object(marker) && Object.keys(marker).sort().join('|') === 'member_count|review_sha256|version'
      && marker.version === 1 && hash(marker.review_sha256) && typeof marker.member_count === 'number'
      && Number.isSafeInteger(marker.member_count) && marker.member_count >= 2 && marker.member_count <= 16
      && !Object.hasOwn(entry, 'eye_bag_recovery_alias_review')
      && entry.targets === marker.member_count && JSON.stringify(entry.module_scope) === JSON.stringify(['lnx.people_graph.v1']))
      classification = {memberCount: marker.member_count, reviewSha256: marker.review_sha256};
    // A malformed marker can only tighten recovery, never silently downgrade to generic history.
    const id = key(workspace!, entry.batch_id), existing = classifications.get(id);
    // Within an epoch, older status pages cannot erase a receipt-backed safety fence.
    // Conflicting identities tighten recovery rather than replacing the known proof.
    classifications.set(id, existing && (existing.memberCount !== classification.memberCount
      || existing.reviewSha256 !== classification.reviewSha256) ? {memberCount: null, reviewSha256: null} : classification);
  }
}

export function registerFaceStyleAliasReceipt(commit: FaceStyleAliasCommit): boolean {
  if (!validFaceStyleAliasCommit(commit) || workspace !== null && workspace !== commit.documentEpoch) return false;
  if (workspace === null) workspace = commit.documentEpoch;
  const id = key(workspace, commit.batchId), existing = classifications.get(id);
  if (existing && (existing.memberCount !== commit.review.members.length || existing.reviewSha256 !== commit.review.review_sha256)) return false;
  classifications.set(id, {memberCount: commit.review.members.length, reviewSha256: commit.review.review_sha256});
  return true;
}

export function faceStyleAliasHistoryClass(batchId: string | undefined): Classification | undefined {
  return workspace && batchId ? classifications.get(key(workspace, batchId)) : undefined;
}
