# Integrated single-photo host contract

Source wiring is present. Runtime, performance and photographic acceptance are UNRUN.

## Ownership and lifecycle

- Engine owns exactly `_semantic_colour`, `_semantic_colour_bundle`, and
  `_semantic_colour_mask_assets`. Init, neutral document state, capture/restore,
  history, project, frozen export and device replay preserve these fields.
  Decoded mask and full reference bundle hashes are checked at restore. Project
  v12 preserves v11 sky semantics; older readers must reject rather than silently
  omit the new late colour stage. No inference is required to replay an applied
  recipe from valid retained data.
- `semantic_colour_host.SemanticColourHostMixin` owns its commands and cancellation
  metadata. The command thread alone changes editor state. Its controller owns
  revision/history advance, so the generic dispatcher does not double-advance.
  Worker completion is polled from the existing lifecycle tick; document revision
  change cancels the pending proposal, never clears the applied recipe.
- `export_snapshot.state_to_export_snap` is the common active/stored-document
  snapshot builder, extracted from the former server implementation. The semantic
  binding uses the exact same canonical people snapshot returned for rendering.
- `VramPipeline` applies the generic native stage after geometry and PC32455.
  ExportSpec carries recipe, canvas binding, verified original source path/stamp,
  and private mask resources. Active transfer forces float processing; source-file
  changes or geometry/material mismatch stop strict export. Preview preserves the
  recipe visibly suspended. Ordinary upstream colour changes do not trigger ML.
- Freeze excludes only this module's previous contribution, retains PC32455 and
  existing edits, and renders full original pixels with progress cancellation.
  Both inference inputs are exact immutable rendered canvases, not source paths.

## Native protocol and budgets

Tauri `semantic_colour` accepts `{action,request_id,request?}`. Actions request,
status, cancel and release operate an independent epoch-bound mailbox. Request
body is `{action:operation,...payload}`. Engine receives
`{cmd:'semantic_colour',action:'request',request_id,request}`.

Terminal event is `{event:'semantic_colour_result',protocol:1,action:'request',
request_id,success,outcome_unknown,committed,result?|error?}`. Status returns a
matching pending/done/unavailable wrapper. Successful submission is not commit.
No original command is retried after lost acknowledgment. Unknown mutations stay
fenced until cancellation/status reconciliation; released IDs cannot be replayed.

Requests are capped at 2 MiB. Public responses never exceed 8 MiB, with smaller
method reservations (4 MiB normal, 2 MiB mask overlay, 16 KiB start/cancel) and a
16 MiB mailbox cap. Receipts remain until explicit release; no eviction admits a
new native request. The 24 MiB proof/mask allowance exists only in the private
worker. Applied mask arrays remain in project assets/cache, never UI transport.

The existing sample-library cancellation writer and ingress remain intact.
Both owners share one atomic stdin writer. Only cancellation metadata is handled
out of band; semantic reads do not invalidate library capture. Editing intent
cancels pending full-image semantic capture before entering the normal queue.

Operations:
- state: {}
- capture: {context:{document_id,revision},reference:{source,render_sha256,asset_id},session_id}
- start: {session_id,mode,strengths:[overall,tone,colour],reference_selection:null|mask,target_selection:null|mask}
- poll: {session_id}
- commit: {session_id,proof,reviewed:true}
- edit: {context,operation,payload}; strengths, enabled, reset, group_parameters,
  group_enabled, group_reset, group_delete, mask_objects
- cancel: {session_id}; names only the pending session
- mask_overlay: {mask_id,objects:null|edited primitive list}; bounded actual composition

## UI and packaging

`ColourTransferTools` keeps PC32455 and PC32452 separate, consumes the existing
sample-library `selectedReference`, and mounts one recipe shared by quick/precise
views. Load identity controls lifecycle; canonical document/revision controls
writes. Selected-mask previews are lazy and generation-fenced. `stage-engine.sh`
builds the dependency-free native library and stages source/license attribution;
no runtime compiler/network/model fallback is added.

Batch/preset target recomputation and reference intent transport remain separate
pending work. No scope/preset registration copies fitted gains. Local dual-image
mode is explicitly excluded. New sky/landmark/SAM/people adapters are not claimed
by the six-class implementation.
