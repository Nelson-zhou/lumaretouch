// SPDX-License-Identifier: GPL-3.0-or-later
// UNRUN: authored for Qoder's local verification. No test/build/compiler was run here.
import test from 'node:test';
import assert from 'node:assert/strict';
import {CreativeLayerClient} from './client.ts';
import {checkedCreativeDocument, eligibleParents, layerLocked, layerRows, previewMatches,
  type CreativeAuthority, type CreativeDocument, type CreativeLayer, type CreativePorts,
  type CreativeReceipt, type CreativeRequest} from './model.ts';

const layer = (id: string, options: Partial<CreativeLayer> = {}): CreativeLayer => ({
  id, name: id, kind: 'image', parent_id: null, asset_id: `fixture:${id}`, visible: true, locked: false,
  opacity: 1, blend: 'normal', mask_id: null,
  transform: {x: 0, y: 0, scale_x: 1, scale_y: 1, rotation: 0, flip_x: false, flip_y: false}, ...options,
});
const document = (revision = 4): CreativeDocument => ({schema: 1, document_id: 'fixture-document', source_uid: 'fixture-source',
  source_asset: 'fixture:source-asset', revision, canvas: {width: 200, height: 100, dpi: 300}, selected_id: 'top',
  layers: [layer('bottom'), layer('top')],
});
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => {resolve = done;}); return {promise, resolve};
};
function harness(ports: CreativePorts = {}) {
  let authority: CreativeAuthority | null = {document: document(), ownership_token: 'fixture-owner', busy: false};
  let id = 0;
  const client = new CreativeLayerClient(() => authority, () => ports, () => `request-${++id}`);
  return {client, ports, get authority() {return authority;},
    setAuthority(next: CreativeAuthority | null) {authority = next; client.synchronize();},
    revision(revision: number) {authority = {...authority!, document: {...authority!.document, revision}}; client.synchronize();}};
}

test('snapshot validation preserves exact modes/values and rejects broken graph or missing assets', () => {
  const source = document(); assert.deepEqual(checkedCreativeDocument(source), source);
  assert.throws(() => checkedCreativeDocument({...source, layers: [layer('top', {blend: 'overlay' as never})]}));
  assert.throws(() => checkedCreativeDocument({...source, layers: [layer('top', {asset_id: null})]}));
  assert.throws(() => checkedCreativeDocument({...source, layers: [layer('top', {opacity: 1.01})]}));
  assert.throws(() => checkedCreativeDocument({...source, layers: [layer('top', {parent_id: 'missing'})]}));
  assert.throws(() => checkedCreativeDocument({...source, layers: [layer('top', {kind: 'group', asset_id: null, parent_id: 'top'})]}));
  assert.throws(() => checkedCreativeDocument({...source, selected_id: 'missing'}));
});
test('stack is top-to-bottom for each parent; descendant cannot become its own ancestor', () => {
  const value: CreativeDocument = {...document(), selected_id: 'child', layers: [layer('bottom'),
    layer('group', {kind: 'group', asset_id: null, locked: true}), layer('child', {parent_id: 'group'}),
    layer('nested', {kind: 'group', asset_id: null, parent_id: 'group'})]};
  assert.deepEqual(layerRows(value).map(row => [row.layer.id, row.depth]), [['group', 0], ['nested', 1], ['child', 1], ['bottom', 0]]);
  assert.equal(layerLocked(value, value.layers[2]), true);
  assert.deepEqual(eligibleParents(value, value.layers[1]), []);
});
test('a command carries the current ownership/revision and duplicate click is fenced', async () => {
  const wait = deferred<CreativeReceipt>(); let request!: CreativeRequest; let count = 0;
  const h = harness({command: async value => {request = value; ++count; return wait.promise;}});
  const work = h.client.execute({action: 'rename', layer_id: 'top', name: 'Renamed'});
  await h.client.execute({action: 'delete', layer_id: 'top'});
  assert.equal(count, 1); assert.equal(h.client.getState().phase, 'sending');
  const sent = request;
  assert.equal(sent.expected_revision, 4); assert.equal(sent.ownership_token, 'fixture-owner');
  wait.resolve({...sent, status: 'applied', revision: 5}); await work;
  assert.equal(h.client.getState().phase, 'awaiting_snapshot');
  assert.equal(h.authority!.document.layers[1].name, 'top', 'client does not mutate the authoritative document');
  h.revision(5); assert.equal(h.client.getState().phase, 'idle');
});
test('newer authoritative snapshot arriving before receipt is retained', async () => {
  const wait = deferred<CreativeReceipt>(); let sent!: CreativeRequest;
  const h = harness({command: value => {sent = value; return wait.promise;}});
  const work = h.client.execute({action: 'select', layer_id: null});
  h.revision(7); wait.resolve({...sent, status: 'applied', revision: 5}); await work;
  assert.equal(h.authority!.document.revision, 7); assert.equal(h.client.getState().phase, 'idle');
});
test('transport failure is uncertain and only querying the same request unlocks it', async () => {
  let count = 0, sent!: CreativeRequest, query!: CreativeRequest;
  const h = harness({command: async value => {sent = value; ++count; throw Error('Connection lost');},
    reconcile: async value => {query = value; return {...value, status: 'rejected', message: 'Not committed'};}});
  await h.client.execute({action: 'delete', layer_id: 'top'});
  assert.equal(h.client.getState().phase, 'uncertain');
  await h.client.execute({action: 'delete', layer_id: 'top'}); assert.equal(count, 1);
  await h.client.reconcile(); assert.deepEqual(query, {document_id: sent.document_id, source_uid: sent.source_uid,
    ownership_token: sent.ownership_token, expected_revision: sent.expected_revision, request_id: sent.request_id});
  assert.equal(h.client.getState().phase, 'idle');
});
test('mismatched receipt stays uncertain; a changed ownership token fences old completion', async () => {
  const h = harness({command: async request => ({...request, request_id: 'wrong-request', status: 'applied', revision: 5})});
  await h.client.execute({action: 'lock', layer_id: 'top', locked: true});
  assert.equal(h.client.getState().phase, 'uncertain');
  const wait = deferred<CreativeReceipt>(); let sent!: CreativeRequest;
  h.setAuthority({...h.authority!, ownership_token: 'next-owner'});
  h.ports.command = request => {sent = request; return wait.promise;};
  const work = h.client.execute({action: 'select', layer_id: null});
  h.setAuthority({...h.authority!, ownership_token: 'third-owner'});
  const before = h.client.getState(); wait.resolve({...sent, status: 'applied', revision: 5}); await work;
  assert.deepEqual(h.client.getState(), before);
});

