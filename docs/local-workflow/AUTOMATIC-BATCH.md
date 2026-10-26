# Explicit automatic batch v1 — source authored, acceptance UNRUN

This is a separate opt-in **fixed exposure/white-balance recipe** batch mode.
It is not complete wedding AI retouching, adaptive exposure analysis, portrait
identity matching, or an assertion of image quality. Existing reviewed presets
remain reviewed. No image-view acknowledgment is generated or waived for them.

## Product reference and deliberate differences

Official [Photoshop batch options](https://helpx.adobe.com/photoshop/desktop/automate-tasks/process-a-batch-of-files/batch-and-droplet-processing-options.html)
separate source, destination/naming and stop-versus-log-error choices. Official
[Capture One Export Recipes](https://support.captureone.com/hc/en-us/articles/360021057158-Export-Recipes)
separate selected image variants and output recipes, processing new output files
non-destructively. Sources inspected 2026-10-25. This implementation follows the
explicit job setup pattern; it does not copy their overwrite options or imply
feature parity. It retains LumaRetouch's stricter no-overwrite and unknown-outcome
fences.

## Explicit intent, then a fresh start

The graph has an `automatic_preset` alternative to `compatible_preset`, never
both. Its exact ordered fields are `kind`, `preset_id`, `preset_sha256`,
`when_all_labels`, `intent`. The intent is:

```json
{"schema":"lrt.automatic-batch-intent.v1","mode":"automatic","scope":"directory_originals","source_mode":"captured_file_list","originals":"managed_copy_only","save":"target_recipe","collision":"fail_no_overwrite","unattended":true}
```

This stored object is **configuration, not fresh user approval**. Native
preflight returns the actual graph SHA-256. At Start the UI displays the exact
scope, preset, target-only project-save permission, output profile/destination,
label conditions and error policies, and requires an ephemeral checkbox. The
start request carries `automatic_ack` with schema
`lrt.automatic-batch-start.v1`, that graph SHA, and `accepted:true`. The native
owner additionally checks the current preflight token, lease and saved graph;
successful start consumes its tokens. Loaded/imported definitions do not restore
the checkbox. Graph/preflight/lease changes, connection loss and dismissal
invalidate it; starting consumes it before dispatch. A lost response is queried
under the same original request, never resubmitted as a new run.

## Finite captured file list

Automatic mode requires `directory_source.include_existing:true`. The existing
directory poller captures a bounded list of paths and full stat identities,
using the configured root, recursion and extension filters. This is a
**captured file list, not an atomic filesystem snapshot**. Later arrivals are
not silently added. Captured files must retain their exact stat identity and
pass a complete stable-byte hash read and the real managed-copy precommit proof.
Changed, replaced or missing captured inputs fail explicitly rather than being
rebased onto a new occurrence.

The same durable runner journals the initial capture before admission, rejects
an over-capacity capture before any image mutation, and seals after all captured
entries are admitted. The existing owner limit is at most 64 inputs (and can be
smaller); there is no automatic lease rotation or silent first-N truncation.
Once sealed, the existing scheduler drains admitted inputs and the real lease
release determines settled completion. The separate reviewed watched workflow
retains its original behavior.

## Canonical owner chain

1. Existing Rust `DurableRunner` records each exact intent before dispatch.
2. Existing managed-copy ingestion proves each original occurrence and saves its
   actual document/provenance receipt. Originals are never edited in place.
3. `AutomaticPresetHandoff` verifies the graph's automatic intent and exact saved
   preset hash. Only `lnx.exposure.v1` and `lnx.white_balance.v1` are admitted.
   An unsupported mixed preset is refused whole, not filtered to a subset.
4. The existing target-load handoff pins source bytes, document revision, clean
   project CAS, prior editor state and every unrelated document. Canonical
   candidate/source/render-input proofs assess this target. This is **not** a
   human visual review and produces no before/after image-view receipt.
5. The assessment is explicitly `requires_review:false, review:null`, bound to
   the automatic graph/intent/target. The core and actual engine graph reject
   using that assessment on a reviewed node. The public handoff says
   `mode:"automatic"`; manual review steps and image ACKs are rejected.
6. The journaled ApplyPreset enters the normal preset dispatcher, canonical
   candidate replay and existing history. The automatic owner checks the actual
   post-history receipt and actual resulting complete state against the frozen
   candidate; it does not install a second recipe or history system.
7. Existing scoped project codec/CAS save commits only this target and its
   ordinary history. Existing verified editor return must preserve the original
   editor recipe. Only then is the genuine `preset_applied` receipt emitted.
8. Existing destination planner freezes exact per-document outputs; normal
   export/render/atomic publication and byte-hash readback prove completion.
   JPEG95/RGB8/sRGB/scale1 is the explicitly chosen currently supported profile,
   not a guessed settings hash. Collisions never overwrite or silently rename.

The completed-document origin fix keeps the original import receipt/source proof
while comparing its owner readback's **current** revision with the completed
saved revision. The completed row stamp independently prevents stale output.
It does not reinterpret the original import as having applied the later edit.

## Failures and unsupported scope

Source and import failures stop. Automatic preset and export offer stop/skip for
definitive failures before an uncertain effect. Once a target transition,
application, save or output may have occurred, missing/unknown outcomes remain
query-only and keep ownership fenced. Skip is never permission to discard an
unresolved loaded target or partial save. Stop is not rollback or cancellation;
the existing handoff barrier waits for verified target return. Restart never
recreates an old lease or restarts a mutation. Current unknown-owner recovery
may require explicit inspection; automatic repair/replay is not claimed.

Only directory originals are supported by this slice. Existing project/group
selection is not relabeled as supported. Skin, finish, texture, geometry,
identity-dependent effects, XMP adaptation and manual-support modules are
refused whole. Finish/texture currently require each enabled target face's own
measured skin/occlusion/landmark analysis and canonical people state; automatic
portrait preparation remains a later owner extension, not a fallback algorithm.

## Verification and acceptance gates

Only source reading, Python AST, JSON/text and hash inspection are permitted in
this development pass. Fixtures are authored **UNRUN**. No tests, typechecks,
builds, inference, photos, product runtime, dependency install/download or
publication were performed by this workstream.

Local QA must cover fresh and imported definitions; old reviewed mode; expired
preflight and dismissed/reopened UI; changed preset/source/root; empty capture;
new arrivals; cap refusal; multi-poll capture/seal; restart around checkpoint and
every intent/send/commit boundary; unknown load/apply/save/export; retained
normal undo/redo and save/reopen; no unrelated document changes; exact original
provenance after revision advancement; collisions and no-clobber output;
skip/stop/partial results; genuine final output bytes and actual photographic
quality. Source inspection is not a passed acceptance result.

## Separate automatic semantic archive scope

The explicit global six-class `.lrtcolour` path is documented in
[AUTOMATIC-SEMANTIC.md](AUTOMATIC-SEMANTIC.md). It reuses the same finite scheduler
and fresh Start gate, not the scalar catalogue or same-scene reference fitter.
Its source integration, fixtures and all runtime/photographic acceptance remain UNRUN.
