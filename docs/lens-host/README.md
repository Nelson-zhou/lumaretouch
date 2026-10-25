# Current-photo lens host: AUTHORED / UNRUN

This source lane adds `lens_blur_host.py` and `lens_blur_jobs.py`. It uses the
existing complete current-edit capture, lens review stage, original Rust aperture
bridge, and `CreativeHost.commit_return(mode='new_image')`. It does not add a
numeric solver, depth inference, image downloads, replacement history owner,
original-file write, export implementation, or product acceptance result.

Only source reading, static Python AST parsing and hashes were performed during
authoring. Imports, product execution, tests, typechecks, builds, inference and
photographic acceptance were not run. The parent integration owns shared engine,
reader, transport and application registrations; this directory does not imply
that those registrations, native packages or UI paths have passed execution.

## Protocol migration and exact result semantics

The previously isolated source UI used wire version 1 and interpreted an applied
receipt as an edit to the original document with an advanced revision and a
history entry. That cannot describe the existing new-image creative return.
The aligned host uses protocol 2 for manual/preview/apply/cancel commands, reviews
and write receipts. Numeric lens recipes, depth assets and renderer capabilities
remain version 1. Old write envelopes are rejected, not silently reinterpreted.
This is a wire migration, not a saved recipe migration.

The review adds `result_source_sha256`: the actual full-resolution canonical
output asset ID without its `sha256:` prefix. This is not a PNG, original-file,
depth-raster or pixel-content-only digest. Apply must echo it and specify
`return_mode: 'new_image'`, in addition to the session, owner, candidate token,
recipe digest, both actual full-frame display-image digests and `reviewed: true`.
The stage candidate privately binds that output asset ID into its token too.

An applied receipt has exactly these fields:

```
version: 2
request_id, session_id, action: 'apply', owner, token
phase: 'done', outcome_unknown: false, outcome: 'applied', message
recipe_sha256, before_sha256, after_sha256
return_mode: 'new_image'
copied_original_document_id, result_document_id
result_revision, result_source_sha256, no_change
```

`copied_original_document_id` is the reviewed source document. The result ID must
be a distinct actual row. `result_revision` is that row's runtime decimal uint64
revision, not the original's revision and not its creative layer-document
revision. The common return currently advances the new row once, so it is
normally `"1"`, while the new creative layer document starts at revision 0.
There is no invented `history_entry_id` or original `document_revision` field.

`no_change` means byte-identical full-resolution output pixels. The stage reuses
the source asset in that case, so canonical output identity also equals source
identity. An explicitly requested neutral save still creates a distinct new
image; it is not reported as an original-document no-op. The original row and
its undo/redo history are preserved by the common return owner. The new image is
a baked canonical result with a normal creative base layer, not a newly invented
editable lens-recipe layer.

Pending and unknown receipts contain only the base identity, `phase`,
`outcome_unknown: true` and message. Rejected/cancelled terminal receipts add
only `outcome` with `outcome_unknown: false`. Cancelled is valid only for a cancel
command. Cancelling an already applied session returns rejected, never rolls
back or relabels that applied operation.

## Parent transport integration

All host commands execute on the existing serialized engine command thread.

```
{cmd:'lens_blur', action:'current', request_id}
{cmd:'lens_blur', action:'prepare_manual_plane', request_id, command}
{cmd:'lens_blur', action:'preview', request_id, command}
{cmd:'lens_blur', action:'submit', request_id, command: originalApplyOrCancel}
{cmd:'lens_blur', action:'receipt', request_id: freshLookupId,
 command: originalUnchangedApplyOrCancel}
```

All non-query outer request IDs must equal the nested command ID. A receipt
lookup uses its own mailbox ID while its nested command stays unchanged. Exact
schemas and request-size bounds are checked; unknown fields are not stripped.
The engine event is `lens_blur_result` with outer `request_id`, `status`, and
one of `context`, `review`, `receipt` or a failure `message`. Current acquisition
also returns the exact renderer `capability`. Unavailable native support returns
an unavailable capability and null context, never successful substitute pixels.

Parent hooks:

- `lens_blur_host.handle(engine, request, emit)` owns execution and receipts.
- `lens_blur_host.read_only(request)` identifies current/manual/preview/query.
- `lens_blur_host.guard_other(engine, name, request)` protects an unresolved copy.
- `lens_blur_host.dispatch_rejected(request, message, started, emit, engine=engine)` completes a
  mailbox rejected outside this host. Once execution might have begun, it must
  report unknown rather than a safe-to-retry rejection. Authoritative host
  receipts take precedence over generic outer guard errors. Without the engine
  receipt owner this adapter conservatively reports unknown for any write.
- `lens_blur_host.invalidate(engine)` optionally reclaims expired/stale leases.
- `lens_blur_jobs.controller(engine).ingress(line)` is the reader's Event-only
  cancellation hook. `stop()` sets all read/session Events on shutdown.

Do not pre-advance the source document revision for any lens command. The source
owner must still match when apply enters; the common copy transaction advances
the new row itself. Do not replace the engine-lifetime lens host on panel mount,
unmount, document switch or native capability refresh. Transport and UI must not
retry a timed-out write. Query its original command instead.

A cancellation-only reader control for the native bridge is:

```
{cmd:'lens_blur_cancel_read', request_id: originalReadId,
 request: originalCompleteReadEnvelope}
```

Native must retain and echo the same parsed envelope it originally emitted.
Python computes both its admission and cancellation digests itself; native and
JavaScript must not guess Python's float JSON serialization. The supplied proof
must name the same read request ID and one of the three exact read actions.
The full request-content identity is still checked, not just a partial owner
or session key. An optional internal digest-only control is also available:

