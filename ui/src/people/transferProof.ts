import type {FaceRef, ParameterValue} from './model';

export type DocumentFence = {document_id: string; epoch: string; revision: number};
export type EffectiveSourceProof = {
  asset_sha256: string; original_sha256: string;
  creative_source: null | {sha256: string; width: number; height: number};
};
/** A document and its own graph, never an identity inferred from source pixels. */
export type PeopleEndpointProof = {
  document: DocumentFence; people_scope: string; state_revision: number; association_revision: number;
  graph_sha256: string; source_proof: EffectiveSourceProof;
};
export type ConfirmedPeopleProof = {
  document_id: string; document_epoch: string; document_revision: number;
  state_revision: number; association_revision: number; person_id: string;
};
export type PeopleTransferProof = ConfirmedPeopleProof | PeopleEndpointProof;
type SelectedParameters = {source_ref: FaceRef; selection: Record<string, string[]>};
export type ExplicitPeopleRequest = SelectedParameters & {
  target_policy: 'explicit_face_map'; source: PeopleEndpointProof;
  targets: {target: PeopleEndpointProof; target_refs: FaceRef[]}[];
};
export type PeopleTransferRequest = SelectedParameters & {target_policy: 'confirmed_person_only'} | ExplicitPeopleRequest;
type ReviewBase = {
  version: 1; source_document: DocumentFence; target_document: DocumentFence;
  source_ref: FaceRef; target_refs: FaceRef[];
  parameters: {operation_id: string; parameter_path: string; value: ParameterValue}[];
  source_state_revision: number; target_state_revision: number;
  source_association_revision: number; target_association_revision: number;
  transfer_policy: 'selected_parameter_keys_replace'; excluded: string[];
};
export type PeopleTransferReview = ReviewBase & ({
  confirmed_person_id: string; target_policy: 'confirmed_person_only'; confirmation_revisions: [string, number][];
  source_owner: PeopleEndpointProof; target_owner: PeopleEndpointProof;
} | {target_policy: 'explicit_face_map'; source_owner: PeopleEndpointProof; target_owner: PeopleEndpointProof});

