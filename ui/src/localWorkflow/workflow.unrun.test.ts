// SPDX-License-Identifier: GPL-3.0-or-later
/** Authored source fixtures only. NEVER EXECUTED in this implementation pass. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {WorkflowController} from './controller.ts';
import {edgeProblem, leaseMatches, newDefinition, pathsOverlap, validateGraph} from './model.ts';
import type {PreflightReport, ProjectLease, WorkflowCapabilities, WorkflowCommand, WorkflowDefinition,
  WorkflowExportProfile, WorkflowHostPort, WorkflowOutcome, WorkflowReceipt, WorkflowRun, WorkflowWorkspace} from './contracts.ts';

const capabilities: WorkflowCapabilities = {available: true, can_save: true, can_run: true, can_open_review: true,
  error_policies: {directory_source: ['stop'], managed_import: ['stop', 'skip'], path_labels: ['stop', 'skip'],
    compatible_preset: ['stop', 'skip', 'keep_continue'], export: ['stop', 'skip']}};
/** Exact source fixture for engine workflow_owner_protocol.RECIPE_PROFILE, never imported/executed. */
const nestedProfile = (): WorkflowExportProfile => ({profile: 'lrt.workflow-export.jpeg-srgb.v1',
  export_options: {format: 'jpg', quality: 95, tile: 1024, bit_depth: 8, scale: 1, upscale_backend: 'lanczos3',
    sharpen: 0, output_profile: 'srgb', metadata_include_gps: false, conflict_policy: 'skip_and_report', tiff_compression: 'deflate'},
  destination: {mode: 'chosen_root', retain_hierarchy: false, conflict: 'ask', create_missing: false}, watermark: null, layout: null});
function definition(): WorkflowDefinition {
  const value = newDefinition('workflow-a');
  value.storage_revision = 'stored-1';
  value.graph.nodes[0].operation = {kind: 'directory_source', root: '/incoming',
    recursive: false, include_existing: false, extensions: ['jpg'], settle_ms: 1000};
  value.graph.nodes[1].operation = {kind: 'managed_import', project_id: 'project-a', project_path: '/projects/a.lrt', managed_root: '/managed'};
  value.graph.nodes[2].operation = {kind: 'export', output_root: '/output', recipe_sha256: 'a'.repeat(64)};
  return value;
}
const lease = (): ProjectLease => ({lease_id: 'lease-a', project_id: 'project-a', project_path: '/projects/a.lrt', saved: true, dedicated: true,
  expires_at: new Date(Date.now() + 600_000).toISOString()});
const run = (status: WorkflowRun['status'] = 'running', sequence = 1): WorkflowRun => ({run_id: 'run-a', workflow_id: 'workflow-a', graph_revision: 1,
  status, sequence, lease_id: 'lease-a', started_at: '2026-10-25T00:00:00Z', total_files: 1, completed_files: status === 'complete' ? 1 : 0,
  files: [], records_truncated: false, diagnostics: [], review: null, effects_settled: ['stopped', 'complete', 'failed'].includes(status)});
