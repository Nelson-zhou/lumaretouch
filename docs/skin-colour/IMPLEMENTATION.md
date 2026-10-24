# Face-skin temperature and tint: source-connected, partial, UNRUN

Baseline: `6641d733988b9b66e9918a387e469a8f77d12f97`.

## Requirements and deliberate boundaries

- `LNX-REF-PC-32465-C-f0ba809461`: 肤色色温, left cool and right warm.
- `LNX-REF-PC-32465-C-0146f740bd`: 肤色色调, left green and right purple/magenta.
- [Official desktop skin guide](https://www.pixcakeai.com/guide/32465), updated 2026-05-26, checked 2026-10-23. The supplied handbook mapping and `ui/src/spec/refine.json` retain these IDs. Official numerical ranges/defaults are not disclosed.
- This source slice supports measured **face skin only**. It does not claim complete whole-person skin coverage. Both requirements remain **partial**, not photographically accepted.
- Whole-body whitening `d82f09f52f`, rosy skin `60936d5259`, eight skin palettes `2472d3ea69`, skin unification and blemish removal remain distinct, unfinished operations. Generic white balance and smoothing are not aliases for this feature.

## Original algorithm, no new model

`lnx.skin_colour.v1` has version 1 and signed `temperature`/`tint` scalars in [-1,1], neutral zero. These are project-defined units, not Kelvin or proprietary preset compatibility. Original Rust CIELAB colour correction preserves L*, shifts b* toward warm/cool and a* toward magenta/green, uses common chroma gamut reduction rather than independent RGB clipping, and mixes by coverage in linear light. See `core/skin_colour/README.md` for exact numerical contracts and limitations. Gamut reduction can desaturate and is not perceptually perfect. No blur, healing, texture synthesis or neural colour solver is substituted.

Primary practice: [darktable's Lab colour-correction explanation](https://www.darktable.org/2012/03/color-correction/) establishes a mature colour-axis grading approach; [W3C CSS Color 4](https://www.w3.org/TR/css-color-4/) documents colour transforms and gamut tradeoffs. Our deliberately D65-referenced CIELAB is not CSS D50 Lab or CSS gamut-mapping conformance. Implementation is original GPL-3.0-or-later; no copied third-party implementation or new downloaded weights. Existing six-class portrait and MediaPipe landmarks retain their existing model/code licence and hash gates.

## Anatomy, source and ownership

The existing producer's actual `face_skin` confidence is separately transported. Merged face/body `skin` is never substituted. Optional `face_skin_observation` binds source SHA, loaded semantic-model SHA and producer-grid dimensions. Old analyses without these fields remain usable for old operations; active skin colour fails closed without them.

`selected_face_skin` intersects semantic confidence with the actual selected 478-point face oval, feathers inward, protects eyes/lips/brows, and excludes other retained face ovals. Exclusion evidence additionally removes existing hair/clothes/background support. No person-instance segmentation, complete glasses/hand/lash detection or perfect feature edge is claimed. Verified neighbouring faces use their measured ovals, including disabled faces. Unresolved/manual neighbours instead contribute their exact retained source boxes as conservative protective vetoes only, with outward feathering; these boxes never become positive skin masks or fabricated anatomy. Thus adding or disabling a face does not require inventing measurements, while uncertain overlap can be deliberately left unchanged.

The consumer validates budgets before raster allocation. It receives frozen repaired source RGB, never another person's corrected output. Each target builds its own support. Zero intent does not require anatomy, models or native core. Missing or malformed evidence refuses the whole prepared graph, not a partially applied edit.

## Integration map

- `skin_colour_state.py`: strict versioned scalars and real loaded-ABI capability.
- `skin_colour_support.py`, `people_binding.py`, `people_host_commands.py`, `people_retained_analysis.py`, `people_snapshot.py`: actual source-owned class transport, optional backward compatibility and immutable copies.
- `skin_colour_people.py`, `people_render_runtime.py`: measured support, independent source ROI, native solve and frozen `LocalEffect`.
- `people_algorithms.py`: a dedicated signed operation, not unsigned eye enhancement.
- `people_effects.py`, `people_pipeline.py`, `vram.py`: source delta stage before existing face-detail/makeup stages and common geometry. Other effects may subsequently change luminance; isolated-kernel invariants are not a claim about arbitrary combined edits.
- `creative_derived_effects.py`: only this actual derived-aware canonical operation is admitted. Effective source, FaceRef, model and document fences remain mandatory.
- Full-source export uses existing `people_export` → `prepare_export` → `people_snapshot.at_dimensions` → preparation and shared tile field bank. Anatomical support and colour are rebuilt on full-source float pixels; no enlarged corrected preview. Semantic confidence may be resampled from the measured producer grid, not claimed newly resolved full-resolution edges.
- Existing canonical graph, projects, history, virtual-copy/dormant ownership and receipt flow remain the only edit owner. No separate skin history or serialized raster cache.
- `skin_colour_scope.py`: scalar-only preset transport, explicit canonical target, no transferred model/mask/FaceRef. Confirmed face batch uses independently prepared target sources. Generic unmanaged or derived legacy scope replay remains refused.
- `ui/src/skinColour`: two exact handbook leaves, signed controls, current canonical scope, independent reset and pending/uncertain fences. UI reports face-only coverage and imperfect support. Core availability does not certify per-face evidence. Conservative pending/edit-queue fences can interrupt continuous dragging; uninterrupted live drag has not been established. Atomic two-leaf zero resets are available for missing-core recovery, but do not erase another scope's active overrides.
- `packaging/build-skin-colour.sh` and stage hook: authored native build/package integration; no build was run here.

## Acceptance and remaining work

All new numerical, geometry, native boundary, UI and integration fixtures are **AUTHORED / UNRUN**. Static AST/JSON/hash/whitespace checks are not runtime or photographic acceptance. No tests, product imports, compiler, typechecker, build, inference, download or installation ran during this slice.

Full-body owner-aware selection, manual face-skin coverage review/painting, dedicated skin recovery, accurate occluder segmentation, HDR/alpha retouch and unconstrained large-image performance remain unfinished. The native API supports cancellation callbacks; this synchronous canonical skin consumer currently uses the default callback, so prompt cancellation during its solve is not established. Existing SDR/opacity refusals remain intact; no clipping/downconversion is used to claim these capabilities. Qoder/local validation still needs original/derived/PNG16 source comparisons, target-specific batch, interrupted receipt/reset flows, undo/project reopening, export pixel agreement, geometry edge/occlusion tests and real portraits across skin tones and lighting.
