# Authoritative common-apply receipt readback

Baseline: ff0984c556f7dc2f366cd85e68448105b904175f. Source-only; all runtime,
UI, Rust compilation, Python imports, numerical and integration fixtures are UNRUN.

## Problem and bounded recovery

The original UI polls a native terminal receipt. A lost or malformed transport
reply can produce a native unknown even when the same engine holds a definite
committed/rejected receipt. Reapplying would risk a duplicate operation. Conversely,
matching visible parameters or undo counts does not establish the transaction's
history integrity after an actual failed rollback.

This slice adds a separate exact read-only lookup. It reconstructs the original
apply envelope and checks its digest against the existing engine cache. It never
creates an apply controller, reads or installs a matte, requires a surviving
preview, rebuilds a pipeline, fences history, or retries the original command.
Missing/evicted evidence explicitly means unknown, not rejected/not applied.

A separate native not-sent receipt is allowed only on the synchronous validated-ID
submission error path when that ID has never been admitted. This is evidence from
the actual pre-admission failure, not inference from a missing engine receipt.
Any prior admission, uncertain send, ledger-budget refusal or lock failure prevents
such a clean noncommit claim.

The native side binds the lookup to its original accepted request identity and
engine epoch, independently of generic terminal ReceiptHost. Original native
receipt and authoritative readback remain separate evidence. A clean exact cached
success/rejection can release the editing lock; genuine unknown/requires_reload,
missing evidence and an engine epoch change cannot. Native audit evidence survives
an engine reset within the application process; this is not a claim of on-disk
recovery across a complete application-process restart.

The UI explicitly requests readback, retains an audit of the original operation
and native receipt, and distinguishes it from the authoritative result. It never
silently resubmits. Readback is available independently of ordinary image editing
readiness, because a broken live pipeline must not prevent receipt lookup.

A native process-lifetime audit inventory lets a remounted webview reconstruct all
unresolved original identities before permitting another edit. An unavailable
inventory fails closed. Cleanly settled entries remain audit records; unresolved
entries are not evicted to make room. Engine replacement never converts an old
unknown into a rejection. These are source contracts, not observed remount tests.

Inventory bootstrap also rotates a native-only admission generation. The original
apply captures that generation; validation and admission occur under the same
ledger mutex as inventory rotation. Therefore either an old invocation is already
visible in the replacement inventory, or it is rejected before admission. The
generation is removed before transport and never changes the engine's original
request digest. The curve-edit barrier belongs to cancellable UI preflight, before
an original request is registered; failure there is not an uncertain application.

A synthetically unknown native transport receipt is not the same as an actual
engine-issued rollback-unknown receipt. The latter is authoritative and immutable:
readback must agree with it even when it remains unknown. A contradictory clean
receipt cannot unlock editing. Only synthetic transport uncertainty can be resolved
by a subsequently verified engine receipt. This comparison applies in both arrival
orders, and original-result polling prefers the validated audit over generic native
receipt state so a contradictory late event cannot bypass the check.

## Autosave fence integrity

A superficially terminal common event must not settle the cross-domain native
receipt fence before CommonBackgroundKind verifies full correlation and shape.
Only validated clean evidence can settle the original request's fence. This does
not clear unrelated pending requests or the engine's independently tainted recovery
state. A readback command itself is read-only and bypasses mutation boundaries.

## What this does not solve

A real rollback failure has no durable repair transaction in the current common
controller. Engine loss/cache eviction cannot be repaired by inference from pixels.
Those outcomes remain blocked pending a separately verified checkpoint-recovery
workflow, not an unsafe generic 'reload and forget'. Existing recovery candidates
can be restored as new non-overwriting project copies, but opening a copy is a new
workspace choice, not proof about the old operation.

Required future checkpoint-unlock proof includes selected persistent document,
project/checkpoint hash, source audit and fresh actual image readiness. In particular:
- project_created retains live documents and is not recovery evidence;
- project_opened is emitted before automatic image loading finishes;
- generic load_image first remembers potentially uncertain live state;
- selecting the current row can be a no-op;
- host doc_rev and cached engine_status are not transaction receipts.

Do not remove these fences merely to improve apparent availability. A complete
application restart, actual failed rollback and verified checkpoint reload remain
explicit unfinished paths, not concealed acceptance claims.

## Integration map and validation boundary

- Engine `common_background_readback.py`, dispatched by `studio_tools_dispatch.py`
  and the read-only branch in `server.py`, reads the existing common controller cache.
- Native `common_background_readback.rs` owns the process ledger and the
  `common_background_audit`, `common_background_readback`, and
  `common_background_readback_status` commands. `common_background_api.rs` binds
  original admission; `native_dispatch.rs` checks stale generations before capture
  invalidation; `engine.rs` correlates events and preserves read-only transport.
- UI `readback.ts` validates inventory/receipts; `workflow.ts` owns bootstrap,
  cancellable preflight, original query and distinct readback. The receipt panel is
  mounted from App independently of the collapsible RetouchPanel and workspace.
- Authored fixtures: eight Python test functions (including parametrized cases),
  fourteen native Rust tests, twenty-three new UI tests and eighteen retained UI
  workflow tests adapted to mandatory bootstrap. All are UNRUN. Python AST parsing,
  source inspection and whitespace checks do not establish functional acceptance.

Qoder should exercise real engine success with lost native delivery, engine-issued
rollback-unknown, cache eviction, engine replacement, webview remount at either side
of admission, curve-barrier rejection/cancellation and unrelated pending autosave
fences. No photo-quality or numerical result is claimed by this receipt-only slice.
