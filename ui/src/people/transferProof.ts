import {validCollarboneVisual,type CollarboneVisual} from '../collarbone/transferModel';
import {sameAssociationRequest, type AssociationRequest} from './associationProof';
import type {FaceRef, ParameterValue} from './model';
import {validOwnFaceReference, type OwnFaceReference} from '../bodyFaceMatch/reference';
import {validFaceStyleRecipe, type FaceStyleRecipe} from '../faceStyle/model';
import {sameFaceStyleRecipe, validFaceStyleSelection, validFaceStyleBatchVisual, type FaceStyleBatchVisual} from '../faceStyle/batchModel';

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
  face_style?: FaceStyleRecipe;
};
export type PeopleTransferRequest = SelectedParameters & {target_policy: 'confirmed_person_only'} | ExplicitPeopleRequest | AssociationRequest;
export type SkinColourCoverage = {
  version: 1; support_transfer: 'none';
  targets: {face_ref: FaceRef; scope: 'face-only' | 'face-and-reviewed-body' | 'neutral-no-effect'; body_review_sha256: string | null}[];
};
/** Structurally identical disclosure, independently keyed to finish intent. */
export type SkinFinishCoverage = SkinColourCoverage;
/** Body-evenness never has a face-only fallback or a transferable source support. */
export type BodySkinEvennessCoverage = {
  version: 1; support_transfer: 'none';
  targets: {face_ref: FaceRef; scope: 'reviewed-body-only' | 'neutral-no-effect'; body_review_sha256: string | null}[];
};
/** Every target keeps its own reviewed body and measured same-face source identity. */
export type BodyFaceMatchCoverage = {
  version: 1; support_transfer: 'none';
  targets: {face_ref: FaceRef; scope: 'reviewed-body-own-face' | 'neutral-no-effect'; body_review_sha256: string | null;
    own_face_reference: OwnFaceReference | null}[];
};
/** Source geometry is never copied; every target discloses its own manual eligibility and visible sides. */
export type CollarboneCoverage = {
  version: 1; support_transfer: 'none';
  targets: {face_ref: FaceRef; scope: 'reviewed-clavicle-only' | 'neutral-no-effect'; body_review_sha256: string | null;
    clavicle_category: 'female' | 'elder_female' | null; clavicle_sides: ('left' | 'right')[]}[];
};
type ReviewBase = {
  version: 1; source_document: DocumentFence; target_document: DocumentFence;
  source_ref: FaceRef; target_refs: FaceRef[];
  parameters: {operation_id: string; parameter_path: string; value: ParameterValue}[];
  source_state_revision: number; target_state_revision: number;
  source_association_revision: number; target_association_revision: number;
  transfer_policy: 'selected_parameter_keys_replace'; excluded: string[];
  skin_colour_coverage?: SkinColourCoverage;
  skin_finish_coverage?: SkinFinishCoverage;
  body_skin_evenness_coverage?: BodySkinEvennessCoverage;
  body_face_match_coverage?: BodyFaceMatchCoverage;
  collarbone_coverage?: CollarboneCoverage;
  collarbone_visual?: CollarboneVisual;
  face_style?: FaceStyleRecipe;
  face_style_visual?: FaceStyleBatchVisual;
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
/** Every disclosed extent belongs to an exact target, not to the source preset. */
export function validSkinColourCoverage(value: unknown, refs: FaceRef[]): value is SkinColourCoverage {
  if (!object(value) || !keys(value, ['version', 'support_transfer', 'targets']) || value.version !== 1
    || value.support_transfer !== 'none' || !Array.isArray(value.targets) || value.targets.length !== refs.length) return false;
  const seen = new Set<string>();
  for (const row of value.targets) {
    if (!object(row) || !keys(row, ['face_ref', 'scope', 'body_review_sha256']) || !validFaceRef(row.face_ref)
      || seen.has(row.face_ref.face_instance_id) || !refs.some(ref => sameFace(ref, row.face_ref as FaceRef))) return false;
    if (row.scope === 'face-and-reviewed-body' ? !digest(row.body_review_sha256)
      : (row.scope !== 'face-only' && row.scope !== 'neutral-no-effect') || row.body_review_sha256 !== null) return false;
    seen.add(row.face_ref.face_instance_id);
  }
  return seen.size === refs.length;
}
export function validSkinFinishCoverage(value: unknown, refs: FaceRef[]): value is SkinFinishCoverage {
  return validSkinColourCoverage(value, refs);
}
export function validBodySkinEvennessCoverage(value: unknown, refs: FaceRef[]): value is BodySkinEvennessCoverage {
  if (!object(value) || !keys(value, ['version', 'support_transfer', 'targets']) || value.version !== 1
    || value.support_transfer !== 'none' || !Array.isArray(value.targets) || value.targets.length !== refs.length) return false;
  const seen = new Set<string>();
  for (const row of value.targets) {
    if (!object(row) || !keys(row, ['face_ref', 'scope', 'body_review_sha256']) || !validFaceRef(row.face_ref)
      || seen.has(row.face_ref.face_instance_id) || !refs.some(ref => sameFace(ref, row.face_ref as FaceRef))) return false;
    if (row.scope === 'reviewed-body-only' ? !digest(row.body_review_sha256)
      : row.scope !== 'neutral-no-effect' || row.body_review_sha256 !== null) return false;
    seen.add(row.face_ref.face_instance_id);
  }
  return seen.size === refs.length;
}
export function validBodyFaceMatchCoverage(value: unknown, refs: FaceRef[]): value is BodyFaceMatchCoverage {
  if (!object(value) || !keys(value, ['version', 'support_transfer', 'targets']) || value.version !== 1
    || value.support_transfer !== 'none' || !Array.isArray(value.targets) || value.targets.length !== refs.length) return false;
  const seen = new Set<string>();
  for (const row of value.targets) {
    if (!object(row) || !keys(row, ['face_ref', 'scope', 'body_review_sha256', 'own_face_reference']) || !validFaceRef(row.face_ref)
      || seen.has(row.face_ref.face_instance_id) || !refs.some(ref => sameFace(ref, row.face_ref as FaceRef))) return false;
    if (row.scope === 'reviewed-body-own-face' ? !digest(row.body_review_sha256) || !validOwnFaceReference(row.own_face_reference, row.face_ref)
      : row.scope !== 'neutral-no-effect' || row.body_review_sha256 !== null || row.own_face_reference !== null) return false;
    seen.add(row.face_ref.face_instance_id);
  }
  return seen.size === refs.length;
}
export function validCollarboneCoverage(value: unknown, refs: FaceRef[]): value is CollarboneCoverage {
  if (!object(value) || !keys(value, ['version', 'support_transfer', 'targets']) || value.version !== 1
    || value.support_transfer !== 'none' || !Array.isArray(value.targets) || value.targets.length !== refs.length || !refs.length) return false;
  const seen = new Set<string>();
  for (const row of value.targets) {
    if (!object(row) || !keys(row, ['face_ref', 'scope', 'body_review_sha256', 'clavicle_category', 'clavicle_sides'])
      || !validFaceRef(row.face_ref) || seen.has(row.face_ref.face_instance_id)
      || !refs.some(ref => sameFace(ref, row.face_ref as FaceRef)) || !Array.isArray(row.clavicle_sides)) return false;
    if (row.scope === 'reviewed-clavicle-only') {
      if (!digest(row.body_review_sha256) || (row.clavicle_category !== 'female' && row.clavicle_category !== 'elder_female')
        || row.clavicle_sides.length < 1 || row.clavicle_sides.length > 2
        || !row.clavicle_sides.every(side => side === 'left' || side === 'right')
        || new Set(row.clavicle_sides).size !== row.clavicle_sides.length) return false;
    } else if (row.scope !== 'neutral-no-effect' || row.body_review_sha256 !== null
      || row.clavicle_category !== null || row.clavicle_sides.length !== 0) return false;
    seen.add(row.face_ref.face_instance_id);
  }
  return seen.size === refs.length;
}
function validSelection(v: unknown): v is Record<string, string[]> {
  return object(v) && Object.keys(v).length > 0 && Object.entries(v).every(([op, paths]) => token(op)
    && Array.isArray(paths) && paths.length > 0 && paths.every(path => typeof path === 'string' && path.startsWith('/') && path.length <= 512)
    && new Set(paths).size === paths.length);
}
export function samePeopleRequest(value: unknown, expected: PeopleTransferRequest): boolean {
  if (expected.target_policy === 'persistent_association') return sameAssociationRequest(value, expected);
  if (!object(value) || !validFaceRef(value.source_ref) || !sameFace(value.source_ref, expected.source_ref)
    || value.target_policy !== expected.target_policy || !validSelection(value.selection) || !validSelection(expected.selection)) return false;
  const selection = value.selection, ops = Object.keys(expected.selection).sort();
  if (JSON.stringify(Object.keys(selection).sort()) !== JSON.stringify(ops)
    || !ops.every(op => JSON.stringify([...selection[op]].sort()) === JSON.stringify([...expected.selection[op]].sort()))) return false;
  if (expected.target_policy === 'confirmed_person_only') return keys(value, ['source_ref', 'selection', 'target_policy']);
  const recipe = expected.face_style, named = recipe !== undefined;
  if (named ? !validFaceStyleRecipe(recipe) || !sameFaceStyleRecipe(value.face_style, recipe)
    || !validFaceStyleSelection(expected.selection) || !validFaceStyleSelection(selection) : Object.hasOwn(value, 'face_style')) return false;
  if (!keys(value, ['source_ref', 'selection', 'target_policy', 'source', 'targets', ...(named ? ['face_style'] : [])])
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
  if (request.target_policy === 'persistent_association') return false;
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
  const named = request.target_policy === 'explicit_face_map' ? request.face_style : undefined;
  if (named ? !sameFaceStyleRecipe(v.face_style, named) || !validFaceStyleBatchVisual(v.face_style_visual, v)
    : Object.hasOwn(value, 'face_style') || Object.hasOwn(value, 'face_style_visual')) return false;
  for (const leaf of v.parameters) {
    if (!leaf || !wanted.delete(JSON.stringify([leaf.operation_id, leaf.parameter_path]))
      || !(['string', 'boolean'].includes(typeof leaf.value) || (typeof leaf.value === 'number' && Number.isFinite(leaf.value)))) return false;
    // Named recipes replace only their bounded authored leaves, not donor values. The
    // backend composes the exact coefficients and the digest binds the named intent.
    if (named && (leaf.parameter_path.endsWith('/linked') ? leaf.value !== true
      : typeof leaf.value !== 'number' || Math.abs(leaf.value) > 0.30 * named.amount || named.amount === 0 && leaf.value !== 0)) return false;
  }
  const skinSelected = Object.prototype.hasOwnProperty.call(request.selection, 'lnx.skin_colour.v1');
  if (skinSelected ? !validSkinColourCoverage(v.skin_colour_coverage, v.target_refs) : v.skin_colour_coverage !== undefined) return false;
  if (skinSelected) {
    const scalars = v.parameters.filter(leaf => leaf.operation_id === 'lnx.skin_colour.v1');
    if (scalars.some(leaf => !['/temperature', '/tint'].includes(leaf.parameter_path)
      || typeof leaf.value !== 'number' || leaf.value < -1 || leaf.value > 1)) return false;
    if (scalars.some(leaf => leaf.value !== 0)
      && v.skin_colour_coverage!.targets.some(row => row.scope === 'neutral-no-effect')) return false;
  }
  const finishSelected = Object.prototype.hasOwnProperty.call(request.selection, 'lnx.skin_finish.v1');
  if (finishSelected ? !validSkinFinishCoverage(v.skin_finish_coverage, v.target_refs) : v.skin_finish_coverage !== undefined) return false;
  if (finishSelected) {
    const scalars = v.parameters.filter(leaf => leaf.operation_id === 'lnx.skin_finish.v1');
    if (scalars.some(leaf => !['/whitening', '/rosiness'].includes(leaf.parameter_path)
      || typeof leaf.value !== 'number' || leaf.value < 0 || leaf.value > 1)) return false;
    if (scalars.some(leaf => leaf.value !== 0)
      && v.skin_finish_coverage!.targets.some(row => row.scope === 'neutral-no-effect')) return false;
  }
  const bodyEvennessSelected = Object.prototype.hasOwnProperty.call(request.selection, 'lnx.body_skin_evenness.v1');
  if (bodyEvennessSelected ? !validBodySkinEvennessCoverage(v.body_skin_evenness_coverage, v.target_refs)
    : v.body_skin_evenness_coverage !== undefined) return false;
  if (bodyEvennessSelected) {
    const scalars = v.parameters.filter(leaf => leaf.operation_id === 'lnx.body_skin_evenness.v1');
    if (scalars.length !== 1 || scalars[0].parameter_path !== '/amount'
      || typeof scalars[0].value !== 'number' || scalars[0].value < 0 || scalars[0].value > 1) return false;
    const neutral = scalars[0].value === 0;
    if (v.body_skin_evenness_coverage!.targets.some(row => (row.scope === 'neutral-no-effect') !== neutral)) return false;
  }
  const bodyFaceMatchSelected = Object.prototype.hasOwnProperty.call(request.selection, 'lnx.body_face_match.v1');
  if (bodyFaceMatchSelected ? !validBodyFaceMatchCoverage(v.body_face_match_coverage, v.target_refs)
    : v.body_face_match_coverage !== undefined) return false;
  if (bodyFaceMatchSelected) {
    const scalars = v.parameters.filter(leaf => leaf.operation_id === 'lnx.body_face_match.v1');
    if (scalars.length !== 1 || scalars[0].parameter_path !== '/amount'
      || typeof scalars[0].value !== 'number' || scalars[0].value < 0 || scalars[0].value > 1) return false;
    const neutral = scalars[0].value === 0;
    if (v.body_face_match_coverage!.targets.some(row => (row.scope === 'neutral-no-effect') !== neutral)) return false;
  }
  const collarboneSelected = Object.prototype.hasOwnProperty.call(request.selection, 'lnx.collarbone.v1');
  if (collarboneSelected ? !validCollarboneCoverage(v.collarbone_coverage, v.target_refs) : v.collarbone_coverage !== undefined) return false;
  if (collarboneSelected ? !validCollarboneVisual(v.collarbone_visual,v) : v.collarbone_visual !== undefined) return false;
  if (collarboneSelected) {
    const scalars = v.parameters.filter(leaf => leaf.operation_id === 'lnx.collarbone.v1');
    if (scalars.length !== 1 || scalars[0].parameter_path !== '/amount' || typeof scalars[0].value !== 'number'
      || !Number.isFinite(scalars[0].value) || scalars[0].value < 0 || scalars[0].value > 1) return false;
    const neutral = scalars[0].value === 0;
    if (v.collarbone_coverage!.targets.some(row => (row.scope === 'neutral-no-effect') !== neutral)) return false;
  }
  return wanted.size === 0 && JSON.stringify([...v.excluded].sort()) === JSON.stringify(['identity_links', 'landmarks', 'local_assets', 'masks']);
}
