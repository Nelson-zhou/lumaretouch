// UNRUN source fixtures. Local test execution is intentionally not claimed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {explicitRequest, validInventory, validInventoryEntry} from './transferInventory.ts';
import {inventory, entry, selection, sourceContext, sourceRef, targetId} from './transferFixtureData.test.ts';

test('inventory is exact and does not auto-select even a single verified target', () => {
  const data = inventory();
  assert.equal(validInventory(data, 'read-1', [targetId], sourceContext()), true);
  assert.equal(explicitRequest(data, [targetId], sourceRef, selection, {}), undefined);
  assert.equal(explicitRequest(data, [targetId], sourceRef, selection, {[targetId]: [sourceRef]})?.targets.length, 1);
});
test('missing, duplicate, unrequested or stale inventory fails closed', () => {
  for (const mutate of [
    (v: any) => {v.targets = [];}, (v: any) => {v.targets.push(structuredClone(v.targets[0]));},
    (v: any) => {v.targets[0].document.document_id = 'f'.repeat(32);},
    (v: any) => {v.source.document.revision++;}, (v: any) => {v.source.state_revision++;},
    (v: any) => {v.source.faces[0].face_ref.analysis_revision++;},
    (v: any) => {v.source.source_preview.source_sha256 = 'f'.repeat(64);},
    (v: any) => {v.request_id = 'another-read';}, (v: any) => {v.action = 'preflight';},
  ]) {
    const value = structuredClone(inventory()); mutate(value);
    assert.equal(validInventory(value, 'read-1', [targetId], sourceContext()), false);
  }
});
test('blocked and rejected rows explain every selected document but cannot create a face map', () => {
  const data = inventory();
  data.targets = [{document: {document_id: targetId}, blocked: 'Analyse this independent source first'}];
  assert.equal(validInventory(data, 'read-1', [targetId], sourceContext()), true);
  assert.equal(explicitRequest(data, [targetId], sourceRef, selection, {[targetId]: [sourceRef]}), undefined);
  data.targets = []; data.rejected_docs = [{doc: targetId, error: 'Removed'}];
  assert.equal(validInventory(data, 'read-1', [targetId], sourceContext()), true);
  assert.equal(explicitRequest(data, [targetId], sourceRef, selection, {[targetId]: [sourceRef]}), undefined);
});
test('disabled, synthetic and unresolved faces are never selectable', () => {
  for (const patch of [{enabled: false}, {analysis_status: 'synthetic' as const}, {analysis_status: 'unresolved' as const}]) {
    const data = inventory(), target = entry(targetId, 19); Object.assign(target.faces[0], patch); data.targets = [target];
    assert.equal(explicitRequest(data, [targetId], sourceRef, selection, {[targetId]: [sourceRef]}), undefined);
  }
});
test('normalized boxes, PNG identity and bounded dimensions are checked', () => {
  for (const mutate of [
    (v: any) => {v.faces[0].box = [.7, .2, .4, .9];}, (v: any) => {v.faces[0].box[0] = -.1;},
    (v: any) => {v.faces[0].box[2] = NaN;}, (v: any) => {v.source_preview.width = 321;},
    (v: any) => {v.source_preview.mime = 'image/svg+xml';}, (v: any) => {v.source_preview.base64 = 'not-png';},
    (v: any) => {v.source_preview.base64 += 'A'.repeat(400000);},
    (v: any) => {v.faces = Array.from({length: 129}, () => v.faces[0]);},
  ]) {const value = entry(targetId); mutate(value); assert.equal(validInventoryEntry(value), false);}
});
