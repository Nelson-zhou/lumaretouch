// Authored acceptance coverage only. Execution status: UNRUN; Qoder owns runtime checks.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {affectedRows, changedRows, isOutcome, isState, rowLabel, sameOperationProject,
  type PendingVirtualCopy, type VirtualCopyRow, type VirtualCopyState} from './model.ts';

const row = (id: string, copy: number, trashed = false): VirtualCopyRow => ({
  document_id: id, root_document_id: 'original', source_asset_id: 'asset',
  copy_number: copy, path: '/photos/shared.jpg', trashed, revision: copy + 1,
});
const state = (...rows: VirtualCopyRow[]): VirtualCopyState => ({workspace: 'workspace-1', project_id: 'project-1', rows});
const operation = (project_id: string | null = 'project-1'): PendingVirtualCopy => ({
  request_id: 'original-operation', workspace: 'workspace-1', project_id, action: 'create', document_ids: ['original'],
});
const ids = (rows: VirtualCopyRow[]) => rows.map(item => item.document_id);

test('same-path documents remain distinct create targets', () => {
  const value = state(row('original', 0), row('copy-1', 1), row('copy-2', 2));
  assert.deepEqual(ids(affectedRows(value, ['copy-1', 'copy-2'], 'create')), ['copy-1', 'copy-2']);
  assert.equal(isState(value), true);
  assert.equal(rowLabel(value.rows[1]), 'shared.jpg · 虚拟副本 1');
});
test('trash original revision-fences every sibling, including already trashed siblings', () => {
  const value = state(row('original', 0), row('copy-1', 1), row('copy-2', 2, true));
  const affected = affectedRows(value, ['original'], 'trash');
  assert.deepEqual(ids(affected), ['original', 'copy-1', 'copy-2']);
  assert.deepEqual(ids(changedRows(affected, 'trash')), ['original', 'copy-1']);
});
test('trash copy never includes the original or sibling copies', () => {
  assert.deepEqual(ids(affectedRows(state(row('original', 0), row('copy-1', 1), row('copy-2', 2)), ['copy-1'], 'trash')), ['copy-1']);
});
test('restore copy includes original but never another copy', () => {
  const value = state(row('original', 0, true), row('copy-1', 1, true), row('copy-2', 2, true));
  assert.deepEqual(ids(affectedRows(value, ['copy-1'], 'restore')), ['original', 'copy-1']);
  assert.deepEqual(ids(affectedRows(value, ['original'], 'restore')), ['original']);
});
test('batch closure is deduplicated and never crosses a different root', () => {
  const other = {...row('other-original', 0), root_document_id: 'other-original'};
  const value = state(row('original', 0), row('copy-1', 1), row('copy-2', 2), other);
  assert.deepEqual(ids(affectedRows(value, ['original', 'copy-1'], 'trash')), ['original', 'copy-1', 'copy-2']);
});
test('malformed or duplicated identities cannot become an accepted state', () => {
  assert.equal(isState(state(row('same', 0), row('same', 1))), false);
  assert.equal(isState(state({...row('original', 0), revision: -1})), false);
  assert.equal(isState(state({...row('original', 0), copy_number: 1.5})), false);
  assert.equal(isState({workspace: '', rows: []}), false);
});
test('only bounded outcome vocabulary and valid state are accepted', () => {
  assert.equal(isOutcome({operation_id: 'op', status: 'unknown'}), true);
  assert.equal(isOutcome({operation_id: 'op', status: 'succeeded', state: state(row('original', 0))}), true);
  assert.equal(isOutcome({operation_id: 'op', status: 'saved'}), false);
  assert.equal(isOutcome({operation_id: 'op', status: 'succeeded', state: {rows: []}}), false);
});
test('saved project identity retains uncertainty across workspace restart', () => {
  assert.equal(sameOperationProject(operation(), {workspace: 'workspace-after-restart', project_id: 'project-1'}), true);
  assert.equal(sameOperationProject(operation(), {workspace: 'workspace-after-restart', project_id: 'other-project'}), false);
  assert.equal(sameOperationProject(operation(), {workspace: 'workspace-1', project_id: 'other-project'}), false);
});
test('unsaved uncertainty only binds to its exact original workspace', () => {
  assert.equal(sameOperationProject(operation(null), {workspace: 'workspace-1', project_id: null}), true);
  assert.equal(sameOperationProject(operation(null), {workspace: 'new-unsaved-workspace', project_id: null}), false);
  assert.equal(sameOperationProject(operation(null), {workspace: 'different-workspace', project_id: 'project-1'}), false);
  assert.equal(sameOperationProject(operation(null), {workspace: 'workspace-1', project_id: 'first-save'}), true);
});
test('state must explicitly identify saved or unsaved project', () => {
  assert.equal(isState({...state(row('original', 0)), project_id: null}), true);
  assert.equal(isState({...state(row('original', 0)), project_id: undefined}), false);
  assert.equal(isState({...state(row('original', 0)), project_id: ''}), false);
});
