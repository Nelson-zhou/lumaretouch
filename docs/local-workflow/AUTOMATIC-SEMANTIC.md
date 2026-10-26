# Automatic directory semantic colour — source-only integration / UNRUN

This adds a separate explicit **global, six-class semantic colour** intent to the
existing `automatic_preset` execution node. It is not the existing ORB/homography
same-scene reference recipe. No new node/scheduler, model, history owner, generic
text-preset registration, source-mask copy or human-image ACK is introduced.

Requirements traced: `ui/src/spec/workflows.json` automatic 追色 workflow and
`ui/src/spec/refine.json` full-image batch/preset per-target recomputation. The
existing reviewed semantic batch/preset and reviewed workflow continue to require
their real review. Automatic execution is opt-in, never a migration of those modes.

## Selection, identity and Start

1. Select the semantic scope in the local workflow panel, enter an existing
   `.lrtcolour` absolute path, and explicitly validate/select it. The read-only
   native action returns metadata, never image bytes. It snapshots a bounded
   regular no-follow leaf, validates the existing archive manifest/chunks and
   authentic full-float reference resource. No semantic inference runs here.
2. The graph pins `preset_id = semantic:<archive SHA-256>`, the same
   `preset_sha256`, `reference_source_policy = reject_same_source`,
   `semantic_scope = global_six_class_per_target_fit` and `semantic_archive`:
   exact path, file byte count/SHA, intent SHA and **canonical portable JSON text**.
   The text preserves Python float representations through JavaScript/Rust; it
   must not be parsed/re-serialized to construct the graph. It contains the full
   reference source/asset/render identities, mode, strengths, all requested group
   switches and all 50 manual offsets per group. No target gain or mask is portable.
3. Save the definition and preflight the real project lease. The engine takes a
   new private byte snapshot and rejects any difference from the selected metadata.
   It retains that exact archive before returning the matching preflight identity.
   Later original-file replacement cannot substitute new archive contents. Every
   target rechecks the retained archive and reference resource hashes.
4. The panel displays identities, complete intent, source/managed/output paths,
   selected output profile and error policies before the existing fresh,
   graph-bound Start checkbox can be enabled. Missing/mismatched archive readback
   blocks consent. Loading definitions, edits, rechecks, disconnects and dismissal
   do not restore old consent. Read/validation and the checkbox do not start work.

## Existing finite scheduler and owners

The same captured-directory scheduler requires `include_existing:true`, refuses
an over-capacity list before imports, admits at most the genuine lease limit
(currently at most 64), excludes later arrivals and checks each captured stat and
complete source identity. It imports managed copies, never edits originals.

`workflow_auto_semantic.AutomaticSemanticHandoff` reuses exact target opening,
other-document/source fences, the original-editor return and scoped project
codec/CAS save. Archive ownership is separate from the ordinary preset catalogue;
generic preset admission explicitly refuses semantic intent. Mixed portrait,
scalar, same-scene-reference, local-mask or unknown intent fields are refused.

`FrozenArchive` lazily runs the existing reference `BatchFitJob` once, after Start.
Its cache contains only exact reference binding, real model/runtime receipt and
full-precision spatial reference samples. Failed reference analysis is not silently
retried. Each managed target receives its own original full-canvas render, real
six-class semantic analysis and independent Rust colour fit through
`semantic_colour_batch_target.prepare`. Requested missing classes (including
closed groups), unsupported sources, offsets outside parameter bounds and missing
models fail explicitly, without dropped groups, proxy substitution or copied fit.
The reference photo and identical source-byte aliases are explicitly refused.

Each target's fit is frozen once. Automatic preparation does not generate review
images. A complete candidate render is still checked against source/people/repair
identities. The existing full-source, 32-million-pixel, worker-time/result and memory
bounds remain; the adapter additionally admits retained reference copying before
full candidate render. There is one active target proposal, not a directory-wide
bank of full images or masks. A failed target preparation cannot be refitted under
its original identity.

After the durable core ApplyPreset intent, commit rechecks the frozen proposal
and uses `semantic_colour_batch_ledger.publish` for the AI-owned fields plus the
normal live history boundary. No fit or inference call occurs at commit, save,
return, export, undo or redo. The actual post-history revision and complete applied
state must match the frozen candidate. The existing target-only project encoder,
manifest CAS/readback and verified prior-editor return must finish before export.
The existing immutable JPEG/PNG8/TIFF16 profiles remain available; incompatible
source precision or codec/effect capability is refused, never format-fallback.

## No fabricated review, no unsafe skip

Automatic assessments have `requires_review:false, review:null`; reviewed-mode
steps/images are refused. Persisted semantic diagnostics use the legacy recipe
summary field `last_review` with an explicit `authorization` record containing
`reviewed:false`, graph/operation/archive identities. The semantic panel labels
these as machine assessments, not viewed photographs. They cannot be extracted
as an already-reviewed portable preset or reviewed source until genuine single-
image review/application has occurred. No image-view approval is manufactured.

Only observed pre-write failure with exact no-effect proof and successful editor
return can be reported as a skippable target failure. Lost load, publication,
history, save/CAS, return or export outcomes retain the original identity and
query-only state. Even a renderer rollback attempt is not treated as proven safe
continuation. There is no automatic replay, rebase, overwrite or lease renewal.

## Scope and acceptance limits

Classes are background, hair, body skin, face skin, clothes and others, plus the
global base. There is no sky/lip/person-instance classifier, identity transfer,
depth, super-resolution, texture generation, mixed portrait recipe or local masks.
Reference archive is bounded by the existing 256 MiB resource plus bounded
manifest/ZIP overhead. The reference snapshot/cache remains one per workflow owner,
released on replacement/owner cleanup; it is not a durable cross-restart resume
capability. Engine loss stays query-only and cannot reconstruct an old job.

Only source inspection, Python AST, JSON parsing and whitespace checks are allowed
in this delivery. TS/TSX and Rust parsers were unavailable; their syntax parsing is
UNRUN, not typechecked. All authored Python/Rust/TS fixtures remain **UNRUN**.
No build, tests, typecheck, model inference, installation, download or image-quality
claim is made. Qoder must validate real reference-once/target-independent behaviour,
low-memory and missing-class refusal, all stop/skip/unknown races, archive tamper,
ordinary and semantic history/undo/redo, saved project reopen, editor return and
all supported export profiles against full-resolution RGB8/16 photographs.
