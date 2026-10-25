# Local workflow editor and run panel

Status: isolated source implementation. No execution, imports, tests, typecheck,
build, browser rendering or integration validation was performed in this pass.
The UI must not be described as a working native runner until a real host adapter
is implemented and verified. No `App`, native bridge, engine or shared files are
changed by this module.

## Scope and reference

Reference: [PixCake automation workflow handbook](https://www.pixcakeai.com/guide/8YEKwsjJg7),
read 2026-10-25 (page update 2026-10-12). This implementation adopts its local
node configuration, explicit connection editing, preflight, start/stop and run
record interaction. It is a bounded local implementation, not a claim of the
reference product's broader feature parity or a copied implementation.

Supported editable graph: directory source → managed import → optional path
labels → optional compatible preset → export. Nodes and edges are real data,
edited through accessible structured forms, not a nonfunctional decorative
canvas. No preset is invented for the minimal three-node workflow. Adding or
removing a node requires the user to repair its connections before preflight.

No ERP, network fetching, arbitrary scripts, AI culling, branching, loops,
cross-device template service or implicit interactive-project mutation is
implemented. Filesystem paths and immutable preset/export fingerprints are
entered explicitly. A genuine engine-returned fixed export profile may instead
be deliberately adopted into the draft. There are no nonfunctional file chooser
buttons, guessed recipe hashes or generic export-configuration claims.

## Integration surface

- `ui/src/localWorkflow/index.ts` exports `LocalWorkflowPanel`,
  `WorkflowController`, and all v1 DTOs.
- `contracts.ts` contains the injected `WorkflowHostPort`. Its graph DTO mirrors
  `core/local_workflow/schema.rs`, including `include_existing: false` by default.
- `controller.ts` owns request recovery, readback, editor locks and snapshot
  ordering. Keep one controller and port per stable host `scope_id` outside the
  panel. A host scope change requires a new controller; dispose the old one only
  after its pending identity has been retained by the host journal.
- `LocalWorkflowPanel.tsx` renders the editor and records. Mounting reads the
  workspace; while visible, a two-second non-overlapping timer only queries
  existing requests/runs. Dismissing the panel removes that timer, not the run.
- `model.ts` provides local structural checks, conservative path-overlap checks
  and lease matching. Host canonical filesystem checks remain mandatory.

The parent integration supplies the port. Passing `null` to `WorkflowController`
allows local draft editing but never creates a pretend saved definition,
preflight, lease, successful receipt or active run. No native command name is
invented. Do not construct a new port/controller on each React render.

The UI port is an orchestration boundary, **not** the raw core per-node
`Command`/`Receipt` transport. The adapter must translate owner-validated core
results into `WorkflowRun`/`WorkflowFileRecord`/`WorkflowNodeRecord`; it must not
derive success from a dispatched command, queued callback or elapsed time.

## Host requirements

1. `readWorkspace` returns a monotonic workspace revision, genuine capabilities,
   persistent saved-definition/run summaries, the active run, and **every**
   unresolved request for this scope. An unknown result remains unresolved until
   its owner establishes a terminal outcome. A missing journal entry is not
   proof that a mutation never occurred. Bound record pages and report
   `records_truncated` and actual totals honestly.
   Optional `recipe_sha256` and nested `recipe_profile` fields come from the real
   read-only engine profile request, not a UI-generated profile or digest. The
   supported exact shape mirrors `workflow_owner_protocol.RECIPE_PROFILE`:
   `profile`, full `export_options`, full `destination`, `watermark: null` and
   `layout: null`. Validation requires every declared v1 field/value, rejects
   unknown/missing settings and limits the serialized profile to 8 KiB. The
   complete unchanged nested object is displayed as escaped JSON, including
   destination conflict/creation behavior and null watermark/layout. Nothing is
   silently flattened or omitted, and the client never recomputes or substitutes
   the engine-owned hash. The panel provides a separate “use returned profile”
   action. That action copies only the verified host-returned hash to the export
   node, increments the graph revision, marks the definition dirty and clears
   preflight. It does not save or start. `recipe_profile_pending: true` enables
   read-only workspace polling until this actual request finishes; absent/false
   does not cause endless profile polling. A compatible preflight report can
   also carry those descriptive profile fields, after its identity is verified.
2. `readDefinition` returns the requested graph plus an opaque storage revision.
   `save_definition` uses `expected_storage_revision` for compare-and-swap. Do
   not replace someone else's newer definition. Saving never starts a run.
3. `acquire_project_lease` validates the **exact currently loaded, already saved,
   clean project**, its identity/revision and exclusive workflow ownership.
   `dedicated: true` means this current project is exclusively leased to the
   workflow, not that another project is silently opened. The host pauses
   interactive edits while it owns the lease; it must not implicitly save,
   switch, open or close a project. The opaque expiring lease binds that exact
   project/path. A lease alone never imports photos. Explicit
   `release_project_lease {lease_id}` is available only with no active/unsettled
   run or unknown request. Its terminal outcome is
   `{kind: 'release_project_lease', released: true, lease_id}`; it must reflect
   actual host release. Unknown release outcomes retain the original request
   and ownership state for query, never a new release attempt. Editing/loading a
   different draft must not hide an already held lease. Panel closure must not
   silently release active-run ownership. The runner owns safe renewal and must
   keep unresolved owner effects fenced. Native workspace responses always
   populate `lease` (including null) for rehydration and `host_scope_id` matching
   the port's persistent `scope_id`; these fields remain optional in the v1 type
   for older adapters. An absent field is not evidence that no lease exists.
4. `preflight` is read-only. Validate the full graph, host policy support,
   canonical paths, absence of symlink aliases, existing roots, image-source
   capabilities, pinned preset/recipe identity and saved-project lease. Source,
   managed originals and export roots must be pairwise disjoint, and the project
   file must reside outside them. Bind the returned token to the exact graph,
   lease, relevant filesystem state and immutable preset/export content. Recheck
   at `start` and at actual mutation; client validation is not a security lease.
5. Before side effects, durably journal each submitted request ID and its command
   fingerprint. Query the **same** request ID on lost responses, pending or
   unknown outcomes. Do not replay an unknown request under a fresh ID. A success
   response must include the matching typed outcome and real owner readback.
   Failed/cancelled are definitive terminal outcomes only, never timeout aliases.
6. `start` admits a frozen graph only with a valid preflight and lease. Its run
   snapshot must identify the same graph revision/lease. `stop` requests the
   scheduler's safe stop and returns its actual current state. A stop request is
   not immediate rollback and cannot erase already committed/imported/exported
   effects. `readRun` must return terminal records after a run stops, not merely
   omit it from the active list. Sequence numbers strictly increase whenever a
   run snapshot changes; lower/equal sequences cannot overwrite newer snapshots.
   `effects_settled` must remain false while any owner operation needs readback,
   including after the scheduler reports `stopped`. The UI keeps querying and
   keeps the graph locked until the host positively reports all effects settled.
7. Map review-bearing preset families to their existing retained review systems.
   Report `paused` plus the file/node/family/reason and `review_id`. `open_review`
   opens that real review UI only. There is deliberately no `approve`, `ack`,
   “approve all” or UI resume action. The scheduler may proceed only after the
   original effect owner validates the exact document/source/preset/review
   receipt and existing pixel-presentation requirements. An unsupported preset
   or unavailable review entry stays blocked; never bypass it with a fallback.
8. Advertise policies per node only when actually implemented. Directory-source
   discovery requires `stop`. `keep_continue` is restricted to compatible preset
   failures where the owner proves a definitive failure and an unchanged, usable
   retained document. Unknown commits and required review cannot become `skip`
   or `keep_continue`. Unsupported selections remain visible and block preflight.

## Safety and lifecycle behavior

All graph modifications increment the graph revision, mark the draft unsaved
and discard preflight. Start requires a saved definition, matching unexpired
dedicated lease, matching unexpired successful host preflight and no diagnostics
or pending writes. Active/paused/stopping runs and unresolved writes lock graph
editing. Replacing an unsaved draft requires an explicit inline discard choice.
An explicitly requested safe stop is still allowed for a known active run while
its original start response is unknown, unless a stop is itself unresolved.
This never replays the start; late older start snapshots cannot resurrect a
stopped run. Multiple unresolved request IDs are queried in rotation.

The controller serializes its asynchronous operations. Request IDs are retained
in memory and best-effort session storage before submission; the host journal is
the authoritative recovery source across process restarts. Browser storage only
contains request IDs/kinds, never project paths or lease credentials. Closing or
disposing the view does not cancel a possibly committed mutation. A disposed
controller ignores late responses. Inspection dismissal has its own generation
fence so a late read cannot reopen dismissed records. Workspace/run versions and
preflight/request identity are checked before applying results.

Path checks in the browser are intentionally insufficient for symlinks, platform
case rules and filesystem races. Canonical ownership validation is the host's
responsibility. Graph limits mirror the source schema: 3–5 nodes, single chain,
250–300000 ms settling, 1–32 unique lowercase extensions, up to 64 label rules,
lowercase SHA-256 fingerprints and 256 KiB serialized graph size.

## Authored acceptance fixtures: UNRUN

`ui/src/localWorkflow/workflow.unrun.test.ts` contains source-only fixtures for:

- Minimal graph without a pretend preset; explicit first-scan inclusion.
- Source/export port rules, cycle/duplicate/fan-in/fan-out and disconnected graph.
- Pairwise directory overlap, project-in-root refusal and policy support.
- Label producers/conditions and fingerprint/parameter boundaries.
- Edit invalidation, lease expiry and foreign preflight refusal.
- Explicit unused-lease release, workspace ownership rehydration, no hidden
  lease loss on draft replacement, and release refusal while effects/receipts
  remain unsettled.
- Explicit actual-engine export-profile adoption, invalid/absent profile
  refusal and host-declared pending-profile polling without auto-save/start.
- Exact nested engine-profile preservation, including destination and null
  watermark/layout, plus rejection of partial, unknown, nonfinite, oversized or
  altered structured profiles. The profile fixture matches the source constant;
  fixture hashes are test-only supplied values, not a production digest claim.
- Unknown/mismatched receipts, identical-request querying and duplicate-click lock.
- Disposal during pending mutation and dismissal during pending record read.
- Actual-review opening without auto-ACK/resume and authoritative safe-stop state.

Runtime fixtures use an explicit test-only host. They are not a production
adapter and are never imported by the panel. The current source-only instruction
forbids executing them. Before claiming integration readiness, authorize and run
the repository's applicable typecheck/tests/build plus real host/browser QA for
keyboard access, narrow layout, delayed replies, interrupted requests, reopening,
source-folder arrivals, retained review proofs, stable source stamps, collision
handling, stop boundaries, saved-definition CAS and process-restart recovery.
