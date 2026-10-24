// AUTHORED / UNRUN. One-pixel fixture verifies transport bytes, never product quality.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fetchEyeBagBatchImage, type EyeBagBatchImageReply, type EyeBagBatchImageTransport} from './batchTransport';
const base64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGq0AAAAASUVORK5CYII=';
function fixture() {
  const sha256 = createHash('sha256').update(Buffer.from(base64, 'base64')).digest('hex');
  const expected = {mime: 'image/png' as const, width: 1, height: 1, sha256};
  const image = {...expected, base64};
  const request = {preflightToken: 'a'.repeat(32), documentId: 'b'.repeat(32), revision: '20', side: 'before' as const, sha256, requestId: 'read-1'};
  const reply: EyeBagBatchImageReply = {request_id: request.requestId, action: 'eye_bag_visual', success: true,
    preflight_token: request.preflightToken, document_id: request.documentId, revision: request.revision, side: request.side,
    sha256, compact: {...expected}, image};
  const calls: unknown[] = [];
  const api: EyeBagBatchImageTransport = {request: async value => {calls.push(value); return {requested: true};},
    read: async id => ({phase: 'done', request_id: id, result: reply})};
  return {expected, image, request, reply, api, calls};
}
test('each page requires exact token/document/revision/side/request and real PNG bytes', async () => {
  const f = fixture(); assert.deepEqual(await fetchEyeBagBatchImage(f.api, f.request, f.expected), f.image); assert.equal(f.calls.length, 1);
  for (const field of ['action', 'request_id', 'preflight_token', 'document_id', 'revision', 'side', 'sha256']) {
    const invalid = fixture(); (invalid.reply as unknown as Record<string, unknown>)[field] = 'wrong';
    await assert.rejects(fetchEyeBagBatchImage(invalid.api, invalid.request, invalid.expected));
  }
});
test('compact metadata, decoded header, content digest and uncertain results cannot be substituted', async () => {
  for (const mutate of [(r: any) => {r.compact.width = 2;}, (r: any) => {delete r.compact;},
    (r: any) => {r.image.base64 = 'iVBORbad';}, (r: any) => {r.image.height = 2;},
    (r: any) => {r.outcome_unknown = true;}, (r: any) => {r.success = false;}]) {
    const f = fixture(); mutate(f.reply); await assert.rejects(fetchEyeBagBatchImage(f.api, f.request, f.expected));
  }
});
test('cancelled read submits no new image page and never sends a mutation', async () => {
  const f = fixture(); await assert.rejects(fetchEyeBagBatchImage(f.api, f.request, f.expected, () => false)); assert.equal(f.calls.length, 0);
});

test('read request rejects forged action, support payload and malformed coordinates before queueing', async () => {
  for (const patch of [{action: 'commit'}, {support: {}}, {preflightToken: 'wrong'}, {documentId: 'wrong'}, {revision: '9007199254740992'}]) {
    const f = fixture(); await assert.rejects(fetchEyeBagBatchImage(f.api, {...f.request, ...patch}, f.expected)); assert.equal(f.calls.length, 0);
  }
});
test('late image from a cancelled generation cannot become displayed evidence', async () => {
  const f = fixture(); let live = true;
  f.api.read = async id => {live = false; return {phase: 'done', request_id: id, result: f.reply};};
  await assert.rejects(fetchEyeBagBatchImage(f.api, f.request, f.expected, () => live)); assert.equal(f.calls.length, 1);
});