function harness() {
  let serial = 0;
  const submits: {request_id: string; command: WorkflowCommand}[] = [], queries: string[] = [];
  let activeRun: WorkflowRun | null = null;
  const receipts = new Map<string, WorkflowReceipt>();
  const workspace: WorkflowWorkspace = {port_version: 1, workspace_revision: 1, capabilities, definitions: [], runs: [], active_run: null, unresolved_requests: []};
  const host: WorkflowHostPort = {
    version: 1, scope_id: `fixture-${Math.random()}`,
    readWorkspace: async () => ({...workspace, active_run: activeRun}),
    readDefinition: async () => definition(),
    preflight: async input => ({workflow_id: input.graph.workflow_id, graph_revision: input.graph.revision, lease_id: input.lease_id,
      preflight_token: 'preflight-a', valid_until: new Date(Date.now() + 300_000).toISOString(), can_start: true, diagnostics: []}),
    submit: async input => {
      submits.push(input);
      let outcome: WorkflowOutcome;
      switch (input.command.kind) {
        case 'acquire_project_lease': workspace.lease = lease(); outcome = {kind: input.command.kind, lease: workspace.lease}; break;
        case 'release_project_lease': workspace.lease = null; outcome = {kind: input.command.kind, released: true, lease_id: input.command.lease_id}; break;
        case 'save_definition': outcome = {kind: input.command.kind, definition: {...input.command.definition, storage_revision: 'stored-2'}}; break;
        case 'start': activeRun = run(); outcome = {kind: input.command.kind, run: activeRun}; break;
        case 'stop': activeRun = run('stopped', 2); outcome = {kind: input.command.kind, run: activeRun}; break;
        case 'review_step': outcome = {kind: input.command.kind, run_id: input.command.run_id, operation_id: input.command.operation_id, step: input.command.step, message: 'Fixture step only'}; break;
        case 'open_review': outcome = {kind: input.command.kind, opened: true, message: 'Fixture review view opened; no approval.'}; break;
      }
      const receipt: WorkflowReceipt = {request_id: input.request_id, command_kind: input.command.kind, status: 'succeeded', outcome};
      receipts.set(input.request_id, receipt); return receipt;
    },
    queryRequest: async id => {queries.push(id); const receipt = receipts.get(id); if (!receipt) throw new Error('Fixture receipt missing'); return receipt;},
    readRun: async () => activeRun ?? run(),
  };
  const controller = new WorkflowController(host, definition(), () => `request-${++serial}`);
  return {controller, host, submits, queries, workspace, receipts, setRun: (next: WorkflowRun | null) => {activeRun = next;}};
}
async function ready(h: ReturnType<typeof harness>) {await h.controller.refresh(); await h.controller.acquireLease(); await h.controller.check();}

