# Versioned white-balance actions

Candidate implementation, not yet GUI/photographic acceptance. The preceding
state integration77add60a passed CI39740442969: 1150 lightweight engine tests,
432 skipped; separate CPU Torch runs passed3 preset cases and31 WB cases without
skips. All non-GPU jobs passed; GPU jobs skipped. Synthetic images are not wedding
photo evaluation. Qoder local verification still awaits the correct project binding.

## Native entry points

The white-balance tool group exposes explicit old/corrected algorithm selection
and WB-only reset. Selection warns that appearance can change. Current mode comes
from authoritative document state, never optimistic selection. Reset zeros manual
temperature/tint and picked gains only; it preserves algorithm, reference (including
an unspecified/null reference), exposure and tone. Existing eyedropper UI remains
unimplemented; these buttons do not claim to sample a neutral point.

Commands carry document/request identity and require advertised protocol1 support.
The engine validates current load identity and editability, uses the same exposure
transaction, and records each effective one-shot action as a separate undo step.
No-op actions do not call rendering or manufacture a history step. Terminal receipts
are finalized after history, with before/after values and history counts. An
explicit transaction success is required; a printed error or queue acknowledgment
cannot become success. Render rollback failure invalidates the render session.

Rust registers a document/epoch-bound mailbox before enqueue. The host validates
before/after invariants, terminal identity and evidence. Engine deduplication is
bounded to64 replies of at most16KiB each; this is not durable exactly-once storage.
After uncertainty the app only queries the original ID; it never resubmits. A lost
result can be acknowledged only after a different loaded-document identity, not
merely by clicking the same mutation again.

The workflow owner lives at App scope, across panel folding. Send/query/refresh
waits are bounded, unmount cancels local waiting by generation, and late responses
cannot publish into the replacement owner. A confirmed mutation remains confirmed
if subsequent status refresh fails. Old receipt state is never installed into the
current document. Native status refresh continues to use the existing status fence.

## Verification still required for this candidate

CI includes backend controller failure/dedup/UTF8/bounds tests, a real synthetic
engine mode/reset/undo protocol flow, native mailbox tests and frontend lifecycle
unit tests. These new tests have not yet run for this candidate at this edit.
Actual desktop interaction, visual quality, GPU behavior and slider latency remain
separate acceptance, not inferred from unit tests or a successful build.
