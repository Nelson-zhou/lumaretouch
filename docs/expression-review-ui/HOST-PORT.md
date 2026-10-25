# Expression replacement native adapter and App owner

Status: source authored, runtime UNRUN. This slice owns only new `nativePort.ts`, `useExpressionReplacement.ts`, and this document. Shared App mounting, Tauri registration, engine dispatch and copy publication remain parent-owned. The presence of these adapters is not evidence that end-to-end operation has run.

## Exact hook contract

Import `useExpressionReplacement` directly from `ui/src/expressionReplacement/useExpressionReplacement.ts`. Call it unconditionally once at App lifetime, not inside the expression panel or conditional tool route:

`useExpressionReplacement(context, onChanged)`

Context fields:

- `sourceUid: string`: actual `doc.source_uid`, the stable row identity.
- `loadId: string`: actual `doc.document_id`, the current load identity.
- `engineKey: string`: existing App engine-instance key, for example its existing `String(pid)` key. This does not fabricate the native mailbox epoch.
- `hostRevision: number`: actual `status.doc_rev`.
- `available: boolean`: existing engine/protocol/current-loaded-image availability, not an optimistic default.
- `busy: boolean`: all incompatible external edit/export/capture work. Exclude this module's own `busy` from this input to avoid a feedback loop. Panel visibility must not be encoded as unavailable or busy.

`onChanged: () => Promise<void>` must invoke the actual existing document/session/image refresh after a committed copy. It is not a placeholder callback. It is called once when the controller accepts the exact copy receipt, not when a native send is accepted. Refresh failure preserves the saved result identity and warns against saving again.

Returned fields:

- `controller`: the stable `ExpressionController` used by `ExpressionReplacementPanel`.
- `current`: a fully validated, scope-current `Current` or null. Mount the existing panel with this value and the stable controller.
- `state`: the controller snapshot, including its original request and receipt fences.
- `capability`: the real native capability response, initially unavailable until checked.
- `acquisition`: null or `{request_id, phase, cancel_requested}` for the explicit full-render/source-analysis request.
- `canAcquire`, `busy`, `message`, `lastResult`, `refreshing`.
- `acquireCurrent(): Promise<void>`: explicitly start exactly one current full-render capture and independently measured face analysis.
- `cancelCurrent(): void`: request cancellation of that original capture. Before native dispatch, cancel the unsent start; after dispatch, use the native-returned digest and retain the original request until terminal evidence.
- `check(): Promise<void>`: query existing current/controller requests without creating new ones.

Provide an explicit “获取当前完整来源” control using `canAcquire` and `acquireCurrent`, a source-acquisition cancel/check control, and the owner message beside the mounted panel. This new file does not edit the existing panel or App.

Hook construction, a render, a status update, opening the panel or refreshing after a copy never triggers a new full capture. A 1.2-second observer runs only while a request is retained, issuing status reads only. Hiding the panel does not recreate the controller, stop status reconciliation or discard an unknown save. Source, load, engine-instance, revision or external-availability loss invalidates source review immediately; it requests cancellation of reads, while retaining a sent save's original owner. The displayed current snapshot is fenced by the full captured scope, including engine key, before rendering.

## Frozen native protocol

The adapter uses direct envelopes only. An earlier pending/result wrapper description is superseded; no dual parser or fallback endpoint is implemented.

Tauri invocations:

- `expression_replacement_capability` with no arguments returns `{protocol: 1, operation_id: 'lnx.expression_replacement.v1', available, reason}`.
- `expression_replacement_request` receives `{request: envelope}`.
- `expression_replacement_status` receives `{requestId}` and only reads the original mailbox.
- `expression_replacement_cancel` receives `{requestId, commandSha256}`.

Engine request envelopes:

- Current: `{cmd: 'expression_replacement', action: 'current', request_id}`.
- Packet command: `{cmd: 'expression_replacement', action: packet.command.action, request_id: packet.command.request_id, packet}`.
- Donor packet alone may additionally carry `path`, selected through the real native file dialog.
- Release: `{cmd: 'expression_replacement', action: 'release', request_id, preview_token}`.

Packet results are `{event: 'expression_replacement_result', request_id, receipt}`, where `receipt` is the exact validated UI-model receipt, including native pending/unknown/cancelling responses. A missing or evicted native record is `{event, request_id, phase: 'unknown', message}`. The adapter translates that absence to an identity-bound unknown receipt, never a success, no-write proof or new dispatch.

Current results are direct `current_ready/current`, `pending`, `unknown`, `cancelling`, or terminal `rejected`/`cancelled` with `no_write: true`. Current nonterminal responses include the native-generated `command_sha256`; the hook retains it unchanged and checks that it never changes. It never independently reserializes or guesses that digest. `Current.binding.document_id` must equal the stable source row ID, `load_id` the current document load, while canonical `document_revision` is independently verified by the engine. App `hostRevision` is only a UI invalidation counter, not that canonical revision. The native mailbox independently owns the engine epoch.

Cancellation returns an acknowledgement `{requested, request_id, command_sha256}`, not task-exit evidence. Completion comes only from the original request's status. Native may return `requested: false` when the original already has a terminal result; this is not itself cancellation success. Current-source terminal completion is discarded rather than adopted after cancellation. Packet terminal-race handling is described by the existing controller contract and must remain aligned with the native first-terminal-wins mailbox.

Release completion is `{event, request_id, phase: 'released', preview_token}`. Each token retains one release request ID; repeats query that ID instead of dispatching another release. Failure is not called successful cleanup; host-owned preview lease expiration remains the fallback, as in the source module contract.

## Real donor selection and cancellation races

The native dialog is single-file, non-directory. Only its returned absolute path, with the native bounds and no control characters, is passed to the host. No donor URL, basename expansion, guessed storage location, browser download or fabricated pixel data is involved.

The immutable command identity is retained before asynchronous SHA verification so simultaneous cancellation cannot be lost. The exact UTF-8 command string is bounded to the native 256 KiB limit, SHA-checked, and compared with the retained object. A request is marked sent before invoking Tauri; a rejected Promise, lost acknowledgement or timeout leads only to status reads, never another write. Native admission failures that explicitly return a validated no-write receipt can unlock; generic invoke failure remains unknown.

The OS picker is not a native engine job yet. If cancelled while the picker remains open, the adapter reports nonterminal cancellation-requested and asks the user to close the picker; it does not claim force-close or task completion. Any later selected path is discarded. After the dialog resolves or fails, the original `choose_donor` packet is sent exactly once without a path, so the host returns a genuine cancelled/no-write receipt. It does not synthesize successful cancellation. Once an engine job is registered, cancellation uses its exact ID/hash and is dispatched at most once; subsequent calls only query status. Apply is never sent through cancellation.

## Remaining verification and integration

Only source inspection and TypeScript AST parsing were performed. No product import/execution, typecheck, build, tests, image import, native inference, Git or GitHub operations ran in this slice.

Required later checks include real dialog cancellation and late-path races, source change during capability lookup/capture/analysis, pending/unknown/cancelling direct envelopes, native epoch changes, duplicate clicks and exact byte-hash bounds, complete current-render source provenance, actual donor analysis and mask output, copy publication/rollback, real post-copy refresh, hidden-panel polling, React lifecycle cleanup and native capability removal. Do not call the feature accepted from these source adapters alone.