test('history closing the creative document invalidates its envelope without recreating state', async () => {
  const wait = deferred<CreativeReceipt>(); let request!: CreativeRequest; let commands = 0;
  const h = harness({undo: value => {request = value; return wait.promise;},
    command: async value => {++commands; return {...value, status: 'applied', revision: 5};}});
  const work = h.client.undo();
  h.setAuthority(null);
  wait.resolve({...request, status: 'applied', revision: 0}); await work;
  assert.equal(h.authority, null); assert.equal(h.client.getState().phase, 'idle');
  await h.client.execute({action: 'select', layer_id: null});
  assert.equal(commands, 0, 'an absent authoritative document cannot reuse the old request envelope');
});
test('regressed host revision prevents commands until latest state is restored', async () => {
  let count = 0;
  const h = harness({command: async request => {++count; return {...request, status: 'no_change', revision: request.expected_revision};}});
  h.revision(9); h.revision(8); assert.equal(h.client.getState().phase, 'stale');
  await h.client.execute({action: 'select', layer_id: null}); assert.equal(count, 0);
  h.revision(9); await h.client.execute({action: 'select', layer_id: null}); assert.equal(count, 1);
});
test('undo restoring an older revision waits for its explicit new ownership token', async () => {
  const h = harness({undo: async request => ({...request, status: 'applied', revision: 2, next_ownership_token: 'history-owner'})});
  await h.client.undo();
  assert.equal(h.client.getState().phase, 'awaiting_snapshot', 'old owner revision 4 cannot acknowledge new owner revision 2');
  h.setAuthority({...h.authority!, ownership_token: 'history-owner', document: document(2)});
  assert.equal(h.client.getState().phase, 'idle');
});
test('busy or missing ports never claim success and stale preview cannot be returned', async () => {
  let count = 0;
  const h = harness({returnNew: async request => {++count; return {...request, status: 'applied', revision: request.expected_revision};}});
  await h.client.execute({action: 'select', layer_id: null}); assert.match(h.client.getState().message, /未接入/);
  const preview = {document_id: 'fixture-document', source_uid: 'fixture-source', ownership_token: 'fixture-owner',
    revision: 3, render_id: 'fixture-render', url: 'blob:fixture-only-not-a-real-image'};
  assert.equal(previewMatches(preview, h.authority!), false);
  await h.client.returnImage('new', preview); assert.equal(count, 0);
  h.setAuthority({...h.authority!, busy: true}); await h.client.returnImage('new', {...preview, revision: 4}); assert.equal(count, 0);
  h.setAuthority({...h.authority!, busy: false}); await h.client.returnImage('new', {...preview, revision: 4}); assert.equal(count, 1);
});
