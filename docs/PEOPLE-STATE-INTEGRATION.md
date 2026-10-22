# Anonymous people integration: source implementation, runtime acceptance pending

This snapshot connects the canonical graph to the actual portrait renderer, project
lifecycle, scoped history, frozen confirmed-person transfer, recovery banking and
reachable native/UI commands. It is not a claim that PORTRAIT-003–006 or BATCH-001–004
has passed acceptance. Only static source/AST/data/whitespace checks were permitted.
No product import, inference, model download, test, build, typecheck or compiler was run.

## Handbook and provenance

The baseline handbook `manual-text.txt` lines 962–972 and 1012–1027 supplies the
stronger original granular inheritance contract. Mapping controls under PC-47211:
labels dacc840b92; single person 7077d6f614; current-photo all people 06d9ae036b;
linked groups d381bdebf7; manual age/gender correction 84338ba2d8; detection correction
cb1b252660; face add/delete 5180dee1ad. Workflows: WF-47211-94a68c31d0 and
WF-32480-c75523501b. Mapping: `baseline_probe/AI开发资料包/功能需求验收映射.json`.
The [official guide](https://www.pixcakeai.com/guide/47211), updated 2026-09-09 in the
prior source audit, is a product comparison, not a claim about its implementation.
The supported [MediaPipe BaseOptions](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/BaseOptions)
byte-buffer loader is used to hash the actual immutable detector bytes supplied to
the backend. Semantic model evidence is separate. No proprietary algorithm, automatic
cross-photo identification, demographic inference, real names, accounts or uploads.

## Canonical state and ownership

`people_state`, `people_graph_owner`, `people_associations` and `people_resolver` own
one project/session graph with monotonic graph and association fences. FaceRef is
`{asset_sha256, face_instance_id, analysis_revision}`. Random instance IDs survive
selection and detection order changes. Frozen measured landmarks and their actual
model/backend evidence are retained separately from manual labels/status. Reopening
cannot upgrade ownership to a changed model or silently attach by proximity/index.
Explicit reanalysis increments the analysis revision. A manually added rectangle is
unresolved until the real region detector succeeds; full-source semantic masks still
come from the actual segmenter. Detection has a visible 32-face bound and explicitly
reports that it is not a guaranteed census.

Sparse scalar leaves resolve face > explicitly confirmed anonymous person > user
priority group > captured current-photo asset SHA > neutral. Missing higher-priority
keys inherit. Equal-priority differing group values refuse rather than using creation
order. Unset deletes one leaf. Person/group cross-photo effects require explicit
membership/confirmation and explicit scope selection. Selection is only an editing
cursor and does not appear in the final image plan. The same resolver supplies UI
values/provenance, preview, export and transfer. `people_scope.describe()` is the
actual portable leaf catalogue; unsupported masks/identity state are not listed.

`people_command` and `people_host_commands` fence commands by document ID, workspace
epoch, document revision, graph revision, association revision and exact target/ref.
People receipts include request/action identity and authoritative doc_state. Reused
request IDs with different bodies refuse. Native receipt/status transport keeps
uncertain requests queryable rather than silently resending them.

## Real render consumers

`people_algorithms`, `people_geometry`, `people_effects`, `people_render_runtime`,
`people_pipeline` and `people_engine_runtime` adapt the existing algorithms rather
than replacing their solvers. Every enabled face uses its own frozen source analysis.
The geometric chain is M(E(N(B(A(x))))), evaluated off-grid and sampled once, without
repeated strength. Overlapping supports use deterministic stable-instance priority;
unsafe Jacobians, missing evidence, group conflicts and memory/support budgets refuse
publication. Refusals are per-face facts, not permission to silently omit an active edit.

The real preview and original RGB8/16 tiled export use this common map for image
sampling, source masks, local recovery deltas and reference-colour authentic-scene
support. Full export prepares effects from the original source, not enlarged proxy
corrections. Lip and wrinkle effects run on frozen source pixels before common
geometry; eye detail/enhancement supports follow the same geometry. Source-owned
support cannot be inherited as another face's mask. Export reports the all-face plan,
actual per-face facts, overlap policy and full-resolution preparation separately from
legacy single-face statistics.

`people_support_assets` and `people_recovery` retain append-only, content-addressed,
source-normalized lip/wrinkle recovery vectors with exact FaceRef and landmark/backend
proof. Real brush preview temporarily installs candidate all-face prepared state and
restores it afterward. Commit uses the canonical publication transaction. These two
recovery targets require explicit face scope; the existing whole-photo targets keep
their original controller. Clear removes the active pointer, not bytes required by
undo/reopen. Old detached global rows cannot resurrect on later synchronization.

## Lifecycle, migration and history

`people_host`, `people_project`, `people_retained_analysis`, `people_snapshot`,
`people_export` and the existing server/project/export hooks persist the graph, measured
analysis and immutable support store. Stored legacy recipes are retained; only the
prepared export snapshot neutralizes duplicate legacy consumers. Ambiguous old box
banks, ownerless lip intent and nonzero `_deform_default` are archived unresolved.
The old default only rendered the selected face, so it is never silently expanded to
all people. Reachable review can explicitly bind portable parameters to a face/current
photo or retain them inactive. Multiple unresolved records can be reviewed in stages.
Missing/ambiguous active intent blocks edited rendering/export. A clearly flagged
original-unapplied loading/history view keeps correction controls reachable; it is
not presented as an edited preview or successful export.

Existing document history carries sparse touched-record/leaf patches and a pinned
association fence, not copied project graphs. Protected undo refuses overlapping
later edits or changed association ownership and cannot overwrite another photo.
Project persistence retains existing undo/redo stacks and source-addressed missing
photo histories. Support/landmark assets remain available for earlier revisions.
Shared mutations use the existing batch ledger and its protected group undo/redo.
History may deliberately refuse after association changes rather than guessing a
new identity binding.

## Confirmed transfer and reachable UI

`people_confirmed_transfer`, `people_transfer_adapter`, `people_batch_transfer` and
`people_batch_ledger` extend the existing FrozenBatchController, token store, document
versions, receipt transport and ledger. There is no second unrelated batch engine.
Preflight freezes explicit target paths, unique confirmed anonymous person, exact
source/target refs, selected operation/parameter leaves, source bytes, document and
association revisions, and confirmation revisions. It prepares actual target-owned
consumers before review. Commit is token-only, rechecks bytes/revisions after expensive
preparation, preserves unselected leaves, and reports each target's expected/current/
result revision. Masks, landmarks, local support and identity links never copy.
Unconfirmed/missing/changed targets are blocked or skipped according to the reviewed
policy. Undo/redo uses protected graph patches through the existing ledger; project
persistence retains these entries and only rebinds documents by exact path/source.

The PeoplePanel replaces misleading all-person locks and disabled correction chips.
It exposes face selection, asset all-people scope, explicit groups/person confirmation,
manual labels/status, region analysis, sparse overrides/unset, provenance/conflicts and
legacy review. Geometry gestures capture target context and cancel pending intent on
scope changes. Numeric portrait sliders use one-inflight/latest-leaf sparse requests.
An App-lifetime confirmed-transfer panel uses the existing batch workflow with explicit
per-leaf checkboxes, frozen evidence review and real protected undo/redo. Whole-photo
skin/clothing controls remain labelled as whole-photo semantic operations, not invented
per-face controls. Existing generic single-face batch restrictions remain intact;
canonical portrait transfer is only enabled through the explicit confirmed-target path.

## Required qoder runtime gates, not executed here

1. Edit A then B; revisit A; save/reopen; undo/redo; preview and RGB8/16 export must
   preserve both edits and remain identical when only the editing cursor changes.
2. Three or more faces, changed detection order, overlapping supports, explicit
   reanalysis, disabled/unresolved selection, failed region detection and visible
   truncation. No old recipe may bind to a newly detected different face.
3. Per-leaf inheritance/unset, conflicting equal-priority groups, explicit confirmed
   person scopes across photos, stale document/association/target receipts and races.
4. Old default/box banks, ownerless lip and source-owned recovery migration, staged
   legacy review, missing models/source photos and retained unapplied loading view.
5. Different A/B recovery vectors; preview, clear, undo/redo/save/reopen; face-scope
   rejection under group/person/all-people; source/analysis change refusal; mask and
   reference-colour provenance alignment through all-face plus downstream geometry.
6. Confirmed-target selective transfer with reviewed leaves, target changes after
   preflight, skip/recheck policies, protected group undo/redo, persistence and uncertain
   receipt lookup. Unselected target parameters and unrelated photo edits must survive.
7. Proxy/full-resolution correspondence, original RGB16 precision, memory budgets,
   all-face refusal visibility and no silently truncated active effects.
