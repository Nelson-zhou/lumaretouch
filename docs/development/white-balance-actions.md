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

## Verified automated evidence and remaining acceptance

Candidate de5e8e2f26277bab9a30ec87ce12e0d4626d36c3 passed
https://github.com/Nelson-zhou/lumaretouch/actions/runs/39744013157 . All non-GPU
jobs passed; GPU jobs skipped. Evidence:
- Lightweight engine:1158 passed,433 skipped,71.87s.
- Separate CPU Torch preset protocol:3 passed,0 skipped,4.44s.
- WB bridge/state/controller/actual mode-reset-undo protocol:40 passed,0 skipped,4.28s.
- Frontend:176 passed,0 failed, including10 WB lifecycle tests.
- Rust WB mailbox:3 passed; Rust checking, frontend typechecking and builds passed.

Lifecycle tests include hung send/query/refresh, old-document replies and stale
confirmation after owner disposal/reactivation. Backend evidence includes terminal
receipts after history, no-op/deduplication, bounded invalid identities and preserved
non-WB settings. Actual desktop interaction, visual quality, GPU behavior and slider
latency remain separate acceptance, not inferred from these results.