test('minimal source/import/export graph needs no invented preset', () => {
  assert.deepEqual(validateGraph(definition().graph, capabilities), []);
  assert.equal(newDefinition('new-a').graph.nodes.length, 3);
  const source = newDefinition('new-a').graph.nodes[0].operation;
  assert.equal(source.kind === 'directory_source' && source.include_existing, false);
});
test('edge guards refuse source input, export output, duplicate and cycle', () => {
  const graph = definition().graph;
  assert.ok(edgeProblem(graph, {from: 'node-2', to: 'node-1'}));
  assert.ok(edgeProblem(graph, {from: 'node-3', to: 'node-2'}));
  assert.ok(edgeProblem(graph, {from: 'node-1', to: 'node-2'}));
  assert.ok(edgeProblem(graph, {from: 'node-1', to: 'node-3'}));
  assert.ok(validateGraph({...graph, edges: []}).some(item => item.code === 'chain'));
  graph.nodes.push({id: 'labels', error_policy: 'stop', operation: {kind: 'path_labels', rules: [{target: 'filename', contains: 'a', label: 'A'}]}});
  graph.edges = [{from: 'node-2', to: 'labels'}];
  assert.match(edgeProblem(graph, {from: 'labels', to: 'node-2'})!, /循环/);
});
test('all root overlaps and project-inside-root are rejected lexically', () => {
  assert.equal(pathsOverlap('/incoming', '/incoming/out'), true);
  assert.equal(pathsOverlap('/incoming', '/incoming-other'), false);
  assert.equal(pathsOverlap('C:\\Photos', 'c:\\photos\\out'), true);
  const graph = definition().graph;
  graph.nodes[2].operation = {kind: 'export', output_root: '/managed/results', recipe_sha256: 'a'.repeat(64)};
  assert.ok(validateGraph(graph).some(item => item.code === 'managed_export_overlap'));
  graph.nodes[1].operation = {kind: 'managed_import', project_id: 'project-a', project_path: '/incoming/a.lrt', managed_root: '/managed'};
  assert.ok(validateGraph(graph).some(item => item.code === 'project_inside_root'));
});
test('policy and label conditions fail closed', () => {
  const graph = definition().graph;
  graph.nodes[0].error_policy = 'skip';
  assert.ok(validateGraph(graph, capabilities).some(item => item.code === 'source_must_stop'));
  graph.nodes[0].error_policy = 'stop';
  graph.nodes.push({id: 'preset', error_policy: 'keep_continue', operation: {kind: 'compatible_preset', preset_id: 'preset-a', preset_sha256: 'b'.repeat(64), when_all_labels: ['unproduced']}});
  graph.edges = [{from: 'node-1', to: 'node-2'}, {from: 'node-2', to: 'preset'}, {from: 'preset', to: 'node-3'}];
  assert.ok(validateGraph(graph, capabilities).some(item => item.code === 'unknown_label'));
  assert.ok(validateGraph(graph, {...capabilities, error_policies: {}}).some(item => item.code === 'policy_unavailable'));
});
test('preflight is invalidated by edits and expired lease blocks start', async () => {
  const h = harness(); await ready(h);
  assert.equal(h.controller.canStart(), true);
  assert.equal(leaseMatches(definition().graph, {...lease(), expires_at: '2000-01-01T00:00:00Z'}), false);
  h.controller.updateDraft(value => ({...value, description: 'changed'}));
  assert.equal(h.controller.getState().preflight, null);
  assert.equal(h.controller.canStart(), false);
});
test('revision, path, lowercase fingerprint and settling boundaries match core', () => {
  const graph = definition().graph;
  graph.revision = 0;
  graph.nodes[0].operation = {kind: 'directory_source', root: '/incoming/../incoming', recursive: true, include_existing: false,
    extensions: ['JPG', 'jpg', 'jpg'], settle_ms: 249};
  graph.nodes[2].operation = {kind: 'export', output_root: '/output', recipe_sha256: 'A'.repeat(64)};
  const codes = validateGraph(graph).map(item => item.code);
  for (const code of ['graph_identity', 'absolute_path', 'extensions', 'settle', 'recipe']) assert.ok(codes.includes(code));
});
test('unknown start receipt queries the identical request, never replays start', async () => {
  const h = harness(); await ready(h);
  const realSubmit = h.host.submit;
  h.host.submit = async input => {
    const receipt = await realSubmit(input);
    if (input.command.kind !== 'start') return receipt;
    const unknown: WorkflowReceipt = {request_id: input.request_id, command_kind: 'start', status: 'unknown'};
    h.receipts.set(input.request_id, unknown); return unknown;
  };
  await h.controller.start();
  const original = h.controller.getState().pending[0].request_id;
  await h.controller.start(); await h.controller.tick(); await h.controller.tick();
  assert.equal(h.submits.filter(item => item.command.kind === 'start').length, 1);
  assert.deepEqual(h.queries, [original, original]);
  assert.equal(h.controller.editingLocked, true);
  h.receipts.set(original, {request_id: original, command_kind: 'start', status: 'succeeded', outcome: {kind: 'start', run: run()}});
  await h.controller.queryPending();
  assert.equal(h.controller.getState().active_run?.status, 'running');
});
test('mismatched terminal receipt keeps recovery lock', async () => {
  const h = harness(); await ready(h);
  h.host.submit = async input => ({request_id: `${input.request_id}-wrong`, command_kind: input.command.kind, status: 'cancelled', message: 'not the original'});
  await h.controller.start();
  assert.equal(h.controller.getState().pending.length, 1);
  assert.equal(h.controller.getState().active_run, null);
});
test('disposal ignores late mutation result without cancelling or replaying it', async () => {
  const h = harness(); await ready(h);
  let finish!: (receipt: WorkflowReceipt) => void;
  let requestId = '';
  h.host.submit = input => {requestId = input.request_id; return new Promise(resolve => {finish = resolve;});};
  const pending = h.controller.start(); h.controller.dispose();
  finish({request_id: requestId, command_kind: 'start', status: 'succeeded', outcome: {kind: 'start', run: run()}});
  await pending;
  assert.equal(h.controller.getState().active_run, null);
  assert.equal(h.controller.getState().pending.length, 1);
});
test('opening actual review never approves it or resumes the run', async () => {
  const h = harness();
  h.setRun({...run('paused'), review: {review_id: 'review-a', file_id: 'file-a', node_id: 'preset', family: 'reviewed-family', reason: 'Actual retained preview required'}});
  await h.controller.refresh(); await h.controller.openReview(); await h.controller.tick();
  assert.equal(h.controller.getState().active_run?.status, 'paused');
  assert.deepEqual(h.submits.map(item => item.command.kind), ['open_review']);
});
test('stop is a host action and only authoritative terminal run unlocks editing', async () => {
  const h = harness(); await ready(h); await h.controller.start();
  assert.equal(h.controller.editingLocked, true);
  await h.controller.stop();
  assert.equal(h.controller.getState().active_run?.status, 'stopped');
  assert.equal(h.controller.editingLocked, false);
});
test('known run can be stopped while original start is unknown; late start cannot resurrect it', async () => {
  const h = harness(); await ready(h);
  const originalSubmit = h.host.submit;
  h.host.submit = async input => {
    const result = await originalSubmit(input);
    if (input.command.kind !== 'start') return result;
    const unknown: WorkflowReceipt = {request_id: input.request_id, command_kind: 'start', status: 'unknown'};
    h.receipts.set(input.request_id, unknown); return unknown;
  };
  await h.controller.start();
  const startId = h.controller.getState().pending[0].request_id;
  await h.controller.refresh();
  assert.equal(h.controller.canStop(), true);
  await h.controller.stop(); await h.controller.stop();
  assert.equal(h.submits.filter(item => item.command.kind === 'stop').length, 1);
  assert.equal(h.controller.getState().active_run?.status, 'stopped');
  h.receipts.set(startId, {request_id: startId, command_kind: 'start', status: 'succeeded', outcome: {kind: 'start', run: run('running', 1)}});
  await h.controller.queryPending();
  assert.equal(h.controller.getState().active_run?.status, 'stopped');
});
test('dismissed run inspection cannot be reopened by its late response', async () => {
  const h = harness(); await h.controller.refresh();
  let finish!: (value: WorkflowRun) => void;
  h.host.readRun = () => new Promise(resolve => {finish = resolve;});
  const read = h.controller.inspectRun('run-a');
  h.controller.clearInspection(); finish(run('complete'));
  await read; assert.equal(h.controller.getState().inspected_run, null);
});
test('stopped dispatch with unsettled effects remains locked and queries original owner progress', async () => {
  const h = harness(); await ready(h); await h.controller.start();
  const originalSubmit = h.host.submit;
  h.host.submit = async input => {
    const receipt = await originalSubmit(input);
    if (input.command.kind !== 'stop') return receipt;
    const unsettled = {...run('stopped', 2), effects_settled: false}; h.setRun(unsettled);
    return {request_id: input.request_id, command_kind: 'stop', status: 'succeeded', outcome: {kind: 'stop', run: unsettled}};
  };
  await h.controller.stop();
  assert.equal(h.controller.editingLocked, true);
  assert.equal(h.controller.canStop(), false);
  h.setRun(run('stopped', 3)); await h.controller.tick();
  assert.equal(h.controller.editingLocked, false);
});
test('foreign preflight cannot authorize current graph', async () => {
  const h = harness(); await h.controller.refresh(); await h.controller.acquireLease();
  h.host.preflight = async input => ({workflow_id: 'other', graph_revision: input.graph.revision, lease_id: input.lease_id,
    preflight_token: 'foreign', valid_until: new Date(Date.now() + 300_000).toISOString(), can_start: true, diagnostics: []} satisfies PreflightReport);
  await h.controller.check();
  assert.equal(h.controller.canStart(), false);
  assert.equal(h.controller.getState().preflight, null);
});
test('unused current-project lease is explicitly released and draft replacement cannot hide it', async () => {
  const h = harness(); await h.controller.refresh(); await h.controller.acquireLease();
  assert.equal(h.controller.canReleaseLease(), true);
  h.controller.newWorkflow();
  assert.equal(h.controller.getState().lease?.lease_id, 'lease-a');
  assert.equal(h.controller.canReleaseLease(), true);
  await h.controller.releaseLease();
  assert.equal(h.controller.getState().lease, null);
  assert.equal(h.controller.getState().preflight, null);
  assert.deepEqual(h.submits.at(-1)?.command, {kind: 'release_project_lease', lease_id: 'lease-a'});
});
test('workspace restores held lease and refuses a foreign persistent host scope', async () => {
  const h = harness(); h.workspace.lease = lease(); h.workspace.host_scope_id = h.host.scope_id;
  await h.controller.refresh();
  assert.equal(h.controller.canReleaseLease(), true);
  h.workspace.host_scope_id = 'foreign-scope'; await h.controller.refresh();
  assert.equal(h.controller.getState().ready, false);
  assert.equal(h.controller.canReleaseLease(), false);
});
test('release is unavailable during running or unsettled stopped effects', async () => {
  const h = harness(); await ready(h); await h.controller.start();
  assert.equal(h.controller.canReleaseLease(), false);
  h.setRun({...run('stopped', 2), effects_settled: false}); await h.controller.tick();
  assert.equal(h.controller.canReleaseLease(), false);
  h.setRun(run('stopped', 3)); await h.controller.tick();
  assert.equal(h.controller.canReleaseLease(), true);
});
test('unknown release retains lease and only queries the original request', async () => {
  const h = harness(); await h.controller.refresh(); await h.controller.acquireLease();
  h.host.submit = async input => {
    h.submits.push(input);
    const receipt: WorkflowReceipt = {request_id: input.request_id, command_kind: input.command.kind, status: 'unknown'};
    h.receipts.set(input.request_id, receipt); return receipt;
  };
  await h.controller.releaseLease();
  const originalId = h.controller.getState().pending[0].request_id;
  await h.controller.releaseLease(); await h.controller.queryPending();
  assert.equal(h.controller.getState().lease?.lease_id, 'lease-a');
  assert.equal(h.submits.filter(item => item.command.kind === 'release_project_lease').length, 1);
  assert.deepEqual(h.queries, [originalId]);
});
test('returned engine profile is explicit draft-only adoption and invalidates preflight', async () => {
  const h = harness();
  h.workspace.recipe_sha256 = 'c'.repeat(64);
  h.workspace.recipe_profile = nestedProfile();
  await ready(h);
  assert.deepEqual(h.controller.getState().export_profile?.recipe_profile, nestedProfile());
  assert.notEqual(h.controller.getState().export_profile?.recipe_profile, h.workspace.recipe_profile);
  assert.notEqual(h.controller.getState().export_profile?.recipe_profile.export_options, h.workspace.recipe_profile.export_options);
  const oldRevision = h.controller.getState().draft.graph.revision;
  const before = h.controller.getState().draft.graph.nodes.find(node => node.operation.kind === 'export')!.operation;
  assert.equal(before.kind === 'export' && before.recipe_sha256, 'a'.repeat(64));
  h.controller.useReturnedExportProfile();
  const state = h.controller.getState();
  const after = state.draft.graph.nodes.find(node => node.operation.kind === 'export')!.operation;
  assert.equal(after.kind === 'export' && after.recipe_sha256, 'c'.repeat(64));
  assert.equal(state.draft.graph.revision, oldRevision + 1);
  assert.equal(state.dirty, true);
  assert.equal(state.preflight, null);
  assert.equal(h.controller.canStart(), false);
  assert.deepEqual(h.submits.map(item => item.command.kind), ['acquire_project_lease']);
});
test('missing or malformed real profile cannot manufacture a recipe hash', async () => {
  const h = harness();
  h.workspace.recipe_sha256 = 'not-a-hash'; h.workspace.recipe_profile = nestedProfile();
  await h.controller.refresh();
  const original = structuredClone(h.controller.getState().draft);
  h.controller.useReturnedExportProfile();
  assert.equal(h.controller.getState().export_profile, null);
  assert.deepEqual(h.controller.getState().draft, original);
});
test('profile discovery polls only while host says the real read is pending', async () => {
  const h = harness(); let reads = 0;
  const original = h.host.readWorkspace;
  h.host.readWorkspace = async () => {reads += 1; return original();};
  h.workspace.recipe_profile_pending = true;
  await h.controller.refresh(); await h.controller.tick();
  assert.equal(reads, 2);
  h.workspace.recipe_profile_pending = false; h.workspace.recipe_sha256 = 'c'.repeat(64); h.workspace.recipe_profile = nestedProfile();
  await h.controller.tick(); await h.controller.tick();
  assert.equal(reads, 3);
  assert.equal(h.controller.getState().export_profile?.recipe_sha256, 'c'.repeat(64));
});
test('partial, unknown, nonfinite or altered nested profiles fail closed without flattening', async () => {
  const realShape = nestedProfile();
  const invalid: unknown[] = [
    {format: 'jpeg'},
    {...realShape, export_options: {format: 'jpg', quality: 95}},
    {...realShape, export_options: {...realShape.export_options, extra: 'not-declared'}},
    {...realShape, export_options: {...realShape.export_options, sharpen: Infinity}},
    {...realShape, destination: {...realShape.destination, create_missing: true}},
    {...realShape, layout: {}},
    {...realShape, profile: 'x'.repeat(9000)},
  ];
  for (const profile of invalid) {
    const h = harness(); h.workspace.recipe_sha256 = 'c'.repeat(64);
    h.workspace.recipe_profile = profile as WorkflowExportProfile;
    await h.controller.refresh();
    const before = structuredClone(h.controller.getState().draft);
    h.controller.useReturnedExportProfile();
    assert.equal(h.controller.getState().export_profile, null);
    assert.deepEqual(h.controller.getState().draft, before);
  }
});

