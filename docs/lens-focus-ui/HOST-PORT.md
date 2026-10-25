# Lens native port and App owner — AUTHORED / UNRUN

These source modules add the real native bridge and a persistent owner. They do not establish native registration, App mounting, compilation, runtime availability, numerical correctness or photographic acceptance by themselves. Existing v2 wire validation and the separately owned Python/Rust host remain authoritative. No fallback image renderer, synthetic AI depth, automatic model download, project auto-save or image export is added.

## App integration contract

Import `useLensBlur` directly from `ui/src/lensBlur/useLensBlur.ts` and call it unconditionally at App lifetime, not inside a conditional lens panel. Keep the same hook instance across source switches, hidden panels and engine replacement.

Context fields are `sourceUid`, `loadId`, `engineKey`, `hostRevision`, `active`, `available`, `externalBusy`, `queueBusy`. Use real App/native identities, not filenames, label-derived IDs or image thumbnails. `sourceUid` is the canonical source-row identity and must match `LensContext.owner.document_id`; `loadId` is the current native loading-session identity. `hostRevision` is the UI event/invalidation counter only. Never copy it into `owner.document_revision`, compare it numerically to the canonical revision, or derive a new result revision from it. The exact source/load/engine/UI-revision tuple scopes acquisition and invalidates stale UI results.

`available` requires the live matching native engine and lens protocol 2. `active` permits explicit new work in the intended workspace, but hiding the panel does not discard ownership or stop receipt polling. `externalBusy` contains other tools and incompatible editing modes; it must exclude this lens owner's own activity. `queueBusy` reflects the shared engine queue and is admission-only. It blocks starting new reads/writes, but must never invalidate or cancel a read simply because that same read entered the queue.

The hook returns:

- `workflow`: stable `LensBlurWorkflow`, passed to `LensBlurWorkspace`.
- `state`: the subscribed `LensState`; `capability`: exact renderer capability.
- `acquisition`: null or `{request_id, phase, cancel_requested}`, where phase is `working`, `pending`, `unknown` or `cancelling`.
- `canAcquire`, `busy`, `message`, `refreshing`, `lastResult`.
- `acquireCurrent()`, `cancelCurrent()`, `check()`, each returning `Promise<void>`.

Provide `onChanged(receipt, originalCommand): Promise<void>`. It must actually refresh the authoritative editor/session state and document list, using `result_document_id` for an applied receipt where an explicit target is needed. An existing no-argument async refresh callback is assignable if the canonical host already activated the returned copy. Do not replace the callback with a toast, increment a counter and call that a readback, re-run Apply, or fabricate new-document/history identities. The workflow waits for callback completion before automatic exit; a failure retains the known outcome and allows only its read-only refresh retry. A delayed React context update does not erase an already known terminal copy receipt.

`busy` includes outstanding native read identities even when the workflow's bounded wait has timed out into `failed`. Use it to fence other tools and new acquisition. Do not pass this owner's own `busy` as the workspace's blanket `disabled` prop: that would disable the Cancel/Query controls needed to resolve its own work. External fences can disable new editing while the owner keeps status observation alive.

## Explicit acquisition and honest depth

Nothing is captured, rendered or analyzed on mount, activation, frame arrival, host revision change or scope invalidation. `acquireCurrent()` is the explicit action. It settles the existing curve-edit barrier, verifies native capability and requests one full current-source capture. The source receipt must match the unchanged UI scope and canonical `sourceUid`, then pass the existing complete PNG/hash/dimension validation before image presentation and editing.

The native host captures the actual original or derived full-source state; the browser does not reconstruct it from the displayed preview. Unsupported alpha/HDR return semantics remain an explicit host refusal. There is no clipping, compositing onto an invented background, reduced-resolution output fallback or silent original/derived identity substitution here.

Manual depth is available only through the workspace's explicit `prepare_manual_plane` action and its exact `acknowledged_manual: true` provenance. The port preserves all v2 command fields and unwraps the real returned context. It never supplies a gradient, inferred subject, model result or default manual baseline on its own.

## Exact native calls

The port invokes only these genuine Tauri commands:

- `lens_blur_capability()` returns the exact v1 `LensCapability` object.
- `lens_blur_request({request})` sends an exact outer envelope.
- `lens_blur_status({requestId})` polls the already retained native request without queueing it again.
- `lens_blur_cancel({requestId})` signals cancellation of an original read only. It does not interrupt Apply, undo a returned copy or establish that a task has already stopped.

The outer request is `{cmd: 'lens_blur', action, request_id}` for `current`. Other actions add one `command` field. `prepare_manual_plane` and `preview` carry their exact corresponding v2 commands. `submit` carries an exact Apply or Cancel command. Those outer and inner request IDs must match. `receipt` carries the exact original write command but uses a fresh independent outer query ID. The original command never changes and is never resubmitted.

Request and status calls return the direct wrapper `{event: 'lens_blur_result', request_id, ...}`. There is no guessed `{phase, result}` mailbox or alternate wrapper fallback:

- Read progress is `status: 'pending' | 'unknown'` plus `message`.
- Read failure is `status: 'rejected' | 'cancelled'` plus `message`.
- Current success is `status: 'ready'`, exact `capability`, and valid `context` (or null only with unavailable capability); an optional message is allowed.
- Manual-plane success is `status: 'ready'` plus valid `context`.
- Preview success is `status: 'ready'` plus the exact v2 `review`.
- Write/query success is `status: 'ready'` plus the exact matching `receipt`, which may itself be pending, unknown or terminal. The query wrapper's request ID is distinct from the inner receipt's original write ID.

All successful contexts/reviews/receipts are validated against their expected command before unwrapping. A generic native `status: 'unknown'` without a retained receipt remains unknown, never successful, cancelled or a no-write proof. A locally failed preflight can report rejection only before the native operation is retained or invoked; after invoke begins, errors are uncertain and only the original status is queried.

An uncertain write receives at most one automatic host receipt readback. Background observation thereafter polls the retained original/query native statuses only, without creating more query identities. The hook's explicit user `check()` permits another read-only host reconciliation if needed; the hidden timer calls a separate polling path that does not grant that permission. This keeps unknown outcomes visible without filling native request ledgers through hours of automatic fresh queries. Neither path resubmits Apply or Cancel.

## Cancellation, leases and interruptions

The native port separately retains read identities for current capture, manual preparation and preview. Timeout does not remove them. Hidden-panel polling continues at 1.2-second intervals while any read or write remains unresolved, and the native read wait itself polls only the same request. `canAcquire` and new preview/Apply admission stay blocked while a previous read may still run. The owner reports uncertainty rather than pretending a heavy serialized task disappeared when a React panel unmounted.

Source, load, engine, UI-revision or external-tool changes revoke the old UI context and request cancellation of outstanding reads. The native cancellation API retrieves its own exact retained original outer envelope, sends that as proof to Python, and Python computes its own parsed hash. JavaScript never reproduces Python float serialization or sends a guessed command digest. Cancellation is sent once after native admission is known; uncertain cancellation acknowledgements are not retried. The cancellation response `{requested, request_id, message}` is acceptance only, and actual terminal status must still be read.

The workflow's canonical session Cancel first requests read cancellation out of band and then submits its exact normal write envelope. Only the matching final Cancel receipt closes that editing lifetime. An unresolved Apply remains protected across source switches and engine changes; only the original write can be reconciled. The first valid terminal write receipt is retained even if a later native cache lookup is unavailable.

Browser read/write identity ledgers are bounded to 256 each and fail closed when full; they do not evict unresolved work to admit new work. Native/Python owners separately enforce their image/session/candidate/memory leases. Old readonly image results can be discarded after their terminal outcome or scope invalidation without turning absence into proof about a write.

## Verification still required

Only source/AST/hash inspection is permitted for this slice. Product imports, test execution, typechecking, builds, native calls, inference, downloads and Git writes were not performed. Before claiming an integrated feature, verify exact native registration and App mount; explicit capture; alpha/HDR refusal; genuine manual provenance and PNG loads; pending-read timeout and late completion; cancellation before/after admission; hidden-panel polling; separate externalBusy/queueBusy; source/load/revision/engine switches; original/query receipt correlation; no repeated Apply; actual post-copy refresh and its failure/retry; and project save/reopen/export independently.
