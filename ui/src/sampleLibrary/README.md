# Local sample-library UI, source handoff

This directory owns the reusable React panel and its native host integration.
The panel/adapter stay native-agnostic. `nativePort.ts` uses direct Tauri calls,
and App mounts one persistent owner plus a hidden-on-close host. Minimal shared
changes add the capability type and the PC-32452 launcher while preserving the
preset/LUT controls. No sample photographs or cloud links are shipped.

## Scope and product traceability

Manual, local, user-owned sample management only. This is not completion evidence
for every feature associated with the product IDs below. In particular, AI style
matching, AI recommendation, official cloud catalogs, and destructive resource
reclamation are not implemented or claimed here.

Guide identifiers reserved for this manual-library handoff:

- PC-32452-C-af312f51a2
- PC-32452-C-9ac5aa4d79
- PC-32452-C-831245a683
- PC-32452-C-faf6a4e2e8
- PC-32452-C-710056cf5d

These identifiers are traceability anchors, not invented per-row definitions or
completion assertions. The original guide rows must be checked before declaring
any entire row accepted. This source implements only the manual capabilities
listed below; any broader capability remains explicitly outside this handoff.

## Files

- `model.ts`: strict header/page/small-receipt parsing, source and asset identities,
  page-local ordering, names, capacity and outcome labels.
- `adapter.ts`: native-agnostic Promise port and validated callback adapter.
- `useSampleLibrary.ts`: single-flight state, revision capture, stale reply fences,
  cancelled-close reconciliation, document-change capture cancellation and
  uncertain-write review gate.
- `SampleLibraryPanel.tsx`: standalone management/reference modes, empty state,
  groups, imports, capture, search, paginated thumbnails and metadata, selection,
  ordering, recoverable trash and per-file receipts.
- `nativePort.ts`: bounded six-request native transport, request/status/cancel/release,
  strict terminal identities, no resend, and pending-write reconciliation.
- `useSampleLibraryHost.ts`: App-owned frozen reference identity and canonical
  backend context refresh. `SampleLibraryHost.tsx` supplies launch/card/hidden host.
- `WorkspaceTopbar.tsx`: genuine extraction of existing navigation, adding a
  capability-gated entry that does not require an open photo.
- `sampleLibrary.css`: scoped responsive styling and keyboard-visible focus.
- `empty-catalog.fixture.json` and `empty-page.fixture.json`: empty protocol
  fixtures only; neither is auto-loaded.
- `REVIEW.md`: manual/host verification plan; not a record of passed tests.

## Integrated App/native host

`App` owns `sampleLibrary = useSampleLibraryHost({enabled, documentId, refreshKey})`.
Its `selectedReference` is a frozen/read-only
`{sample_id,source:{sha256,width,height},render_sha256,asset_id} | null`.
`setSelectedReference(reference|null)` and `clearSelectedReference()` are explicit
handoff points for a future semantic-color owner. Selection itself runs no color
operation, does not call the existing same-scene flow, and clears on target change,
explicit clear, confirmed removal, or a fresh header proving it no longer active.
An independent document-target key fences late selection even while canonical
capture context is unavailable. Canonical capture revisions always come from
backend `context`; its `load_id` is compared against App `doc.document_id` (a load
identity), never against canonical `context.document_id`. Editor status/load/queue
changes trigger rereads, not fabricated
canonical revision values.

`sample_library_protocol === 1` and a live engine gate opening, without requiring
an image. The topbar opens management; PC-32452 offers management and reference
selection with a truthful identity card. The mounted-hidden host preserves pending
and unknown-write reconciliation. Four exact manual import/capture baseline leaves
are de-duplicated; official cloud, AI matching/models, local matching and other
uncovered controls remain explicit unavailable leaves. No entire family is marked
accepted or hidden by the local-library launcher.

Wire calls use `tauriInvoke('sample_library', {request:{action,request_id,request?}})`
and `sample_library_choose({kind})`, bypassing editor inspection invalidation.
Request IDs are unique; lost enqueue acknowledgment is queried, never resent.
Status polling backs off from 120 ms to 800 ms; IPC calls are bounded at 10 s,
read requests at 2 minutes and writes at 15 minutes. Those deadlines mean unknown
sent-write outcomes, not rollback. Cancellation is deduplicated after submission and
still awaits terminal status; unresolved cancellation may be retried during explicit
refresh, never by resending the original mutation. Terminal payloads are consumed and released; release
failure never changes a confirmed write result. Timed-out writes retain IDs: a
refresh first checks them and refuses to unlock review while any is still pending.
Every nonterminal unknown write also sends cancellation. Native pre-admission
tombstones prevent an invocation delayed beyond its acknowledgment timeout from
being admitted later. Before refresh can unlock review, the host requires a valid
cancellation-barrier response and a valid terminal receipt. A cancel response that
already carries a terminal is consumed with its truthful result, including success.
Pending cancellation is confirmed only by `cancel_requested:true` and still needs
terminal status. Failed/malformed cancellation
leaves review blocked and retries only cancellation/status on explicit refresh.
Unavailable receipts remain explicitly unknown and cannot alone unlock review.
Once the retained request is terminal, fresh catalog review and explicit manual
acknowledgment are still required for an unknown committed outcome. Only a terminal failure explicitly reporting
`outcome_unknown:false, committed:false` is known not applied. The adapter normalizes
legacy null group IDs to the reserved `ungrouped` ID before sending.

