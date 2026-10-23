# Canonical host integration: source-authored, UNRUN

Integration baseline: `e43795633d9336c507b6158ea7495b13b3a6370a`.
No new persistent session, history or batch owner is introduced.

## Registry, graph and transactions

`people_algorithms.specifications` registers `lnx.eye_light.v1`, recipe schema 2.
Its leaves are `/linked` and `/left/...`, `/right/...` for asset, strength,
horizontal, vertical, rotation and flip. Linked recipes require exact matching
side values. The existing `people_edit.stage` validates intermediate eye-light
scalar domains using an unlocked neutral, then its existing final all-face recipe
validation enforces linked equality atomically. No partial linked gesture can
publish one eye. The UI selects the reference side before linking; unlinking
preserves both sides independently.

`people_host_commands` and native `people_api.rs` admit `eye_light_reference`
and `eye_light_review` using the existing document/graph fences and people receipt
owner. `eye_light_host.stage_review` returns a graph candidate and retains only
append-only immutable support bytes. Existing publish/rollback commits the graph
through PeopleGraphOwner, existing history captures pointers, and the existing
project persists the canonical bank. No extra undo stack exists.

## Real source-reference and reviewed visibility acquisition

`EyeLightPanel` is mounted at exact `PC-32470|眼神光` in RetouchPanel. All five
subcontrols route through that family, without covering unrelated eye functions.
It provides draft controls and an atomic Apply action, independently persisted
eye parameters, source-reference request, and per-eye brush-review editor.

`eye_light_host.reference` calls the existing
`body_pose_commands.source_preview(engine)` producer. Despite its original module
name, this function creates a verified unretouched whole-frame source reference
without body detection or inference. It carries source digest, original and
decoded dimensions, EXIF-normalized orientation and normalized-full-frame mapping.
`EyeLightSupportEditor` uses the existing sourcePreview receipt validator and
inverse source viewport. New source/face/image identity clears drafts and checks.
The thumbnail proves mapping, not discernible microscopic detail: photo-quality
review, sufficient detail and zoom usability remain unverified local QA needs.

`eye_light_support.retain/resolve/check_record/raster` delegate into the existing
`people_support_assets` bank, use its content digest and envelope, and keep only
source-normalized user brush vectors plus explicit visible/unoccluded/ownership
checks. Updating one eye preserves the other eye's reviewed support. Every record
is tied to the exact source, original dimensions, face_ref and landmark digest.
The normal store validator dispatches these records instead of treating them as
recovery. Project validation resolves active and historical pointers. Rendering
checks the descriptor even if creative strength is zero.

Visibility rasterization is the existing Rust-backed local_mask_recipe.raster at
requested preview/export dimensions, not interpolation of a proxy mask. Measured
semantic exclusion, actual 16-point eyelid polygon and actual iris landmarks
further gate it. User confirmation cannot bypass small/closed/invalid geometry.
Both requested active eyes must succeed, or the whole proposal fails.

## Source color / preview / export / recovery

`people_owned_inputs.preview` forwards the SAME canonical support bank on all
engine-owned preview paths. `people_engine_runtime` forwards it into preparation,
and frozen export snapshots already contain it as support_assets.
`people_render_runtime.prepare` calls `eye_light_people.prepare` from the real
frozen repaired `effect_source`. That source is explicitly working-sRGB, not
linear just because it is float32. The Rust transfer converts it to linear,
generates original procedural light, then converts differences back into encoded
working-sRGB deltas. Existing LocalEffect records own the two source ROIs.

`people_effects.STAGES`, `people_pipeline.source_effect` and `vram.py` include the
new eye_light stage after existing source hair color and before common geometry.
All body operation ordering remains unchanged. Existing `_local` and `_merge_delta`
crop source deltas to export tile halos; they never solve material per tile.
The new eye-light stage does not clamp its own delta; all pre-existing stages keep
their prior behavior. Existing catchlight enhancement remains untouched.

`effect_recovery_state`, `facial_wrinkle_recovery.FACE_TARGETS` and the UI recovery
model register eye_light. Existing per-person coverage attenuates its own delta
once before shared geometry. Preview availability has an explicit unavailable
fallback for unmanaged documents. Existing recovery/history/project semantics
remain the owner; support review is not confused with recovery coverage.

Source precision limits: the current host still admits working-sRGB 0..1, and
later pre-existing stages/export may clip values. Native functions accept finite
HDR/negative float32 without clipping, but this does NOT establish an end-to-end
HDR pipeline. Original RGB16 export remains on the original-source float32 path;
no eye-light preview uint8 pixels are used as final render source.

## Presets / batch / packaging

`eye_light_scope` is a parameter-only preset adapter registered in scope.py.
`workflow_ports` captures an ephemeral preset DTO from the canonical selected
face; it is NOT a DOC_FIELDS property or another rendering owner. Existing
people_scope.replay_preset consumes it into graph leaves, requires a single
unambiguous target and strict real preparation, and rolls back via the existing
preset transaction. Support, identities and recovery never enter preset files.

Canonical confirmed-face batch transfer discovers the registered operation and
copies chosen leaves only. Each target retains its own support; missing review
refuses rather than silently skipping. Legacy whole-document batch cannot invent
a face or transfer a review and is intentionally refused for this module.

`packaging/build-eye-light.sh` and stage-engine.sh wire the native shared library;
server capability is gated on its file presence, and runtime verifies ABI. Build
and native code have NOT been executed. Missing/broken native code refuses.
