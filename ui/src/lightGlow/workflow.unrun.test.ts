// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Never imported, executed, typechecked or built during this change.
// Deliberately synthetic fixtures exercise contracts only, not native rendering quality or UI visibility.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {deflateSync} from 'node:zlib';
import {LightGlowController} from './controller.ts';
import {verifyGlowCoverage, verifyGlowPng} from './imagery.ts';
import {GLOW_MODES, GLOW_OPERATION, GLOW_MATH, glowPresetRecipe, glowReviewKey, matchingGlowPreset,
  validGlowCapability, validGlowContext, validGlowCurrentReply, validGlowRecipe, validGlowReview, validGlowWriteCommand,
  type GlowCapability, type GlowContext, type GlowPng, type GlowPreviewCommand, type GlowReceipt, type GlowReview,
  type GlowWriteCommand, type LightGlowPort} from './model.ts';

const hash = (bytes: Uint8Array): string => createHash('sha256').update(bytes).digest('hex');
const digest = (character: string): string => character.repeat(64);
function crc(bytes: Uint8Array): number {
  let value = 0xffffffff;
  for (const byte of bytes) {value ^= byte; for (let bit = 0; bit < 8; bit++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);}
  return (value ^ 0xffffffff) >>> 0;
}
function png(red = 20, alpha: number | null = null): GlowPng {
  const chunk = (kind: string, payload: Buffer): Buffer => {
    const body = Buffer.concat([Buffer.from(kind), payload]), head = Buffer.alloc(4), tail = Buffer.alloc(4);
    head.writeUInt32BE(payload.length); tail.writeUInt32BE(crc(body)); return Buffer.concat([head, body, tail]);
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(2, 0); header.writeUInt32BE(2, 4); header[8] = 8; header[9] = alpha === null ? 2 : 6;
  const pixel = alpha === null ? [red, 30, 40] : [0, 255, 0, alpha], row = [0, ...pixel, ...pixel];
  const bytes = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.from([...row, ...row]))), chunk('IEND', Buffer.alloc(0))]);
  return {mime: 'image/png', width: 2, height: 2, sha256: hash(bytes), base64: bytes.toString('base64')};
}
const capability = (): GlowCapability => ({version: 1, operation_id: GLOW_OPERATION, status: 'available', abi: 1, math_version: GLOW_MATH, reason: null, modes: [...GLOW_MODES]});
function context(): GlowContext {
  return {version: 1, operation_id: GLOW_OPERATION, session_id: 'session',
    owner: {document_id: 'doc', document_epoch: 'epoch', document_revision: '2', source: {sha256: digest('1'), width: 2, height: 2, orientation: 'exif_normalized_once'}},
    source_evidence: {kind: 'current_full_edited_source', capture_version: 3, original_sha256: digest('2'), people_graph_sha256: digest('3'),
      repair_stack_sha256: digest('4'), document_revision: '2', load_id: 'load', capture_token: 'capture'},
    before: png(), capability: capability(), message: ''};
}
function review(command: GlowPreviewCommand, source = context()): GlowReview {
  const neutral = command.recipe.strength === 0;
  return {version: 1, operation_id: GLOW_OPERATION, request_id: command.request_id, session_id: command.session_id, owner: command.owner,
    source_evidence: source.source_evidence, token: 'review', recipe: command.recipe, recipe_sha256: digest('5'),
    result_source_sha256: neutral ? command.owner.source.sha256 : digest('6'), coverage_sha256: digest('7'),
    before: source.before, after: neutral ? source.before : png(70), coverage: png(0, neutral ? 0 : 40), no_change: neutral, notes: []};
}
const identity = (command: GlowWriteCommand) => ({version: 1 as const, operation_id: GLOW_OPERATION, request_id: command.request_id,
  session_id: command.session_id, action: command.action, owner: command.owner, token: command.token, message: ''});
function applied(command: GlowWriteCommand): GlowReceipt {
  if (command.action !== 'apply') throw Error('Wrong fixture command.');
  return {...identity(command), phase: 'done', outcome_unknown: false, outcome: 'applied', result_document_id: 'copy',
    copied_original_document_id: command.owner.document_id, result_revision: '1', result_source_sha256: command.result_source_sha256,
    no_change: command.result_source_sha256 === command.owner.source.sha256};
}
function deferred<T>() {let resolve!: (value: T) => void; const promise = new Promise<T>(done => {resolve = done;}); return {promise, resolve};}
async function setup(overrides: Partial<LightGlowPort> = {}, options: ConstructorParameters<typeof LightGlowController>[1] = {}) {
  let sequence = 0, returned: unknown = null;
  const sent: GlowWriteCommand[] = [], queries: GlowWriteCommand[] = [], previews: GlowPreviewCommand[] = [];
  const port: LightGlowPort = {protocol: 1, refreshCapability: async () => capability(),
    acquireCurrent: async request_id => ({event: 'light_glow_result', request_id, status: 'ready', context: context()}),
    currentStatus: async request_id => ({event: 'light_glow_result', request_id, status: 'unknown', message: 'fixture'}),
    cancelCurrent: async () => {}, cancelReads: async () => {}, checkReads: async () => {}, pendingReads: () => false, subscribe: () => () => {},
    preview: async command => {previews.push(command); return review(command);},
    submit: async command => {sent.push(command); return {...identity(command), phase: 'pending', outcome_unknown: true};},
    receipt: async command => {queries.push(command); return returned;}, ...overrides};
  const controller = new LightGlowController(port, {requestId: () => `request-${++sequence}`, ...options});
  await controller.setContext(context()); controller.sourceLoaded(context().before.sha256, 2, 2, true);
  return {controller, port, sent, queries, previews, setReceipt(value: unknown) {returned = value;}};
}
function showAll(controller: LightGlowController) {
  const value = controller.snapshot().review!;
  for (const side of ['before', 'after', 'coverage'] as const) controller.presented(side, glowReviewKey(value), 2, 2, true);
}

