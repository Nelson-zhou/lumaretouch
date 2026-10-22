import {operationLabel, type FaceRef, type ParameterValue} from './model';

export type PeopleTransferRequest = {
  source_ref: FaceRef; selection: Record<string, string[]>; target_policy: 'confirmed_person_only';
};
export type PeopleTransferProof = {
  document_id: string; document_epoch: string; document_revision: number;
  state_revision: number; association_revision: number; person_id: string;
};
type DocumentFence = {document_id: string; epoch: string; revision: number};
export type PeopleTransferReview = {
  version: 1; source_document: DocumentFence; target_document: DocumentFence;
  source_ref: FaceRef; target_refs: FaceRef[];
  parameters: {operation_id: string; parameter_path: string; value: ParameterValue}[];
  source_state_revision: number; target_state_revision: number;
  source_association_revision: number; target_association_revision: number;
  transfer_policy: 'selected_parameter_keys_replace'; excluded: string[];
  confirmed_person_id: string; target_policy: 'confirmed_person_only';
  confirmation_revisions: [string, number][];
};
const revision = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;
const token = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 128;
function face(v: unknown): v is FaceRef {
  if (!v || typeof v !== 'object') return false;
  const f = v as FaceRef;
  return typeof f.asset_sha256 === 'string' && /^[a-f0-9]{64}$/.test(f.asset_sha256)
    && token(f.face_instance_id) && revision(f.analysis_revision);
}
function sameFace(a: FaceRef, b: FaceRef) {
  return a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
}
export function samePeopleRequest(value: unknown, expected: PeopleTransferRequest): boolean {
  if (!value || typeof value !== 'object') return false;
  const v = value as PeopleTransferRequest;
  if (!face(v.source_ref) || !sameFace(v.source_ref, expected.source_ref) || v.target_policy !== expected.target_policy
    || !v.selection || typeof v.selection !== 'object' || Array.isArray(v.selection)) return false;
  const ops = Object.keys(expected.selection).sort();
  return JSON.stringify(Object.keys(v.selection).sort()) === JSON.stringify(ops)
    && ops.every(op => Array.isArray(v.selection[op]) && JSON.stringify([...v.selection[op]].sort()) === JSON.stringify([...expected.selection[op]].sort()));
}
export function validPeopleReview(value: unknown, request: PeopleTransferRequest, proof: PeopleTransferProof,
  target: {document_id: string; revision?: string}): value is PeopleTransferReview {
  if (!value || typeof value !== 'object') return false;
  const v = value as PeopleTransferReview;
  if (v.version !== 1 || !face(v.source_ref) || !sameFace(v.source_ref, request.source_ref)
    || v.target_policy !== 'confirmed_person_only' || v.confirmed_person_id !== proof.person_id
    || v.transfer_policy !== 'selected_parameter_keys_replace'
    || v.source_document?.document_id !== proof.document_id || v.source_document.epoch !== proof.document_epoch
    || v.source_document.revision !== proof.document_revision
    || v.target_document?.document_id !== target.document_id || v.target_document.epoch !== proof.document_epoch
    || !revision(v.target_document.revision) || String(v.target_document.revision) !== target.revision
    || v.source_state_revision !== proof.state_revision || v.target_state_revision !== proof.state_revision
    || v.source_association_revision !== proof.association_revision || v.target_association_revision !== proof.association_revision
    || !Array.isArray(v.target_refs) || !v.target_refs.length || !v.target_refs.every(face)
    || !Array.isArray(v.parameters) || !Array.isArray(v.confirmation_revisions) || !Array.isArray(v.excluded)) return false;
  const refs = new Set(v.target_refs.map(ref => ref.face_instance_id));
  if (refs.size !== v.target_refs.length || v.target_refs.some(ref => ref.asset_sha256 === request.source_ref.asset_sha256
    || ref.asset_sha256 !== v.target_refs[0].asset_sha256)) return false;
  const confirmations = new Set<string>();
  for (const row of v.confirmation_revisions) {
    if (!Array.isArray(row) || row.length !== 2 || !refs.has(row[0]) || confirmations.has(row[0]) || !revision(row[1])) return false;
    confirmations.add(row[0]);
  }
  if (confirmations.size !== refs.size || [...refs].some(id => !confirmations.has(id))) return false;
  const wanted = new Set(Object.entries(request.selection).flatMap(([op, paths]) => paths.map(path => JSON.stringify([op, path]))));
  for (const leaf of v.parameters) {
    if (!leaf || !wanted.delete(JSON.stringify([leaf.operation_id, leaf.parameter_path]))
      || !(['string', 'boolean'].includes(typeof leaf.value) || (typeof leaf.value === 'number' && Number.isFinite(leaf.value)))) return false;
  }
  return wanted.size === 0 && JSON.stringify([...v.excluded].sort()) === JSON.stringify(['identity_links', 'landmarks', 'local_assets', 'masks']);
}
export function PeopleTransferEvidence({value}: {value: PeopleTransferReview}) {
  return <details><summary>已确认关联：{value.target_refs.length} 张人脸 · {value.parameters.length} 项参数</summary>
    <p>只替换明确勾选的参数；不复制蒙版、关键点或人物关联。</p>
    <p>匿名人物：{value.confirmed_person_id}。关联版本：{value.target_association_revision}。</p>
    <ul>{value.target_refs.map(ref => <li key={ref.face_instance_id}>目标人脸 {ref.face_instance_id} · 分析版本 {ref.analysis_revision}</li>)}</ul>
    <ul>{value.parameters.map(leaf => <li key={`${leaf.operation_id}:${leaf.parameter_path}`}>
      {operationLabel(leaf.operation_id)} · {leaf.parameter_path}：{String(leaf.value)}</li>)}</ul>
  </details>;
}
