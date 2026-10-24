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
The authored waist scalar route is stricter: an uncertain waist commit cannot
use inspect-and-end to release its original identity. It is query-only; queries
read the retained native mailbox and do not guarantee reconciliation of a lost
terminal result. See `../waistLength/TRANSFER-UNRUN.md` for source-only limits.

Tests are listed in `ui/package.json`. Native receipt contracts live in
`ui/src-tauri/src/batch_host.rs`; engine snapshot/conflict tests are separate. The
integrated candidate passed basic CI/Qoder checks on c7594167; real GUI
acceptance remains pending. See docs/development/frozen-batch-verification-2026-10-21.md. No physical presentation or full-product completion is implied.
