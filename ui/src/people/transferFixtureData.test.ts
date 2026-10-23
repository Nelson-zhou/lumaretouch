// UNRUN source fixtures. Execution is delegated to the user's local test owner.
import type {FaceRef} from './model';
import type {PeopleEndpointProof, ExplicitPeopleRequest, PeopleTransferReview} from './transferProof';
import type {InventoryEntry, InventorySource, PeopleInventoryResult} from './transferInventory';
export const sourceId = 'a'.repeat(32), targetId = 'b'.repeat(32), asset = 'c'.repeat(64);
export const sourceRef: FaceRef = {asset_sha256: asset, face_instance_id: 'retained-face', analysis_revision: 3};
export function endpoint(id: string, state = 2): PeopleEndpointProof {
  return {document: {document_id: id, epoch: 'workspace-1', revision: state + 1}, people_scope: id,
    state_revision: state, association_revision: state + 4, graph_sha256: (id === sourceId ? 'd' : 'e').repeat(64),
    source_proof: {asset_sha256: asset, original_sha256: asset, creative_source: null}};
}
export function entry(id: string, state = 2): InventoryEntry {
  return {...endpoint(id, state), faces: [{face_ref: {...sourceRef}, box: [.1, .2, .8, .9], enabled: true, analysis_status: 'verified'}],
    blocked: null, source_preview: {mime: 'image/png', width: 1, height: 1, source_sha256: asset,
      base64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGq0AAAAASUVORK5CYII='}};
}
export function inventory(requestId = 'read-1'): PeopleInventoryResult {
  return {request_id: requestId, action: 'people_targets', success: true, people_transfer: true,
    source: entry(sourceId), targets: [entry(targetId, 19)], rejected_docs: []};
}
export const selection = {'lnx.deform.v1': ['/face_slim']};
export function request(): ExplicitPeopleRequest {
  return {source_ref: {...sourceRef}, selection, target_policy: 'explicit_face_map', source: endpoint(sourceId),
    targets: [{target: endpoint(targetId, 19), target_refs: [{...sourceRef}]}]};
}
export function sourceContext(): InventorySource {
  const p = endpoint(sourceId);
  return {binding: {document_id: sourceId, document_epoch: p.document.epoch, document_revision: p.document.revision, asset_sha256: asset},
    state_revision: p.state_revision, association_revision: p.association_revision, face_ref: {...sourceRef}};
}
export function review(): PeopleTransferReview {
  const r = request(), t = r.targets[0];
  return {version: 1, source_document: {...r.source.document}, target_document: {...t.target.document},
    source_ref: {...sourceRef}, target_refs: [{...sourceRef}], target_policy: 'explicit_face_map',
    source_owner: r.source, target_owner: t.target, source_state_revision: r.source.state_revision, target_state_revision: t.target.state_revision,
    source_association_revision: r.source.association_revision, target_association_revision: t.target.association_revision,
    transfer_policy: 'selected_parameter_keys_replace', excluded: ['identity_links', 'landmarks', 'local_assets', 'masks'],
    parameters: [{operation_id: 'lnx.deform.v1', parameter_path: '/face_slim', value: .3}]};
}
