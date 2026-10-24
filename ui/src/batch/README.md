# Reviewed recipe synchronization

- `batchWorkflow.ts`: pure command/receipt lifecycle over explicit transport ports.
- `useBatchWorkflow.ts`: React/native adapter; stable controller across rerenders.
- `BatchActions.tsx`: reachable filmstrip entry and independent target-conflict policy.
- `BatchReview.tsx`: frozen source/parameters, target eligibility, per-target outcomes,
  focus containment and persistent unresolved-operation launcher.

Never call unreviewed commit from UI. Commit sends only the server-issued token and
request identity. Context changes invalidate an unsubmitted review. Queue acceptance
is not success. Unknown outcomes retain ownership across hiding and can be queried;
a new mutation requires resolution or explicit inspect-and-end-tracking acknowledgment.
That acknowledgment neither cancels nor rolls back an already-submitted operation.
The named face-style route is a separate explicit-face-map-only operation, not
donor-parameter copying. Binding v1 replaces exactly 30 leaves across 10 sorted
operations from `face_style_recipes.py`, with one shared seven-style recipe and
amount. Zero replaces the owned values with neutral values, not prior-state
restoration. Each eligible target requires its own read-only image pages, SHA-256
and decoded-size checks, recipe digest validation, and an explicit checkbox.
Its commit and known named-batch undo/redo requests are query-only when uncertain;
generic inspect-and-end cannot release their identities. This addition is
AUTHORED / UNRUN: no tests, typecheck, build, runtime or GUI acceptance were run.
The authored waist scalar route is stricter: an uncertain waist commit cannot
use inspect-and-end to release its original identity. It is query-only; queries
read the retained native mailbox and do not guarantee reconciliation of a lost
terminal result. See `../waistLength/TRANSFER-UNRUN.md` for source-only limits.

Tests are listed in `ui/package.json`. Native receipt contracts live in
`ui/src-tauri/src/batch_host.rs`; engine snapshot/conflict tests are separate. The
integrated candidate passed basic CI/Qoder checks on c7594167; real GUI
acceptance remains pending. See docs/development/frozen-batch-verification-2026-10-21.md. No physical presentation or full-product completion is implied.