## Reusable panel integration contract

Memoize one `createSampleLibraryPort(bindings)` per local catalog root and keep that
port stable while the panel is mounted. Invoke no backend command names from JSX.
Supply `open`, optional `onClose`, and either `mode="manage"` or `mode="reference"`.
The default is management. Provide `onReferenceSelected` only when a genuine host
reference picker exists. That callback receives `sample_id`, `source` with the
original `{sha256,width,height}`, `render_sha256` and `asset_id`; it should store a
manual choice, not silently run a color operator.

The backend's returned arrays own ordering. `group_id="ungrouped"` is reserved and
cannot be renamed or deleted. Group deletion moves both active and archived rows
to that group while preserving their trash state. UI parsing tolerates null group
IDs for compatibility, but current writes use the reserved ID. The fixed group
must remain in `groups`. Sample reorder submits every active ID exactly once;
current-page reorder preserves all other page/hidden positions using `order_ids`. Group reorder submits all group
IDs, preserving the fixed group's position. Sorting buttons are the keyboard and
non-drag alternative.

Binding signatures:

- `snapshot({signal}) -> header` with `{version,revision,groups,capacity,storage,
  warnings,counts:{active,trash,total},group_counts,order_ids}`. There is no
  `samples` field. `order_ids` is the complete active ID list, at most 2000 IDs.
- `page({view,search,limit:48,cursor}, expectedRevision, {signal}) ->
  {revision,samples,total,offset,limit,next_cursor}`. The opaque cursor is pinned
  server-side to the canonical query and exact revision.
- `command(op,payload,expectedRevision,{signal}) ->
  {revision,affected_ids,capacity,counts,group_counts?,outcomes?}`.
- `chooseImportPaths('images'|'folder', {signal}) -> string[] | null`.
- `thumbnail(id, {signal}) -> data:image/jpeg|png|webp;base64,...`.
- `select(id,expectedRevision,{signal}) ->
  {revision,sample_id,reference,notice?,...smallReceipt}`.
- optional `captureCurrentResult(input,expectedRevision,{signal}) ->
  {revision,sample_id,reference,duplicate?,archived?,message?,capture,...smallReceipt}`.

Metadata is actually paged by the backend, not sliced from a downloaded catalog.
The UI keeps one page and a cursor chain, plus a Map containing only explicitly
selected rows from other pages. Page changes and header refresh preserve that
selection; intentional query/view/mode changes, explicit clear, a changed catalog
root, or a confirmed completed mutation clear it. Displayed counts come from the
header and server-filtered total, never from the current page length. Search is
submitted with Enter/the Search button, at most 240 UTF-16 code units, so typing
cannot cause a series of stale overlapping reads.

A stale page invalidates the view and requires explicit header refresh. The UI
never retries an old cursor at a new revision or silently truncates a page. It
validates offsets, page lengths, continuation/end boundaries, pinned revision,
IDs, group membership and header/filter totals. It never preloads every page or
fetches thumbnails for off-page cards. Pagination does not shrink catalog limits.

After a confirmed write or deferred reference materialization, the UI requests a
fresh header and first page at the returned revision or newer. A failed follow-up
read is reported as a read failure after a confirmed write, not as an unknown
write or permission to repeat it. New mutations remain disabled until a coherent
header/page pair is available.

Operations and payloads match the local backend:

- `group_create {name}`; `group_rename {id,name}`; `group_delete {id}`;
  `group_reorder {ids}`.
- `import_paths {paths,group_id}`. Images and folders use a native path chooser,
  not browser `File.name`, web upload, or a guessed local pathname. Directory
  expansion, path safety, bounded walks, format decoding, duplicate checks,
  storage budget and per-file capacity checks remain authoritative server work.
- `sample_rename {id,name}`; `sample_move {ids,group_id}`;
  `sample_remove {ids}`; `sample_restore {ids}`; `sample_reorder {ids}`.