```
{cmd:'lens_blur_cancel_read', request_id: originalReadId,
 command_sha256: exactOuterRequestDigest}
```

The digest is SHA-256 of `b'lrt-lens-host-command-v1\0'` plus sorted, compact,
ASCII-escaped, finite JSON bytes of the original complete outer request. This
control is consumed by the reader and sets only the matching source-job Event.
Ordinary `submit(cancel)` is not consumed: its matching session Event is set
early, then the complete command remains queued. Only after actual source-job
unwind does the serialized host publish a cancelled receipt. Apply transactions
are never registered for reader cancellation or repeated by that hook.

## Genuine current-source ownership

Capture uses a job-local `AssetStore`, never the long-lived creative host cache.
`creative_document_base.capture_current_asset` freezes the complete current
edited photograph at full source resolution, including its supported crop,
geometry, layers and repairs. No thumbnail or original-file pixels are relabeled
as an edited source. Import intermediates and capture snapshots are released
before review-display staging. Only immutable canonical bytes survive.

The public source owner is:

- Current row's actual `document_id`.
- `DocumentVersions.workspace` as `document_epoch`.
- Actual runtime document revision encoded as a decimal string.
- The resulting canonical edited asset ID, width, height and
  `exif_normalized_once` orientation.

Private ownership additionally captures the row object and index, document
version owner, load ID, creative owner nonce, actual people graph owner/fence,
complete graph digest, original pathname, device/inode/size/time stamp and real
original-file digest. Hot cancellation checks compare owners/fences/stamps only;
file and graph contents are rechecked at source, preview and commit boundaries.
Reopened epochs, same-size changed files, cross-document identities, changed
people context and later edits cannot authorize an old candidate.

This host accepts original and derived current photos only when their actual
canonical capture is opaque SDR, because the common retouch return rejects
transparent, signed or HDR pixels. Source and candidate are checked without
clipping, matting or integer conversion. Unsupported originals and canonical
creative assets are unchanged. The underlying numeric stage can retain HDR and
alpha, but that does not make this narrower return path compatible with them.

## Manual depth and real preview

No model or subject-focus path is enabled. Capture returns `manual-required`
with no depth. Only the exact explicit `prepare_manual_plane` acknowledgement
creates the constant raster; its provenance retains the acknowledgement request
ID and session. It is labeled an artificial editing plane, not measured or AI
depth. Supplied-depth import is not exposed by this host.

The stage performs the existing exact source-centre depth resampling and brush
rasterization and calls the original Rust aperture bridge on the full captured
source. Both full-frame PNGs are real display samples of those exact immutable
assets. The UI verifies image structure/hash/decode/natural dimensions and
requires both actual images to have been presented before acknowledgement.
The server correlates the submitted acknowledgement with the retained review;
it does not claim to independently observe the user's screen.

Point-focus validation independently samples four owned u16 raster values using
the UI's exact source-centre mapping and binary64 bilinear operation order. Its
near/far interval must contain that sample and be a symmetric radius around it,
clipped only at zero and one. No new saved-recipe radius restriction is imposed.
The `1e-12` validation tolerance covers
binary64 interchange, not a depth threshold adjustment. Arbitrary unrelated
intervals cannot masquerade as point focus. UI sliders explicitly switch to
interval mode. This checks provenance/intent and does not change the native
numeric solver or alter accepted focus values.

## Resource leases and outcome safety

There is one retained source, depth and candidate at a time. Conservative total
lease admission is 1,000,000,000 bytes including a 4 MiB ledger reserve. Working
admission is at most 2,000,000,000 bytes and the existing available-memory guard;
source/radius/brush detail is never silently reduced to fit. The stage's native
tap/refinement ceilings and cooperative 120-second deadline checks still apply.
Full capture also polls a 120-second deadline. This is not a force-kill timeout
or a bound on cancellation latency: existing whole-plane allocation/fill,
immutable serialization and shared canonical asset validation/hash sections may
run between polls. Later polls reject cancelled or expired work before candidate
publication and apply revalidates ownership; no partial result is committed.

Source leases are usable for 600 seconds and candidates for 180 seconds. Expired
or source-stale data is lazily released at the next host call or lifecycle hook;
there is no background timer. Replacing depth releases depth and candidate first;
replacing a preview releases the prior candidate. An unknown write retains its
bounded proof rather than expiring into an apparently safe retry.

Runtime ledgers have finite admission: 64 sessions, 256 read requests, 128 writes
and 2 MiB of write command/receipt bytes. Old write outcomes are never evicted to
make room. Read replay only returns an extant correlated lease or a prior failure;
it does not rerun a completed source operation. These are engine-process
receipts, not a newly persisted project log. After process loss a missing write
is unknown; old session/epoch commands cannot obtain a new execution.

Before calling the common return, the original exact write and unknown receipt
are stored. Successful publication is read back from the actual new row,
canonical bytes, source ownership and creative document structure. The terminal
receipt is saved before user-visible delivery or cleanup. A failed response,
late cancel, malformed result or post-commit cleanup failure cannot turn known
success into rejection or trigger another copy.

When the commit raises or readback is inconclusive, other mutations remain
blocked. Query can reconcile only positive proof of exactly one matching new
row with the expected canonical asset and private creative structure. No row or
an ambiguous row remains unknown; it is never guessed to be cancelled, retried
or overwritten. A failed common rollback may therefore require inspection and
recovery rather than a synthetic terminal success.