export const safeRevision = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
export const digest = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export const documentId = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{32}$/.test(v);
const token = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 128;
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
export function validFaceRef(v: unknown): v is FaceRef {
  return object(v) && keys(v, ['asset_sha256', 'face_instance_id', 'analysis_revision'])
    && digest(v.asset_sha256) && token(v.face_instance_id) && safeRevision(v.analysis_revision);
}
export function sameFace(a: FaceRef, b: FaceRef) {
  return a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
}
export function validDocumentFence(v: unknown): v is DocumentFence {
  return object(v) && keys(v, ['document_id', 'epoch', 'revision'])
    && documentId(v.document_id) && token(v.epoch) && safeRevision(v.revision);
}
export function sameDocument(a: DocumentFence, b: DocumentFence) {
  return a.document_id === b.document_id && a.epoch === b.epoch && a.revision === b.revision;
}
export function validEndpoint(v: unknown): v is PeopleEndpointProof {
  if (!object(v) || !keys(v, ['document', 'people_scope', 'state_revision', 'association_revision', 'graph_sha256', 'source_proof'])
    || !validDocumentFence(v.document) || (v.people_scope !== 'project' && v.people_scope !== v.document.document_id)
    || !safeRevision(v.state_revision) || !safeRevision(v.association_revision) || !digest(v.graph_sha256)) return false;
  const p = v.source_proof;
  if (!object(p) || !keys(p, ['asset_sha256', 'original_sha256', 'creative_source'])
    || !digest(p.asset_sha256) || !digest(p.original_sha256)) return false;
  const c = p.creative_source;
  return c === null ? p.asset_sha256 === p.original_sha256 : object(c) && keys(c, ['sha256', 'width', 'height'])
    && c.sha256 === p.asset_sha256 && safeRevision(c.width) && c.width > 0 && safeRevision(c.height) && c.height > 0;
}
/** Explicit fields, not JSON property order, define an endpoint's identity. */
export function sameEndpoint(a: PeopleEndpointProof, b: PeopleEndpointProof): boolean {
  const x = a.source_proof, y = b.source_proof;
  return sameDocument(a.document, b.document) && a.people_scope === b.people_scope && a.state_revision === b.state_revision
    && a.association_revision === b.association_revision && a.graph_sha256 === b.graph_sha256
    && x.asset_sha256 === y.asset_sha256 && x.original_sha256 === y.original_sha256
    && (x.creative_source === null ? y.creative_source === null : y.creative_source !== null
      && x.creative_source.sha256 === y.creative_source.sha256 && x.creative_source.width === y.creative_source.width
      && x.creative_source.height === y.creative_source.height);
}
export function peopleProofDocument(proof: PeopleTransferProof): DocumentFence {
  return 'document' in proof ? proof.document : {document_id: proof.document_id, epoch: proof.document_epoch, revision: proof.document_revision};
}
function uniqueRefs(refs: unknown): refs is FaceRef[] {
  return Array.isArray(refs) && refs.length > 0 && refs.every(validFaceRef)
    && new Set(refs.map(ref => ref.face_instance_id)).size === refs.length;
}
function sameRefs(a: FaceRef[], b: FaceRef[]) {
  return a.length === b.length && a.every(ref => b.some(other => sameFace(ref, other)));
}
function validSelection(v: unknown): v is Record<string, string[]> {
  return object(v) && Object.keys(v).length > 0 && Object.entries(v).every(([op, paths]) => token(op)
    && Array.isArray(paths) && paths.length > 0 && paths.every(path => typeof path === 'string' && path.startsWith('/') && path.length <= 512)
    && new Set(paths).size === paths.length);
}
export function samePeopleRequest(value: unknown, expected: PeopleTransferRequest): boolean {
  if (!object(value) || !validFaceRef(value.source_ref) || !sameFace(value.source_ref, expected.source_ref)
    || value.target_policy !== expected.target_policy || !validSelection(value.selection) || !validSelection(expected.selection)) return false;
  const selection = value.selection, ops = Object.keys(expected.selection).sort();
  if (JSON.stringify(Object.keys(selection).sort()) !== JSON.stringify(ops)
    || !ops.every(op => JSON.stringify([...selection[op]].sort()) === JSON.stringify([...expected.selection[op]].sort()))) return false;
  if (expected.target_policy === 'confirmed_person_only') return keys(value, ['source_ref', 'selection', 'target_policy']);
  if (!keys(value, ['source_ref', 'selection', 'target_policy', 'source', 'targets'])
    || !validEndpoint(value.source) || !validEndpoint(expected.source) || !sameEndpoint(value.source, expected.source)
    || value.source.source_proof.asset_sha256 !== value.source_ref.asset_sha256
    || !Array.isArray(value.targets) || !value.targets.length || value.targets.length > 16 || value.targets.length !== expected.targets.length) return false;
  const source = value.source, seen = new Set<string>();
  for (const item of value.targets) {
    if (!object(item) || !keys(item, ['target', 'target_refs']) || !validEndpoint(item.target) || !uniqueRefs(item.target_refs)
      || item.target_refs.length > 128) return false;
    const target = item.target;
    if (target.document.document_id === source.document.document_id || target.document.epoch !== source.document.epoch || seen.has(target.document.document_id)
      || item.target_refs.some(ref => ref.asset_sha256 !== target.source_proof.asset_sha256)) return false;
    const requested = expected.targets.find(row => row.target.document.document_id === target.document.document_id);
    if (!requested || !validEndpoint(requested.target) || !uniqueRefs(requested.target_refs)
      || !sameEndpoint(target, requested.target) || !sameRefs(item.target_refs, requested.target_refs)) return false;
    seen.add(target.document.document_id);
  }
  return true;
}
export function validPeopleReview(value: unknown, request: PeopleTransferRequest, proof: PeopleTransferProof,
  target: {document_id: string; revision?: string}): value is PeopleTransferReview {
  if (!object(value) || !samePeopleRequest(request, request)) return false;
  const v = value as unknown as PeopleTransferReview;
  if (v.version !== 1 || !validFaceRef(v.source_ref) || !sameFace(v.source_ref, request.source_ref)
    || v.target_policy !== request.target_policy || v.transfer_policy !== 'selected_parameter_keys_replace'
    || !validDocumentFence(v.source_document) || !validDocumentFence(v.target_document)
    || v.target_document.document_id !== target.document_id || String(v.target_document.revision) !== target.revision
    || !uniqueRefs(v.target_refs) || !Array.isArray(v.parameters) || !Array.isArray(v.excluded)) return false;
  if (request.target_policy === 'explicit_face_map') {
    const row = request.targets.find(item => item.target.document.document_id === target.document_id);
    if (v.target_policy !== 'explicit_face_map' || !row || !('document' in proof) || !validEndpoint(proof)
      || !sameEndpoint(proof, request.source) || !validEndpoint(v.source_owner) || !validEndpoint(v.target_owner)
      || !sameEndpoint(v.source_owner, request.source) || !sameEndpoint(v.target_owner, row.target)
      || !sameDocument(v.source_document, request.source.document) || !sameDocument(v.target_document, row.target.document)
      || v.source_state_revision !== request.source.state_revision || v.target_state_revision !== row.target.state_revision
      || v.source_association_revision !== request.source.association_revision || v.target_association_revision !== row.target.association_revision
      || !sameRefs(v.target_refs, row.target_refs) || v.target_refs.some(ref => ref.asset_sha256 !== row.target.source_proof.asset_sha256)
      || 'confirmed_person_id' in value || 'confirmation_revisions' in value || 'person_id' in value) return false;
  } else {
    if (v.target_policy !== 'confirmed_person_only' || 'document' in proof || v.confirmed_person_id !== proof.person_id
      || !sameDocument(v.source_document, peopleProofDocument(proof)) || v.target_document.epoch !== proof.document_epoch
      || v.source_state_revision !== proof.state_revision || v.target_state_revision !== proof.state_revision
      || v.source_association_revision !== proof.association_revision || v.target_association_revision !== proof.association_revision
      || v.target_refs.some(ref => ref.asset_sha256 === request.source_ref.asset_sha256 || ref.asset_sha256 !== v.target_refs[0].asset_sha256)
      || !Array.isArray(v.confirmation_revisions) || !validEndpoint(v.source_owner) || !validEndpoint(v.target_owner)
      || !sameDocument(v.source_owner.document, v.source_document) || !sameDocument(v.target_owner.document, v.target_document)
      || v.source_owner.state_revision !== proof.state_revision || v.target_owner.state_revision !== proof.state_revision
      || v.source_owner.association_revision !== proof.association_revision || v.target_owner.association_revision !== proof.association_revision
      || v.source_owner.people_scope !== v.target_owner.people_scope || v.source_owner.graph_sha256 !== v.target_owner.graph_sha256
      || v.source_owner.source_proof.asset_sha256 !== request.source_ref.asset_sha256
      || v.target_refs.some(ref => ref.asset_sha256 !== v.target_owner.source_proof.asset_sha256)) return false;
    const refs = new Set(v.target_refs.map(ref => ref.face_instance_id)), confirmations = new Set<string>();
    for (const row of v.confirmation_revisions) {
      if (!Array.isArray(row) || row.length !== 2 || !refs.has(row[0]) || confirmations.has(row[0]) || !safeRevision(row[1])) return false;
      confirmations.add(row[0]);
    }
    if (confirmations.size !== refs.size) return false;
  }
  const wanted = new Set(Object.entries(request.selection).flatMap(([op, paths]) => paths.map(path => JSON.stringify([op, path]))));
  for (const leaf of v.parameters) {
    if (!leaf || !wanted.delete(JSON.stringify([leaf.operation_id, leaf.parameter_path]))
      || !(['string', 'boolean'].includes(typeof leaf.value) || (typeof leaf.value === 'number' && Number.isFinite(leaf.value)))) return false;
  }
  return wanted.size === 0 && JSON.stringify([...v.excluded].sort()) === JSON.stringify(['identity_links', 'landmarks', 'local_assets', 'masks']);
}