`outcomes` accepts the backend `{index,name,status,message,sample_id}` shape;
`path`/`id` are also accepted when provided. Do not manufacture success outcomes
when the backend did not report them. Maximum active samples: 2000; per import:
1000. All mutations, including deferred reference materialization, use atomic
expected-revision checks. Small mutation receipts never echo the full catalog.
Selection/capture receipts retain the verified stable reference directly.

Map confirmed backend failures to `SampleLibraryError(message, code,
'not-applied')`. When `outcome_unknown` or `committed` is true, use mutationState
`'unknown'` unless a successful durable receipt is available. Generic rejected
Promises and malformed write receipts are conservatively unknown. Never turn a
transport timeout into a known rollback or retry a mutation automatically.

## Storage disclosure and admission policy

The header's required `storage` fields are `library_bytes` (owned originals,
thumbnails, staging, catalog and recovery metadata), `shared_reference_bytes` (the entire shared NPZ cache,
including other projects and unindexed resources), their sum `bytes`,
`free_disk_bytes` for the library filesystem, `shared_free_disk_bytes` for the
reference-cache filesystem, and configurable `budget_bytes`.

The panel displays owned/shared usage separately and exposes both free-space
readings with the current admission policy. Binary units are labelled KiB/MiB/GiB.
`LRT_SAMPLE_LIBRARY_MAX_BYTES` configures the backend admission policy, default
16 GiB. This is not a reserved or globally enforced quota: other cache writers do
not reserve against it and may increase usage. Parsing therefore accepts usage
already above policy and the panel reports it without hiding existing samples or
deleting resources. The two free-space readings may describe the same filesystem
and must never be added or described as reserved capacity. Free space is a read-time
observation, not a guarantee that a later write will fit. The empty fixture's zero
free-space values are synthetic structural values, never observations of a disk.

## Current-result capture: required evidence

`CaptureContext` must come from the backend's read-only `{method:'context'}`
response. Its canonical document revision is not `App`'s `status.doc_rev` or a
viewport revision. Do not reconstruct it from a preview. App `doc.document_id` is a load identity; compare it only to `context.load_id`. The context shape is: `{key,load_id,document_id,revision,label,available,unavailableReason?}`.
`key` must change on document or relevant edit revision change; it is used only
for local cancellation. The submitted input is
`{name,group_id,expected_context:{document_id,revision}}`.

`capture` evidence must come from the actual original-resolution render owner:
`{document_id,revision,state_key,sample_id,source_kind:'frozen_render',
original_resolution:true,render_sha256}`. The adapter validates requested identity,
returned evidence and the receipt's stable reference hash. Freeze and verify the
expected document before queued work starts and again immediately before atomic
catalog commit. Never use shared-memory display pixels, an HTML canvas, a viewport
screenshot, an upscaled preview, or a JPEG thumbnail for this operation. No render
capability means omit the port: the control stays disabled with a clear reason.

A duplicate capture may identify an already archived row. The UI distinguishes
that case and asks the user to restore it; it does not claim a new sample exists.
Cancellation after commit returns the truthful committed result, not a fake
rollback. Cancellation before commit must not create a catalog entry. Import deliberately
returns a truthful partial receipt: stopping only cancels remaining files, while
completed files remain catalogued. Both the cancel control and progress text state
that it is not a whole-batch rollback. Staged but unindexed assets are never
claimed as catalog entries or automatically destroyed by the UI.

## Close, cancellation and unknown outcomes

An AbortSignal is a cancellation request, not proof of rollback. The host must
forward it into its cancellation mechanism. Do not implement writes using only
`Promise.race` against a signal. A native write must return its committed receipt,
or an explicit known-not-applied/unknown failure. The UI does not reset a pending
write on repeated clicks. Closing requests cancellation and fences old replies;
reopening waits for the previous call to settle before reading the catalog. Keep
the adapter/controller alive if the panel is temporarily hidden, or arrange the
same pending-work reconciliation in the host if the component is unmounted.

Unknown writes block new mutations and reference selection. Refresh is read-only;
only explicit review acknowledgment releases the UI gate, never an automatic
retry. A fresh snapshot is not itself proof that a lost request never committed.
The host must not leave a still-running native write detached after rejecting its
Promise. If it cannot establish a terminal outcome, keep the write pending or
provide a dedicated receipt-query integration before enabling continued writes.

## Honesty and validation status

Only source inspection/static syntax parsing is allowed in this handoff. No
product execution/import, typecheck, build, test, model download/install, browser
session, or UI screenshot has been performed. Native/App integration is implemented
in source; compile/runtime/backend round-trip checks and the manual cases in
`REVIEW.md` remain outstanding. This is not tested end-to-end completion.