test('handoff pauses Stop and requires both verified displayed images plus explicit checkbox before approval', async () => {
  const {handoffFixture, pageFixture} = await import('./presetReviewFixture.unrun.test.ts');
  const {reviewKey} = await import('./presetReview.ts');
  const h = harness(), handoff = handoffFixture();
  h.setRun({...run('paused', 2), handoff}); h.host.readReviewImage = async input => pageFixture(input);
  await h.controller.refresh();
  assert.equal(h.controller.canStop(), false);
  assert.equal(h.controller.canReviewStep('approve'), false);
  await h.controller.reviewStep('approve'); assert.equal(h.submits.length, 0);
  await h.controller.loadReviewImages();
  const key = reviewKey('run-a', handoff);
  h.controller.acknowledgeReview(key, true); assert.equal(h.controller.canReviewStep('approve'), false);
  h.controller.reviewImageDisplayed(key, 'before', true, 2, 2);
  h.controller.reviewImageDisplayed(key, 'after', false, 2, 2);
  h.controller.acknowledgeReview(key, true); assert.equal(h.controller.canReviewStep('approve'), false);
  h.controller.reviewImageDisplayed(key, 'after', true, 2, 2);
  assert.equal(h.controller.canReviewStep('approve'), false);
  h.controller.acknowledgeReview(key, true); assert.equal(h.controller.canReviewStep('approve'), true);
  await h.controller.reviewStep('approve');
  assert.equal(h.submits.length, 1); assert.equal(h.submits[0].command.kind, 'review_step');
  assert.equal(h.controller.canReviewStep('approve'), false);
});
test('handoff target changes and panel dismissal revoke prior display acknowledgement', async () => {
  const {handoffFixture, pageFixture} = await import('./presetReviewFixture.unrun.test.ts');
  const {reviewKey} = await import('./presetReview.ts');
  const h = harness(), handoff = handoffFixture();
  h.setRun({...run('paused', 2), handoff}); h.host.readReviewImage = async input => pageFixture(input);
  await h.controller.refresh(); await h.controller.loadReviewImages();
  const key = reviewKey('run-a', handoff);
  for (const side of ['before', 'after'] as const) h.controller.reviewImageDisplayed(key, side, true, 2, 2);
  h.controller.acknowledgeReview(key, true); h.controller.clearReviewPresentation(key);
  assert.equal(h.controller.canReviewStep('approve'), false);
  h.setRun({...run('paused', 3), handoff: {...handoff, phase: 'unknown'}}); await h.controller.tick();
  for (const step of ['open_target', 'approve', 'save_project', 'return_target'] as const) assert.equal(h.controller.canReviewStep(step), false);
  assert.equal(h.submits.length, 0);
});
