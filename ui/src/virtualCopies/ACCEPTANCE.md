# Virtual copy controls acceptance

Status: **UNRUN**. No product execution, imports by an execution environment, tests,
compiler, build, typecheck, inference, download, installation, or Git writes were run.
Only source inspection and source edits were performed. Qoder owns runtime acceptance.

## Integration

- Add `mod virtual_copy_api;` in the native root.
- Register `virtual_copy_api::virtual_copy_request` and
  `virtual_copy_api::virtual_copy_status` in the Tauri invoke handler.
- Route `virtual_copy_result` in the engine event match to
  `crate::virtual_copy_api::receive(inspection_epoch, &v)`.
- Import `VirtualCopyControls` from `./virtualCopies/VirtualCopyControls`.
- Mount exactly one instance for the active gallery or retouch surface, with
  `projectKey`, `onChanged` to refresh session/project state, and optional
  `activeDocumentId`, `selectedDocumentIds`, and `disabled`.
- IDs must be canonical document IDs, not source paths or current image load IDs.
- On a gallery context-menu action, prevent the browser menu and dispatch
  `new CustomEvent('lrt-virtual-copy-context', {detail: {documentId}})` on `window`.
  This only selects/focuses the panel; it never submits a mutation.
- For existing batch trash/restore buttons, dispatch the same event with
  `{documentIds: canonicalIds, action: 'trash'}` or `action: 'restore'`. This opens
  the shared cascade review and still requires the explicit confirm button.

## Contract

Command: `virtual_copy`; actions: `state`, `create`, `trash`, `restore`, `query`.
Writes carry `workspace`, selected `document_ids`, `expected_revisions` for the
full affected closure, and identical `request_id`/`operation_id`. Query names the
original `operation_id` with a fresh read-only request ID.

The envelope is `{event:'virtual_copy_result',request_id,success,result,error}`.
State result is `{workspace,project_id,rows}`, with a stable nonempty `project_id`
for a saved project and explicit `null` for an unsaved workspace. Mutation/query result is
`{status,operation_id,state,changed_document_ids?,error?}`. The state rows carry
`document_id,source_asset_id,root_document_id,copy_number,path,trashed,revision`.

Native requests are correlated to an engine epoch, duplicate requests are not
sent again, and original write receipts are retained within that engine epoch. UI calls and polling are
bounded. Timeout, missing receipt, stale epoch, malformed receipt, and unknown
outcome do not authorize retry. Pending records preserve the original request ID,
workspace, and project ID and use persistent local storage, with session/in-memory
fallback and migration of old records. Matching a non-null project ID keeps the
same saved project locked after workspace/app restart. Unrelated project IDs do
not share locks. A first save can add stable identity only within the exact same
live workspace; orphaned unsaved operations remain visibly unknown and are not
assigned to unrelated projects. Explicit readback does not clear
an unresolved original operation merely because a state list was returned.

`pendingFor(workspace, projectId = null)` finds the retained original operation
for the exact workspace or same saved project. Query sends the **current**
`workspace`/`project_id` plus the original `operation_id` and `original_workspace`.
Only a query with matching non-null project identity may reconcile a receipt
across workspace changes. The engine must validate the supplied project ID and
return current state rather than a stale state snapshot from the stored receipt.
Original mutations still require their exact current workspace. Automatic
`refreshKey` changes invalidate an open cascade review; they never approve it.

## Runtime checks for Qoder

1. Create one copy in gallery and retouch; batch-copy two same-source documents.
   Confirm distinct document IDs, shared source asset/path, independent edits and
   a dirty project. Save/reopen explicitly to verify persistence.
2. Verify Ctrl/Cmd+apostrophe copies selected visible documents, or the active
   retouch document when none is selected. It must ignore repeat, text fields,
   content-editable targets, Alt, and Shift. Ensure only one panel is mounted.
3. Right-click an original and a copy. Confirm selection/focus and no mutation
   until a subsequent explicit action.
4. Trash original: review includes the original and all its active copies.
   Trash copy: review includes only that copy. Original source bytes remain.
5. Restore copy: review includes the copy and its trashed original, not sibling
   copies. Restore original: only original returns. Mixed active/trash selection
   disables ambiguous batch actions.
6. Change any affected revision after review; native/core must reject the whole
   operation rather than partially apply it. Refresh and explicitly review again.
7. Delay/drop a reply past the polling bound. Confirm new writes lock, querying
   names the original operation, and gallery/retouch switching never duplicates
   a mutation. State readback must not automatically clear unknown outcome.
8. Reuse one request ID with identical/different payloads and across engine
   restart. Confirm exact repeat is not resent, conflict is rejected, old-engine
   event cannot complete a new operation, and query is read-only.
9. Exercise the authored `model.test.ts` cases under the project's chosen runner.
10. UI must never call an accepted send a saved project, auto-save, or imply a
    source image was copied/deleted. Confirm project/session refresh reflects
    linked trash/restore results in both gallery and retouch.
11. Create an uncertain write in saved project A, restart engine/application, and
    reopen A with a new workspace. New mutations must remain locked. Explicit
    query must name the original operation and may reconcile a persisted terminal
    receipt whose state has the same project ID and the new workspace. Unknown
    results and state-only reads must not unlock. Opening unrelated project B
    must not inherit A's lock.
12. Leave an uncertain operation in an unsaved workspace, then open another
    workspace. The old operation must remain visibly unknown, never be retried,
    and not become attached to the other project. Saving the original still-live
    workspace may supply its stable identity without changing the operation ID.
