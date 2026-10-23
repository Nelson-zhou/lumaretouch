# Lipstick isolated source slice, not whole makeup completion

Base supplied by parent: f68a5d7d. Shared integration was subsequently granted and
source-wired in 29 host files. This is source integration, not runtime acceptance.
Status: source authored; Python AST and JSON/hash inspection only. Native build,
Python imports, tests, UI typecheck, runtime/inference and visual acceptance UNRUN.

## Reference and exact requirement scope

Official https://www.pixcakeai.com/guide/32471 accessed 2026-10-23, section 口红
and 妆容素材换颜色. It specifies 13 effects, degree, satin/matte/cream/pearl/water
textures, recommended colours, picker, RGB/HEX and at most six favourites. It
provides no calibrated transfer functions. Local originals are approximations,
not equivalent proprietary assets. Manual baseline: manual-text.txt lines 544–545;
AI pack: 功能需求验收映射.json exact IDs in acceptance.json. No image asset copied.

## Source-wired integration interfaces

- Operation: lnx.lipstick.v1; recipe version 1; leaves /pattern /strength /colour
  /texture. Defaults in lipstick_state.neutral; validator check; graph validate_graph.
- Stage: lipstick, separate from lip_makeup (existing saturation/brightness/shape
  enhancement). Keep lip_makeup untouched. Add lipstick to people_effects.STAGES,
  people_pipeline pre-deform admission, vram pre-deform composition and export
  recovery filtering. Keep canonical order explicit.
- people_algorithms: import lipstick_state as LIPSTICK and add OP to specifications.
- people_effects.prepare: add lipstick_review=None; call lipstick_layer.prepare_record
  with ref, landmarks, values[LIPSTICK.OP], frozen repaired source, excluded,
  backend, semantic_sha and reviewed=lipstick_review. NO skin argument required.
- people_render_runtime.prepare: add lipstick_assets=None. Validate dedicated
  lipstick_visibility descriptor through lipstick_support.resolve, and rebuild
  reviewed vectors via lipstick_support.raster(state,bank,face_ref,(h,w)) only
  when active. Pass lipstick_review into effects.prepare.
- Forward lipstick_assets through people_engine_runtime signatures, prepare/sync,
  frozen export snapshot, and people_owned_inputs using same _people_support bank.
- people_support_assets.check_store delegates target lipstick_visibility to
  lipstick_support.check_record. Exclude that target from recovery raster routes.
- Commands: lipstick_palette, lipstick_reference, lipstick_review, plus ordinary
  patch. people_host_commands dispatch mirrors blush; reference is non-history
  read, palette participates existing history/receipt, review stages graph.
  lipstick_review payload is {regions:{upper:review,lower:review}}. Both reviews
  have normalized brush recipe, visible/unoccluded/ownership_confirmed true.
  Reference guard retains exact source+face identity. No second history owner.
- people_host report key lipstick = lipstick_host.report(...).
- people_project: validate lipstick_library and _lipstick_library, validate all
  dormant graph leaves, validate lipstick_support descriptors across history.
- workflow_ports/server: library empty/init/reset/capture/restore/save/prepare via
  lipstick_project; include _lipstick_library in history_policy; report capability
  lipstick_protocol=1 ONLY after host routes are connected; package library file.
- scope.py registers lipstick_scope.OP / FIELDS / check_params / install;
  people_scope captures lipstick_scope and maps _lipstick_preset. Presets carry
  intent only. Batch uses existing confirmed people_transfer_adapter.prepare;
  no source landmarks, review, recovery or palette transferred to target.
- effect_recovery_state/runtime + facial_wrinkle_recovery register lipstick
  target/stage; retained source-owned recovery through existing support bank.
- packaging/stage-engine.sh explicitly invokes packaging/build-lipstick.sh; never
  runtime compile. Build script provided but UNRUN. Rust cdylib ABI 1 installed
  at engine/src/lumaretouch_engine/bin/liblrt_lipstick.so.
- ui/src-tauri/src/people_api.rs registers all three lipstick commands in the
  existing correlated receipt allowlist.
- ui/src/people/model.ts adds lipstick?: LipstickView and 3 command literals,
  operation display name. native.ts capability field lipstick_protocol.
- App imports useLipstickPicker + LipstickPanel, owns hook, explicit mutual
  exclusion/cancel with existing samplers, verified capture overlay present/pick
  callbacks. Reuse capture controller, not screenshot sampling. RetouchPanel
  receives lipstickPanel slot; do not replace lipMakeup controls. Register preset
  and batch scope in presets/presetModel.ts and batch/batchScopeOptions.ts.

## Boundaries

13 analytical spatial coverages are implemented in Rust, not colour aliases.
Five material responses use source-only lip luminance detail and normalized
support convolution: no generated folds, anatomy, random shine or copied assets.
Exact measured outer-minus-inner lip contours protect teeth/cavity and feather
inward; no skin/chroma/luminance threshold excludes dark lipstick. Source-owned
manual visible-lip review and known semantic hair/clothes/background exclusions
are required. Unknown skin-coloured occluders still require correct user review.
Strong sidefaces, clipping, degenerate landmarks and insufficient resolution fail
without partial publish. Geometry does not reshape lips.

working-sRGB float32 in [0,1] only. RGB16-origin data stays float until host export,
but this is not an HDR scene-linear operator or proof of full RGB16 equivalence.
Picker reads locked proxy float output, not full-resolution original pixels;
only selected final swatch rounds to RGB8. Material visual fidelity, performance,
full-image/tile parity, concurrency/history/export all require local acceptance.

## Static inspection record

30 Python implementation files plus one authored contract fixture were AST parsed
without imports. Catalogue and acceptance JSON parsed; all 11 baseline IDs were
found. Rust/TS source was inspected but neither parsed by a compiler nor typechecked.
No tests, builds, product execution, inference, installs, downloads or Git writes.
Shared file changes preserve the existing blush, independent-eye-light and body
forwarding source routes. Their runtime regression acceptance remains UNRUN.
