// AUTHORED / UNRUN. These fixtures are not evidence of execution or acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseSelection, parseSnapshot, parsePage, parseThumbnail, reorderedIds, type MaterialQuery } from './model.ts';

const library = '1'.repeat(32), material = '2'.repeat(32), sha = 'a'.repeat(64);
const selection = { version: 1, library_id: library, material_id: material, catalog_revision: 4, sha256: sha };
const head = {
  version: 1, library_id: library, revision: 4, groups: [{ id: 'ungrouped', name: '未分组' }], order_ids: [material],
  counts: { active: 1, trash: 0, total: 1 }, storage: { bytes: 100, budget_bytes: 10000 },
  limits: { max_active: 2000, max_records: 20000, max_groups: 200, max_import: 1000, max_object_bytes: 10000000, max_pixels: 32000000 }, warnings: [],
};
const query: MaterialQuery = { group_id: null, text: '', trash: false, sort: 'manual', offset: 0, limit: 48 };
const row = { id: material, name: 'My background', group_id: 'ungrouped', sha256: sha, bytes: 100, width: 10, height: 10,
  bits: 16, format: 'PNG', has_alpha: true, created_at: 1, deleted_at: null };

test('strict immutable selection cannot carry source paths or preview pixels', () => {
  const result = parseSelection(selection);
  assert.equal(Object.isFrozen(result), true);
  assert.deepEqual(Object.keys(result).sort(), ['version', 'library_id', 'material_id', 'catalog_revision', 'sha256'].sort());
  assert.throws(() => parseSelection({ ...selection, path: '/tmp/material.png' }));
  assert.throws(() => parseSelection({ ...selection, data_url: 'data:image/png;base64,AAAA' }));
  assert.throws(() => parseSelection({ ...selection, catalog_revision: Number.MAX_SAFE_INTEGER + 1 }));
  assert.throws(() => parseSelection({ ...selection, sha256: sha.toUpperCase() }));
});
test('header holds identities and counts, not full material metadata', () => {
  assert.equal(parseSnapshot(head).counts.active, 1);
  assert.throws(() => parseSnapshot({ ...head, items: [row] }));
  assert.throws(() => parseSnapshot({ ...head, order_ids: [] }));
  assert.throws(() => parseSnapshot({ ...head, groups: [] }));
});
test('page rejects revision, query, count, trash and identity drift', () => {
  const snapshot = parseSnapshot(head), page = { version: 1, library_id: library, revision: 4, query, total: 1, items: [row], next_offset: null };
  assert.equal(parsePage(page, query, snapshot).items[0]?.bits, 16);
  assert.throws(() => parsePage({ ...page, revision: 5 }, query, snapshot));
  assert.throws(() => parsePage({ ...page, query: { ...query, text: 'other' } }, query, snapshot));
  assert.throws(() => parsePage({ ...page, items: [] }, query, snapshot));
  assert.throws(() => parsePage({ ...page, next_offset: 48 }, query, snapshot));
  assert.throws(() => parsePage({ ...page, items: [{ ...row, deleted_at: 2 }] }, query, snapshot));
  assert.throws(() => parsePage({ ...page, items: [{ ...row, id: '3'.repeat(32) }] }, query, snapshot));
});
test('thumbnail is display-only and revision pinned', () => {
  const thumb = { version: 1, id: material, revision: 4, thumbnail_sha256: sha, data_url: 'data:image/png;base64,AAAA' };
  assert.equal(parseThumbnail(thumb, material, 4), thumb.data_url);
  assert.throws(() => parseThumbnail(thumb, material, 5));
  assert.throws(() => parseThumbnail({ ...thumb, data_url: 'file:///tmp/thumbnail.png' }, material, 4));
  assert.throws(() => parseThumbnail({ ...thumb, data_url: 'data:image/svg+xml;base64,AAAA' }, material, 4));
});
test('manual page ordering preserves every hidden position', () => {
  assert.deepEqual(reorderedIds(['a', 'hidden', 'b', 'other', 'c'], ['a', 'b', 'c'], 'a', 'c'), ['b', 'hidden', 'c', 'other', 'a']);
  assert.deepEqual(reorderedIds(['a', 'b'], ['a'], 'absent', 'a'), ['a', 'b']);
});
