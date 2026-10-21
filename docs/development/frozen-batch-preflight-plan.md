# Frozen batch preflight: end-to-end candidate

Original AI acceptance BATCH-001 preserves source-version snapshot; BATCH-002
protects targets edited after preflight. The new token backend freezes source/targets and consumes reviewed plans. It is
verified in focused Qoder backend checks; native/UI review wiring is now present
but awaits its own checks at this checkpoint.
Legacy commits without a token remain explicitly direct_unreviewed compatibility
operations. The narrow scoped-undo correction alone did not close this gap.

## Ownership

A separate document-version owner assigns runtime UUID row identities plus a
monotonic mutation fence outside recipes/undo snapshots. Retained/reordered rows
keep identity; removed/re-added paths do not. Successful project create/open rotates
workspace generation. _load_id is a render/import identity, not a stable document ID.
Undo never rewinds a fence. State hashes or stack length cannot detect edit→undo.

Preflight owns bounded immutable records: random token, workspace generation,
source identity/version/path, canonical serialized transferable module parameters,
selected modules/policy, target identities/expected versions/eligibility and rejected
inputs. Do not retain image/precompute arrays or mutable row references.

Commit consumes a token, not another editable source/selection definition. Reject
unknown, expired, consumed, foreign-generation tokens and conflicting extra fields.
Keep bounded terminal results for idempotent repeated commit requests.

## Commit

Resolve targets by stable identity, not stale index/path. Changed versions or missing
identities are explicit conflicts. Recheck eligibility; a preflight-blocked target
must not silently become authorized. skip_and_report applies unchanged eligible
ones; recheck writes nothing until a fresh preflight/reconfirmation. No overwrite.
Use frozen source modules even if current source is edited, switched or removed;
report those diagnostics without substituting the current photograph.

Revision fencing must cover admitted live mutation boundaries, effective history
undo/redo, parked batch writes, recipe-changing proxy recovery and eligibility
changes outside EDIT_CMDS. A conservative attempted-mutation fence may produce
false conflicts but must not be advertised as an exact changed-recipe counter.
Read-only status, compare, thumbnails and pure selection must not bump it.
Finalize result revisions before publishing success; outer history recording must
not double-increment or publish old metadata.

## History and UI

Keep one undo step per affected document. Batch undo retains scoped-value conflict
checking, but restores only recorded modules into current state so unrelated later
edits survive. Stable identities must also replace index/path-only ledger lookup.

Use dedicated request IDs and an epoch-bound native batch result owner/API. Enqueue
acceptance and command_done are not success. UI: preflighting→review→committing→
terminal, with actual source/version and target/conflict details. Selection/scope/
policy changes invalidate the plan; dismissed/late replies cannot revive it.

Required tests: frozen source after source edits/removal; target edit→undo/redo and
same-gesture return; reorder/remove/re-add; project create/open/restart; skip/recheck
zero-write behavior; identity/eligibility/proxy changes; duplicate token/click; live
and parked undo retaining unrelated edits; no conflicts from pure reads/selection.

## Backend candidate and remaining integration

- DocumentVersions owns runtime row IDs/workspace generation/conservative fences.
- PreflightStore owns at most 8 pending plans (30-minute lifetime, 2 MiB each),
  and 32 terminal records with a shared 16 MiB budget (8 MiB per receipt). Eviction
  never reopens a consumed token. Claim occurs before writes; an unencodable final
  receipt leaves an explicit unknown outcome, not permission to execute twice.
- FrozenBatchController owns resolution, conflict policy and correlated results.
  Stable identity lookup is linear in workspace+target count, not target×workspace.
- BatchSync validates all target histories/revision capacity before writes, renders
  the live target before parked writes, attempts live rollback on failure, and
  marks the project dirty for parked-only changes. This is an in-memory ordered
  operation, not a crash-durable database transaction. Unknown failure outcomes
  must not be presented as proof that nothing changed.
- Source version diagnostics and stable per-target revision/outcome evidence are
  retained in terminal results. Repeated completed tokens replay before edit guards.
- Lifecycle fences cover explicit strength, proxy recovery, internal precompute,
  failed face reattachment and device migration, not only normal edit commands.
- Native epoch-bound receipt ownership and the user review dialog are wired in
  this candidate; basic native/UI checks and hardware acceptance remain pending.

## Official / mature open-source comparison

The conditional-write principle follows RFC 9110 section 13.1.1, which checks a
representation validator before mutation to prevent lost updates:
https://www.ietf.org/ietf-ftp/rfc/rfc9110.html#section-13.1.1
This implementation adapts that principle to local document IDs/fences; it does not
claim HTTP conformance or use wall-clock timestamps as version authority.

SQLite documents serialized writes and snapshot isolation:
https://sqlite.org/isolation.html
The engine similarly orders mutation on one execution sequence and freezes review
parameters, but does not inherit SQLite's rollback journal or durability guarantees.
Pure metadata tests, actual engine integration and later UI checks must prove our
implementation rather than assuming these references make it correct.

## Native and UI ownership

`batch_host.rs` owns bounded request receipts, exact engine epoch/action/request
correlation, readiness admission and first terminal result. Engine stdout receipts
are drained before exit synthesizes unknown outcomes. `batch_api.rs` owns command
arguments; main only registers and routes. Existing unreviewed compatibility
commands remain available, but production UI synchronization always uses a token.

`batchWorkflow.ts` owns a pure preflight→review→commit→receipt lifecycle. It validates
source/target receipt identity, rejects stale review on selection/scope/policy/source
context changes and never treats queue acceptance as success. Both IPC awaits are
bounded. Timeouts/unknown results retain their request ID, even when the dialog is
hidden; the persistent launcher works outside retouch/filmstrip. Fresh mutations
remain blocked until receipt resolution or an explicit inspect-and-end-tracking
action. This acknowledgment does not cancel or undo an already-sent command.

`useBatchWorkflow` adapts React lifecycle and native ports. `BatchActions` provides
the real filmstrip entry, independent recipe conflict policy and scoped batch undo.
`BatchReview` shows the frozen source, modules, parameters, eligible/blocked targets
and actual per-target outcomes. App global comparison/history shortcuts do not
intercept dialog keys. Registry preflight/commit actions open this reviewed flow;
they are not mislabeled export dry-run or cross-file atomic export controls.
