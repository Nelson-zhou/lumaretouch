import {validCapsule,type AssociationCapsule} from './associationProof';
import type {FaceRef, PeopleBinding} from './model';
import {documentId, safeRevision, sameFace, validEndpoint, validFaceRef,
  type ExplicitPeopleRequest, type PeopleEndpointProof} from './transferProof.ts';

export const PEOPLE_TRANSFER_LIMITS = {targets: 16, faces: 128, previewEdge: 320, previewBase64: 400000} as const;
export type InventoryFace = {face_ref: FaceRef; box: [number, number, number, number]; enabled: boolean;
  analysis_status: 'verified' | 'unresolved' | 'synthetic'};
export type InventoryEntry = PeopleEndpointProof & {faces: InventoryFace[]; blocked: null; associations?:AssociationCapsule[];
  source_preview: {mime: 'image/png'; base64: string; width: number; height: number; source_sha256: string}};
export type BlockedInventoryEntry = {document: {document_id: string}; blocked: string};
export type PeopleInventoryResult = {request_id: string; action: 'people_targets'; success: true; people_transfer: true;
  source: InventoryEntry; targets: (InventoryEntry | BlockedInventoryEntry)[]; rejected_docs: {doc: string; error: string}[]};
export type InventorySource = {binding: PeopleBinding; state_revision: number; association_revision: number; face_ref: FaceRef};
export type FaceChoices = Record<string, FaceRef[]>;
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
export function endpointOf(entry: InventoryEntry): PeopleEndpointProof {
  const {document, people_scope, state_revision, association_revision, graph_sha256, source_proof} = entry;
  return {document, people_scope, state_revision, association_revision, graph_sha256, source_proof};
}
export function isAvailableEntry(entry: InventoryEntry | BlockedInventoryEntry): entry is InventoryEntry {
  return entry.blocked === null;
}
export function selectableFace(face: InventoryFace) { return face.enabled && face.analysis_status === 'verified'; }
export function validInventoryEntry(value: unknown): value is InventoryEntry {
  if (!object(value) || value.blocked !== null) return false;
  const v = value as unknown as InventoryEntry;
  if (!validEndpoint(endpointOf(v)) || !Array.isArray(v.faces) || !v.faces.length || v.faces.length > PEOPLE_TRANSFER_LIMITS.faces) return false;
  if(v.associations!==undefined&&(!Array.isArray(v.associations)||v.associations.length>4096||!v.associations.every(c=>validCapsule(c)&&c.local_document_id===v.document.document_id)))return false;
  const ids = new Set<string>();
  for (const row of v.faces) {
    if (!row || !validFaceRef(row.face_ref) || row.face_ref.asset_sha256 !== v.source_proof.asset_sha256
      || typeof row.enabled !== 'boolean' || !['verified', 'unresolved', 'synthetic'].includes(row.analysis_status)
      || !Array.isArray(row.box) || row.box.length !== 4 || !row.box.every(n => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1)
      || row.box[0] >= row.box[2] || row.box[1] >= row.box[3] || ids.has(row.face_ref.face_instance_id)) return false;
    ids.add(row.face_ref.face_instance_id);
  }
  const p = v.source_preview;
  return !!p && p.mime === 'image/png' && typeof p.base64 === 'string' && p.base64.length <= PEOPLE_TRANSFER_LIMITS.previewBase64
    && p.base64.length % 4 === 0 && /^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(p.base64)
    && safeRevision(p.width) && p.width > 0 && p.width <= PEOPLE_TRANSFER_LIMITS.previewEdge
    && safeRevision(p.height) && p.height > 0 && p.height <= PEOPLE_TRANSFER_LIMITS.previewEdge
    && p.source_sha256 === v.source_proof.asset_sha256;
}
/** Every requested document is accounted for once; a partial inventory is never a map. */
export function validInventory(value: unknown, requestId: string, docs: string[], source: InventorySource): value is PeopleInventoryResult {
  if (!object(value) || value.request_id !== requestId || value.action !== 'people_targets' || value.success !== true
    || value.people_transfer !== true || !validInventoryEntry(value.source) || !Array.isArray(value.targets)
    || !Array.isArray(value.rejected_docs) || !docs.length || docs.length > PEOPLE_TRANSFER_LIMITS.targets
    || !docs.every(documentId) || new Set(docs).size !== docs.length) return false;
  const actual = value.source, expected = source.binding;
  if (actual.document.document_id !== expected.document_id || actual.document.epoch !== expected.document_epoch
    || actual.document.revision !== expected.document_revision || actual.source_proof.asset_sha256 !== expected.asset_sha256
    || actual.state_revision !== source.state_revision || actual.association_revision !== source.association_revision
    || !actual.faces.some(face => sameFace(face.face_ref, source.face_ref) && selectableFace(face))) return false;
  const remaining = new Set(docs);
  for (const row of value.targets) {
    if (!object(row) || !object(row.document) || !documentId(row.document.document_id)
      || !remaining.delete(row.document.document_id) || row.document.document_id === actual.document.document_id) return false;
    if (row.blocked === null) { if (!validInventoryEntry(row)) return false; }
    else if (typeof row.blocked !== 'string' || !row.blocked || row.blocked.length > 2000
      || Object.keys(row).sort().join('|') !== 'blocked|document' || Object.keys(row.document).join('|') !== 'document_id') return false;
  }
  for (const row of value.rejected_docs) {
    if (!object(row) || typeof row.doc !== 'string' || !remaining.delete(row.doc)
      || typeof row.error !== 'string' || !row.error || row.error.length > 2000) return false;
  }
  return remaining.size === 0;
}
/** No default face, nearest face, first face, or digest-based owner inference. */
export function explicitRequest(inventory: PeopleInventoryResult | null, docs: string[], sourceRef: FaceRef | undefined,
  selection: Record<string, string[]>, choices: FaceChoices): ExplicitPeopleRequest | undefined {
  if (!inventory || !sourceRef || !Object.keys(selection).length || inventory.rejected_docs.length
    || !docs.length || new Set(docs).size !== docs.length || docs.length !== inventory.targets.length
    || !inventory.source.faces.some(face => sameFace(face.face_ref, sourceRef) && selectableFace(face))) return undefined;
  const targets: ExplicitPeopleRequest['targets'] = [];
  for (const id of docs) {
    const entry = inventory.targets.find(row => row.document.document_id === id), refs = choices[id];
    if (!entry || !isAvailableEntry(entry) || !refs?.length || new Set(refs.map(ref => ref.face_instance_id)).size !== refs.length
      || !refs.every(ref => entry.faces.some(face => sameFace(face.face_ref, ref) && selectableFace(face)))) return undefined;
    targets.push({target: endpointOf(entry), target_refs: refs.map(ref => ({...ref}))});
  }
  return {target_policy: 'explicit_face_map', source_ref: {...sourceRef}, selection,
    source: endpointOf(inventory.source), targets};
}
