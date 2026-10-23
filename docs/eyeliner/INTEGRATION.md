# Eyeliner source slice, NOT runtime acceptance

Isolated base supplied by coordinator: f68a5d7d. Shared wiring authorized at
local03a0b4e968afe4222caf8d1ebb0daad6abc5c8ee. No product import, test, build,
compiler, typecheck, inference, download, install or Git write was performed.
All executable cases are UNRUN. Shared integration below is source-wired,
not a claim of execution or visual acceptance.

## Verified requirements

Official source read 2026-10-23: https://www.pixcakeai.com/guide/32471,
section 眼线 and 妆容素材换颜色. Six effects, strength, left/right unlock,
recommended colours, picker, RGB/HEX and maximum six favourites. Width range
0–1 and the names/shapes below are ORIGINAL local definitions, not asserted
PixCake names or visual parity. No downloaded PixCake art or model.
Manual baseline lines 541–545; AI mapping lines 3858–3871, 4278–4346.
LNX-REF-PC-32471-C- suffixes: fa257bcc51, 97481ec9e4, d1f91e8f4d,
e42b06d0e5, 0677331ed6, 2590457a9a.

## Actual adapter map / source-wired registrations

- people_algorithms.specifications: eyeliner_state.OP -> neutral/check. Seven
  canonical leaves: linked plus each side's pattern/strength/colour. Each UI
  edit submits the whole recipe in ONE people patch, never two transactions.
  people_edit validates scalar leaves with linked=False then validates the
  complete staged recipe for every affected face before publication.
- people_state accepts source-owned named kinds; people_support_assets registers
  eyeliner_visibility separately from eye_light_visibility; dispatch check,
  retain, resolve and raster via eyeliner_support. Independent source-normalized
  manual brush records must include visible/unoccluded/ownership_confirmed/
  open_eye true. Eye-light evidence NEVER authorizes eyelid paint.
- people_render_runtime.prepare: accept eyeliner_assets from SAME canonical
  engine._people_support. Resolve visibility descriptors instead of treating
  them as recovery. Call eyeliner_people.prepare with the verified analysis,
  frozen effect_source, recipe and graph revision. Both requested sides stage
  before any output returns. A failed face/side prevents publication.
- people_effects.STAGES, preview pipeline and source export stage order:
  add eyeliner. LocalEffect delta is working-sRGB float32. Recovery remains
  the existing source-local canonical compositor, target eyeliner; NEVER
  bake recovery into recipe or create another recovery/history owner.
- people_host_commands: eyeliner_reference -> eyeliner_host.reference;
  eyeliner_review -> stage_review candidate; eyeliner_palette ->
  eyeliner_adapters.stage_palette. Existing receipt transaction publishes,
  rolls back and records history. Add actions to native IPC allowed lists.
- people host report: eyeliner_host.report under eyeliner DTO. Source preview
  is independent _eyeliner_reference, source/person-bound and transient.
- document/history/project: _eyeliner_library in normal capture/restore;
  server DOC_FIELDS/default/capture/restore owns _eyeliner_library;
  people_project.validate_records validates library and dormant recipe fields;
  support project validation
  via eyeliner_support.validate_project. Persist catalogue digest and palette.
  Validate dormant/historical recipe leaves and independently resolve review
  descriptors. Preserve append-only support records needed by undo/redo.
- preset registration: eyeliner_scope. Applied leaves only travel through
  canonical graph. eyeliner_adapters.preset_command/batch_payload use existing
  edit and transfer adapters, not an alternate owner. Do not copy review masks,
  source identity, landmark evidence, palette or recovery into presets/batches.
  Each target needs its own current detection and eyelid review.
- ui/src/people/model.ts: EyelinerView and three action identifiers. App owns
  useEyelinerPicker, EyelinerPanel and existing capture overlay forwarding
  presented/pick/failed, mutual cancellation and source revision. No screenshot
  sampling. Side is captured with exact graph/document/target context.
- packaging/stage-engine.sh invokes packaging/build-eyeliner.sh and includes
  pinned JSON, Rust source, LICENSE and integration/MediaPipe licensing notice.
  The script is authored UNRUN; it packages liblrt_eyeliner.so only when
  explicitly invoked in an authorized build. No runtime compilation/fallback.

## Geometry and scope

Nine observed upper-rim points per anatomical eye, real 478-point MediaPipe
analysis, open-aperture cutoff, no extrapolation beyond either canthus. Original
fine/outer/arch/taper/bold/split width curves make six distinct coverage patterns.
Rust follows measured segments outward from observed eye centre; bounds coverage
by individually reviewed eyelid vectors and semantic exclusions. No iris content,
lash growth, eyeshadow, hidden-eye reconstruction or full eye-makeup claim.
The curves have no unobserved wings. Closed/occluded/cropped/too-small/degenerate
geometry refuses; users can unlock and zero the unavailable side. Scale cutoffs
and visual quality require real local acceptance at preview and source resolution.

RGB colours are explicit 8-bit user selections; rendering is unquantized float32
working-sRGB. Picker samples the verified PRESENTED proxy floating output, not
ungraded/original-resolution pixels. A no-change result is not painted success.
Native availability is file presence, not proof of ABI load or visual acceptance.

## Local acceptance needed

Run the fixture cases after authorized build. Compare each curve on real open
left/right eyes, varied skin tones/resolutions, rotation, glasses, lashes,
partial profile, eyelid folds and severe occlusion. Inspect both proxy and
full-resolution export, outside-review invariance and recovery isolation.
Collect screenshots, pixel metrics, project roundtrip and receipt/history logs.
Six unique source curves are NOT six visually accepted results.

## Source audit result (2026-10-23)

All changed Python parsed with standard-library ast.parse without importing
product code; JSON files decoded; source bytes hashed. No TypeScript/Rust
compiler, test or native load was run. Existing lipstick/blush/eye-light stages
retain their order; eyeliner is appended before common face/body deformation.
The existing Viewer receives eyeliner's capture owner through the same
ColorSamplePanel + presented/pick/failed path. Other tools cancel it, and it
observes conflicting owners/document context. Body and hair tools are blocked
while its capture is active. Existing body render composition was not changed.

The manifest contains this slice's isolated and shared paths only, excluding
neck's isolated work. SHA256.json does not hash itself; coordinator must hash the
manifest separately for its commit/review receipt. All 18 acceptance cases and
the Rust unit cases remain UNRUN.