test('mode presets are distinct scalar recipes; unknown vendor numbers are not encoded as official facts', () => {
  const black = glowPresetRecipe('black_mist')!, white = glowPresetRecipe('white_mist')!, glow = glowPresetRecipe('glow')!;
  assert.equal(matchingGlowPreset(black), 'quarter'); assert.equal(matchingGlowPreset(white), 'quarter'); assert.equal(matchingGlowPreset(glow), 'weak');
  assert.notDeepEqual(black, white); assert.notDeepEqual(white, glow);
  assert.equal(glowPresetRecipe('glow', 'quarter'), null); assert.equal(glowPresetRecipe('white_mist', 'strong'), null);
  assert.equal(validGlowRecipe({...black, radius_px: .5}), false); assert.equal(validGlowRecipe({...black, strength: NaN}), false);
  assert.equal(validGlowRecipe({...black, math_identity: 65538}), false); assert.equal(validGlowRecipe({...black, preset: 'quarter'}), false);
  assert.equal(validGlowRecipe({...black, tint: {...black.tint, hue_deg: 181}}), false);
  assert.equal(validGlowCapability({...capability(), modes: ['bloom']}), false);
});
test('full-source evidence, revision and current request identity cannot be laundered by a UI counter', () => {
  const source = context(); assert.ok(validGlowContext(source));
  assert.equal(validGlowContext({...source, source_evidence: {...source.source_evidence, document_revision: '3'}}), false);
  assert.equal(validGlowContext({...source, before: {...source.before, width: 3}}), false);
  assert.equal(validGlowCurrentReply({event: 'light_glow_result', request_id: 'other', status: 'ready', context: source}, 'expected'), false);
  assert.equal(validGlowContext({...source, source_evidence: {...source.source_evidence, capture_version: 2}}), false);
});
test('image structure/hash and RGBA diagnostic coverage are verified separately', async () => {
  assert.equal(await verifyGlowPng(png()), true); assert.equal(await verifyGlowCoverage(png(0, 40)), true);
  assert.equal(await verifyGlowCoverage(png()), false); assert.equal(await verifyGlowPng({...png(), sha256: digest('f')}), false);
  assert.equal(await verifyGlowPng({...png(), width: 3}), false);
});
test('browser decode does not grant approval; all images plus explicit review are required', async () => {
  const {controller: c, sent} = await setup(); await c.preview(); c.acknowledge(true); await c.apply(); assert.equal(sent.length, 0);
  const value = c.snapshot().review!; c.presented('before', glowReviewKey(value), 2, 2, true);
  c.presented('after', glowReviewKey(value), 2, 2, true); c.acknowledge(true); await c.apply(); assert.equal(sent.length, 0);
  showAll(c); c.acknowledge(true); assert.equal(c.canApply(), true);
  c.presented('after', glowReviewKey(value), 0, 0, false); assert.equal(c.canApply(), false);
  showAll(c); c.acknowledge(true); c.releasePresentation(); await c.apply(); assert.equal(sent.length, 0);
});
test('local editing, per-mode drafts and undo/redo retain values but revoke old review', async () => {
  const {controller: c} = await setup();
  c.edit({...c.snapshot().recipe!, strength: .61}); const saved = c.snapshot().recipe;
  c.selectMode('white_mist'); c.selectMode('black_mist'); assert.deepEqual(c.snapshot().recipe, saved);
  await c.preview(); showAll(c); c.acknowledge(true);
  c.edit({...c.snapshot().recipe!, exposure_ev: 1}); assert.equal(c.snapshot().review, null); assert.equal(c.snapshot().reviewed, false);
  c.undo(); assert.deepEqual(c.snapshot().recipe, saved); c.redo(); assert.equal(c.snapshot().recipe!.exposure_ev, 1);
  assert.throws(() => {c.snapshot().recipe!.strength = .99;}, TypeError);
});
test('late preview and mismatched evidence cannot become a current review', async () => {
  const wait = deferred<unknown>(); let command!: GlowPreviewCommand;
  const {controller: c} = await setup({preview: async value => {command = value; return wait.promise;}});
  const work = c.preview(); c.markStale(); wait.resolve(review(command)); await work;
  assert.equal(c.snapshot().review, null); assert.equal(c.snapshot().stale, true);
  const source = context(), expected = {version: 1, operation_id: GLOW_OPERATION, action: 'preview', request_id: 'request', session_id: source.session_id, owner: source.owner, recipe: glowPresetRecipe('glow')!} as const;
  const valid = review(expected, source); assert.ok(validGlowReview(valid, expected, source));
  assert.equal(validGlowReview({...valid, source_evidence: {...valid.source_evidence, load_id: 'old'}}, expected, source), false);
  assert.equal(validGlowReview({...valid, before: png(99)}, expected, source), false);
  assert.equal(validGlowReview({...valid, recipe: {...valid.recipe, scattering: .9}}, expected, source), false);
});
test('pending or unknown apply survives source changes and hide; only original receipt may resolve it', async () => {
  const {controller: c, sent, queries, setReceipt} = await setup();
  await c.preview(); showAll(c); c.acknowledge(true); await c.apply(); assert.equal(sent.length, 1);
  const original = sent[0]; c.releasePresentation(); c.markStale();
  await c.apply(); await c.cancel(); assert.equal(sent.length, 1); await c.check(); assert.equal(c.snapshot().phase, 'unknown');
  assert.deepEqual(queries[0], original);
  await c.setContext({...context(), session_id: 'new'}); assert.equal(c.snapshot().request?.request_id, original.request_id);
  setReceipt({...applied(original), result_document_id: original.owner.document_id}); await c.check(); assert.equal(c.snapshot().phase, 'unknown');
  setReceipt({...applied(original), result_source_sha256: digest('8')}); await c.check(); assert.equal(c.snapshot().phase, 'unknown');
  setReceipt(applied(original)); await c.check(); assert.equal(c.snapshot().phase, 'applied'); assert.equal(sent.length, 1);
  assert.equal(c.snapshot().terminal_refresh, 'not-configured');
});
test('cancel is single-flight and requires its own actual terminal receipt', async () => {
  const wait = deferred<void>();
  const {controller: c, sent, setReceipt} = await setup({cancelReads: () => wait.promise});
  const first = c.cancel(), second = c.cancel(); assert.equal(sent.length, 0); wait.resolve(); await Promise.all([first, second]);
  assert.equal(sent.length, 1); assert.equal(c.snapshot().phase, 'pending'); await c.cancel(); assert.equal(sent.length, 1);
  setReceipt({...identity(sent[0]), phase: 'done', outcome_unknown: false, outcome: 'cancelled'});
  await c.check(); assert.equal(c.snapshot().phase, 'cancelled');
});
test('source update modes are invalid; immutable new-image result identity is not display PNG identity', async () => {
  const {controller: c, sent} = await setup(); await c.preview(); showAll(c); c.acknowledge(true); await c.apply();
  const command = sent[0]; assert.equal(command.action, 'apply'); if (command.action !== 'apply') throw Error('wrong fixture');
  assert.equal(command.return_mode, 'new_image'); assert.notEqual(command.result_source_sha256, command.after_sha256);
  assert.equal(validGlowWriteCommand({...command, return_mode: 'source_image'}), false);
  assert.equal(validGlowWriteCommand({...command, source_path: '/guessed/source.png'}), false);
});
test('neutral source identity remains exact and requires the same review/write discipline', async () => {
  const {controller: c, sent, setReceipt} = await setup();
  c.edit({...c.snapshot().recipe!, strength: 0, exposure_ev: 4, tint: {hue_deg: 180, saturation: 1, lightness: 1}});
  await c.preview(); const value = c.snapshot().review!;
  assert.equal(value.no_change, true); assert.equal(value.result_source_sha256, context().owner.source.sha256);
  showAll(c); c.acknowledge(true); await c.apply(); setReceipt(applied(sent[0])); await c.check();
  assert.equal(c.snapshot().phase, 'applied'); assert.equal(c.snapshot().terminal_receipt?.phase, 'done');
});
test('refresh failure preserves success; retry invokes only read-only refresh, never apply', async () => {
  let refreshes = 0;
  const {controller: c, sent, setReceipt} = await setup({}, {onTerminal: async () => {if (++refreshes === 1) throw Error('refresh unavailable');}});
  await c.preview(); showAll(c); c.acknowledge(true); await c.apply(); setReceipt(applied(sent[0])); await c.check();
  assert.equal(c.snapshot().phase, 'applied'); assert.equal(c.snapshot().terminal_refresh, 'failed');
  await c.refreshTerminal(); assert.equal(c.snapshot().terminal_refresh, 'ready'); assert.equal(refreshes, 2); assert.equal(sent.length, 1);
});
