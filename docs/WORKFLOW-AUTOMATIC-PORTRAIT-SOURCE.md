# Automatic own-target portrait extension — SOURCE / UNRUN

The finite directory job can explicitly opt into `portrait_scope:
all_verified_detected_faces`. Omission retains the previous exposure/WB-only
consent. Its existing graph hash binds the preset content hash, captured existing
file scope, output and stop/skip policy. Originals remain untouched; output
collisions are not overwritten or renamed.

Supported portrait families are `lnx.skin_finish.v1` and
`lnx.skin_texture.v1`, optionally together with exposure/white balance. Complete
unsupported presets are refused. Legacy `lnx.skin.v1` is not reinterpreted.

Each managed target is actually opened and analyzed through PeoplePreparation,
using its own canonical detected faces, landmarks, skin/face-skin/exclusion
observations. All verified detected instances (1–8, non-limit-hit) are selected;
this does not mean every person in the scene was detected. No identity matching,
association or cross-photo mask transfer occurs. Edited, associated, ambiguous,
manual, limited or unsupported targets are refused.

TargetPortraitPlan reuses the retained group planner, full-source candidate
validation and existing people batch ledger, including atomic mixed global/graph
history. It creates no image-view acknowledgment and no second scheduler, graph
or undo owner. Preparation/evidence is not photographic quality acceptance.

The scoped save wrapper validates the exact prepared graph, authorized face
leaves and applied context, and reuses the existing group history serializer and
workflow CAS persistence/editor return. Known pre-apply rejection becomes a safe
skip only after observed preparation rollback and verified original editor
return. Lost ownership, uncertain mutation/save or failed rollback stays Unknown
and query-only; it is not retried as a new target operation.

## Verification boundary

Only source inspection and Python AST parsing were performed. Authored fixtures
are UNRUN. No tests, typechecks, builds, model inference, product launch, installs
or external pushes were performed. Local QA still needs real single/multi-face
photos, missing-native/model and ambiguous/limit-hit cases, mixed undo/redo and
reopen persistence, cancellation/interruption, no-overwrite export and visual
quality/performance checks.
