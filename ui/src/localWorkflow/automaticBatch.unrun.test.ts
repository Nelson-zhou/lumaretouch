import {checkedSemanticArchive, semanticIntent, type SemanticArchive} from './semanticArchive.ts';
// SPDX-License-Identifier: GPL-3.0-or-later
/** AUTHORED / UNRUN. No tests, typechecks, builds, engine or image processing executed. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {checkedExportProfiles, WorkflowController} from './controller.ts';
import {newDefinition, newOperation, validateGraph, validAutomaticIntent} from './model.ts';
import {checkedHandoff} from './presetReview.ts';
import type {WorkflowCapabilities, WorkflowCommand, WorkflowDefinition, WorkflowHostPort, WorkflowReceipt, WorkflowWorkspace, WorkflowExportProfile} from './contracts.ts';

const hash = 'a'.repeat(64);
const legacyExport: WorkflowExportProfile = {profile: 'lrt.workflow-export.jpeg-srgb.v1',
  export_options: {format: 'jpg', quality: 95, tile: 1024, bit_depth: 8, scale: 1, upscale_backend: 'lanczos3',
    sharpen: 0, output_profile: 'srgb', metadata_include_gps: false, conflict_policy: 'skip_and_report', tiff_compression: 'deflate'},
  destination: {mode: 'chosen_root', retain_hierarchy: false, conflict: 'ask', create_missing: false}, watermark: null, layout: null};

const capabilities: WorkflowCapabilities = {available: true, can_save: true, can_run: true, can_open_review: true,
  error_policies: {directory_source: ['stop'], managed_import: ['stop'], automatic_preset: ['stop', 'skip'], compatible_preset: ['stop'], export: ['stop', 'skip']}};
function definition(): WorkflowDefinition {
  const value = newDefinition('auto-fixture');
  value.storage_revision = 'saved';
  value.graph.nodes[0].operation = {kind: 'directory_source', root: '/input', recursive: false, include_existing: true, extensions: ['jpg'], settle_ms: 1000};
  value.graph.nodes[1].operation = {kind: 'managed_import', project_id: 'project', project_path: '/project.lrt', managed_root: '/managed'};
  value.graph.nodes[2].operation = {kind: 'export', output_root: '/output', recipe_sha256: hash};
  const automatic = newOperation('automatic_preset');
  if (automatic.kind !== 'automatic_preset') throw Error('Fixture declaration mismatch');
  value.graph.nodes.push({id: 'auto', error_policy: 'skip', operation: {...automatic, preset_id: 'scalar', preset_sha256: hash}});
  value.graph.edges = [{from: 'node-1', to: 'node-2'}, {from: 'node-2', to: 'auto'}, {from: 'auto', to: 'node-3'}];
  return value;
}
function harness(initial = definition(), catalogue?: unknown) {
  const sent: WorkflowCommand[] = [];
  let token = 0, broken = false, sequence = 0;
  const workspace: WorkflowWorkspace = {port_version: 1, workspace_revision: 1, capabilities, definitions: [], runs: [], active_run: null, unresolved_requests: [], preset_catalogue: catalogue,
    recipe_sha256: hash, recipe_profile: structuredClone(legacyExport),
    lease: {lease_id: 'lease', project_id: 'project', project_path: '/project.lrt', saved: true, dedicated: true, expires_at: new Date(Date.now() + 600000).toISOString()}};
  const host: WorkflowHostPort = {version: 1, scope_id: 'automatic-fixture',
    readWorkspace: async () => {if (broken) throw Error('Disconnected fixture'); return structuredClone(workspace);},
    readDefinition: async () => definition(),
    preflight: async input => ({workflow_id: input.graph.workflow_id, graph_revision: input.graph.revision, lease_id: input.lease_id,
      graph_sha256: hash, preflight_token: `preflight-${++token}`, can_start: true, valid_until: new Date(Date.now() + 300000).toISOString(), diagnostics: []}),
    submit: async input => {sent.push(structuredClone(input.command)); return {request_id: input.request_id, command_kind: input.command.kind, status: 'unknown'};},
    queryRequest: async request_id => ({request_id, command_kind: 'start', status: 'unknown'} as WorkflowReceipt),
    readRun: async () => {throw Error('No fixture run');}};
  const controller = new WorkflowController(host, initial, () => `request-${++sequence}`);
  return {controller, host, sent, workspace, disconnect: () => {broken = true;}, reconnect: () => {broken = false;}};
}
async function ready(h: ReturnType<typeof harness>) {await h.controller.refresh(); await h.controller.check();}

test('automatic declaration remains separate from reviewed mode and refuses keep-continue or mixed presets', () => {
  const value = definition(); assert.deepEqual(validateGraph(value.graph, capabilities), []);
  const node = value.graph.nodes[3];
  assert.equal(node.operation.kind === 'automatic_preset' && validAutomaticIntent(node.operation.intent), true);
  assert.equal(validAutomaticIntent({unattended: true}), false);
  node.error_policy = 'keep_continue';
  assert.ok(validateGraph(value.graph, capabilities).some(row => row.code === 'keep_not_supported'));
  node.error_policy = 'skip';
  value.graph.nodes.push({id: 'reviewed', error_policy: 'stop', operation: {kind: 'compatible_preset', preset_id: 'scalar', preset_sha256: hash, when_all_labels: []}});
  assert.ok(validateGraph(value.graph, capabilities).some(row => row.code === 'preset_count'));
});
test('saved automatic intent never starts without current explicit run acknowledgment', async () => {
  const h = harness(); await ready(h);
  assert.equal(h.controller.canStart(), false); await h.controller.start(); assert.equal(h.sent.length, 0);
  assert.equal(h.controller.canAcknowledgeAutomaticStart(), true);
  h.controller.acknowledgeAutomaticStart(true); assert.equal(h.controller.canStart(), true);
  await h.controller.start();
  const start = h.sent[0]; assert.equal(start.kind, 'start');
  if (start.kind !== 'start') throw Error('Fixture start expected');
  assert.deepEqual(start.automatic_ack, {schema: 'lrt.automatic-batch-start.v1', graph_sha256: hash, accepted: true});
  assert.equal(h.controller.getState().automatic_start_ack, null);
  await h.controller.start(); await h.controller.queryPending(); assert.equal(h.sent.length, 1);
});
test('fresh preflight, graph edit, restored definition and disconnect discard consent', async () => {
  for (const change of ['preflight', 'edit', 'load', 'disconnect', 'dismiss'] as const) {
    const h = harness(); await ready(h); h.controller.acknowledgeAutomaticStart(true);
    if (change === 'preflight') await h.controller.check();
    if (change === 'edit') h.controller.updateDraft(value => ({...value, description: 'new intent'}));
    if (change === 'load') await h.controller.load('auto-fixture');
    if (change === 'disconnect') {h.disconnect(); await h.controller.refresh(); h.reconnect(); await h.controller.refresh();}
    if (change === 'dismiss') h.controller.acknowledgeAutomaticStart(false);
    assert.equal(h.controller.getState().automatic_start_ack, null, change);
    assert.equal(h.controller.canStart(), false, change);
  }
});
test('automatic directory jobs require finite captured existing-file scope', () => {
  const value = definition(), source = value.graph.nodes[0].operation;
  if (source.kind !== 'directory_source') throw Error('Fixture source');
  source.include_existing = false;
  assert.ok(validateGraph(value.graph, capabilities).some(row => row.code === 'automatic_source_mode'));
  const auto = value.graph.nodes[3].operation;
  if (auto.kind !== 'automatic_preset') throw Error('Fixture auto');
  assert.equal(auto.intent.source_mode, 'captured_file_list');
  const {source_mode, ...oldIntent} = auto.intent;
  assert.equal(validAutomaticIntent(oldIntent), false);
});
test('legacy preflight without canonical graph hash cannot authorize automatic start', async () => {
  const h = harness(), preflight = h.host.preflight;
  h.host.preflight = async input => {const result = await preflight(input); delete result.graph_sha256; return result;};
  await ready(h); h.controller.acknowledgeAutomaticStart(true);
  assert.equal(h.controller.canStart(), false); assert.equal(h.controller.canAcknowledgeAutomaticStart(), false);
});
test('automatic handoff is explicitly not an image review or acknowledgment', () => {
  const value = {version: 1, mode: 'automatic', operation_id: hash, document_id: 'document', preset_id: 'scalar', preset_sha256: hash, phase: 'authorized', review: null, message: 'Automatic owner pending'};
  assert.ok(checkedHandoff(value));
  assert.equal(checkedHandoff({...value, phase: 'reviewing'}), null);
  assert.equal(checkedHandoff({...value, review: {accepted: true}}), null);
  assert.equal(checkedHandoff({...value, mode: 'reviewed'}), null);
});

// Source-authored only: no runtime claim.
test('portrait scope is absent by default and only exact all-verified scope is accepted', () => {
  const op = newOperation('automatic_preset');
  if (op.kind !== 'automatic_preset') throw Error('Fixture automatic declaration');
  assert.equal(Object.prototype.hasOwnProperty.call(op.intent, 'portrait_scope'), false);
  assert.equal(validAutomaticIntent({...op.intent, portrait_scope: 'all_verified_detected_faces'}), true);
  for (const scope of [null, undefined, '', 'same_person_across_photos', 'all_people'])
    assert.equal(validAutomaticIntent({...op.intent, portrait_scope: scope}), false);
  assert.equal(validAutomaticIntent({...op.intent, portrait_scope: 'all_verified_detected_faces', match_identity: true}), false);
});

test('adding portrait scope invalidates a scalar job start acknowledgment', async () => {
  const h = harness(); await ready(h); h.controller.acknowledgeAutomaticStart(true);
  assert.equal(h.controller.canStart(), true);
  h.controller.updateDraft(value => {
    for (const node of value.graph.nodes) if (node.operation.kind === 'automatic_preset')
      node.operation.intent = {...node.operation.intent, portrait_scope: 'all_verified_detected_faces'};
    return value;
  });
  assert.equal(h.controller.getState().automatic_start_ack, null);
  assert.equal(h.controller.getState().preflight, null);
  assert.equal(h.controller.canStart(), false);
});

// AUTHORED / UNRUN: reference fitting is a separate exact declaration, not review.
test('reference scope requires paired rejection policy and excludes portrait scope', () => {
  const op = newOperation('automatic_preset');
  if (op.kind !== 'automatic_preset') throw Error('Fixture automatic declaration');
  const reference = {...op.intent, reference_scope: 'stored_reference_per_target_fit', reference_source_policy: 'reject_same_source'};
  assert.equal(validAutomaticIntent(reference), true);
  for (const policy of [undefined, null, '', 'copy_source', 'silently_skip'])
    assert.equal(validAutomaticIntent({...reference, reference_source_policy: policy}), false);
  assert.equal(validAutomaticIntent({...reference, portrait_scope: 'all_verified_detected_faces'}), false);
  const {reference_source_policy, ...missingPolicy} = reference;
  assert.equal(validAutomaticIntent(missingPolicy), false);
});

test('reference scope invalidates consent and cannot authorize without disclosed saved reference', async () => {
  const h = harness(); await ready(h); h.controller.acknowledgeAutomaticStart(true);
  h.controller.updateDraft(value => {
    for (const node of value.graph.nodes) if (node.operation.kind === 'automatic_preset')
      node.operation.intent = {...node.operation.intent, reference_scope: 'stored_reference_per_target_fit', reference_source_policy: 'reject_same_source'};
    return value;
  });
  assert.equal(h.controller.getState().automatic_start_ack, null);
  assert.equal(h.controller.canAcknowledgeAutomaticStart(), false);
  assert.equal(h.controller.canStart(), false);
});

// A saved profile is still not fresh run consent; absent or malformed reference metadata blocks disclosure.
test('reference start requires exact immutable reference metadata before fresh consent', async () => {
  const initial = definition();
  const automatic = initial.graph.nodes[3].operation;
  if (automatic.kind !== 'automatic_preset') throw Error('Fixture automatic');
  automatic.intent = {...automatic.intent, reference_scope: 'stored_reference_per_target_fit', reference_source_policy: 'reject_same_source'};
  const row = {id: 'scalar', name: 'Stored reference', kind: 'user', builtin: false, preset_sha256: hash,
    module_ids: ['lnx.reference_color.v1'], workflow_supported: false, support_reason: '', automatic_supported: true,
    automatic_reference: {asset_id: 'b'.repeat(64), render_sha256: 'c'.repeat(64), source_sha256: 'd'.repeat(64)}};
  for (const metadata of [row.automatic_reference, undefined, {...row.automatic_reference, asset_id: 'invalid'}]) {
    const h = harness(initial, {schema: 'lrt.workflow-preset-catalogue.v1', complete: true, errors: [], presets: [{...row, automatic_reference: metadata}]});
    await ready(h);
    assert.equal(h.controller.canStart(), false);
    h.controller.acknowledgeAutomaticStart(true);
    assert.equal(h.controller.canStart(), metadata === row.automatic_reference);
  }
});

// Expanded output profiles: all authored / UNRUN.
test('only exact bounded format settings can be disclosed', () => {
  const png = {...structuredClone(legacyExport), profile: 'lrt.workflow-export.png8-srgb.v1',
    export_options: {...legacyExport.export_options, format: 'png'}};
  assert.equal(checkedExportProfiles([{recipe_sha256: hash, recipe_profile: png}]).length, 1);
  for (const change of [{quality: 90}, {scale: 2}, {format: 'webp'}, {bit_depth: 16}, {output_profile: 'source'}]) {
    assert.deepEqual(checkedExportProfiles([{recipe_sha256: hash, recipe_profile: {...png,
      export_options: {...png.export_options, ...change}}}]), []);
  }
  assert.deepEqual(checkedExportProfiles([{recipe_sha256: hash, recipe_profile: legacyExport},
    {recipe_sha256: hash, recipe_profile: png}]), []);
});
test('missing selected disclosure blocks consent and profile choice invalidates it', async () => {
  const h = harness(); await ready(h); h.controller.acknowledgeAutomaticStart(true);
  const png: WorkflowExportProfile = {...structuredClone(legacyExport), profile: 'lrt.workflow-export.png8-srgb.v1',
    export_options: {...legacyExport.export_options, format: 'png'}};
  h.workspace.export_profiles = [{recipe_sha256: hash, recipe_profile: legacyExport},
    {recipe_sha256: 'b'.repeat(64), recipe_profile: png}];
  await h.controller.refresh(); h.controller.useReturnedExportProfile('b'.repeat(64));
  assert.equal(h.controller.getState().automatic_start_ack, null);
  assert.equal(h.controller.getState().dirty, true);
  assert.equal(h.controller.selectedExportProfile()?.recipe_profile.export_options.format, 'png');
  assert.equal(h.sent.length, 0);
  h.workspace.export_profiles = []; delete h.workspace.recipe_profile;
  await h.controller.refresh(); assert.equal(h.controller.canAcknowledgeAutomaticStart(), false);
});


function semanticArchive(): SemanticArchive {
  return {path: '/fixture/reference.lrtcolour', file_bytes: 8192, file_sha256: 'd'.repeat(64), intent_sha256: 'e'.repeat(64),
    portable_intent_json: JSON.stringify({version: 1, algorithm: 'semantic-oklab-log-ot-pchip-hsv8-v1', enabled: true,
      mode: 'harmonious', strengths: [100, 80, 90], offset_policy: 'recompute-then-user-offset-v1', class_policy: 'require-requested-support-v1',
      reference: {asset_id: 'a'.repeat(64), render_sha256: 'b'.repeat(64), source: {sha256: 'c'.repeat(64), width: 64, height: 64}},
      groups: [{id: 'global', enabled: true, offsets: Array(50).fill(0)}, {id: 'others', enabled: false, offsets: Array(50).fill(0)}]})};
}
function semanticDefinition() {
  const value = definition(), operation = value.graph.nodes[3].operation, archive = semanticArchive();
  if (operation.kind !== 'automatic_preset') throw Error('Fixture automatic');
  operation.preset_id = `semantic:${archive.file_sha256}`; operation.preset_sha256 = archive.file_sha256;
  operation.intent = {...operation.intent, reference_source_policy: 'reject_same_source', semantic_scope: 'global_six_class_per_target_fit', semantic_archive: archive};
  return value;
}
test('semantic metadata retains complete intent text and cannot claim unknown classes or authority', () => {
  const archive = semanticArchive();
  assert.deepEqual(checkedSemanticArchive(archive), archive);
  assert.equal(semanticIntent(archive)?.groups[1].enabled, false);
  for (const changed of [{file_bytes: 256*1024*1024+128*1024+1}, {path: '/fixture/preset.json'}, {reviewed: true}, {portable_intent_json: '{}'}])
    assert.equal(checkedSemanticArchive({...archive, ...changed}), null);
  const op = semanticDefinition().graph.nodes[3].operation;
  if (op.kind !== 'automatic_preset') throw Error('Fixture automatic');
  assert.equal(validAutomaticIntent(op.intent), true);
  assert.equal(validAutomaticIntent({...op.intent, portrait_scope: 'all_verified_detected_faces'}), false);
  assert.equal(validAutomaticIntent({...op.intent, reference_scope: 'stored_reference_per_target_fit'}), false);
  assert.equal(validAutomaticIntent({...op.intent, semantic_archive: null}), false);
});
test('semantic Start consent requires identical engine-frozen preflight archive and remains one-shot', async () => {
  for (const returned of [semanticArchive(), undefined, {...semanticArchive(), file_sha256: '9'.repeat(64)}]) {
    const h = harness(semanticDefinition()), preflight = h.host.preflight;
    h.host.preflight = async input => ({...await preflight(input), semantic_archive: returned});
    await ready(h); assert.equal(h.controller.canStart(), false);
    h.controller.acknowledgeAutomaticStart(true);
    const matched = returned?.file_sha256 === semanticArchive().file_sha256;
    assert.equal(h.controller.canStart(), matched);
    await h.controller.start(); assert.equal(h.sent.length, matched ? 1 : 0);
    assert.equal(h.controller.getState().automatic_start_ack, null);
  }
});
test('selecting an archive only changes the draft and clears all old consent', async () => {
  const h = harness(semanticDefinition()); await h.controller.refresh();
  h.host.inspectSemanticArchive = async path => ({...semanticArchive(), path});
  await h.controller.selectSemanticArchive('auto', '/fixture/new.lrtcolour');
  assert.equal(h.controller.getState().dirty, true); assert.equal(h.controller.getState().preflight, null);
  assert.equal(h.controller.getState().automatic_start_ack, null); assert.equal(h.sent.length, 0);
  const op = h.controller.getState().draft.graph.nodes[3].operation;
  assert.equal(op.kind === 'automatic_preset' && op.intent.semantic_archive?.path, '/fixture/new.lrtcolour');
});
